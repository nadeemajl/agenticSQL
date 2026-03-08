"""
orchestrator/agent.py
=====================
OrchestratorAgent: the main orchestration pipeline.

Pipeline (per turn):
  1. SQL Generator + Intent Classifier  — LLM Call #1
     Determines intent (QUERY_DB / GENERAL_CHAT / UNSUPPORTED) and generates SQL if needed.
  2. SQL Validator (deterministic, no LLM)
  3. SQL Executor (read-only SQLAlchemy)
     Retry up to `max_retries` times if execution fails, feeding error context back to LLM.
  4. Response Formatter — LLM Call #2
     Converts raw query results into natural language.

Conversation persistence:
  Uses LangChain's SQLChatMessageHistory to store every message in conversations.db.
  All turns are persisted to disk; only the last MAX_HISTORY_TURNS are sent to the LLM
  to stay within the context window.

  Sessions are identified by a string session_id. Resuming a previous session just
  requires constructing OrchestratorAgent with the same session_id.
"""

import json
import logging
import os
import re
import sqlite3
from typing import Optional

from dotenv import load_dotenv
from langchain_community.chat_message_histories import SQLChatMessageHistory
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field, field_validator

from orchestrator.prompts import FORMATTER_SYSTEM_PROMPT, SQL_GENERATOR_SYSTEM_PROMPT
from orchestrator.validators import ExecutionResult, execute_sql, validate_sql

load_dotenv()

logger = logging.getLogger("agenticSQL.agent")

# Path to the conversations database (sibling of the other DB files)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONVERSATIONS_DB = f"sqlite:///{os.path.join(_BASE_DIR, 'conversations.db')}"

# Number of most-recent turns to include in each LLM call.
# ALL turns are persisted to conversations.db regardless of this limit.
MAX_HISTORY_TURNS = 10


# ---------------------------------------------------------------------------
# Pydantic Models for Structured LLM Output
# ---------------------------------------------------------------------------

class SQLIntentResult(BaseModel):
    """Structured output from the SQL Generator + Intent Classifier LLM call."""

    intent: str = Field(..., description="QUERY_DB, GENERAL_CHAT, or UNSUPPORTED")
    sql: Optional[str] = Field(None, description="SQL SELECT statement, or null")
    chat_answer: Optional[str] = Field(
        None, description="Conversational response for non-DB intents"
    )
    explanation: str = Field(..., description="Brief explanation of the decision")

    @field_validator("intent")
    @classmethod
    def validate_intent(cls, v: str) -> str:
        allowed = {"QUERY_DB", "GENERAL_CHAT", "UNSUPPORTED"}
        v_upper = v.upper().strip()
        if v_upper not in allowed:
            raise ValueError(f"intent must be one of {allowed}, got: {v!r}")
        return v_upper


# ---------------------------------------------------------------------------
# OrchestratorAgent
# ---------------------------------------------------------------------------

