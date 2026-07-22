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
- **Selector reuse cache** — a selector plan is cached once it passes validation and
  reused on later runs, so re-scraping the same site with the same request costs no LLM
  calls at all. Keyed by (host, normalised prompt, field set); a cached plan that later
  fails validation is invalidated, so stale selectors self-heal.
- **Cost visibility** — per-run input/output token counts are recorded and shown in the
  run history.
- **Live progress** — node-level execution streamed to the UI over Server-Sent Events.
- **Persistence & export** — every run is stored; browse history and export any result
  to CSV or Excel. Results can optionally be pushed to an external database.
- **Operational robustness** — automatic backoff retries on transient LLM errors, a cap
  on concurrent browser renders, a DOM prompt-size budget, and runs left mid-flight by a
  crash or restart are reconciled to `interrupted` at startup rather than hanging.

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

`gen_selectors` consults the **selector cache** first: on a hit the LLM call is skipped
entirely and the cached plan goes straight to `execute_selectors`. The cache is bypassed
on a reflection retry, where the point is to produce something different from what just
failed. `validate_result` maintains it — a plan is stored once it passes, and a cached
plan that later fails is invalidated, so stale selectors self-heal.

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
      export_service   records -> CSV / Excel
      extraction/      planner, selector_gen, executor, llm_extractor,
                       validator, cache (selector-plan reuse)
      llm/             role-based chat-model factory
      sinks/           pluggable external result sink
    models/            API schemas + SQLAlchemy ORM
    repository/        task + selector-cache persistence
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

All settings are read from `backend/.env` (see `.env.example`) via pydantic-settings;
nothing is hard-coded. Defaults below are what ships in `app/core/config.py`.

**LLM**

| Variable | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER` | `dashscope` | `dashscope` (Aliyun, OpenAI-compatible) or `claude` |
| `DASHSCOPE_API_KEY` | – | DashScope key; required for any extraction |
| `DASHSCOPE_BASE_URL` | `.../compatible-mode/v1` | Swap for the international endpoint if needed |
| `LLM_MODEL` | `qwen3-8b` | General reasoning: planning, LLM extraction |
| `LLM_CODE_MODEL` | `qwen3-coder-30b-a3b-instruct` | Code task: selector generation |
| `ANTHROPIC_API_KEY` | – | Only when `LLM_PROVIDER=claude` |
| `LLM_MAX_RETRIES` | `3` | Backoff retries on transient errors (429/5xx/timeouts) |
| `LLM_TIMEOUT_S` | `60` | Per-call timeout |
| `DOM_PROMPT_CHAR_BUDGET` | `12000` | Char budget for the DOM embedded in a prompt |

**Extraction quality**

| Variable | Default | Purpose |
|---|---|---|
| `MAX_EXTRACTION_RETRIES` | `2` | Reflection-loop retry cap across strategies |
| `MIN_FIELD_COVERAGE` | `0.5` | Below this, a result fails validation and triggers a retry |

**Persistence**

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./scraper.db` | Application state: tasks, logs, results, selector cache |
| `RESULT_SINK_URL` | *(empty)* | Optional external DB for **result records only**; empty keeps everything local |

**Fetching**

| Variable | Default | Purpose |
|---|---|---|
| `FETCH_TIMEOUT_MS` | `30000` | Page fetch/render timeout |
| `MAX_CONCURRENT_BROWSERS` | `2` | Cap on simultaneous Playwright renders (memory-heavy) |
| `BLOCK_PRIVATE_ADDRESSES` | `true` | SSRF guard: reject private/loopback targets |
| `STATIC_FETCH_MIN_TEXT` | `200` | Visible-text threshold below which the browser path is used |
| `USER_AGENT` | project UA | Sent on outbound requests |

**Server**

| Variable | Default | Purpose |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:3000` | Comma-separated allowed origins |
| `LOG_LEVEL` / `DEBUG` | `INFO` / `false` | Logging verbosity and FastAPI debug mode |

Model IDs are config-driven: prefer `qwen3-*`, moving to higher versions if a size is
unavailable. Two documented profiles ship in `.env.example` — small models for logic
tests, larger models for extraction-quality evaluation.

The selector cache has no settings: it is always on, has no TTL, and is maintained by
outcome (stored on validation pass, invalidated on later failure).

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

61 backend tests cover the graph end to end (fake LLMs + HTML fixtures), the controlled
selector executor, DOM compression, validation and the reflection loop, persistence and
export, the selector cache, and schema reconciliation on an older database. The frontend
has unit tests for the SSE client.

CI runs all of the above plus the frontend test and build on every push
([.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Docker

```bash
DASHSCOPE_API_KEY=sk-... docker compose up --build
```

Runs the backend (with Chromium) on :8000; the SQLite file persists on a named volume.
Run the frontend with `npm start` during development.

## Scope & limits

This is a "given a page, extract this content" tool, not a large-scale crawler: it
fetches the single page you point it at, does not do proxy rotation or CAPTCHA solving,
and enforces an SSRF guard against private addresses. Login-gated pages, infinite scroll
and cross-page dedup are out of scope.

It does **not** currently read `robots.txt` or apply per-host rate limiting — it issues
one request per run, so pacing is a function of how often you invoke it. If you point it
at a site whose terms disallow automated access, that is on the operator; add a
robots.txt check before using it on anything beyond pages you are entitled to scrape.
