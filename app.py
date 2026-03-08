"""
app.py
======
Interactive CLI entry point for the AgenticSQL orchestration agent.

Usage:
    # Interactive REPL — creates/resumes the 'default' session:
    python app.py

    # Interactive REPL with a named session (persisted across restarts):
    python app.py --session my-analysis

    # Single query mode:
    python app.py "How many customers are there?"
    python app.py --session my-analysis "How many customers are there?"
"""

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

from orchestrator import OrchestratorAgent, list_sessions

BANNER = """
╔══════════════════════════════════════════════════════════╗
║          AgenticSQL — Banking Database Assistant         ║
║                                                          ║
║  Ask questions about customers, accounts, transactions,  ║
║  loans, branches, employees, and loyalty points.        ║
║                                                          ║
║  Commands:                                               ║
║    exit / quit / q  →  End the session                   ║
║    clear / reset    →  Clear conversation history        ║
║    history          →  Show turn count for this session  ║
║    sessions         →  List all saved sessions           ║
╚══════════════════════════════════════════════════════════╝
"""

SEPARATOR = "─" * 60


def parse_args() -> tuple[str, str | None]:
    """
    Simple argument parser — no argparse dependency.

    Returns:
        (session_id, query_or_none)

    Supports:
        app.py                          → session='default', query=None
        app.py --session foo            → session='foo',     query=None
        app.py "my query"               → session='default', query='my query'
        app.py --session foo "my query" → session='foo',     query='my query'
    """
    args = sys.argv[1:]
    session_id = "default"
    query: str | None = None

    i = 0
    remaining = []
    while i < len(args):
        if args[i] in ("--session", "-s") and i + 1 < len(args):
            session_id = args[i + 1]
            i += 2
        else:
            remaining.append(args[i])
            i += 1

    if remaining:
        query = " ".join(remaining)

    return session_id, query


def run_single_query(agent: OrchestratorAgent, query: str) -> None:
    print(f"\n🔍 Query: {query}")
    print(SEPARATOR)
    response = agent.run(query)
    print(f"💬 Answer:\n{response}")
    print()


def run_interactive(agent: OrchestratorAgent) -> None:
    print(BANNER)
    print(f"📂 Session: {agent.session_id!r}  ({agent.turn_count} previous turn(s))\n")

    while True:
        try:
            raw_input = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\n👋 Goodbye!")
            break

        if not raw_input:
            continue

        lower = raw_input.lower()

        if lower in ("exit", "quit", "q"):
            print("\n👋 Goodbye!")
            break

        if lower in ("clear", "reset"):
            agent.clear_history()
            print("✅ Conversation history cleared. Starting fresh.\n")
            continue

        if lower == "history":
            print(f"📝 {agent.turn_count} turn(s) stored in session {agent.session_id!r}.\n")
            continue

        if lower == "sessions":
            sessions = list_sessions()
            if not sessions:
                print("📂 No saved sessions found.\n")
            else:
                print(f"📂 Saved sessions ({len(sessions)}):")
                for s in sessions:
                    active = " ← current" if s["session_id"] == agent.session_id else ""
                    print(f"   • {s['session_id']!r:30s}  {s['turn_count']:>3} turns{active}")
                print()
            continue

        print()
        response = agent.run(raw_input)
        print(f"Agent: {response}\n")
        print(SEPARATOR)


def main() -> None:
    session_id, query = parse_args()
    agent = OrchestratorAgent(session_id=session_id)

    if query:
        run_single_query(agent, query)
    else:
        run_interactive(agent)


if __name__ == "__main__":
    main()
