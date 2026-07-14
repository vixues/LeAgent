# 05｜状态所有权：会话、检查点、记忆与工作流

## 定位、难度与先修

- **定位**：分清 Agent 系统里最常被混为一谈的四类状态。
- **难度**：★★★☆☆
- **先修**：[03](03-one-kernel-many-ingresses.md)、[04](04-agent-event-stream.md)

## 学习目标

1. 用「所有者 / 生命周期 / 用途」三列对比 transcript、checkpoint、memory、workflow state。
2. 解释「继续聊天」与「从 pause 点恢复同一 turn」为何不同。
3. 知道 TraceStore 属于可观测平面，不是对话 SSOT。
4. 在排障时判断该查哪张表 / 哪个 store。

## 核心心智模型：一类状态，一个所有者

把所有东西塞进 `messages` 数组，短期省事，长期必乱：压缩策略会误删检查点、记忆写入会污染 transcript、工作流暂停无法独立恢复。

LeAgent 的契约（见执行拓扑）是：

| 状态 | 所有者 | 持久化 | 主要用途 |
|------|--------|--------|----------|
| 聊天 transcript SSOT | `TieredSessionStore`（`session_state_v1`） | 是 | 跨 turn 用户可见历史 |
| Agent turn 暂停 | `CheckpointStore`（`agent_checkpoints`） | 是（有 DB 时 SQL） | 同 turn 暂停/恢复 |
| 认知记忆 | `AgentMemory`（episodic / semantic / procedural） | 可选向量 + SQL | 跨会话召回 |
| 工作流运行 | `WorkflowStateStore` | 是 | DAG 节点进度与边状态 |
| 运行追踪 | `TraceStore` | 是 | 评测 / 排障，非产品聊天 UI |

「每一类状态只有一个 durable owner」——避免双重写入与漂移。

## LeAgent 的真实实现

- **Session**：`backend/leagent/services/session/manager.py`、`store.py`。L1 LRU + DB blob；messages 表是 UI 投影。`SessionManager.locked()` 保证同会话串行写入。
- **Checkpoint**：`backend/leagent/sdk/kernel/checkpoint.py`。`run_loop` 在 `RESUMABLE_CHECKPOINT_REASONS`（如 `awaiting_user_input`、`max_turns`、`aborted`）下保存 `RunState.messages` 快照。无 DB 时退回 `InMemoryCheckpointStore`。
- **Memory**：`backend/leagent/memory/agent_memory.py`。`record_*` / `recall` / `observe_turn`——**不是** transcript 的别名。
- **Workflow**：`WorkflowExecutor` + `WorkflowStateStore`；Agent 节点还可额外带 `checkpoint_id` 输出（见 `AGENT_OUTPUT_NAMES`）。
- **Trace**：`backend/leagent/telemetry/trace/`——与 resume 平面分离。

统一暂停令牌 `PauseToken`（`backend/leagent/runtime/execution_run.py`）可携带 `checkpoint_id` 或 workflow 恢复坐标，以及 `scope`：`chat_turn` | `workflow` | `task` | `tool_only`。

## 分步对照：三种「记住」

```text
用户说「继续」：
  A. 普通多轮 → 读 Session transcript → 新开一轮 run_loop
  B. 刚 ask_user 暂停 → 用 checkpoint_id resume → 在同 turn 状态上继续
  C. 「上周我们怎么做的」→ recall / conversation_history 工具 → 注入上下文
```

误用例子：

- 把 checkpoint 当长期记忆 → 进程清理后或完成态后信息丢失或噪音过大。
- 把 memory fact 当聊天消息插入 → UI 与压缩逻辑失控。
- 把 workflow 进度写进 session extensions 却不更新 WorkflowStateStore → 编辑器与 resume API 不一致。

## 验证命令

```bash
cd backend
uv run pytest tests/test_session_manager.py tests/test_kernel_checkpoint.py tests/test_agent_memory.py -v
```

可选：`tests/test_chat_checkpoint_resume.py`、`tests/workflow/test_executor_resume.py`。

## 常见误区

1. **「有 messages 就不需要别的 store」**：多轮历史、turn 暂停、长期知识生命周期不同。
2. **「CLI 也有完整 memory」**：多数 CLI 路径未注入 `AgentMemory`。
3. **「Trace 可以代替 transcript」**：Trace 可截断 payload 且面向调试，不是聊天 SSOT。
4. **「completed 默认存 checkpoint」**：默认只对可恢复 reason 存盘；除非显式 `checkpoint_on_complete`。

## 业内对照

- LangGraph：checkpointer 类似 turn/图中断恢复；store 跨会话记忆类似 semantic/episodic。
- Google ADK：Session/State（短期）vs MemoryService（长期）——命名不同，分层同构。
- Anthropic：compaction + memory tool——对应「压缩历史」与「外置长期笔记」，不是把一切塞进 context。

## 数据流：一次「继续」到达哪类 store

```text
用户点「继续」
  ├─ 普通多轮闲聊 → 读 TieredSessionStore transcript → 新 turn 的 run_loop
  ├─ ask_user / 审批暂停 → CheckpointStore.load(checkpoint_id) → resume
  ├─ 「上周我们怎么做」→ AgentMemory.recall 或 conversation_history 工具
  └─ 工作流停在人工节点 → WorkflowStateStore + workflow resume API
```

排障时先问所属平面，再打开对应表或 API：`session_state_v1` / `agent_checkpoints` / memory 集合 / workflow execution。把 TraceStore 里的截断 payload 当聊天原文，是最常见的误诊。相邻篇 [25](25-session-identity.md)–[30](30-checkpoint-pause-resume.md)、[31](31-memory-boundaries.md)–[33](33-memory-formation.md)、[41](41-agent-nodes-and-dag.md)–[42](42-human-in-the-loop-workflows.md) 分别深挖各平面。

### 写入冲突与双重真相

- Session 必须 `locked()` 串行；同会话并行发送会导致交错轮次。  
- Checkpoint 默认只在可恢复 reason 落盘；不要假设 completed 总能 resume。  
- Memory 写入失败不应掀翻 SSE；formation `never raises`。  
- Workflow 进度若只写在 chat message extensions，编辑器 resume 会对不上。

### 路径速查

- Session：`services/session/manager.py`、`store.py`  
- Checkpoint：`sdk/kernel/checkpoint.py`、`RESUMABLE_CHECKPOINT_REASONS`  
- Memory：`memory/agent_memory.py`  
- PauseToken：`runtime/execution_run.py`  
- 权威表：`docs/technical/execution-topology_zh.md`

## 总结与延伸阅读

排障第一问：「这是哪一类状态？所有者是谁？」答对了，就很少在错误的 API 上浪费时间。

- [25｜Session Identity](25-session-identity.md)
- [30｜Checkpoint 暂停与恢复](30-checkpoint-pause-resume.md)
- [31｜记忆边界](31-memory-boundaries.md)
- [执行拓扑 · 状态所有权](../../technical/execution-topology_zh.md)
