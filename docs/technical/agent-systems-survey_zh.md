# Agent 系统调研

> 状态：参考文档。为 `leagent/runtime/`、`leagent/sdk/` 以及 Agent 栈分层升级提供参考。

英文版：[agent-systems-survey.md](./agent-systems-survey.md)

在演进 LeAgent Agent 架构之前，我们调研了公开文档化的 Agent 运行时（harness），以识别它们共享的抽象，并决定 LeAgent 应在何处与既有模式**对齐**、在何处**有意偏离**。本文档记录该调研及其驱动的设计决策。它是描述性的，而非愿景性的：每一项「对齐」都对应分层计划中的具体阶段。

---

## 1. 参考系统

### OpenAI Codex (`codex-core`)

- 一个 Rust **核心库**（`codex-core`）在所有前端（TUI、无头 exec、App Server / IDE、CLI）之后复用。业务逻辑只写一次；UI 层很薄。
- 通信采用 **Submission Queue / Event Queue（SQ/EQ）** 模式：客户端提交操作，Agent 在工作推进时发出事件流。
- `Session` 编排器拥有 `SessionState`（历史、权限、环境）。`ThreadManager` 创建新线程或从持久化状态恢复。
- **`RolloutRecorder`** 将 `RolloutItem` 持久化到状态 DB，使会话在进程重启后仍可恢复。
- `AgentControl` 委派给带可配置上下文历史的专用子 Agent。`ToolRouter` 分发工具调用；结果进入下一次采样请求。
- App Server 协议是**双向**的：服务端可以发起请求（例如审批 / MCP elicitation），并**暂停当前轮次**，直到客户端应答。
- Token 用量按轮次跟踪并写入遥测。

### Claude Code Agent SDK

- 一个 **Agent 循环**以库的形式（Python + TypeScript）在调用方自己的进程中运行；同一循环也驱动 CLI。
- 在生命周期节点上有丰富的 **Hook 分类**：`PreToolUse`、`PostToolUse`、`UserPromptSubmit`、`Stop`、`SessionStart` / `SessionEnd`、`PreCompact`、`SubagentStart` / `SubagentStop`。Hook 可校验、阻断或变换行为。
- **子 Agent** 在**隔离的上下文窗口**中运行，仅向父 Agent 返回摘要；消息携带 `parent_tool_use_id` 用于归因。
- **会话恢复**：从 init 消息捕获 `session_id`，通过 `resume` 传回。Transcript 以 JSONL 形式存盘；持久化托管通过 **`SessionStore` 适配器**接入（参考适配器：S3、Redis、Postgres）。会话也可**分叉（fork）**。
- **部分消息流式**：启用 streaming 后，循环发出 `StreamEvent` 增量（原始 `content_block_delta` 文本 / tool-input 分块），供 UI 快速响应。
- 文档指出的弱点：**「默认无结构化遥测」**——追踪工具调用 / 推理需要外部工具。

### ComfyUI

- **图执行引擎**：用户图编译为从前到后的**拓扑排序**，按依赖顺序执行（`PromptExecutor`）。
- **声明式、即插即用插件注册**：导出 `NODE_CLASS_MAPPINGS`（以及可选的 `NODE_DISPLAY_NAME_MAPPINGS` / `WEB_DIRECTORY`）的 `custom_nodes` 包在启动时自动发现。无需修改核心代码。
- **WebSocket 事件流**驱动 UI：`execution_start`、`executing`、`progress`、`executed`。
- 节点输出**缓存**与运行时将**节点展开**为子图（通过尾递归实现循环）。

### Pi (`earendil-works/pi`)

- 极简主义 TypeScript monorepo，层次清晰：`pi-ai`（统一多 Provider LLM API）→ `pi-agent-core`（约 418 行的**事件驱动 Agent 循环** + 状态）→ `pi-coding-agent`（工具、JSONL 会话、扩展）→ `pi-tui`（终端 UI）。
- **双循环**：内层工具调用循环，外层由 **steering 消息**（运行中中断；剩余排队的工具调用以合成错误结果短路，以保持历史一致）和 **follow-up 消息**（Agent 本将停止后排队的继续执行）驱动。
- 通过 `agent.subscribe` 提供细粒度**生命周期事件**（轮次开始/结束、消息开始/更新/结束、工具执行开始/更新/结束）。
- 刻意区分 **`AgentMessage`（应用层）与 LLM `Message`（模型层）**，在边界处通过 `transformContext` / `convertToLlm` 转换。
- 可扩展的插件/扩展系统承载核心刻意省略的较重能力（子 Agent、MCP、plan mode）。

---

## 2. 共享抽象与 LeAgent 立场

