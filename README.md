# Webpage Content Scraper Agent

An LLM agent that extracts user-specified content from any webpage and returns it as
structured, exportable data. Give it a URL and a plain-language description of what you
want ("extract each product's name, price and rating"); the agent plans the fields,
chooses an extraction strategy, self-checks the result, and returns a table.

Built for a small (~10-person) data-analysis team as an internal tool — no
high-concurrency requirements, optimized for correctness, cost control and operability.

## What it does

- **Natural-language extraction requests** → typed field schema (planning step).
- **Two extraction strategies, chosen per page:**
  - *selector* — the LLM emits a declarative CSS-selector plan that fixed, auditable
    code executes (no arbitrary code execution). Cheap and reusable across similar pages.
  - *llm* — the LLM reads the compressed DOM and returns records directly. Robust on
    irregular content.
- **Reflection loop** — a quality check (row count, per-field coverage) can send a poor
  result back to retry with the other strategy, carrying the failure as feedback.
- **Live progress** — node-level execution streamed to the UI over Server-Sent Events.
- **Persistence & export** — every run is stored; browse history and export any result
  to CSV or Excel. Results can optionally be pushed to an external database.

## Architecture

A [LangGraph](https://github.com/langchain-ai/langgraph) state machine:

```
fetch_page ─▶ structure_dom ─▶ plan_extraction ─▶ (route by strategy)
  httpx→        compress DOM      NL → field           │
  Playwright    (token budget)    schema + strategy     ├─▶ gen_selectors ─▶ execute_selectors ┐
                                                        └─▶ llm_extract ───────────────────────┤
                                                                                               ▼
                                                                                        validate_result
                                                                              pass │            │ fail (≤N retries)
                                                                                   ▼            ▼
                                                                                finalize   retry other strategy
```

The controlled selector executor is the security-relevant design choice: the model only
ever produces a declarative plan (selectors + field map), never executable code. See
[docs/REFACTOR_PLAN.md](docs/REFACTOR_PLAN.md) for the full design rationale.

## Tech stack

| Layer | Choice |
|---|---|
| Agent orchestration | LangGraph |
| LLM access | LangChain, Aliyun **DashScope** (OpenAI-compatible) with role-based Qwen3 models |
| Web framework | FastAPI + uvicorn (fully async) |
| Fetching | httpx (static fast path) + Playwright (JS rendering) |
| HTML parsing | BeautifulSoup / lxml |
| Persistence | SQLAlchemy 2.0 (async) + SQLite |
| Export | pandas / openpyxl |
| Frontend | React + Ant Design |

## Project layout

```
backend/
  app/
    main.py            FastAPI app + lifespan wiring
    core/              config (pydantic-settings), logging, exceptions, db
    api/v1/            scrape (+ SSE stream), tasks (history + export)
    agents/            LangGraph graph, state, one module per node
    services/
      fetch_service    httpx + Playwright, SSRF guard, browser lifecycle
      dom_service      DOM compression (token budget)
      extraction/      planner, selector_gen, executor, llm_extractor, validator
      llm/             role-based chat-model factory
      sinks/           pluggable external result sink
    models/            API schemas + SQLAlchemy ORM
    repository/        task persistence
  tests/               unit + integration (fake LLMs, HTML fixtures, in-memory SQLite)
frontend/              React + antd single-page UI
```

## Getting started

### Prerequisites
- Python ≥ 3.12, Node.js ≥ 18
- A DashScope API key ([Aliyun Bailian](https://bailian.console.aliyun.com/))

### Backend

```bash
cd backend
python -m venv .venv && source .venv/Scripts/activate   # Windows Git Bash
pip install -e ".[dev]"
python -m playwright install chromium

cp .env.example .env      # then set DASHSCOPE_API_KEY
uvicorn app.main:app --reload --port 8000
```

Interactive API docs: http://localhost:8000/docs

### Frontend

```bash
cd frontend
npm install
npm start                 # http://localhost:3000 (proxies /api to :8000)
```

## Configuration

All settings are read from `backend/.env` (see `.env.example`). Key ones:

| Variable | Purpose |
|---|---|
| `DASHSCOPE_API_KEY` | Aliyun DashScope key |
| `LLM_MODEL` | General model (planning, LLM extraction) |
| `LLM_CODE_MODEL` | Code model (selector generation), e.g. a Qwen3-Coder |
| `MAX_EXTRACTION_RETRIES` / `MIN_FIELD_COVERAGE` | Reflection-loop thresholds |
| `DATABASE_URL` | Local application-state store |
| `RESULT_SINK_URL` | Optional external DB for result records only |

Model IDs are config-driven: prefer `qwen3-*`, moving to higher versions if a size is
unavailable. Two documented profiles ship in `.env.example` — small models for logic
tests, larger models for extraction-quality evaluation.

## API

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/v1/scrape` | Run a scrape, return the result |
| POST | `/api/v1/scrape/stream` | Same, streaming node progress (SSE) |
| GET | `/api/v1/tasks` | Paginated run history |
| GET | `/api/v1/tasks/{id}` | Run detail (records, log, validation) |
| GET | `/api/v1/tasks/{id}/export?format=csv\|xlsx` | Export a result |
| GET | `/healthz` | Health check |

## Testing & quality

```bash
cd backend
ruff check app tests      # lint + import order
mypy app                  # type check
pytest -q                 # unit + integration (no network / API key needed)
```

CI runs all of the above plus the frontend build on every push
([.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Docker

```bash
DASHSCOPE_API_KEY=sk-... docker compose up --build
```

Runs the backend (with Chromium) on :8000; the SQLite file persists on a named volume.
Run the frontend with `npm start` during development.

## Scope & limits

This is a "given a page, extract this content" tool, not a large-scale crawler: it
respects a single-page focus, does not do proxy rotation or CAPTCHA solving, and enforces
an SSRF guard against private addresses. Login-gated pages, infinite scroll and cross-page
dedup are out of scope.
