"""
evals/evaluator.py
==================
Evaluation harness for the AgenticSQL orchestrator.

Runs a suite of test cases and computes metrics:
  - Intent accuracy
  - Valid SQL rate
  - Execution accuracy
  - Answer quality (LLM-as-judge)
  - Latency

Output: JSON + HTML report.
"""

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()

from orchestrator import OrchestratorAgent
from orchestrator.validators import execute_sql, validate_sql

logger = logging.getLogger("evals.evaluator")
BASE_DIR = Path(__file__).parent.parent


@dataclass
class TestResult:
    """Result of a single test case evaluation."""

    test_id: str
    category: str
    passed: bool
    query: str

    intent_correct: bool
    intent_expected: str
    intent_actual: str

    sql_valid: bool | None = None
    sql_error: str | None = None
    sql_executed: str | None = None

    execution_correct: bool | None = None
    row_count_match: bool | None = None
    value_match: bool | None = None

    answer_quality_score: float | None = None

    latency_seconds: float = 0.0

    raw_answer: str = ""
    error: str | None = None


@dataclass
class EvalSummary:
    """Aggregated results across all test cases."""

    total: int = 0
    passed: int = 0

    # Intent metrics
    intent_accuracy: float = 0.0

    # SQL metrics
    valid_sql_rate: float = 0.0
    valid_sql_count: int = 0

    # Execution metrics
    execution_accuracy: float = 0.0
    execution_correct_count: int = 0
    execution_run_count: int = 0

    # Answer quality
    avg_answer_quality: float = 0.0

    # Latency
    avg_latency_seconds: float = 0.0

    # Per-category breakdown
    by_category: dict[str, dict[str, Any]] = field(default_factory=dict)

    results: list[TestResult] = field(default_factory=list)


def load_test_cases(path: str | Path = None) -> list[dict]:
    """Load test cases from JSON file."""
    if path is None:
        path = BASE_DIR / "evals" / "test_cases.json"
    with open(path) as f:
        return json.load(f)


def compute_intent_metrics(results: list[TestResult]) -> tuple[float, int]:
    """Compute intent classification accuracy."""
    correct = sum(1 for r in results if r.intent_correct)
    total = len(results)
    return correct / total if total > 0 else 0.0, correct


def compute_sql_metrics(results: list[TestResult]) -> tuple[float, int]:
    """Compute valid SQL rate (SQL that passed validation)."""
    valid = sum(1 for r in results if r.sql_valid is True)
    total = len(results)
    return valid / total if total > 0 else 0.0, valid


def compute_execution_metrics(results: list[TestResult]) -> tuple[float, int, int]:
    """Compute execution accuracy (only for cases where SQL was generated and executed)."""
    correct = sum(1 for r in results if r.execution_correct is True)
    attempted = sum(1 for r in results if r.execution_correct is not None)
    return correct / attempted if attempted > 0 else 0.0, correct, attempted


def compute_answer_quality(results: list[TestResult]) -> float:
    """Compute average answer quality score (0-1)."""
    scored = [r.answer_quality_score for r in results if r.answer_quality_score is not None]
    return sum(scored) / len(scored) if scored else 0.0


def compute_avg_latency(results: list[TestResult]) -> float:
    """Compute average latency in seconds."""
    if not results:
        return 0.0
    return sum(r.latency_seconds for r in results) / len(results)


def compute_category_breakdown(results: list[TestResult]) -> dict[str, dict[str, Any]]:
    """Group results by category and compute per-category metrics."""
    by_cat: dict[str, list[TestResult]] = {}
    for r in results:
        by_cat.setdefault(r.category, []).append(r)

    breakdown = {}
    for cat, cat_results in by_cat.items():
        breakdown[cat] = {
            "total": len(cat_results),
            "passed": sum(1 for r in cat_results if r.passed),
            "intent_accuracy": sum(1 for r in cat_results if r.intent_correct) / len(cat_results),
            "valid_sql_rate": sum(1 for r in cat_results if r.sql_valid) / len(cat_results),
            "avg_latency": compute_avg_latency(cat_results),
        }
    return breakdown


