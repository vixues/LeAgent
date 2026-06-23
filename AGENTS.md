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
│   │   ├── sdk/          # Agent SDK: public surface, protocols, kernel
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
│   │   ├── llm/          # LLM service + providers + transport + streaming
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

Execution topology (agent loop, workflow engine, state ownership): [`docs/technical/execution-topology.md`](../docs/technical/execution-topology.md).

### Layered Domain Model: File → Code → Project

The backend uses a strict three-layer architecture. Dependencies flow downward only.

| Layer | Package | Responsibility |
|---|---|---|
| **File** | `leagent/file/` | Unified blob storage, metadata, lifecycle. `FileService` is the single ingress for all managed files. `primitives.py` holds shared utilities (`sanitize_filename`, `detect_mime`, `classify_file_kind`, `is_path_inside`, `FileScope`, `FileKind`). |
| **Code** | `leagent/code/` | Code execution sandbox, workspace management, artifact handling. Builds on File layer for artifact registration. |
| **Project** | `leagent/project/` | Coding project workspaces: file editing, project scaffold, dev server, templates. Never imports from File layer (`FileService`/`FileRef`). |
| **Persistence** | `leagent/db/` | Infrastructure persistence: `DatabaseService`, `engine.make_async_engine` (SQLite-WAL / PG-pool), SQLModel `models/`, sqlite compat, and per-domain `repositories/` (`ChatRepository`, `FileRepository`, `TaskRepository`, `WorkflowExecutionRepository`, modeled on `cron/repository.py`). Exposed lazily via `DatabaseService.repositories`. |

**Key rules:**
- `leagent/project/` must never import `FileService` or `FileRef` (enforced by `test_file/test_invariants.py`).
- All managed-blob writes go through `FileService.register()` — no direct `open(..., 'wb')`/`write_bytes`/`write_text` in blob paths (INV-1, hard-asserted). Genuinely non-managed writes (CLI, app/provider/cron config, workflow-definition exports, Tier-B sandbox/output-path tool writes) live in `_INV1_ALLOWLIST` in `test_file/test_invariants.py` with a written justification + CODEOWNERS review.
- Path containment checks must use `leagent.file.primitives.is_path_inside()`, not inline `relative_to`/`commonpath` (INV-7, hard-asserted).
- Persistence lives in `leagent/db/` (canonical). There is no `leagent.services.database` package or shim; all imports use `leagent.db.*`.
- Tools persist output bytes via `leagent.file.tool_output.register_tool_artifact()` (or `SessionManager.register_artifact_bytes`) rather than writing a temp file and re-registering it.
- Legacy shim modules have been removed. All imports must use canonical paths (`leagent.file.*`, `leagent.code.*`, `leagent.project.*`, `leagent.db.*`).

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

### Game-art asset nodes (first-class generation pipeline)

The art path is a hand-authored, ComfyUI-style node system — **not** the
`Model.<task>.<provider>` factory (deprecated for art; audio TTS/ASR still uses
it). Full reference: [`docs/workflow-engine/art-asset-nodes.md`](backend/docs/workflow-engine/art-asset-nodes.md).

- **Typed media sockets + `MediaRef`.** `IO.Image` / `IO.Video` / `IO.Mesh3D`
  (`workflow/io/types.py`) carry assets *by reference* as a `MediaRef`
  (`workflow/io/media.py`) — never base64 — using `/api/v1/files/{id}/preview`.
- **Generation backends (Strategy + Registry).** `leagent/llm/generation/` is the **media plane** (image / video / 3D / vfx / audio). Vendor HTTP clients live in `generation/providers/`; strategy backends in `generation/backends/`. All media generation goes through `GenerationService.generate()` (retry + failover). Chat image generation (`LLMService.generate_image`) delegates here too. Kinds: `image` / `video` / `model3d` / `vfx` / `audio`. Backends include `OpenAIImageBackend`, `DashScopeImageBackend`, `SiliconFlowImageBackend`, `LocalDiffusionBackend`, `HttpUpscaleBackend`, `HttpVideoBackend`, `HttpMesh3DBackend`, `HttpVfxBackend`, `ReplicateBackend`, `ElevenLabsBackend`, plus a deterministic `offline` floor (`LEAGENT_ART_OFFLINE=1` or `provider: offline`). Config: `providers.yaml` → `image_gen` section (`ImageGenConfigStore`). Capability discovery: single `CapabilityRegistry` shared by `GenerationService` and `bootstrap_capabilities()`.
- **Art node pack.** `workflow/nodes/art/` exports `ArtNodeExtension`;
  `BaseGenerationNode` (Template Method) owns the execute skeleton. Nodes:
  `Art.ImageGen`, `Art.Upscale` (dedicated super-resolution), `Art.VideoGen`,
  `Art.Mesh3D`, `Art.VFXGen` (flipbook/sprite-sheet), `Art.QualityCritic`
  (perceptual/LLM scoring). They emit `NodeOutput.ui.gen_ui` asset previews.
