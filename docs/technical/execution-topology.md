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
