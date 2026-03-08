# AgenticSQL

A conversational AI agent that lets you query a banking database and loyalty points system using plain English. Ask questions, get natural language answers — no SQL knowledge required.

## Overview

AgenticSQL is an orchestration agent built on top of [Groq](https://groq.com/) (Llama 3.3 70B) and LangChain. It handles:

- **Intent detection** — determines whether your question requires a database query, is general conversation, or is an unsupported operation
- **NL → SQL generation** — converts your natural language question into a safe, read-only SQL query
- **Cross-database querying** — joins data across the banking database (`agentic_sql.db`) and the loyalty points system (`loyalty.db`) in a single query
- **Response formatting** — turns raw query results into readable, conversational answers
- **Multi-turn conversations** — resolves follow-up questions using conversation history (e.g. *"What about credit accounts?"* after asking about savings accounts)
- **Security** — enforces read-only access; no INSERT, UPDATE, DELETE, DROP, or PRAGMA commands can be executed

### Databases

| Database | File | Contents |
|---|---|---|
| Banking | `agentic_sql.db` | Branches, customers, employees, accounts, transactions, loans (~85 MB) |
| Loyalty | `loyalty.db` | Loyalty customers, point events, redeemed rewards |

The two databases are linked by `customer_id` — the same ID used in both systems.

### Architecture

```
User query
    ↓
[LLM Call #1] SQL Generator + Intent Classifier (Llama 3.3 70B via Groq)
    → GENERAL_CHAT  → return conversational answer
    → UNSUPPORTED   → return polite refusal
    → QUERY_DB      → continue
    ↓
[Deterministic] SQL Validator
    Whitelist: SELECT only | Blacklist: DROP/DELETE/PRAGMA/etc. | Read-only SQLite URI
    ↓
[SQLAlchemy] SQL Executor
    agentic_sql.db (main schema) + loyalty.db (attached as "loyalty.")
    Auto-LIMIT 100 rows | Result truncation metadata
    ↓
[LLM Call #2] Response Formatter → natural language answer
    ↓
Answer returned + stored in conversation history
```

---

## Installation

### Prerequisites

- Python 3.11 or later
- A [Groq API key](https://console.groq.com/) (free tier available)

### Steps

1. **Clone the repository**

   ```bash
   git clone https://github.com/your-org/agenticSQL.git
   cd agenticSQL
   ```

2. **Create and activate a virtual environment**

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Linux / macOS
   .venv\Scripts\activate         # Windows
   ```

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Configure your API key**

   Create a `.env` file in the project root:

   ```env
   GROQ_API_KEY=your_groq_api_key_here
   ```

5. **Initialise and seed the databases** *(skip if `agentic_sql.db` and `loyalty.db` already exist)*

   ```bash
   # Banking database
   python database.py
   pip install faker          # required for seed scripts
   python seed_data.py

   # Loyalty database
   python loyalty_database.py
   python seed_loyalty_data.py
   ```

---

## Usage

### Interactive REPL (recommended)

Start a multi-turn conversational session:

```bash
python app.py
```

You will see:

```
╔══════════════════════════════════════════════════════════╗
║          AgenticSQL — Banking Database Assistant         ║
╚══════════════════════════════════════════════════════════╝

You: How many customers are there?

Agent: There are 500 customers in the banking database.

────────────────────────────────────────────────────────────
You: How many of them have loyalty points?

Agent: All 500 customers are enrolled in the loyalty programme.
       Together they have earned 7,726 point events.
```

**Built-in commands:**

| Command | Action |
|---|---|
| `exit` / `quit` / `q` | End the session |
| `clear` / `reset` | Wipe conversation history and start fresh |
| `history` | Show the number of conversation turns so far |

### Single-query mode

Pass your question as a command-line argument:

```bash
python app.py "Who are the top 5 customers by total loyalty points?"
```

### Programmatic usage

```python
from orchestrator import OrchestratorAgent

agent = OrchestratorAgent()

# Single query
response = agent.run("How many savings accounts have a balance over $10,000?")
print(response)

# Multi-turn conversation
agent.run("How many checking accounts are there?")
response = agent.run("What is the average balance on those?")   # follow-up
print(response)

# Clear history to start fresh
agent.clear_history()
```

### Example queries

```
# Banking queries
"Show me branches with more than 20 employees"
"What is the total loan amount outstanding for mortgage loans?"
"List the 10 most recent transactions for account number ACC-00042"

# Loyalty queries
"Who has the highest total loyalty points?"
"Which rewards have been redeemed most often?"
"Show me customers who earned points in January 2025"

# Cross-database queries
"What is the account balance and total loyalty points for customer ID 7?"
"Which customers have both a frozen account and active loyalty points?"
"Show me the top 10 customers ranked by both account balance and loyalty points"
```

---

## Project Structure

```
agenticSQL/
├── .env                      # GROQ_API_KEY (not committed)
├── agentic_sql.db             # Banking SQLite database
├── loyalty.db                 # Loyalty points SQLite database
├── app.py                     # CLI entry point (interactive REPL + single-query mode)
├── database.py                # SQLAlchemy models for agentic_sql.db
├── loyalty_database.py        # SQLAlchemy models for loyalty.db
├── seed_data.py               # Synthetic data generator for banking DB
├── seed_loyalty_data.py       # Synthetic data generator for loyalty DB
├── requirements.txt           # Python dependencies
├── er_diagram.md              # Entity-relationship diagram (banking DB)
├── orchestrator/
│   ├── __init__.py            # Exports OrchestratorAgent
│   ├── agent.py               # Main pipeline: intent → SQL → validate → execute → format
│   ├── prompts.py             # All LLM system prompts + compact database schema
│   └── validators.py          # SQL safety validation + read-only executor (both DBs)
└── plans/
    ├── architecture-review.md # Design review document (7 concerns + resolutions)
    └── multi-datasource-design.md  # Scaling plan for REST API, NoSQL, object storage
```

---

## Configuration

| Environment Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | ✅ Yes | Your Groq API key |
| `LOG_LEVEL` | No | Logging verbosity: `DEBUG`, `INFO` (default), `WARNING` |

Example with debug logging:

```bash
LOG_LEVEL=DEBUG python app.py
```

---

## Contributing

Contributions are welcome. Please follow these guidelines:

### Getting started

1. Fork the repository and create a feature branch:

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Install dependencies (see [Installation](#installation)).

3. Make your changes, ensuring:
   - Code is formatted with [Black](https://black.readthedocs.io/) (`black .`)
   - Imports are sorted with [isort](https://pycqa.github.io/isort/) (`isort .`)
   - Type hints are added for all new functions and methods

4. Test your changes manually with a variety of queries across both databases.

5. Commit with a clear, descriptive message:

   ```bash
   git commit -m "feat: add support for DynamoDB datasource adapter"
   ```

6. Open a pull request against `main` with a description of what was changed and why.

### Areas for contribution

The [`plans/multi-datasource-design.md`](plans/multi-datasource-design.md) document describes the planned roadmap for extending the system beyond SQLite. Specifically:

- **REST API adapter** — allow querying internal or external REST APIs
- **Object storage adapter** — query files in S3/GCS/Azure Blob
- **NoSQL adapter** — support MongoDB or DynamoDB query generation
- **Web UI** — a FastAPI or Streamlit front-end
- **Unit tests** — test coverage for the validator, executor, and agent pipeline
- **Streaming responses** — stream the LLM response tokens as they arrive

### Code style

| Tool | Config |
|---|---|
| Formatter | Black (default settings) |
| Import sorter | isort |
| Python version | 3.11+ |
| Type hints | Required for all public functions and class methods |

### Reporting bugs

Please open a GitHub issue with:
- The query that caused the problem
- The full error message or unexpected output
- Your Python version (`python --version`)

---

## License

MIT
