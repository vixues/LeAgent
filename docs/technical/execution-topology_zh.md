# LeAgent 执行拓扑

> 状态：活契约。另见 [`agent_sdk_zh.md`](agent_sdk_zh.md) 与
> [`agent-runtime_zh.md`](agent-runtime_zh.md)。

本文档形式化请求如何流经 LeAgent 的执行栈、哪些子系统拥有状态，以及每个调用方应使用的规范入口路径。

英文版：[execution-topology.md](./execution-topology.md)

## 分层模型

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

## 规范 Agent 路径

所有 Agent 轮次**必须**流经 `leagent.sdk.kernel.loop.run_loop`，要么直接调用，要么经由 `AgentRuntime.stream()` / `AgentController._run_via_query_engine()`。

| 调用方 | 入口 | 内核 |
|--------|------|------|
| Chat SSE | `AgentController.run_stream` | `run_loop` |
| SDK | `AgentRuntime.stream` | `run_loop` |
| 后台任务 | `AgentTaskHandler.spawn` | `AgentRuntime.stream` → `run_loop` |
| 子 Agent | `subagent._run_engine` | `run_loop` |
| 工作流 Agent 节点 | `agent_exec.run_agent_node` | `AgentRuntime.stream` → `run_loop` |

直接调用 `QueryEngine.submit_message()` 仅保留给测试与内核内部。

## 运行时接线

使用 `ServiceManager.runtime_context`（懒单例）作为以下内容的唯一工厂：

- `ToolRegistry` / `ToolExecutor`
- `HookManager` + 默认 hooks
- `CheckpointStore`（存在 DB 时用 SQL）
- `SessionManager`、`AgentMemory`、`LLMService`

`build_agent_controller()` 与工作流 bootstrap 消费该服务束。

## 工作流编排模型

| 模型 | Schema | 执行器 | 何时使用 |
|------|--------|--------|----------|
| **DAG 引擎** | `WorkflowDocument` | `WorkflowExecutor` | 已保存流程、cron、Agent `workflow_run`、Agent 节点 |
| **聊天步骤卡** | `ChatWorkflowSpec` → 编译后的线性流程 | `WorkflowService` 作用域运行 | 聊天中的 playbook 步骤 |
| **聊天嵌入** | 已校验的 Flow JSON | Preview + Flow API | 聊天中的图预览 |

聊天步骤卡经 `leagent.chat_workflow.compile` 编译为线性 `WorkflowDocument` 实例，因此步骤执行共享引擎内核。

## 状态所有权

| 状态 | 所有者 | 持久化 |
|------|--------|--------|
| 聊天 transcript SSOT | `TieredSessionStore`（`session_state_v1`） | 是 |
| Agent 轮次暂停 | `CheckpointStore`（`agent_checkpoints`） | 是（SQL） |
| Agent 运行追踪 | `TraceStore`（`agent_traces` / spans） | 是（SQL） |
| 工作流运行 | `WorkflowStateStore` | 是（SQL） |
| 聊天步骤结果 | `Message.extensions.chat_workflow_step_runs` | 是 |
| 后台任务日志 | `TaskManager` 输出文件 | 是 |

## 暂停 / 恢复

统一的 `PauseToken`（`leagent.runtime.execution_run`）引用：

- Agent 作用域暂停的 `checkpoint_id`
- DAG 暂停的 `workflow_execution_id` + `workflow_state_id`
- `scope`：`chat_turn` | `workflow` | `task` | `tool_only`

聊天恢复：`POST /chat/sessions/{id}/resume-checkpoint` + 带 `checkpoint_id` 的流。
工作流恢复：`POST /workflow/prompts/{id}/resume`。

## 可观测性

生命周期事件通过 `EventManager`（`FLOW_*`、`TASK_*`、`AGENT_*`）发布：

- `EventManager.bridge_workflow_progress_event()` — 工作流执行器 → `FLOW_*`
- `EventManager.publish_agent_lifecycle()` — 聊天 SSE 完成追踪
- `EventManager.publish_flow_lifecycle()` — 带 `run_id` / `parent_run_id` 的 flow 运行
- `EventManager.emit_task_event()` — 后台任务生命周期

工作流 WebSocket 与聊天 SSE 仍是传输层；webhook 通过 `EventManager` 订阅。

OTel spans 通过 `ExecutionRun` 上的 `run_id` 与 `parent_run_id` 关联。

## 工作流启动 API

所有 flow 运行使用 `WorkflowService.start(trigger=...)`：

- HTTP `/workflow/prompts`、`/workflow/flows/{id}/run`
- Agent 工具 `workflow_run`
- Cron 任务
- 子工作流节点

触发元数据记录 `manual`、`agent`、`cron`、`chat_step` 或 `subworkflow`。

## 统一执行平面

所有入口表面通过 `leagent.runtime.execution_factory` 铸造一个 `ExecutionRun`，并通过共享关联键在 `EventManager` 上发布生命周期信号。

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

### 关联键

| 键 | 用途 |
|----|------|
| `run_id` | 主执行单元标识符；设置在 `Event.correlation_id` 上 |
| `parent_run_id` | 将子运行（工作流步骤、子 Agent、任务）链接到父聊天轮次 |
| `session_id` | 用于时间线水合的聊天会话作用域 |
| `prompt_id` | 工作流 WebSocket 订阅键（`/workflow/ws/executions/{prompt_id}`） |
| `task_id` | 后台任务队列标识符 |

### 单一运行所有者规则

在 `run_agent_stream` 中，每个聊天轮次铸造一个 `ExecutionRun`。`run_id`
经 `tool_extra["run_id"]` 传入 `AgentController`。子作用域（工作流步骤、子 Agent、后台任务）注册时，`parent_run_id` 指向该聊天轮次或任务运行。

### 聊天步骤 WebSocket 桥接

聊天 playbook 步骤经 `leagent.chat_workflow.compile` 编译，并通过
`WorkflowService.run_compiled_document()` 执行（不是直接 `_executor.execute_async`）。

每次步骤运行：

1. 创建 `WorkflowExecution` 行（`flow_id=null`，`trigger_type=chat_step`）
2. 注册 `ExecutionRun(scope=workflow, parent_run_id=…, prompt_id=…)`
3. 在 `Message.extensions.chat_workflow_step_runs` 中持久化 `prompt_id` 与 `run_id`
4. 通过与编辑器运行相同的 WebSocket 流发布进度

聊天前端订阅 `/workflow/ws/executions/{prompt_id}`，以获得与工作流编辑器叠加层相同的实时节点进度。

### 执行 API

- `GET /chat/sessions/{id}/executions` — 用于时间线水合的进程内活跃/阻塞运行（单 worker；不跨进程持久）
- 聊天 SSE 发出附加的 `execution_started`，携带 `{ run_id, session_id, scope }`

### 单进程注册表说明

`ExecutionRunRegistry` 是进程内单例。多 worker 部署需要粘性会话，或未来的持久化运行存储；阻塞的运行会保留在注册表中，直到恢复或显式 `end_execution`。
