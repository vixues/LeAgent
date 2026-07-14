# 03｜一套 Kernel，多个入口

## 定位、难度与先修

- **定位**：理解 LeAgent「一条 think-act 路径」如何服务聊天、SDK、任务、子 Agent 与工作流。
- **难度**：★★☆☆☆
- **先修**：[01 Agent 与 Chatbot](01-agent-vs-chatbot.md)、[02 Think-Act Loop](02-think-act-loop.md)

## 学习目标

1. 画出 Ingress → Facade → Kernel → Durable State 的四层拓扑。
2. 说出 Chat、SDK、Background Task、Sub-agent、Workflow Agent 节点各自如何到达 `run_loop`。
3. 解释为何 `AgentController` 不是第二套循环，以及为何不要在生产代码里直连 `QueryEngine.submit_message()`。
4. 理解 `ExecutionRun` 关联键在可观测性中的作用与进程内限制。

## 核心心智模型：一个内核，多种门面

初学 Agent 时常见误区是：聊天有一套循环，CLI 又有一套，工作流节点再写一套。这会很快分叉出不一致的工具权限、钩子、检查点和追踪。

LeAgent 的立场相反：

```text
Ingress（HTTP/SSE · WS · CLI · Task · Cron · Channel · Workflow）
        │
        ▼
Facade（AgentController · AgentRuntime · WorkflowService）
        │
        ▼
Kernel（run_loop → QueryEngine.submit_message → query → ToolExecutor）
        │
        ▼
Durable state + Observability
```

**Facade 可以很多，Kernel 只应有一个。** 各门面负责组装会话、鉴权、流式传输和领域参数；真正的思考—行动循环集中在 `run_loop`。

## LeAgent 的真实实现

权威契约见 [`docs/technical/execution-topology_zh.md`](../../technical/execution-topology_zh.md)。关键代码：

| 调用方 | 入口文件 | 到达 Kernel 的方式 |
|--------|----------|-------------------|
| Chat SSE | `backend/leagent/agent/controller.py` | `_run_via_query_engine` → `run_loop` |
| SDK | `backend/leagent/runtime/runtime.py` | `AgentRuntime.stream` / `run` → `run_loop` |
| 后台任务 | `backend/leagent/tasks/handlers/agent_handler.py` | `AgentRuntime` → `run_loop` |
| 子 Agent | `backend/leagent/agent/subagent.py` | `_run_engine` → `run_loop` |
| 工作流 Agent 节点 | `backend/leagent/workflow/nodes/agent_exec.py` | `stream` / `delegate` / `resume` → `run_loop` |

依赖装配单点是 `ServiceManager.runtime_context`（`backend/leagent/services/service_manager.py`）：统一提供 `ToolRegistry`、`ToolExecutor`、`HookManager`、`CheckpointStore`、`SessionManager`、`AgentMemory`、`LLMService`。聊天侧通过 `backend/leagent/api/v1/chat_deps.py` 的 `build_agent_controller()` 消费同一束服务。

`AgentController` 模块注释历史上曾提到 Plan-Execute / Hybrid；当前实现里 planner 标注为 dormant，`run` **只**走 `_run_via_query_engine`。教学与集成都以统一 QueryEngine 路径为准。

每次执行还会铸造一个 `ExecutionRun`（`backend/leagent/runtime/execution_factory.py`），携带 `run_id` / `parent_run_id` / `scope`。子作用域（子 Agent、工作流步骤）挂到父轮次，便于 trace 串联。注意：`ExecutionRunRegistry` 是**进程内**单例——多 worker 部署需要粘性会话。

## 分步理解：从 SDK 到 Chat 的同一条路

### 1. 公共 SDK（推荐集成面）

```python
from leagent.sdk import AgentRuntime

runtime = AgentRuntime.from_service_manager(service_manager)
async for event in runtime.stream("default_agent", "总结附件", session_id=sid):
    ...
```

### 2. Chat 路径多了什么

Chat 并不会另造循环。它多做的是：

- 会话加锁与消息持久化（`SessionManager`）
- SSE 序列化与前端事件适配
- turn 结束后的 episode / formation 等副作用

因此称呼它为**编排壳**比「第二套 Agent」更准确。

### 3. 什么时候可以直连 QueryEngine

拓扑文档写明：直接 `submit_message()` **仅保留给测试与内核内部**。产品集成、渠道桥、工作流节点都应经 Runtime / Controller，否则容易跳过 checkpoint、hooks 与 event 翻译。

## 验证命令

```bash
cd backend
uv run pytest tests/test_execution_topology_invariants.py tests/test_kernel_checkpoint.py tests/test_chat_sse_wire_contract.py -v
```

这些测试约束：生产入口必须走 `run_loop`、SSE 线缆形状不因内核改道而破坏。

## 常见误区

1. **「Controller 和 Runtime 是两套大脑」**：它们共用同一 kernel；差别在会话与传输。
2. **「CLI 与 Server 行为完全一致」**：CLI bootstrap 常把 `agent_memory=None`，不要假设 CLI 默认启用 recall。
3. **「多 worker 自动共享 ExecutionRun」**：注册表不跨进程，扩容需 PostgreSQL + sticky session 等运维策略。
4. **「绕过 run_loop 写个快一点的内部路径」**：会失去统一 hook、checkpoint 与追踪——短期省事，长期分叉。

## 业内对照

- Codex 用单一 `codex-core` 服务多种 UI；Claude Agent SDK 把同一循环以库形式嵌入宿主进程——与「一门面多入口、一内核」同构。
- LangGraph 用图执行器统一节点；LeAgent 的 Agent 对话路径以代码循环为内核，DAG 留给 `WorkflowExecutor`，两者共用可恢复与追踪理念但执行面不同。

## 总结与延伸阅读

「一套 Kernel，多个入口」是 LeAgent 可维护性的主轴：入口可以增殖，行为契约不能分裂。

- [04｜AgentEvent 流式事件协议](04-agent-event-stream.md)
- [05｜状态所有权](05-state-ownership.md)
- [执行拓扑](../../technical/execution-topology_zh.md)
- 源码：[`sdk/kernel/loop.py`](../../../backend/leagent/sdk/kernel/loop.py)、[`runtime/runtime.py`](../../../backend/leagent/runtime/runtime.py)
