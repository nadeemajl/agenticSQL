# AGENTS.md

Python CLI agent that turns natural-language questions into read-only SQL over two SQLite databases using Groq + LangChain. No web server, pyproject, or test framework.

## Layout / entrypoints

- `app.py` — CLI (interactive REPL and single-query mode).
- `orchestrator/agent.py` — pipeline: intent + SQL generation → `validators.py` → execution → response formatting. Conversation history persists to `conversations.db`.
- `orchestrator/validators.py` — deterministic SQL safety and read-only execution; owns the DB connection and the `loyalty.` ATTACH.
- `orchestrator/prompts.py` — system prompts plus `COMPACT_SCHEMA`, the LLM's only knowledge of the schema.
- `database.py` / `loyalty_database.py` — SQLAlchemy models.
- `evals/` — smoke-test harness (not pytest).
- `plans/` — design/roadmap prose only; the adapters described there are **not implemented**.

## Setup

The `.db` files are gitignored and absent from a fresh checkout, so nothing runs until they are seeded. Run every command from the repo root:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install faker                # seed_data.py needs it; it is missing from requirements.txt
cp .env.example .env             # then set GROQ_API_KEY
python3 database.py && python3 seed_data.py
python3 loyalty_database.py && python3 seed_loyalty_data.py
```

- Order matters: `seed_loyalty_data.py` reads customers from `agentic_sql.db`.
- Run from the repo root. `database.py` and `loyalty_database.py` use CWD-relative `sqlite:///…` URLs, while `validators.py` resolves DB paths from the repo root.
- `seed_data.py` drops and recreates the banking tables (safe to re-run). `seed_loyalty_data.py` does **not** clear `loyalty.db`; re-running on an existing DB fails on duplicate primary keys — delete `loyalty.db` first.
- `python` may not exist on this machine; use `python3`.

## Commands / verification

```bash
python3 app.py                                  # interactive, session "default"
python3 app.py --session my-analysis            # named, persisted session
python3 app.py "How many customers are there?"  # one-shot
python3 evals/run_eval.py --quick               # first 5 cases; writes gitignored reports
python3 evals/run_eval.py                       # full suite (30 cases, live Groq calls)
```

There is no unit-test, lint, typecheck, or CI configuration. Do not claim tests pass; verify with a manual query or the eval harness. If queries fail with `unable to open database file`, the databases are not seeded.

## Gotchas

- The eval harness is a smoke test, not ground truth: it reuses **one** agent/session across all cases (history bleeds between cases), guesses intent from answer text, and sets `passed = intent_correct` only.
- Both `app.py` and the evals persist turns to `conversations.db`. Use a distinct `--session` when isolating runs; `*.db` is gitignored.
- When changing `database.py` or `loyalty_database.py`, update `COMPACT_SCHEMA` in `orchestrator/prompts.py` too. The LLM has no other schema source.
- Cross-database access requires the `loyalty.` prefix; both DBs are opened read-only and attached in `validators.py`. Keep that read-only guarantee — validation alone is not the primary defense.
- Validation allows only `SELECT` and rejects blacklisted words (e.g. `REPLACE`, `ANALYZE`, `CREATE`, `BEGIN`) anywhere outside string literals, so a legitimate SQLite function or alias using one of those words will be blocked.
- `MAX_RESULT_ROWS = 100` caps execution; the prompt suggests `LIMIT 50`. Truncation metadata only appears when exactly 100 rows are returned.
- Default model is `llama-3.3-70b-versatile` at temperature 0 via `ChatGroq`; `GROQ_API_KEY` is required. History sent to the LLM is capped at `MAX_HISTORY_TURNS = 10`, though all turns are persisted.

## Conventions

- Keep the boundary: safety logic in deterministic `validators.py`, prompt text in `prompts.py`. Never rely on the LLM to enforce read-only access.
- `requirements.txt` is unpinned. The README recommends Black/isort, but neither is installed or configured; match the existing style (module docstrings, type hints on public functions).
