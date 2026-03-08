"""
orchestrator/validators.py
==========================
Deterministic SQL safety validation and read-only execution.

Supports two SQLite databases via SQLite ATTACH:
  - agentic_sql.db  : the main banking database (default schema, unqualified tables)
  - loyalty.db      : the loyalty points system (access tables as loyalty.<table>)

Defense-in-depth strategy:
  1. Primary:   Both databases opened in read-only mode via SQLite URI
  2. Secondary: Whitelist check — only SELECT statements allowed
  3. Tertiary:  Blacklist check — block dangerous SQLite-specific keywords
  4. Safety:    Auto-add LIMIT clause if missing, result truncation at 100 rows
"""

import re
import logging
from dataclasses import dataclass, field
from typing import Optional

import os

import sqlparse
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger("agenticSQL.validators")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_RESULT_ROWS = 100

# Absolute paths to both databases (resolved at module load time)
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_BANKING_DB = os.path.join(_BASE_DIR, "agentic_sql.db")
_LOYALTY_DB = os.path.join(_BASE_DIR, "loyalty.db")

# Keywords that must never appear anywhere in a validated SQL query
BLACKLISTED_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE",
    "REPLACE", "MERGE", "UPSERT",        # DML
    "PRAGMA", "ATTACH", "DETACH",        # SQLite-specific control
    "LOAD_EXTENSION",                     # SQLite extension loading
    "VACUUM", "REINDEX", "ANALYZE",      # SQLite maintenance
    "BEGIN", "COMMIT", "ROLLBACK",       # Transactions (not needed for SELECT)
    "GRANT", "REVOKE",                   # Permissions
}

# ---------------------------------------------------------------------------
# Read-only SQLAlchemy engine with loyalty.db attached
#
# Strategy:
#   - Open agentic_sql.db in read-only mode (primary database)
#   - Attach loyalty.db as read-only under the alias 'loyalty'
#   - Cross-database queries use loyalty.<table> prefix
# ---------------------------------------------------------------------------
_RO_ENGINE = create_engine(
    f"sqlite:///file:{_BANKING_DB}?mode=ro&uri=true",
    connect_args={"check_same_thread": False},
)


@event.listens_for(_RO_ENGINE, "connect")
def _attach_loyalty_db(dbapi_conn, _connection_record):
    """Automatically attach loyalty.db as 'loyalty' on every new connection."""
    dbapi_conn.execute(f"ATTACH DATABASE 'file:{_LOYALTY_DB}?mode=ro' AS loyalty")
    logger.debug("Attached loyalty.db as 'loyalty' schema")


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------
@dataclass
class ValidationResult:
    is_valid: bool
    reason: str = ""
    sanitized_sql: str = ""


@dataclass
class ExecutionResult:
    success: bool
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    row_count: int = 0
    total_rows_available: Optional[int] = None  # set when truncation occurs
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# SQL Validation
# ---------------------------------------------------------------------------
def validate_sql(sql: str) -> ValidationResult:
    """
    Validate that a SQL string is a safe, read-only SELECT statement.

    Returns a ValidationResult with is_valid=True and the cleaned SQL if safe,
    or is_valid=False with a human-readable reason if not safe.
    """
    if not sql or not sql.strip():
        return ValidationResult(is_valid=False, reason="Empty SQL string")

    # --- 1. Parse with sqlparse ---
    parsed_statements = sqlparse.parse(sql.strip())
    if not parsed_statements:
        return ValidationResult(is_valid=False, reason="Could not parse SQL")

    # Only allow a single statement
    if len(parsed_statements) > 1:
        return ValidationResult(
            is_valid=False,
            reason="Multiple SQL statements are not allowed"
        )

    stmt = parsed_statements[0]

    # --- 2. Whitelist: must be SELECT ---
    stmt_type = stmt.get_type()
    if stmt_type != "SELECT":
        return ValidationResult(
            is_valid=False,
            reason=f"Only SELECT statements are permitted (got: {stmt_type or 'UNKNOWN'})"
        )

    # --- 3. Blacklist: check for dangerous keywords ---
    # Normalize: uppercase, remove comments and string literals for keyword scanning
    normalized = sql.upper()
    # Remove string literals to avoid false positives (e.g., description='DROP TABLE')
    normalized_no_strings = re.sub(r"'[^']*'", "''", normalized)
    normalized_no_strings = re.sub(r'"[^"]*"', '""', normalized_no_strings)

    for keyword in BLACKLISTED_KEYWORDS:
        # Use word boundary checks to avoid matching substrings (e.g., ANALYSIS vs ANALYZE)
        pattern = r"\b" + re.escape(keyword) + r"\b"
        if re.search(pattern, normalized_no_strings):
            return ValidationResult(
                is_valid=False,
                reason=f"Forbidden SQL keyword detected: {keyword}"
            )

    # --- 4. Clean and return sanitized SQL ---
    clean_sql = sql.strip().rstrip(";").strip() + ";"
    return ValidationResult(is_valid=True, sanitized_sql=clean_sql)


