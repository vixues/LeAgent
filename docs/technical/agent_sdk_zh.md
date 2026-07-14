# LeAgent Agent SDK — 技术参考

> **版本：** 0.1.0  
> **包：** `leagent.sdk`

英文版：[agent_sdk.md](./agent_sdk.md)

## 概述

Agent SDK 是单一的、带版本的公共表面，所有调用方（聊天 API、后台任务、CLI、工作流节点、子 Agent 委派）都通过它与 Agent 栈交互。它用统一的、协议驱动的 API，取代了此前手工组装 `QueryEngine` + `ContextManager` + `AgentMemory` + `ServiceManager` 的模式。

```python
from leagent.sdk import AgentRuntime, AgentBuilder

runtime = AgentRuntime.from_service_manager(service_manager)
result = await runtime.run("default_agent", "Summarise this PDF")
```

## 公共 API 表面

### 事件与结果

| 符号 | 种类 | 说明 |
|------|------|------|
| `AgentEvent` | dataclass | 单条流式事件（`{type, data}` 线缆形态） |
| `AgentEventType` | StrEnum | 规范事件类型（`stream_delta`、`tool_use`、`result`、…） |
| `AgentResult` | dataclass | 非流式 `runtime.run()` 调用的聚合结果 |

### 协议

| 符号 | 种类 | 映射到 |
|------|------|--------|
| `LLMClient` | Protocol | `leagent.llm.service.LLMService` |
| `Provider` | Protocol | `leagent.llm.base.LLMProvider` |
| `ContextAssembler` | Protocol | `leagent.context.manager.ContextManager` |
| `MemoryStore` | Protocol | `leagent.memory.agent_memory.AgentMemory` |
| `RecallProvider` | Protocol | `leagent.memory.agent_memory.RecallHandle` |
| `EpisodicStoreProtocol` | Protocol | `leagent.memory.episodic.EpisodicStore` |
| `SemanticStoreProtocol` | Protocol | `leagent.memory.semantic.SemanticStore` |
| `ProceduralStoreProtocol` | Protocol | `leagent.memory.procedural.ProceduralStore` |
| `CheckpointStore` | Protocol | 持久化运行存储（`InMemoryCheckpointStore` / `SQLCheckpointStore`） |
| `RunContext` | dataclass | 取代 `ToolUseContext` + `AgentContext` 鸭子类型 |
| `ToolContext` | dataclass | 暴露给工具实现的 `RunContext` 窄子集 |

### 定义与注册表

| 符号 | 种类 | 说明 |
|------|------|------|
| `AgentDefinition` | Pydantic model | 声明式 Agent 契约 |
| `AgentBuilder` | class | 定义的流畅构建器 |
| `AgentRegistry` | class | 内存中的定义查找 |
| `ToolPolicy` / `ModelPolicy` / `MemoryPolicy` | Pydantic model | 策略子对象 |
| `get_agent_registry()` | function | 进程级单例 |
| `register_builtin_agents()` | function | 用内置项播种注册表 |

### 会话

| 符号 | 种类 | 说明 |
|------|------|------|
| `AgentSession` | class | 有状态多轮会话句柄（`turn`、`stream`、`resume`） |
| `ContextInspector` | dataclass | 上下文组装状态的只读视图 |
| `MemoryInspector` | dataclass | 记忆状态的只读视图 |

### 运行时

| 符号 | 种类 | 说明 |
|------|------|------|
| `AgentRuntime` | class | **唯一**执行门面（`run`、`stream`、`delegate`、`resume`、`session`） |
| `RuntimeContext` | dataclass | 可注入的服务束 |
| `get_delegation_runtime()` | function | 用于子 Agent 委派的进程级运行时 |
| `load_agents_from_yaml()` | function | 从 YAML 配置文件加载定义 |

### 内核（内部）

| 符号 | 种类 | 说明 |
|------|------|------|
| `run_loop()` | async gen | 唯一的 think-act 路径：`SDKMessage → AgentEvent`，快照 `RunState.messages`，单点 hook 分发，暂停时写 checkpoint。驱动聊天 **与** 运行时。 |
| `RunState` | dataclass | 进行中运行的可序列化快照 |
| `InMemoryCheckpointStore` | class | 非持久 checkpoint 存储（默认/测试） |
| `SQLCheckpointStore` | class | 持久化、基于 DB 的存储（`agent_checkpoints`），用于跨进程恢复 |
| `build_checkpoint_store()` | function | DB 存在时返回持久存储，否则 `None`（回退内存） |
| `create_checkpoint()` | function | `Checkpoint` 的便捷工厂 |

## 架构分层

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

每个支柱通过 `leagent.sdk.protocols` 中定义的 **Protocol** 访问。具体实现位于各自的包中，并通过 `RuntimeContext` 接线。

## 版本策略

SDK 遵循**语义化版本**。版本存放在 `leagent/sdk/_version.py`，并以 `leagent.sdk.__version__` 导出。

- **MAJOR** — 对公共表面的破坏性变更。
- **MINOR** — 加法变更（新协议、新事件类型）。
- **PATCH** — 缺陷修复与内部改进。

## 迁移指南

### 从 `leagent.runtime`

`leagent.runtime` 包继续作为再导出层工作。新代码应直接从 `leagent.sdk` 导入：

```python
# Before
from leagent.runtime import AgentRuntime, AgentEvent

# After
from leagent.sdk import AgentRuntime, AgentEvent
```

### 从手工组装的引擎

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