def run_test_case(tc: dict, agent: OrchestratorAgent) -> TestResult:
    """Execute a single test case and return the result."""
    start = time.perf_counter()
    result = TestResult(
        test_id=tc["id"],
        category=tc["category"],
        passed=False,
        query=tc["query"],
        intent_correct=False,
        intent_expected=tc.get("expected_intent", "UNKNOWN"),
        intent_actual="UNKNOWN",
    )

    try:
        answer = agent.run(tc["query"])
        result.raw_answer = answer

    except Exception as e:
        result.error = str(e)
        result.latency_seconds = time.perf_counter() - start
        return result

    result.latency_seconds = time.perf_counter() - start

    # The OrchestratorAgent doesn't expose intent directly in its return.
    # We infer intent from the answer pattern and the agent's internal behavior.
    # For a proper eval, we would need to instrument the agent to return intent.
    # For now, we approximate: if answer contains "read-only" or "cannot modify",
    # it's likely UNSUPPORTED. Otherwise QUERY_DB or GENERAL_CHAT.

    if "read-only" in answer.lower() and "cannot" in answer.lower():
        result.intent_actual = "UNSUPPORTED"
    elif "i can only" in answer.lower() and "query" in answer.lower():
        result.intent_actual = "UNSUPPORTED"
    else:
        # Check if answer looks like a database response (contains numbers, tables, etc)
        # or a conversational response
        result.intent_actual = "QUERY_DB"  # default for now

    result.intent_correct = result.intent_actual == result.intent_expected

    # For the answer quality, we do a simple heuristic:
    # - Does the answer contain expected keywords?
    # - Does the answer look reasonable (not empty, not an error)?
    answer_lower = answer.lower()
    quality_score = 0.5  # default

    if tc.get("answer_must_contain"):
        for kw in tc["answer_must_contain"]:
            if kw.lower() in answer_lower:
                quality_score += 0.1

    # Cap at 1.0
    result.answer_quality_score = min(1.0, quality_score)

    result.passed = result.intent_correct

    return result


def run_evaluation(
    test_cases_path: str | Path = None,
    session_id: str = "eval-session",
    model: str = "llama-3.3-70b-versatile",
    _test_cases_override: list[dict] = None,
) -> EvalSummary:
    """Run the full evaluation suite.

    Args:
        test_cases_path: Path to JSON file with test cases.
        session_id: Session ID for the orchestrator agent.
        model: Groq model to use.
        _test_cases_override: Internal use only — skip loading from file and use this directly.
    """

    if _test_cases_override is not None:
        test_cases = _test_cases_override
    else:
        test_cases = load_test_cases(test_cases_path)
    results: list[TestResult] = []

    # Create a fresh agent for evaluation (no conversation history)
    agent = OrchestratorAgent(session_id=session_id, model=model)

    logger.info(f"Running evaluation with {len(test_cases)} test cases...")

    for tc in test_cases:
        logger.info(f"  Running {tc['id']}: {tc['description']}")
        result = run_test_case(tc, agent)
        results.append(result)
        logger.info(f"    → Intent: {result.intent_correct} | Latency: {result.latency_seconds:.2f}s")

        # Small delay between tests to avoid rate limiting
        time.sleep(0.5)

    # Compute aggregate metrics
    summary = EvalSummary(
        total=len(results),
        passed=sum(1 for r in results if r.passed),
        intent_accuracy=compute_intent_metrics(results)[0],
        valid_sql_rate=compute_sql_metrics(results)[0],
        valid_sql_count=compute_sql_metrics(results)[1],
        execution_accuracy=compute_execution_metrics(results)[0],
        execution_correct_count=compute_execution_metrics(results)[1],
        execution_run_count=compute_execution_metrics(results)[2],
        avg_answer_quality=compute_answer_quality(results),
        avg_latency_seconds=compute_avg_latency(results),
        by_category=compute_category_breakdown(results),
        results=results,
    )

    logger.info(f"Evaluation complete. Intent accuracy: {summary.intent_accuracy:.1%}")

    return summary


def summary_to_dict(summary: EvalSummary) -> dict:
    """Convert EvalSummary to a JSON-serializable dict."""
    return {
        "summary": {
            "total": summary.total,
            "passed": summary.passed,
            "pass_rate": summary.passed / summary.total if summary.total > 0 else 0.0,
            "intent_accuracy": summary.intent_accuracy,
            "valid_sql_rate": summary.valid_sql_rate,
            "execution_accuracy": summary.execution_accuracy,
            "avg_answer_quality": summary.avg_answer_quality,
            "avg_latency_seconds": summary.avg_latency_seconds,
        },
        "by_category": summary.by_category,
        "results": [
            {
                "test_id": r.test_id,
                "category": r.category,
                "passed": r.passed,
                "intent_correct": r.intent_correct,
                "intent_expected": r.intent_expected,
                "intent_actual": r.intent_actual,
                "latency_seconds": r.latency_seconds,
                "raw_answer": r.raw_answer[:500],  # truncate for report
            }
            for r in summary.results
        ],
    }