def _ensure_limit(sql: str, max_rows: int = MAX_RESULT_ROWS) -> str:
    """
    Add a LIMIT clause if the SQL doesn't already have one.
    Does NOT override an existing LIMIT that is smaller than max_rows.
    """
    upper = sql.upper()

    # Check for existing LIMIT clause (simple heuristic)
    limit_match = re.search(r"\bLIMIT\s+(\d+)\b", upper)
    if limit_match:
        existing_limit = int(limit_match.group(1))
        if existing_limit > max_rows:
            # Replace with capped limit
            sql = re.sub(
                r"\bLIMIT\s+\d+\b",
                f"LIMIT {max_rows}",
                sql,
                flags=re.IGNORECASE,
            )
        # else: existing limit is already ≤ max_rows, keep it
    else:
        # No LIMIT — add one before the trailing semicolon
        sql = sql.rstrip().rstrip(";").rstrip()
        sql = f"{sql} LIMIT {max_rows};"

    return sql


# ---------------------------------------------------------------------------
# SQL Execution
# ---------------------------------------------------------------------------
def execute_sql(sql: str) -> ExecutionResult:
    """
    Execute a validated SELECT statement against the read-only database.

    Automatically:
    - Adds a LIMIT clause if missing (capped at MAX_RESULT_ROWS)
    - Returns results as a list of dicts with column names as keys
    - Reports total_rows_available when truncation occurs
    """
    # Safety: validate again (defense in depth — callers should pre-validate)
    val = validate_sql(sql)
    if not val.is_valid:
        return ExecutionResult(success=False, error=f"Validation failed: {val.reason}")

    # Apply LIMIT safety cap
    limited_sql = _ensure_limit(val.sanitized_sql, MAX_RESULT_ROWS)

    logger.info("Executing SQL: %s", limited_sql)

    try:
        with _RO_ENGINE.connect() as conn:
            result = conn.execute(text(limited_sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
            row_count = len(rows)

        # Check if truncation occurred (only meaningful for non-aggregate queries)
        total_rows: Optional[int] = None
        if row_count == MAX_RESULT_ROWS:
            # Try to get the true total — build a COUNT(*) wrapper
            try:
                count_sql = f"SELECT COUNT(*) AS _total FROM ({val.sanitized_sql.rstrip(';')});"
                with _RO_ENGINE.connect() as conn:
                    count_result = conn.execute(text(count_sql))
                    total_rows = count_result.scalar()
            except Exception:
                pass  # Non-fatal — truncation note just won't be shown

        logger.info(
            "SQL executed successfully: %d rows returned (total: %s)",
            row_count,
            total_rows if total_rows else "unknown",
        )

        return ExecutionResult(
            success=True,
            columns=columns,
            rows=rows,
            row_count=row_count,
            total_rows_available=total_rows,
        )

    except SQLAlchemyError as exc:
        error_msg = str(exc.orig) if hasattr(exc, "orig") else str(exc)
        logger.warning("SQL execution error: %s", error_msg)
        return ExecutionResult(success=False, error=error_msg)
    except Exception as exc:
        logger.error("Unexpected execution error: %s", exc, exc_info=True)
        return ExecutionResult(success=False, error=str(exc))