| 共享抽象 | 见于 | LeAgent 对应物 | 立场 |
|---|---|---|---|
| 多 UI 复用的核心库 | Codex `codex-core`、Pi `pi-agent-core` | `leagent.sdk` + 基于 `QueryEngine` 的 `AgentRuntime` | 对齐：使 `AgentRuntime` 成为单一门面 |
| SQ/EQ + 每会话编排器 | Codex `Session` | `QueryEngine.submit_message`，由 `sdk/kernel/run_loop` 包装 | 已完成：聊天**与** runtime 均走同一循环 |
| 持久化会话 + 恢复 | Codex `RolloutRecorder`、Claude `SessionStore` | `CheckpointStore` / `RunState` + `SQLCheckpointStore` + `AgentRuntime.resume` | 已完成：经 `RuntimeContext` 接入持久化存储；暂停时 checkpoint + resume |
| 生命周期 Hook 分类 | Claude hooks | `HookManager` / `AgentHook` + `run_loop` 中单点分发 | 已完成：tool/subagent/pre_compact hooks 触发；`filter_by_names` 已实现 |
| 隔离上下文的子 Agent 返回摘要 | Codex `AgentControl`、Claude subagents | `delegate()` / `_run_subagent_core` | 已完成：子 recipe/model/memory/tool 策略贯穿传递 |
| 统一的流式事件分类 | Claude `StreamEvent`、ComfyUI WS events | `StreamChunk`（provider）→ `AgentEvent`（loop） | 已完成：移除无效的 `LLMStreamEvent` union；两个真实边界 |
| 应用/模型消息边界 | Pi `AgentMessage` vs `Message` | `SDKMessage` vs provider `StreamChunk` | 对齐：经 `ToolCallStreamAssembler` 单一边界 |
| 声明式即插即用插件注册 | ComfyUI `NODE_CLASS_MAPPINGS` | `Agent.<name>` / `Tool.<name>` 提升、`provider_plugin`、`context.plugin` | 对齐：entry-point 加载 |
| 统一多 Provider LLM API | Pi `pi-ai`、Claude/Codex providers | `LLMService` + `provider_plugin` + `HttpTransport` | 对齐：完成 transport/plugin 整合 |
| Steering / follow-up 队列 | Pi 双循环 | `awaiting_user_input` + abort 处理 | 偏离：保留 controller 中介的 ask-user；暂停时 checkpoint |
| 结构化遥测 / 每轮 Token 记账 | Codex telemetry；Claude 的缺口 | 持久化 `TraceStore` + `llm_request_logs.run_id` + 可选 OTel GenAI/OpenInference 属性 | 已完成：见 [`agent-trace_zh.md`](./agent-trace_zh.md) |

### 有意偏离

- **循环内无 steering 队列。** Pi 用 steering 消息中断正在运行的工具批次。LeAgent 保持**由 controller 中介**的交互：循环到达 `awaiting_user_input` / abort，由 `AgentController`（或 SDK 调用方）决定下一步。这使轮次循环保持单线程、持久化模型简单，代价是无法在工具执行中途打断。我们通过在 `awaiting_user_input` 时 checkpoint（Codex 式轮次暂停）补偿，使暂停的轮次可恢复。
- **进程内子 Agent，而非独立 harness 进程。** Claude/Codex 可 spawn 隔离进程；LeAgent 在进程内 fork 子引擎（`fork`/`_run_subagent_core`），使用 scoped tool registry。更轻量且共享服务；沙箱化委托给 `code`/`project` 层。
- **Python entry-points 而非 `custom_nodes` 目录扫描。** ComfyUI 扫描文件夹；LeAgent 偏好 `importlib.metadata` entry-point 组（`leagent.workflow.nodes`，以及新的 `leagent.llm_providers`、`leagent.context_sources`），使第三方包注册时无需触碰「魔法目录」。

---

## 3. 流入分层计划的决策

1. **一条执行路径。** `AgentRef -> AgentRuntime -> sdk/kernel/run_loop -> QueryEngine -> query()`。对应 Codex 的单一 `codex-core` 与 Pi 的单一 `pi-agent-core`。（阶段 3–4。）
2. **一套事件分类。** 端到端规范 `AgentEvent`；provider `StreamChunk` 在单一边界处折叠。对应 Claude `StreamEvent`。（阶段 1、4。）
3. **可持久化、可恢复的会话。** 在可插拔存储（当前内存；后续 DB/Redis）之后接入 `CheckpointStore` / `RunState`。对应 Codex `RolloutRecorder` 与 Claude `SessionStore`。（阶段 3。）
4. **即插即用扩展性。** 为 provider 与 context source 提供 entry-point 加载器，与现有 workflow 节点加载器一致。对应 ComfyUI 注册体验。（阶段 1–2。）
5. **可观测性作为一等支柱。** 带关联 ID 与可选 OTel 导出的单一结构化日志管道——弥补 Claude 文档指出的默认缺口，并匹配 Codex 的每轮遥测。（Logging 轨道。）