- **Self-correction (engine-side).** `Art.QualityCritic` → `QualityGateNode`
  gates a `MediaRef`; `IterativeRefineNode` (in `_LOOP_SAFE_TYPES`) writes
  `refine_feedback` (folded into the regeneration prompt) on a bounded back-edge;
  `AssetExportNode` produces a real downloadable engine-ready `.zip` bundle
  (Unity/Unreal/Godot profiles + import metadata) via the file layer.
- **Engine.** The executor stages ready *batches* and runs independent branches
  concurrently (`max_parallelism`); `ParallelNode` forks/merges state;
  `NodeRunner` applies centralized retry/backoff + runtime `Input.validate()`;
  `control.timeout_sec` is enforced. Workflow Prometheus metrics +
  quality/refine histograms feed procedure memory and a `ProviderStatsStore`
  that biases `CapabilityRouter` ranking within each cost tier.
- **Self-correction (agent-side).** `workflow_save` validates + persists an
  agent-authored graph (returns `flow_id` + digest); paired with
  `chat_workflow_embed_emit` and `workflow_run`/`workflow_status` it closes the
  idea → design → run → evaluate → re-run loop. `workflow_run` returns
  `success=False` below the quality bar so the agent re-runs **in the same turn**;
  the run-aware `ArtifactErrorTracker` also injects a regeneration directive into
  the next system prompt.
- **Planning.** `prompts/art_playbook.py` (surfaced via the `art_playbook`
  context source) supplies the art ontology, a graph-aware node catalog, the
  `TPL-ART-01` pattern, and the required tool sequence; `plan_art_tasks()`
  decomposes a brief into ordered `todo_write` steps.
- Flagship: `config/workflows/templates/TPL-ART-01.yaml`; demo:
  `config/demo-workflows/demo-art-pipeline.yaml`.

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

## Agent SDK (`leagent.sdk`)

The **Agent SDK** (`leagent/sdk/`) is the single, versioned public surface for all agent interactions. See `docs/technical/agent_sdk.md` for the full reference.

**Quick start:**

```python
from leagent.sdk import AgentRuntime, AgentBuilder

runtime = AgentRuntime.from_service_manager(service_manager)
result = await runtime.run("default_agent", "Summarise this PDF")

# Multi-turn session:
session = runtime.session("default_agent", session_id=sid, user_id=uid)
result = await session.turn("Hello")

# Resume a paused turn from a durable checkpoint (Codex RolloutRecorder /
# Claude SessionStore analogue):
async for event in runtime.resume("default_agent", checkpoint_id, "my answer"):
    ...
```

Chat **and** every background path drive through the one think-act loop
(`leagent.sdk.kernel.run_loop`): it maps `SDKMessage → AgentEvent` (identical
`{type, data}` wire shape), snapshots `RunState.messages`, dispatches the
single-site hook lifecycle (tool/subagent/pre_compact), and saves a checkpoint
on `awaiting_user_input`. The store is `InMemoryCheckpointStore` by default and
the durable `SQLCheckpointStore` (table `agent_checkpoints`) when a database is
present — wired via `RuntimeContext.from_service_manager`.

**Key exports:** `AgentRuntime` (`run`/`stream`/`delegate`/`resume`/`session`), `AgentSession`, `AgentDefinition`, `AgentBuilder`, `AgentRegistry`, `AgentEvent`, `AgentResult`, `RunContext`, `ToolContext`, `CheckpointStore`, `InMemoryCheckpointStore`, `SQLCheckpointStore`, protocols (`LLMClient`, `Provider`, `ContextAssembler`, `MemoryStore`, `RecallProvider`).

**Version:** `leagent.sdk.__version__` (semver). Current: `0.1.0`.

## Adding New Tools

Parameter naming conventions and strict contract rules:
[`docs/technical/tool-parameters.md`](../docs/technical/tool-parameters.md).

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

## Desktop (`desktop/`)

Electron 42 shell (main process **ESM**: `"type": "module"`, `tsc` → `NodeNext`): splash → `InstallationManager` → `BackendServer` (`python -m leagent.server` on `:7860`) → React SPA.

| Package | Version |
|---------|---------|
| `electron-log` | ^5.4.4 (`electron-log/main.js`) |
| `electron-updater` | ^6.8.9 |
| `electron-store` | ^11.0.2 |

| Command | Purpose |
|---------|---------|
| `cd desktop/electron && npm run build && npm start` | Dev shell (needs `frontend npm run dev` + `backend uv sync`) |
| `cd desktop/scripts && ./build-mac.sh` | macOS DMG/ZIP |
| `cd desktop/electron && npm test` | Vitest (install/path validators) |

**Env vars set by Electron:** `LEAGENT_DESKTOP=1`, `LEAGENT_DESKTOP_MODE=1`, `LEAGENT_HOME`, `LEAGENT_FRONTEND_DIST` (packaged).

**Frontend bridge:** `window.leagent` (see `desktop/README.md`). Build frontend with `VITE_DESKTOP=true`.

**Releases:** tag `desktop-v*` → `.github/workflows/desktop-release.yml`.

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