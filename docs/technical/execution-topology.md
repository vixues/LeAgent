# LeAgent Execution Topology

> Status: living contract. See also [`agent_sdk.md`](agent_sdk.md) and
> [`agent-runtime.md`](agent-runtime.md).

This document formalizes how requests flow through LeAgent's execution stack,
which subsystems own state, and the canonical entry paths every caller should use.

## Layer Model

```
Ingress (HTTP/SSE/WS/Task/Cron)
        │
        ▼
Facade (ServiceManager.runtime_context, AgentRuntime, WorkflowService)
        │
        ▼
Kernel (run_loop → QueryEngine → query → ToolExecutor)
        │
        ▼
Durable state (SessionState, CheckpointStore, WorkflowStateStore)
        │
        ▼
Observability (EventManager, OTel)
```

## Canonical Agent Path

All agent turns **must** flow through `leagent.sdk.kernel.loop.run_loop`, either
directly or via `AgentRuntime.stream()` / `AgentController._run_via_query_engine()`.

| Caller | Entry | Kernel |
|--------|-------|--------|
| Chat SSE | `AgentController.run_stream` | `run_loop` |
| SDK | `AgentRuntime.stream` | `run_loop` |
| Background task | `AgentTaskHandler.spawn` | `AgentRuntime.stream` → `run_loop` |
| Sub-agent | `subagent._run_engine` | `run_loop` |
| Workflow agent node | `agent_exec.run_agent_node` | `AgentRuntime.stream` → `run_loop` |

Direct `QueryEngine.submit_message()` is reserved for tests and kernel internals.

## Runtime Wiring

Use `ServiceManager.runtime_context` (lazy singleton) as the single factory for:

- `ToolRegistry` / `ToolExecutor`
- `HookManager` + default hooks
- `CheckpointStore` (SQL when DB present)
- `SessionManager`, `AgentMemory`, `LLMService`

`build_agent_controller()` and workflow bootstrap consume this bundle.

## Workflow Orchestration Models

| Model | Schema | Executor | When to use |
|-------|--------|----------|-------------|
| **DAG engine** | `WorkflowDocument` | `WorkflowExecutor` | Saved flows, cron, agent `workflow_run`, agent nodes |
| **Chat step card** | `ChatWorkflowSpec` → compiled linear flow | `WorkflowService` scoped run | Playbook steps in chat |
| **Chat embed** | Validated Flow JSON | Preview + Flow API | Graph preview in chat |

Chat step cards compile to linear `WorkflowDocument` instances via
`leagent.chat_workflow.compile` so step execution shares the engine kernel.

## State Ownership

| State | Owner | Durable |
|-------|-------|---------|
| Chat transcript SSOT | `TieredSessionStore` (`session_state_v1`) | Yes |
| Agent turn pause | `CheckpointStore` (`agent_checkpoints`) | Yes (SQL) |
| Agent running trace | `TraceStore` (`agent_traces` / spans) | Yes (SQL) |
| Workflow run | `WorkflowStateStore` | Yes (SQL) |
| Chat step results | `Message.extensions.chat_workflow_step_runs` | Yes |
| Background task log | `TaskManager` output file | Yes |

## Pause / Resume

Unified `PauseToken` (`leagent.runtime.execution_run`) references:

- `checkpoint_id` for agent-scope pauses
- `workflow_execution_id` + `workflow_state_id` for DAG pauses
- `scope`: `chat_turn` | `workflow` | `task` | `tool_only`

Chat resume: `POST /chat/sessions/{id}/resume-checkpoint` + stream with `checkpoint_id`.
Workflow resume: `POST /workflow/prompts/{id}/resume`.

## Observability

Lifecycle events publish through `EventManager` (`FLOW_*`, `TASK_*`, `AGENT_*`):

- `EventManager.bridge_workflow_progress_event()` — workflow executor → `FLOW_*`
- `EventManager.publish_agent_lifecycle()` — chat SSE completion traces
- `EventManager.publish_flow_lifecycle()` — flow runs with `run_id` / `parent_run_id`
- `EventManager.emit_task_event()` — background task lifecycle

Workflow WebSocket and chat SSE remain transport layers; webhooks subscribe via `EventManager`.

OTel spans link via `run_id` and `parent_run_id` on `ExecutionRun`.

## Workflow Start API

Use `WorkflowService.start(trigger=...)` for all flow runs:

- HTTP `/workflow/prompts`, `/workflow/flows/{id}/run`
- Agent tool `workflow_run`
- Cron jobs
- Subworkflow nodes

Trigger metadata records `manual`, `agent`, `cron`, `chat_step`, or `subworkflow`.

## Unified Execution Plane

All ingress surfaces mint an `ExecutionRun` via `leagent.runtime.execution_factory`
and publish lifecycle signals through `EventManager` with shared correlation keys.

```
Ingress (Chat SSE / Chat step HTTP / Workflow WS / Task / GenUI / Cron)
        │
        ▼
ExecutionRun registry (run_id, parent_run_id, scope, prompt_id)
        │
        ├──► Facade (AgentRuntime, WorkflowService.run_compiled_document)
        │         │
        │         ▼
        │    Kernel (run_loop → QueryEngine → ToolExecutor)
        │
        ▼
Durable state (SessionState, CheckpointStore, WorkflowStateStore, step_runs)
        │
        ▼
Observability (EventManager FLOW_*/TASK_*/AGENT_*, OTel, WS/SSE transports)
```

### Correlation keys

| Key | Purpose |
|-----|---------|
| `run_id` | Primary execution unit identifier; set on `Event.correlation_id` |
| `parent_run_id` | Links child runs (workflow step, sub-agent, task) to parent chat turn |
| `session_id` | Chat session scope for timeline hydration |
| `prompt_id` | Workflow WebSocket subscription key (`/workflow/ws/executions/{prompt_id}`) |
| `task_id` | Background task queue identifier |

### Single run owner rule

One `ExecutionRun` is minted per chat turn in `run_agent_stream`. The `run_id`
is passed into `AgentController` via `tool_extra["run_id"]`. Child scopes
(workflow steps, sub-agents, background tasks) register with
`parent_run_id` pointing at the chat turn or task run.

### Chat-step WebSocket bridge

Chat playbook steps compile via `leagent.chat_workflow.compile` and execute through
`WorkflowService.run_compiled_document()` (not direct `_executor.execute_async`).

Each step run:

1. Creates a `WorkflowExecution` row (`flow_id=null`, `trigger_type=chat_step`)
2. Registers `ExecutionRun(scope=workflow, parent_run_id=…, prompt_id=…)`
3. Persists `prompt_id` and `run_id` in `Message.extensions.chat_workflow_step_runs`
4. Publishes progress via the same WebSocket stream as editor runs

The chat frontend subscribes to `/workflow/ws/executions/{prompt_id}` for live
node progress identical to the workflow editor overlay.

### Execution API

- `GET /chat/sessions/{id}/executions` — active/blocked in-process runs for timeline hydration (single-worker; not durable across processes)
- Chat SSE emits additive `execution_started` with `{ run_id, session_id, scope }`

### Single-process registry note

`ExecutionRunRegistry` is an in-process singleton. Multi-worker deployments require sticky sessions or a future durable run store; blocked runs are retained in-registry until resume or explicit `end_execution`.

