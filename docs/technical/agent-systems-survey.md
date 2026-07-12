# Agent Systems Survey

> Status: reference. Informs `leagent/runtime/`, `leagent/sdk/`, and the
> agent-stack layering upgrade.

Before evolving the LeAgent agent architecture we surveyed publicly documented
agent harnesses to identify the abstractions they share, and to decide where
LeAgent should **align** with established patterns versus **diverge**
deliberately. This document records that survey and the design decisions it
drove. It is descriptive, not aspirational: every "align" item maps to a
concrete phase in the layering plan.

---

## 1. Reference systems

### OpenAI Codex (`codex-core`)

- A Rust **core library** (`codex-core`) is reused behind every front end
  (TUI, headless exec, App Server / IDE, CLI). Business logic lives once;
  UIs are thin.
- Communication uses a **Submission Queue / Event Queue (SQ/EQ)** pattern:
  clients submit operations, the agent emits an event stream as work
  progresses.
- A `Session` orchestrator owns `SessionState` (history, permissions,
  environment). `ThreadManager` spawns new threads or resumes from persisted
  state.
- **`RolloutRecorder`** persists `RolloutItem`s to a state DB, making sessions
  durable and resumable across process restarts.
- `AgentControl` delegates to specialized sub-agents with configurable context
  history. `ToolRouter` dispatches tool calls; results feed the next sampling
  request.
- The App Server protocol is **bidirectional**: the server can initiate a
  request (e.g. an approval / MCP elicitation) and **pause the turn** until the
  client answers.
- Token usage is tracked per turn and recorded in telemetry.

### Claude Code Agent SDK

- One **agent loop** shipped as a library (Python + TypeScript) running in the
  caller's own process; the same loop powers the CLI.
- **Rich hook taxonomy** at lifecycle points: `PreToolUse`, `PostToolUse`,
  `UserPromptSubmit`, `Stop`, `SessionStart` / `SessionEnd`, `PreCompact`,
  `SubagentStart` / `SubagentStop`. Hooks validate, block, or transform
  behavior.
- **Subagents** run with an **isolated context window** and return only a
  summary to the parent; messages carry `parent_tool_use_id` for attribution.
- **Session resume**: capture `session_id` from the init message, pass it back
  via `resume`. Transcripts are JSONL on disk; durable hosting plugs in a
  **`SessionStore` adapter** (reference adapters: S3, Redis, Postgres). Sessions
  can also be **forked**.
- **Partial-message streaming**: with streaming enabled the loop emits
  `StreamEvent` deltas (raw `content_block_delta` text / tool-input chunks) for
  responsive UIs.
- Documented weakness: **"no structured telemetry by default"** — tracing tool
  calls / reasoning requires external tooling.

### ComfyUI

- A **graph execution engine**: user graphs are compiled to a front-to-back
  **topological sort** and executed in dependency order (`PromptExecutor`).
- **Declarative, drop-in plugin registration**: a `custom_nodes` package that
  exports `NODE_CLASS_MAPPINGS` (and optional `NODE_DISPLAY_NAME_MAPPINGS` /
  `WEB_DIRECTORY`) is auto-discovered at startup. No core edits required.
- **WebSocket event stream** drives the UI: `execution_start`, `executing`,
  `progress`, `executed`.
- Node-output **caching** and runtime **node expansion** into subgraphs
  (loops via tail recursion).

### Pi (`earendil-works/pi`)

- Radical-minimalist TypeScript monorepo with clean layer separation:
  `pi-ai` (unified multi-provider LLM API) -> `pi-agent-core`
  (~418-line **event-driven agent loop** + state) -> `pi-coding-agent`
  (tools, JSONL sessions, extensions) -> `pi-tui` (terminal UI).
- **Dual loop**: an inner tool-call loop plus an outer loop fed by **steering
  messages** (interrupt mid-run; remaining queued tool calls are short-circuited
  with synthetic error results to keep history consistent) and **follow-up
  messages** (queued continuations after the agent would otherwise stop).
- Fine-grained **lifecycle events** via `agent.subscribe` (turn start/end,
  message start/update/end, tool execution start/update/end).
- A deliberate **`AgentMessage` (application) vs LLM `Message` (model) boundary**
  with `transformContext` / `convertToLlm` transforms at the edge.
- An extensible plugin/extension system adds the heavier features (subagents,
  MCP, plan mode) the core deliberately omits.

---

## 2. Shared abstractions and LeAgent's stance

