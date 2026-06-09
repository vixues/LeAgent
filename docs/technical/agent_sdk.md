# LeAgent Agent SDK — Technical Reference

> **Version:** 0.1.0  
> **Package:** `leagent.sdk`

## Overview

The Agent SDK is the single, versioned public surface through which every
caller (chat API, background tasks, CLI, workflow nodes, sub-agent
delegation) interacts with the agent stack. It replaces the prior pattern
of hand-assembling `QueryEngine` + `ContextManager` + `AgentMemory` +
`ServiceManager` with a unified, protocol-driven API.

```python
from leagent.sdk import AgentRuntime, AgentBuilder

runtime = AgentRuntime.from_service_manager(service_manager)
result = await runtime.run("default_agent", "Summarise this PDF")
```

## Public API Surface

### Events & Results

| Symbol | Kind | Description |
|--------|------|-------------|
| `AgentEvent` | dataclass | Single streaming event (`{type, data}` wire shape) |
| `AgentEventType` | StrEnum | Canonical event types (`stream_delta`, `tool_use`, `result`, …) |
| `AgentResult` | dataclass | Aggregate result of a non-streaming `runtime.run()` call |

### Protocols

| Symbol | Kind | Maps to |
|--------|------|---------|
| `LLMClient` | Protocol | `leagent.llm.service.LLMService` |
| `Provider` | Protocol | `leagent.llm.base.LLMProvider` |
| `ContextAssembler` | Protocol | `leagent.context.manager.ContextManager` |
| `MemoryStore` | Protocol | `leagent.memory.agent_memory.AgentMemory` |
| `RecallProvider` | Protocol | `leagent.memory.agent_memory.RecallHandle` |
| `EpisodicStoreProtocol` | Protocol | `leagent.memory.episodic.EpisodicStore` |
| `SemanticStoreProtocol` | Protocol | `leagent.memory.semantic.SemanticStore` |
| `ProceduralStoreProtocol` | Protocol | `leagent.memory.procedural.ProceduralStore` |
| `CheckpointStore` | Protocol | Durable run persistence (`InMemoryCheckpointStore` / `SQLCheckpointStore`) |
| `RunContext` | dataclass | Replaces `ToolUseContext` + `AgentContext` duck-typing |
| `ToolContext` | dataclass | Narrow subset of `RunContext` exposed to tool impls |

### Definition & Registry

| Symbol | Kind | Description |
|--------|------|-------------|
| `AgentDefinition` | Pydantic model | Declarative agent contract |
| `AgentBuilder` | class | Fluent builder for definitions |
| `AgentRegistry` | class | In-memory definition lookup |
| `ToolPolicy` / `ModelPolicy` / `MemoryPolicy` | Pydantic model | Policy sub-objects |
| `get_agent_registry()` | function | Process-wide singleton |
| `register_builtin_agents()` | function | Seed registry with builtins |

### Session

| Symbol | Kind | Description |
|--------|------|-------------|
| `AgentSession` | class | Stateful multi-turn session handle (`turn`, `stream`, `resume`) |
| `ContextInspector` | dataclass | Read-only view of context assembly state |
| `MemoryInspector` | dataclass | Read-only view of memory state |

### Runtime

| Symbol | Kind | Description |
|--------|------|-------------|
| `AgentRuntime` | class | **The** execution facade (`run`, `stream`, `delegate`, `resume`, `session`) |
| `RuntimeContext` | dataclass | Injectable services bundle |
| `get_delegation_runtime()` | function | Process-wide runtime for sub-agent delegation |
| `load_agents_from_yaml()` | function | Load definitions from a YAML config file |

### Kernel (internal)

| Symbol | Kind | Description |
|--------|------|-------------|
| `run_loop()` | async gen | The single think-act path: `SDKMessage → AgentEvent`, snapshots `RunState.messages`, single-site hook dispatch, checkpoint-on-pause. Drives chat **and** runtime. |
| `RunState` | dataclass | Serialisable snapshot of an in-progress run |
| `InMemoryCheckpointStore` | class | Non-durable checkpoint store (default/test) |
| `SQLCheckpointStore` | class | Durable, DB-backed store (`agent_checkpoints`) for cross-process resume |
| `build_checkpoint_store()` | function | Returns the durable store when a DB is present, else `None` (in-memory fallback) |
| `create_checkpoint()` | function | Convenience factory for `Checkpoint` |

## Architecture Layers

```
┌─────────────────────────────────────────────────┐
│  leagent.sdk  (public surface, semver-versioned)│
├─────────────────────────────────────────────────┤
│  Kernel   (run loop, RunState, checkpoint)      │
├────────┬────────┬────────┬──────────────────────┤
│  LLM   │Context │Memory  │  Tool executor       │
│(pillar)│(pillar)│(pillar)│  (pillar)            │
└────────┴────────┴────────┴──────────────────────┘
```

Each pillar is accessed through a **Protocol** defined in
`leagent.sdk.protocols`. Concrete implementations live in their own
packages and are wired via `RuntimeContext`.

## Versioning

The SDK follows **semantic versioning**. The version is stored in
`leagent/sdk/_version.py` and exported as `leagent.sdk.__version__`.

- **MAJOR** — breaking changes to the public surface.
- **MINOR** — additive changes (new protocols, new event types).
- **PATCH** — bug fixes and internal improvements.

## Migration Guide

### From `leagent.runtime`

The `leagent.runtime` package continues to work as a re-export layer.
New code should import from `leagent.sdk` directly:

```python
# Before
from leagent.runtime import AgentRuntime, AgentEvent

# After
from leagent.sdk import AgentRuntime, AgentEvent
```

### From hand-assembled engines

```python
# Before (manual wiring)
from leagent.agent.query_engine import QueryEngine, QueryEngineConfig
config = QueryEngineConfig(llm=llm, tools=tools, executor=executor, ...)
engine = QueryEngine(config)
async for msg in engine.submit_message(prompt):
    ...

# After (SDK)
from leagent.sdk import AgentRuntime
runtime = AgentRuntime.from_service_manager(sm)
result = await runtime.run("default_agent", prompt)
```
