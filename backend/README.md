# LeAgent Backend

The Python service powering **LeAgent** — an enterprise-grade intelligent office automation platform that combines
LLM-powered agents, a visual workflow engine, a rule engine, a typed tool system and multi-channel delivery in a single
FastAPI application.

> For a product-level overview of the platform, see the [root README](../README.md).
> For deployment instructions, see [`../deploy/README.md`](../deploy/README.md).
> For contributor conventions, see [`../AGENTS.md`](../AGENTS.md).

---

## Desktop & thin install

- Default database is **SQLite** under `LEAGENT_HOME/leagent.db` (or `DB_SQLITE_PATH`). Use `DB_DRIVER=postgresql+asyncpg` (and related `DB_*` fields) for Postgres.
- Heavy stacks ship as **optional extras**: `leagent[browser]`, `leagent[office]`, `leagent[rag]`, `leagent[ocr]`, `leagent[paddle]` (legacy OCR). Admins can also install packs from **Settings → Plugins** (`/api/v1/extensions`).
- After editing `pyproject.toml`, run `uv lock` to refresh `uv.lock`.

---

## Architecture

The default deployment is a **single-process async monolith** (`leagent/main.py`).
All modules — agent runtime, workflow engine, tool executor, LLM routing, session
management — run in one FastAPI process backed by SQLite. This is suitable for
single-machine and small-team use.

```
                 HTTP / WS / SSE
 clients ─────────────────────────▶  FastAPI (leagent.main:app)
                                       │  auth · CORS · uploads · SSE streaming
                                       │
           ┌───────────────────────────┼──────────────────────────────┐
           ▼                           ▼                              ▼
    QueryEngine                  Workflow Engine               LLM Service
    (agent runtime)              (YAML + visual)               (tier routing)
           │                           │                              │
           ▼                           ▼                              ▼
    ToolExecutor ◄── ToolRegistry ──► Tool.<name> workflow nodes     Providers
    (80+ tools)      (single source   (auto-generated palette)       (DeepSeek,
                      of truth)                                       OpenAI,
                                                                      Anthropic,
                                                                      DashScope,
                                                                      Ollama, vLLM)
           │
           ▼
    SQLite (default) + local filesystem under LEAGENT_HOME
    Optional: PostgreSQL, Milvus (vector memory), MinIO (object storage)
```

An optional gateway entrypoint exists at `leagent/apps/gateway/` for teams that
outgrow the monolith. See [`../AGENTS.md`](../AGENTS.md) for the modular-monolith
discussion and [`../docs/deployment/MODULAR_MONOLITH.md`](../docs/deployment/MODULAR_MONOLITH.md)
for the full topology guide.

---

## Table of contents