| Shared abstraction | Seen in | LeAgent counterpart | Stance |
|---|---|---|---|
| Reusable core library behind many UIs | Codex `codex-core`, Pi `pi-agent-core` | `leagent.sdk` + `AgentRuntime` over `QueryEngine` | Align: make `AgentRuntime` the single facade |
| SQ/EQ + per-session orchestrator | Codex `Session` | `QueryEngine.submit_message`, wrapped by `sdk/kernel/run_loop` | Done: chat **and** runtime drive through the one loop |
| Durable session persistence + resume | Codex `RolloutRecorder`, Claude `SessionStore` | `CheckpointStore` / `RunState` + `SQLCheckpointStore` + `AgentRuntime.resume` | Done: durable store wired via `RuntimeContext`; checkpoint-on-pause + resume |
| Lifecycle hook taxonomy | Claude hooks | `HookManager` / `AgentHook` + single-site dispatch in `run_loop` | Done: tool/subagent/pre_compact hooks fire; `filter_by_names` implemented |
| Isolated-context subagents returning summaries | Codex `AgentControl`, Claude subagents | `delegate()` / `_run_subagent_core` | Done: child recipe/model/memory/tool policy threaded through |
| One normalized streaming event taxonomy | Claude `StreamEvent`, ComfyUI WS events | `StreamChunk` (provider) → `AgentEvent` (loop) | Done: dead `LLMStreamEvent` union removed; two real boundaries |
| Application/model message boundary | Pi `AgentMessage` vs `Message` | `SDKMessage` vs provider `StreamChunk` | Align: single boundary via `ToolCallStreamAssembler` |
| Declarative drop-in plugin registration | ComfyUI `NODE_CLASS_MAPPINGS` | `Agent.<name>` / `Tool.<name>` lifting, `provider_plugin`, `context.plugin` | Align: entry-point loading |
| Unified multi-provider LLM API | Pi `pi-ai`, Claude/Codex providers | `LLMService` + `provider_plugin` + `HttpTransport` | Align: finish transport/plugin consolidation |
| Steering / follow-up queues | Pi dual loop | `awaiting_user_input` + abort handling | Diverge: keep controller-mediated ask-user; checkpoint on pause |
| Structured telemetry / per-turn token accounting | Codex telemetry; Claude's gap | Durable `TraceStore` + `llm_request_logs.run_id` + optional OTel GenAI/OpenInference attrs | Done: see [`agent-trace.md`](./agent-trace.md) |

### Deliberate divergences

- **No in-loop steering queue.** Pi interrupts a running tool batch with
  steering messages. LeAgent keeps interaction **controller-mediated**: the
  loop reaches `awaiting_user_input` / abort and the `AgentController` (or SDK
  caller) decides what happens next. This keeps the turn loop single-threaded
  and the persistence model simple, at the cost of mid-tool interruption.
  We compensate by checkpointing on `awaiting_user_input` (Codex-style turn
  pause) so a paused turn can be resumed.
- **Process-internal subagents, not separate harness processes.** Claude/Codex
  can spawn isolated processes; LeAgent forks an in-process child engine
  (`fork`/`_run_subagent_core`) with a scoped tool registry. Cheaper and
  shares services; sandboxing is delegated to the `code`/`project` layers.
- **Python entry-points over a `custom_nodes` directory scan.** ComfyUI scans a
  folder; LeAgent prefers `importlib.metadata` entry-point groups
  (`leagent.workflow.nodes`, and new `leagent.llm_providers`,
  `leagent.context_sources`) so third-party packages register without touching
  a magic directory.

---

## 3. Decisions that flow into the layering plan

1. **One execution path.** `AgentRef -> AgentRuntime -> sdk/kernel/run_loop ->
   QueryEngine -> query()`. Mirrors Codex's single `codex-core` and Pi's single
   `pi-agent-core`. (Phases 3-4.)
2. **One event taxonomy.** Canonical `AgentEvent` end to end; provider
   `StreamChunk` is collapsed at one boundary. Mirrors Claude `StreamEvent`.
   (Phases 1, 4.)
3. **Durable, resumable sessions.** Wire `CheckpointStore` / `RunState` behind a
   pluggable store (in-memory now; DB/Redis later). Mirrors Codex
   `RolloutRecorder` and Claude `SessionStore`. (Phase 3.)
4. **Drop-in extensibility.** Entry-point loaders for providers and context
   sources, matching the existing workflow-node loader. Mirrors ComfyUI
   registration ergonomics. (Phases 1-2.)
5. **Observability as a first-class pillar.** A single structured logging
   pipeline with correlation IDs and optional OTel export — beating Claude's
   documented default gap and matching Codex's per-turn telemetry. (Logging
   track.)
