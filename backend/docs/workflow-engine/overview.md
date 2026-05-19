# Workflow engine — overview

The `leagent` backend ships a single, canonical workflow engine under the
`/api/v1/workflow/*` namespace. There is no longer a legacy `/api/v1/flows`
namespace; all CRUD, execution, and admin endpoints are served by the
workflow engine router.

Key properties:

- **Single canonical schema.** Every `Flow.data` row in the database, every
  built-in template, every YAML template, and every starter project is
  stored as the canonical workflow document shape described in
  [`io-reference.md`](io-reference.md). There is no runtime migration —
  use [`scripts/workflow/migrate_flows.py`](../../scripts/workflow/README.md)
  to convert historical rows once per environment.
- **Hybrid scheduler.** The engine blends classic control-flow primitives
  (`next`, `conditions`, `human_review`, `parallel`) with a data-flow
  scheduler (`DynamicPrompt`, `TopologicalSort`, `ExecutionList`), yielding
  the developer ergonomics of a DAG while still supporting long-running
  waits and branch-based business logic.
- **WebSocket-first progress.** Execution events flow through
  `ExecutionEventBus` → `/workflow/ws/executions/{prompt_id}` (per-prompt)
  or `/workflow/ws/executions` (fan-in monitor) so the UI can render
  real-time progress without polling.
- **Queue-backed.** Runs are queued through `PromptQueue` (in-memory or
  Redis Streams) and processed by one or more `WorkflowWorker` processes.
  See [`architecture.md`](architecture.md) for topology diagrams and
  [`operations.md`](operations.md) for deployment recipes.

## Quick links

- [Architecture](architecture.md) — package layout and runtime topology.
- [Node authoring](node-authoring.md) — build custom nodes with typed IO.
- [IO reference](io-reference.md) — the canonical document shape and types.
- [API reference](api-reference.md) — REST + WebSocket endpoints.
- [Operations](operations.md) — migrations, workers, and monitoring.
- [Demo flows + Cron](demo-flows-and-cron.md) — bundled public-API samples and scheduling.
