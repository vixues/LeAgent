# LeAgent Development Guidelines

AI coding assistants: this file is the concise contributor reference. For deep subsystem docs see `docs/technical/`.

## Project Overview

LeAgent is a local-first intelligent office automation stack combining LLMs with workflow automation. Key pieces: `QueryEngine` session orchestrator, 80+ domain tools (15 categories), layered prompt management, cognitive three-store agent memory, visual workflow builder (ReactFlow), and a declarative YAML rule engine. Providers: OpenAI, Anthropic, DeepSeek, DashScope, Azure OpenAI, Ollama, vLLM.

## Architecture

```
LeAgent/
├── backend/
│   ├── leagent/
│   │   ├── agent/        # QueryEngine, controller, planner, subagents
│   │   ├── alembic/      # Alembic migration scripts
│   │   ├── api/          # FastAPI routers (v1, v2)
│   │   ├── bootstrap/    # Tool + workflow-node startup
│   │   ├── channels/     # Outbound integrations (IM, console)
│   │   ├── chat_workflow/ # Chat-workflow orchestration
│   │   ├── cli/          # Click CLI (23 modules)
│   │   ├── code/         # Code execution layer (sandbox, workspace, runner)
│   │   ├── config/       # pydantic-settings
│   │   ├── context/      # Source-driven prompt assembly
│   │   ├── file/         # Unified file layer (primitives, FileService, storage)
│   │   ├── llm/          # LLM service + providers
│   │   ├── mcp/          # Model Context Protocol
│   │   ├── memory/       # AgentMemory (episodic/semantic/procedural)
│   │   ├── project/      # Coding project layer (fs, tools, manager, templates)
│   │   ├── prompts/      # PromptBuilder, registry, templates
│   │   ├── rules/        # Rule engine + YAML definitions
│   │   ├── services/     # DB, auth, chat, session, ...
│   │   ├── skills/       # Agent Skills v1.0
│   │   ├── telemetry/    # OTel tracing, structured logging, trace propagation
│   │   ├── tools/        # 80+ tool implementations by category
│   │   └── workflow/     # Engine, nodes, templates
│   └── tests/
├── deploy/               # Dockerfile + SQLite-only Compose
├── frontend/             # React 19 + TypeScript SPA
├── config/               # Demo workflows + workflow templates
├── docs/                 # Architecture, guides, deployment docs
├── scripts/              # Install scripts (sh, ps1, bat)
├── fonts/                # Font assets (CJK, etc.)
├── website/              # Project website
└── start.sh / start.ps1  # Dev orchestrator (uv + npm)
```

Default database is **SQLite** (zero-config). Optional PostgreSQL via `DATABASE_URL`, optional Milvus for vector memory.

### Layered Domain Model: File → Code → Project

The backend uses a strict three-layer architecture. Dependencies flow downward only.

| Layer | Package | Responsibility |
|---|---|---|
| **File** | `leagent/file/` | Unified blob storage, metadata, lifecycle. `FileService` is the single ingress for all managed files. `primitives.py` holds shared utilities (`sanitize_filename`, `detect_mime`, `classify_file_kind`, `is_path_inside`, `FileScope`, `FileKind`). |
| **Code** | `leagent/code/` | Code execution sandbox, workspace management, artifact handling. Builds on File layer for artifact registration. |
| **Project** | `leagent/project/` | Coding project workspaces: file editing, project scaffold, dev server, templates. Never imports from File layer (`FileService`/`FileRef`). |

**Key rules:**
- `leagent/project/` must never import `FileService` or `FileRef` (enforced by `test_file/test_invariants.py`).
- All managed blob writes go through `FileService.register()` — no direct `open(..., 'wb')` in blob paths.
- Path containment checks should use `leagent.file.primitives.is_path_inside()`, not inline `relative_to`/`commonpath`.
- Legacy shim modules have been removed. All imports must use canonical paths (`leagent.file.*`, `leagent.code.*`, `leagent.project.*`).

### Adding a New Tool That Produces Files

Tools that produce output files should return `FileRef` objects via `ToolResult.produced_files`:

```python
from leagent.file.service import FileRef

async def execute(self, context: ToolContext, **kwargs) -> ToolResult:
    output_bytes = await self._generate(...)
    ref = await context.file_service.register(
        output_bytes,
        filename="output.png",
        scope=FileScope.OUTPUT,
        session_id=context.session_id,
    )
    return ToolResult(success=True, data={"path": ref.storage_key}, produced_files=[ref])
```