- [Highlights](#highlights)
- [Tech stack](#tech-stack)
- [Directory layout](#directory-layout)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the server](#running-the-server)
- [CLI](#cli)
- [Database & migrations](#database--migrations)
- [Testing](#testing)
- [Lint, format & type-check](#lint-format--type-check)
- [Extending the platform](#extending-the-platform)
- [Local Desktop State](#local-desktop-state)
- [Observability](#observability)
- [Troubleshooting](#troubleshooting)

---

## Highlights

- **Async FastAPI** application with 20+ versioned routers under `leagent/api/v1/` (auth, chat, tasks, tools, rules, cron, skills, channels, templates, webhooks, MCP, files/folders/documents, metrics, health, ...). The workflow engine owns its own namespace at `/api/v1/workflow/*` (CRUD, prompts, WebSocket progress, node admin). Incubating v2 endpoints live under `leagent/api/v2/`.
- **QueryEngine session orchestrator** (`leagent/agent/query_engine.py`) — session-scoped state, streaming `submit_message()` async generator, DI-friendly `QueryDeps` seam, explicit `Terminal` / `Continue` transitions. The legacy `AgentController` is a compat shim over `QueryEngine`.
- **Hybrid agent runtime** in `leagent/agent/` — a ReAct controller, a Plan-and-Execute planner, a tool executor, sub-agent spawning (`fork_subagent`, `ScriptAgentTool`), and abort-safe runs.
- **Tool system** (`leagent/tools/`) with 80+ tools across 15 categories, aliases, semantic input validation, concurrency classes (`concurrent_safe` / `read_only` / `destructive`), result-size budgets, live activity strings and interrupt behaviour.
- **Layered prompt management** (`leagent/prompts/`) — 8-layer `PromptBuilder`, file-system `PromptRegistry`, per-layer + global budget enforcement, SHA-256 fingerprinting, provider-aware rendering (Anthropic `cache_control`).
- **Workflow engine** (`leagent/workflow/`) — single canonical document schema, typed IO/Schema node contracts, per-node caches, in-memory prompt queue, and a dedicated FastAPI surface at `/api/v1/workflow/*` with WebSocket progress streams.
- **Rule engine** (`leagent/rules/`) supporting 8 primitives: `compare`, `date_range`, `threshold`, `contains_all`, `date_diff`, `regex_match`, `cross_validate`, `llm_judge`.
- **Context assembly** (`leagent/context/`) — source-driven pipeline with `ContextManager`, `ContextRecipe`, 12 `ContextSource` implementations, cost-function budget minimisation, and provider-specific strategies (e.g. `strategies/deepseek.py`).
- **Service layer** (`leagent/services/`) with database, auth (+ HMAC-signed file URLs), chat, session (`SessionManager` + `TieredSessionStore`), code execution (subprocess sandbox), coding projects (scaffolding + `git init`), canvas/gen-UI, file management, and **TaskManager** (lifecycle, abort, byte-offset output streaming).
- **LLM abstraction** (`leagent/llm/`) with tier-based routing and providers: **DeepSeek** (auto-aliased as tier1/tier2 when `DEEPSEEK_API_KEY` is set), OpenAI, Anthropic, DashScope, Ollama, vLLM.
- **Cognitive agent memory** (`leagent/memory/`) — `AgentMemory` facade with episodic, semantic, and procedural stores, `RetrievalPipeline` (hybrid search + reranking), `WorkingScratchpad`, `RecallHandle`, and micro/auto-compaction.
- **Multi-channel delivery** (`leagent/channels/`) — `web`, `console`, `api`, `dingtalk`, `feishu`, `wechat_work`, `weixin`.
- **Agent Skills v1.0** — `SKILL.md`-first skill system (`leagent/skills/`) with progressive disclosure, cross-agent discovery, and a pluggable HTTP registry. See the [Skills guide](../docs/guide/skills.md).
- **Batteries included** — cron scheduler (APScheduler + croniter), MCP client, structured JSON logging, Prometheus metrics, SSE streaming, WebSocket support, polite outbound HTTP (robots.txt, per-host locking).

---

## Tech stack

| Area | Libraries |
|---|---|
| Web framework | FastAPI, Uvicorn, Gunicorn, `sse-starlette`, `websockets` |
| Data layer | SQLModel, SQLAlchemy (async), Alembic, `aiosqlite`, `sqlite-vec`; optional `asyncpg` for PostgreSQL |
| Validation | Pydantic v2, `pydantic-settings`, `jsonschema`, `email-validator` |
| LLM | `openai`, `anthropic`, `tiktoken`, `httpx`, `aiohttp` |
| Docs & data | `pymupdf`, `pdfplumber`, `python-docx`, `openpyxl`, `pandas`, `xlsxwriter`, `reportlab`, `pillow` |
| Web automation | `playwright` (optional extra `leagent[browser]`) |
| Vector & objects | `pymilvus`, `minio` (optional — only needed for RAG memory / object storage) |
| Scheduling | `apscheduler`, `croniter`, `pytz` |
| Security | `python-jose[cryptography]`, `passlib[bcrypt]` |
| CLI & logging | `click`, `rich`, `structlog` |
| Serialization | `orjson`, `pyyaml`, `jinja2`, `aiofiles`, `aiosmtplib` |
| Tooling (dev) | `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff`, `mypy` |

See [`pyproject.toml`](./pyproject.toml) for the authoritative dependency list.

---

## Directory layout

```
backend/
├── alembic.ini                  Alembic configuration (DSN read from env)
├── pyproject.toml               Package metadata, deps, Ruff/Mypy/Pytest config
├── README.md                    (this file)
├── tests/                       Pytest suite (30+ modules)
│   ├── conftest.py
│   ├── fixtures/
│   └── test_*.py                agent, workflow, rules, tools, api, channels, …
└── leagent/
    ├── main.py                  ASGI app factory (FastAPI lifespan, routers, middleware)
    ├── server.py                Uvicorn / Gunicorn bootstrap
    ├── agent/                   QueryEngine (primary) + ReAct/Plan-Execute runtime
    │   ├── query_engine.py      Session orchestrator (submit_message, SDKMessage stream)
    │   ├── query.py · state.py  Per-turn loop + mutable state
    │   ├── transitions.py       Terminal / Continue explicit transition values
    │   ├── deps.py              QueryDeps DI protocol (call_model, micro/autocompact)
    │   ├── tool_use_context.py  Runtime context bundle for tool execution
    │   ├── controller.py        AgentController (compat shim → QueryEngine)
    │   ├── planner.py           Plan-and-Execute path
    │   ├── script_agent.py      Scoped compute / subprocess engine builder
    │   ├── subagent.py          Sub-agent delegation (fork_subagent)
    │   ├── coding_agent.py      Coding-project agent specialisation
    │   ├── runtime_profile.py   Agent runtime profiles
    │   └── hooks.py · recovery.py · executor.py · base.py
    ├── alembic/                 Migration scripts (inside leagent package)
    ├── api/
    │   ├── router.py            Top-level router aggregator
    │   ├── middleware.py        Auth, request IDs, rate limits, metrics
    │   ├── deps.py              FastAPI dependencies (DB session, current user, …)
    │   ├── v1/                  24+ routers (see list below)
    │   └── v2/                  Next-gen endpoints (incubating)
    ├── apps/                    Optional split-deploy entrypoints
    │   └── gateway/             API gateway (for modular-monolith topology)
    ├── bootstrap/               Canonical tool + workflow-node startup
    │   └── tools.py             bootstrap_tools, register_script_agent_tool
    ├── channels/                Delivery adapters + manager + registry + renderer
    │   ├── base.py · manager.py · registry.py · renderer.py
    │   └── web/ · console/ · api/ · dingtalk/ · feishu/ · wechat_work/ · weixin/
    ├── chat_workflow/           Chat-workflow orchestration
    ├── cli/                     Click command groups (23 modules, see CLI section)
    ├── config/                  Pydantic settings, defaults, env loading
    ├── console/                 Rich-based console helpers
    ├── context/                 Source-driven prompt assembly
    │   ├── manager.py · recipe.py · budget.py · types.py · ledger.py · cache.py
    │   ├── file_state.py        Session-scoped file read cache
    │   ├── working_set.py · compression.py · session_compression.py
    │   ├── sources/             12 ContextSource implementations
    │   └── strategies/          Provider-specific strategies (e.g. deepseek.py)
    ├── cron/                    APScheduler-based job manager
    ├── exceptions/              Domain error hierarchy
    ├── extensions/              Optional plugin extensions
    ├── initial_setup/           First-run seeding (admin, default channels, demo data)
    ├── llm/                     LLM service, tiered router, provider adapters
    │   ├── service.py · registry.py · router.py · base.py · provider_config.py
    │   └── providers/           DeepSeek, OpenAI, Anthropic, DashScope, Ollama
    ├── mcp/                     Model Context Protocol client
    ├── memory/                  Cognitive three-store agent memory
    │   ├── agent_memory.py      AgentMemory facade + RecallHandle
    │   ├── episodic.py · semantic.py · procedural.py   Three stores
    │   ├── recall.py            RetrievalPipeline (hybrid search + reranking)
    │   ├── embeddings.py · vector.py   Embedding + Milvus wrappers
    │   ├── working_scratchpad.py   Ephemeral tool history + scratchpad
    │   ├── compact.py · compaction.py   Micro/auto-compaction
    │   └── manager.py · short_term.py · working.py · long_term.py   Legacy paths
    ├── prompts/                 Layered prompt management
    │   ├── builder.py · registry.py · render.py · fingerprint.py · context.py · types.py
    │   └── templates/           .md files with YAML front-matter
    │       ├── default_agent.md · script_agent.md · coding_agent.md · subagent.md
    │       ├── rule_judge.md · compact_summariser.md
    │       └── policies/        Composable policy snippets
    ├── rules/                   Rule engine (8 primitives) + YAML definitions
    ├── schema/                  App-level shared Pydantic schemas
    ├── scripts/                 Ops scripts (e.g. run_migrations with advisory lock)
    ├── services/                Core service layer
    │   ├── database/            SQLModel ORM + repository helpers
    │   ├── auth/                JWT, RBAC, signed URLs
    │   ├── session/             SessionManager + TieredSessionStore
    │   ├── chat/                Chat service + daily greetings
    │   ├── cache/               Cache abstractions
    │   ├── canvas/              Gen-UI rendering + HTML bundling
    │   ├── code_execution/      Subprocess sandbox (workspace, runner, rlimits)
    │   ├── coding_projects/     Scaffold templates (vite-react, fastapi, vanilla-html)
    │   ├── compact/             Compaction service
    │   ├── diagnostics_parsers/ Shell output diagnostics parsing
    │   ├── event/               In-process event bus
    │   ├── execution/           Execution management
    │   ├── file_manager/        File operations
    │   ├── file_processing/     Document processing pipelines
    │   ├── file_store/          File persistence
    │   ├── gen_ui/              GenUI schema, print renderer, PPTX renderer
    │   ├── job_queue/           Background job management
    │   ├── python_env/          Python environment resolution
    │   └── variable/            Variable management
    ├── skills/                  Agent Skills v1.0 (SKILL.md loader, manager,
    │   │                          discovery, HTTP registry, bundle packaging)
    │   └── builtin/             Built-in skills (document-processor, data-analyzer, …)
    ├── tasks/                   Task system (handlers/)
    ├── tools/                   80+ tool implementations across 15 categories
    │   ├── base.py              BaseTool (aliases, validation, budgets, activity, sandbox)
    │   ├── registry.py          ToolRegistry (alias lookup, search, deny rules)
    │   ├── executor.py          ToolExecutor (concurrency, permissions, abort)
    │   ├── _data/               ArtifactRef, TabularSchema, streaming primitives
    │   ├── _sandbox/            PathSandbox (filesystem allow-list enforcement)
    │   ├── doc/ web/ data/ gen/ chart/ image/ code/ db/
    │   ├── canvas/ project/ coding_project/ skills/ workflow/
    │   ├── integration/ util/
    ├── utils/                   Shared helpers (CJK fonts, etc.)
    └── workflow/                Workflow engine + YAML parser + node implementations
        ├── engine/              Runner, executor, graph, caching, progress
        ├── io/                  Schema contracts, bridge, serializer
        ├── layout/              Visual layout engine
        ├── nodes/               Base + loader + tool_factory + builtin/
        ├── queue/               Prompt queue (in-memory)
        └── server/              Workflow-specific API + WebSocket
```

### Telemetry — `leagent/telemetry/`

Cross-cutting observability utilities live in [`leagent/telemetry/`](leagent/telemetry/):

| Module | Purpose |
|--------|---------|
| `otel.py` | OTel SDK bootstrap, `get_tracer`, `_NullTracer` fallback |
| `logging.py` | Structured JSON logging via structlog, context vars |
| `propagation.py` | W3C traceparent inject / extract across transports |

### API routers (v1)

`activities`, `auth`, `canvas`, `channels`, `chat`, `cron`, `documents`, `files`, `flows`, `folder_items`, `folders`, `health`,
`mcp`, `metrics`, `models`, `rules`, `settings_mail`, `skills`, `stats`, `tasks`, `templates`, `tools`, `users`, `webhooks`.

---

## Requirements

- **Python 3.11+** (3.12 recommended)
- **SQLite** (bundled with Python — the default, zero-config database)
- **Playwright browsers** — install via `playwright install chromium` to enable the `tools/web/*` tools (optional extra `leagent[browser]`)

Optional (for advanced features):

- **PostgreSQL 15+** — use `DB_DRIVER=postgresql+asyncpg` for production-grade persistence
- **Milvus 2.4+** — required for vector-backed agent memory (episodic/semantic/procedural recall)
- **MinIO** (or any S3-compatible store) — for object storage
- NVIDIA GPU + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) for local vLLM inference

---

## Installation

```bash
cd backend

# Using uv (recommended)
uv sync --extra dev
uv run playwright install chromium   # if you use browser tools

# Or using pip
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
playwright install chromium
```

This exposes the `leagent` console entry point declared in `pyproject.toml`:

```toml
[project.scripts]
leagent = "leagent.cli.main:cli"
```

---

## Configuration

Configuration is loaded via `pydantic-settings`. The canonical template is [`../deploy/.env.example`](../deploy/.env.example);
for local development you can place a `.env` file in `backend/` or export variables in your shell.

Key variables:

| Variable | Description |
|---|---|
| `LEAGENT_SECRET_KEY` | **Required.** JWT / signing secret. Generate with `openssl rand -hex 32`. |
| `DB_SQLITE_PATH` | SQLite file path (defaults to `~/.leagent/leagent.db`). |
| `DATABASE_URL` | SQLAlchemy async DSN for PostgreSQL, e.g. `postgresql+asyncpg://user:pass@localhost:5432/leagent`. |
| `DEEPSEEK_API_KEY` | DeepSeek provider key (auto-aliases tier1 → v4-pro, tier2 → v4-flash). |
| `OPENAI_API_KEY`, `ANTHROPIC_API_KEY` | Other LLM provider keys. |
| `LLM_TIER1_API_KEY` / `LLM_TIER1_ENDPOINT` | Explicit primary (reasoning) tier. |
| `LLM_TIER2_API_KEY` / `LLM_TIER2_ENDPOINT` | Explicit secondary (fast / cheap) tier. |
| `LEAGENT_LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING`. |
| `LEAGENT_HOME` | Root for data, knowledge, uploads, logs (default `~/.leagent`). |

Settings are loaded by `leagent.config` at startup and are also accessible via:

```bash
leagent config show
leagent env
```

---

## Running the server

### Hot-reload (dev)

```bash
uvicorn leagent.main:app --reload --host 0.0.0.0 --port 7860
# or equivalently:
leagent app --reload
```

Open:

- OpenAPI UI: <http://localhost:7860/docs>
- ReDoc: <http://localhost:7860/redoc>
- Health: <http://localhost:7860/health>
- Prometheus metrics: <http://localhost:7860/metrics>

### Production

The Docker image runs Gunicorn with Uvicorn workers (see `../deploy/supervisord.conf` and
`../deploy/entrypoint.sh`). To reproduce locally:

```bash
gunicorn leagent.main:app \
  -k uvicorn.workers.UvicornWorker \
  -w 4 \
  -b 0.0.0.0:7860 \
  --access-logfile - --error-logfile -
```

---

## CLI

The `leagent` CLI groups operational commands. A selection:

```bash
leagent --help                          # top-level help

# Lifecycle
leagent init                            # initialize config, DB, default admin
leagent app [--reload] [--port 7860]    # run the API server
leagent daemon start|stop|status        # supervisor-style daemon mode
leagent clean                           # clean caches / temp artefacts

# Configuration & diagnostics
leagent config show
leagent env

# Providers, channels, chats
leagent providers list|add|remove
leagent channels   list|add|remove
leagent chats      list|show|delete

# Workflows, rules, templates
leagent workflows list|run|validate
leagent templates list|apply
leagent rules      list|test

# Tasks, cron, skills, webhooks
leagent tasks      list|show|kill|output
leagent cron       list|add|remove|run
leagent skills     list|show|init|validate|lint|migrate|install|uninstall|enable|disable|search
leagent webhooks   list|add|test
```

Implementations live under `leagent/cli/` — one module per command group (e.g. `tasks_cmd.py`, `workflows_cmd.py`).

---

## Database & migrations

Models are SQLModel subclasses under `leagent/services/database/`. The project uses **Alembic** for schema migrations.

```bash
# Apply all migrations (runs automatically on container start via entrypoint.sh)
cd backend
alembic upgrade head

# Generate a new migration after changing a model
alembic revision --autogenerate -m "describe the change"

# Downgrade one step
alembic downgrade -1

# Full history
alembic history --verbose
```

The Alembic config (`alembic.ini`) reads the DSN from `DATABASE_URL`. For local SQLite usage the DSN defaults to a file
under `LEAGENT_HOME`.

---

## Testing

```bash
# Full suite
cd backend
pytest

# Using uv
uv run pytest tests/ -v

# Single module / single test
pytest tests/test_query_engine.py
pytest tests/test_workflow.py::test_parallel_node

# Filter by expression
pytest -k "rule and not slow"

# Coverage
pytest --cov=leagent --cov-report=term-missing --cov-report=html
```

Pytest is configured in `pyproject.toml`:

- `asyncio_mode = "auto"` — no need to decorate async tests.
- `testpaths = ["tests"]`.
- Deprecation warnings are filtered out.

Fixtures for DB sessions, temporary file stores, an in-memory tool registry and stubbed LLM providers live in
`tests/conftest.py` and `tests/fixtures/`.

---

## Lint, format & type-check

```bash
ruff check .               # lint
ruff check . --fix         # auto-fix where safe
ruff format .              # format (Black-compatible)

mypy leagent               # strict type-checking (see pyproject.toml)
```

Ruff is configured with `line-length = 120`, target `py311`, and rule groups `E, W, F, I, N, UP, B, SIM, TCH`.
Mypy runs in **strict mode** with the Pydantic plugin.

---

## Extending the platform

### Add a new tool

1. Create `leagent/tools/<category>/<name>.py`.
2. Subclass `BaseTool` and implement:

   ```python
   from leagent.tools.base import BaseTool, ToolResult

   class InvoiceSummarizer(BaseTool):
       name = "invoice_summarizer"
       aliases = ["invoice_sum", "summarize_invoice"]
       description = "Summarize an invoice PDF into structured fields."
       category = "doc"
       concurrency_class = "read_only"
       result_budget_bytes = 256_000
       activity = "Summarizing invoice..."

       path_params = ("file_path",)           # read-only access
       output_path_params = ("output_path",)  # allows file creation

       async def validate_input(self, payload: dict) -> None:
           if "file_id" not in payload:
               raise ValueError("file_id is required")

       async def run(self, payload: dict, ctx) -> ToolResult:
           ...
   ```

3. Export it from the category `__init__.py` so the registry picks it up on startup.
4. **Declare sandbox path parameters.** If your tool reads or writes files,
   set `path_params` (read-only) and/or `output_path_params` (allows creation)
   on the class. `BaseTool.run()` will validate them against `PathSandbox`
   before execution. For tools with nested path structures (e.g. arrays of
   file objects), override `_enforce_path_sandbox(params, context)`.
5. Add a unit test under `tests/test_tools/` (or a dedicated module) covering `validate_input`, the happy path and one failure path.
6. Verify: `pytest -k invoice_summarizer && leagent tools list | grep invoice_summarizer`.

### Add a new API route

1. Create a router module under `leagent/api/v1/<feature>.py` exposing an `APIRouter`.
2. Register it in `leagent/api/router.py`.
3. Add request/response schemas in `leagent/schema/` (or co-located) — always Pydantic v2.
4. Protect the route with `Depends(get_current_user)` / role dependencies from `leagent/api/deps.py`.

### Add a new channel, rule type, LLM provider or workflow node

- **Channel** — subclass `BaseChannel` under `channels/<name>/`, register in `channels/registry.py`.
- **Rule type** — implement the evaluator in `rules/` and register it in the rule registry.
- **LLM provider** — add an adapter in `llm/providers/` and list it in `cli/providers_cmd.py`.
- **Workflow node** — add a node implementation under `workflow/nodes/builtin/` and register it in the node loader.

See [`../AGENTS.md`](../AGENTS.md) for style conventions and coding guidelines.

---

## Local Desktop State

LeAgent is a local-first desktop app. The backend keeps enough state to power
chat, tool execution, files and background jobs on one machine; it is not a
multi-tenant account system.

### Persistent Data

| Area | Purpose |
|---|---|
| `chat_sessions` | Conversation history, session metadata and authorized local paths |
| `files` | Session uploads, knowledge documents and signed preview/download metadata |
| `coding_projects` | Local coding project records backed by files under `CODING_PROJECTS_ROOT` |
| `tasks` | Background job lifecycle, abort state and file-backed output logs |
| agent memory tables | Episodic, semantic and procedural recall for local agent sessions |

Default installs use SQLite under `LEAGENT_HOME`; optional PostgreSQL is for
heavier single-machine or team deployments, not for workspace isolation.

### Local Access Boundaries

New routes should be scoped around sessions, files, tools and local projects.
For filesystem access, use `PathSandbox` and the session authorized-path APIs
instead of adding account or workspace checks. File preview/download routes use
short-lived HMAC-signed URLs so the desktop UI can open artifacts without
exposing raw paths.

---

## Observability

- **Metrics** -- `GET /metrics` emits Prometheus counters/histograms for HTTP latency, error rates, LLM token usage, tool execution durations and task queue depth.
- **Logs** -- `structlog` outputs JSON with `request_id`, `task_id`, `tool`, `latency_ms`, `level`, `event`. The log level is controlled by `LEAGENT_LOG_LEVEL`.
- **Task output** -- `TaskManager` streams handler output to file-backed logs; the API exposes `GET /api/v1/tasks/{id}/output?offset=<bytes>` for incremental polling.
- **Health** -- `GET /health` reports DB connectivity (and optional Redis/Milvus/MinIO when configured).

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `ModuleNotFoundError: leagent` | Virtualenv not active, or `uv sync --extra dev` / `pip install -e ".[dev]"` was not run in `backend/`. |
| `sqlalchemy.exc.OperationalError` on startup | Check `DATABASE_URL` or `DB_SQLITE_PATH`. For PostgreSQL: verify the server is reachable. |
| `playwright._impl._errors.Error: Executable doesn't exist` | Run `playwright install chromium` inside the active venv. |
| 401 on every endpoint | `LEAGENT_SECRET_KEY` changed between restarts — existing tokens are invalidated. Re-login or pin the secret. |
| LLM calls hang or 429 | Check provider keys (`DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, etc.), tier endpoint config, or provider rate limits. |
| DeepSeek balance errors | Run `leagent providers list` to check balance. Verify `DEEPSEEK_API_KEY` is valid. |
| Alembic `Target database is not up to date` | Run `alembic upgrade head` (the entrypoint does this automatically in Docker). |

For anything else, check the structured logs:

```bash
tail -f ~/.leagent/logs/leagent.log            # local dev
docker compose logs -f leagent                 # Docker
```

---

## License

This codebase is part of the LeAgent platform and is covered by the project's top-level license
(see [`../LICENSE`](../LICENSE)).