class OrchestratorAgent:
    """
    Stateful orchestration agent that processes natural language queries
    against the AgenticSQL banking + loyalty databases.

    Conversation history is persisted to conversations.db via LangChain's
    SQLChatMessageHistory. Resuming a previous session is as simple as
    passing the same session_id on construction.

    Args:
        session_id:  Unique identifier for the conversation session.
                     Defaults to "default". Pass any string to maintain
                     separate, independent conversation histories.
        max_retries: Maximum number of SQL generation retries on execution failure.
        model:       Groq model name to use.
    """

    def __init__(
        self,
        session_id: str = "default",
        max_retries: int = 2,
        model: str = "llama-3.3-70b-versatile",
    ):
        self.session_id = session_id
        self.max_retries = max_retries

        self.llm = ChatGroq(
            model=model,
            temperature=0,
            api_key=os.environ.get("GROQ_API_KEY"),
        )

        # SQLChatMessageHistory persists every message immediately to conversations.db.
        # Use 'connection' (not deprecated 'connection_string') where available,
        # falling back to connection_string for older installs.
        try:
            from sqlalchemy import create_engine as _ce
            self._chat_history = SQLChatMessageHistory(
                session_id=session_id,
                connection=_ce(CONVERSATIONS_DB),
            )
        except TypeError:
            self._chat_history = SQLChatMessageHistory(
                session_id=session_id,
                connection_string=CONVERSATIONS_DB,
            )

        turn_count = len(self._chat_history.messages) // 2
        logger.info(
            "OrchestratorAgent initialised (session=%r, model=%s, "
            "existing turns=%d, max_retries=%d)",
            session_id,
            model,
            turn_count,
            max_retries,
        )
        if turn_count > 0:
            logger.info("Resuming session %r with %d previous turns.", session_id, turn_count)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def run(self, query: str) -> str:
        """
        Process a natural language query and return a natural language answer.

        Each call persists the turn to conversations.db immediately. Call this
        method repeatedly for multi-turn conversations; sessions survive restarts.
        """
        logger.info("Processing query [session=%r]: %r", self.session_id, query)

        error_context: Optional[str] = None
        previous_sql_attempts: list[str] = []

        for attempt in range(self.max_retries + 1):
            if attempt > 0:
                logger.info("Retry attempt %d/%d", attempt, self.max_retries)

            intent_result = self._generate_sql_and_intent(
                query=query,
                error_context=error_context,
                previous_attempts=previous_sql_attempts,
            )

            if intent_result.intent == "GENERAL_CHAT":
                answer = intent_result.chat_answer or "I'm not sure how to answer that."
                self._persist_turn(query, answer)
                return answer

            if intent_result.intent == "UNSUPPORTED":
                answer = (
                    intent_result.chat_answer
                    or "I can only perform read-only queries on the banking and loyalty databases. "
                       "I cannot modify, delete, or create data."
                )
                self._persist_turn(query, answer)
                return answer

            if not intent_result.sql:
                answer = "I wasn't able to generate a SQL query for that question. Could you please rephrase it?"
                self._persist_turn(query, answer)
                return answer

            val_result = validate_sql(intent_result.sql)
            if not val_result.is_valid:
                logger.warning("SQL validation failed: %s | SQL: %s", val_result.reason, intent_result.sql)
                answer = (
                    f"The query could not be processed for safety reasons: {val_result.reason}. "
                    "Please try rephrasing your question."
                )
                self._persist_turn(query, answer)
                return answer

            exec_result = execute_sql(val_result.sanitized_sql)

            if exec_result.success:
                answer = self._format_response(query, val_result.sanitized_sql, exec_result)
                self._persist_turn(query, answer)
                logger.info("Query completed successfully in %d attempt(s)", attempt + 1)
                return answer

            logger.warning("SQL execution failed (attempt %d): %s", attempt + 1, exec_result.error)
            if intent_result.sql in previous_sql_attempts:
                logger.info("Duplicate SQL attempt detected — stopping retry loop early")
                break

            previous_sql_attempts.append(intent_result.sql)
            error_context = (
                f"The following SQL failed with an error:\n"
                f"SQL: {intent_result.sql}\n"
                f"Error: {exec_result.error}\n"
                f"Please generate a corrected SQL query."
            )

        answer = (
            "I was unable to generate a working SQL query for your question after "
            f"{self.max_retries + 1} attempt(s). Please try rephrasing your question."
        )
        self._persist_turn(query, answer)
        return answer

    def clear_history(self) -> None:
        """
        Clear the in-memory window AND delete the persisted history for this
        session from conversations.db.
        """
        self._chat_history.clear()
        logger.info("History cleared for session %r", self.session_id)

    @property
    def history(self) -> list:
        """All persisted messages for this session (full history, not just the window)."""
        return self._chat_history.messages

    @property
    def turn_count(self) -> int:
        """Total number of persisted turns for this session."""
        return len(self._chat_history.messages) // 2

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _get_recent_messages(self) -> list:
        """
        Return the most recent MAX_HISTORY_TURNS turns from persisted history
        for inclusion in LLM calls.

        All turns live in conversations.db. We only pass the tail to the LLM
        to stay within the context window budget.
        """
        all_messages = self._chat_history.messages
        # Each turn = 2 messages (HumanMessage + AIMessage)
        tail = all_messages[-(MAX_HISTORY_TURNS * 2):]
        return tail

    def _persist_turn(self, user_query: str, assistant_response: str) -> None:
        """Write a completed turn to conversations.db immediately."""
        self._chat_history.add_user_message(user_query)
        self._chat_history.add_ai_message(assistant_response)
        logger.debug("Turn persisted to conversations.db (session=%r)", self.session_id)

    def _generate_sql_and_intent(
        self,
        query: str,
        error_context: Optional[str],
        previous_attempts: list[str],
    ) -> SQLIntentResult:
        """LLM Call #1: Determine intent and generate SQL if applicable."""
        system_msg = SystemMessage(content=SQL_GENERATOR_SYSTEM_PROMPT)

        user_content = query
        if error_context:
            user_content = f"{query}\n\n[CORRECTION NEEDED]\n{error_context}"
        if previous_attempts:
            attempts_str = "\n".join(f"  Attempt {i+1}: {s}" for i, s in enumerate(previous_attempts))
            user_content += f"\n\n[PREVIOUS FAILED ATTEMPTS]\n{attempts_str}"

        current_user_msg = HumanMessage(content=user_content)
        recent_history = self._get_recent_messages()
        messages = [system_msg] + recent_history + [current_user_msg]

        logger.debug(
            "LLM call #1: %d messages (%d history turns)",
            len(messages),
            len(recent_history) // 2,
        )

        response = self.llm.invoke(messages)
        return self._parse_sql_intent_response(response.content.strip())

    def _parse_sql_intent_response(self, raw: str) -> SQLIntentResult:
        """Parse the LLM's JSON response into a SQLIntentResult."""
        clean = raw
        if "```" in clean:
            match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", clean)
            if match:
                clean = match.group(1)

        try:
            data = json.loads(clean)
            return SQLIntentResult(**data)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error("Failed to parse LLM response: %s | Raw: %s", exc, raw)
            return SQLIntentResult(
                intent="GENERAL_CHAT",
                sql=None,
                chat_answer="I had trouble understanding that request. Could you please rephrase it?",
                explanation=f"Parse error: {exc}",
            )

    def _format_response(self, query: str, sql: str, exec_result: ExecutionResult) -> str:
        """LLM Call #2: Convert raw SQL results into a natural language answer."""
        results_summary = self._build_results_summary(exec_result)

        truncation_note = ""
        if (
            exec_result.total_rows_available is not None
            and exec_result.total_rows_available > exec_result.row_count
        ):
            truncation_note = (
                f"\n\nNOTE: Results are showing {exec_result.row_count} of "
                f"{exec_result.total_rows_available} total records."
            )

        user_content = (
            f"Original question: {query}\n\n"
            f"SQL executed: {sql}\n\n"
            f"Results ({exec_result.row_count} rows):\n{results_summary}"
            f"{truncation_note}"
        )

        system_msg = SystemMessage(content=FORMATTER_SYSTEM_PROMPT)
        current_msg = HumanMessage(content=user_content)
        recent_history = self._get_recent_messages()
        messages = [system_msg] + recent_history + [current_msg]

        response = self.llm.invoke(messages)
        return response.content.strip()

    def _build_results_summary(self, exec_result: ExecutionResult) -> str:
        """Build a compact string representation of query results for the formatter prompt."""
        if not exec_result.rows:
            return "No rows returned."

        PROMPT_ROW_LIMIT = 50
        rows_to_show = exec_result.rows[:PROMPT_ROW_LIMIT]
        lines = [" | ".join(exec_result.columns), "-" * min(80, sum(len(c) for c in exec_result.columns) + 3 * len(exec_result.columns))]
        for row in rows_to_show:
            lines.append(" | ".join(str(v) for v in row.values()))
        if len(exec_result.rows) > PROMPT_ROW_LIMIT:
            lines.append(f"... and {len(exec_result.rows) - PROMPT_ROW_LIMIT} more rows")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Session management helpers (for CLI use)
# ---------------------------------------------------------------------------

def list_sessions() -> list[dict]:
    """
    Return a list of all sessions stored in conversations.db.
    Each dict has: session_id, turn_count, last_active.
    """
    db_path = os.path.join(_BASE_DIR, "conversations.db")
    if not os.path.exists(db_path):
        return []

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    try:
        # LangChain SQLChatMessageHistory stores: id, session_id, message (JSON blob)
        # No created_at column — use row id as a proxy for ordering
        cur.execute(
            """
            SELECT session_id,
                   COUNT(*) / 2  AS turn_count
            FROM message_store
            GROUP BY session_id
            ORDER BY MIN(id) ASC
            """
        )
        rows = cur.fetchall()
        return [
            {"session_id": r[0], "turn_count": r[1]}
            for r in rows
        ]
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()