The `ArtifactRegistrar` will automatically pick up `produced_files` from the result — no path scraping needed.

## Code Style

### Python

- Type hints on all signatures, `dict[str, Any] | None` union syntax
- Pydantic v2 for validation, `async`/`await` for all I/O
- `black` for formatting, `ruff` for linting
- Google-style docstrings

```python
async def process_document(
    file_path: str,
    options: dict[str, Any] | None = None,
) -> DocumentResult:
    """Process a document and extract data."""
    ...
```

### TypeScript

- Functional components with TypeScript interfaces
- Zustand for state, React Query for API calls
- ESLint + strict mode

```typescript
interface ChatMessageProps {
  message: Message;
  isStreaming?: boolean;
}

export function ChatMessage({ message, isStreaming = false }: ChatMessageProps) {
  // ...
}
```

## Adding New Tools

1. Create `tools/<category>/new_tool.py`
2. Implement `BaseTool`:

```python
from leagent.tools.base import BaseTool, ToolResult, ToolContext

class NewTool(BaseTool):
    name = "new_tool"
    description = "Clear description for LLM"
    parameters = {
        "type": "object",
        "properties": {
            "input": {"type": "string", "description": "Input parameter"}
        },
        "required": ["input"],
    }

    async def execute(self, context: ToolContext, input: str, **kwargs) -> ToolResult:
        result = await self._process(input)
        return ToolResult(success=True, data=result)
```

3. Register in category `__init__.py`
4. Add tests in `tests/test_tools/`

No workflow work needed — the factory auto-generates a `Tool.<name>` node.

## Adding API Endpoints

1. Create router in `api/v1/`:

```python
from fastapi import APIRouter, Depends
from leagent.services.auth.deps import get_current_user_id

router = APIRouter()

@router.get("/items")
async def list_items(
    user_id: str = Depends(get_current_user_id),
    db: DatabaseService = Depends(get_db_service),
):
    return await db.get_items(user_id)
```

2. Register in `api/router.py`

## Adding Frontend Pages

1. Create `pages/NewPage/index.tsx`
2. Add route in `App.tsx`
3. **Add i18n strings** to both locale files (see below)

## Internationalization (i18n)

The frontend uses **i18next** with zh-CN (default) + en-US.

**Rule: every new key must appear in both `zh-CN/<file>.json` and `en-US/<file>.json`.**
The parity test (`npm test -- --run src/i18n/__tests__/parity.test.ts`) enforces this.

| UI area | Bundle file |
|---|---|
| About page | `about.json` |
| Account management | `accounts.json` |
| Admin (providers, users, tasks, rules) | `admin.json` |
| Login / register | `auth.json` |
| Chat view | `chat.json` |
| Coding projects | `codingProjects.json` |
| Shared UI (buttons, labels, toasts) | `common.json` |
| Dashboard | `dashboard.json` |
| Docs page | `docs.json` |
| Error pages | `errors.json` |
| Integrations (webhooks, MCP, channels) | `integrations.json` |
| Knowledge base | `knowledge.json` |
| Modals | `modals.json` |
| Navigation | `nav.json` |
| Notifications | `notifications.json` |
| Pet space | `pet.json` |
| Settings | `settings.json` |
| Workflows, cron, templates | `workflows.json` |

```typescript
import { useTranslation } from 'react-i18next';
const { t } = useTranslation();
// t('common.save'), t('execution.pageTitle', { id })
```

Use `changeAppLanguage(lng)` from `src/i18n/index.ts` (not `i18n.changeLanguage` directly).

## Database Migrations

```bash
cd backend
alembic revision --autogenerate -m "Add new table"
alembic upgrade head
alembic downgrade -1
```

## Testing

```bash
cd backend && uv run pytest tests/ -v --cov=leagent
cd frontend && npm run test
```

## Key Environment Variables

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | PostgreSQL connection (default: SQLite) |
| `SECRET_KEY` | JWT / signing secret |
| `DEEPSEEK_API_KEY` | DeepSeek provider (auto-aliases as tier1/tier2) |
| `OPENAI_API_KEY` | OpenAI provider |
| `ANTHROPIC_API_KEY` | Anthropic provider |
| `LEAGENT_DEBUG` | Enable debug mode |

See `AGENTS.md` env table in the README or `deploy/.env.example` for the full list.

## Python Environment

Use **[uv](https://docs.astral.sh/uv/)** with the backend project (`backend/pyproject.toml`):

```bash
cd backend
uv sync
uv run python -m pytest tests/ -v
```

Direct interpreter: `backend/.venv/bin/python`.