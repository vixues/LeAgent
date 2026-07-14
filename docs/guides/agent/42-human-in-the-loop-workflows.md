# 42. Human-in-the-Loop 与可恢复工作流

## 定位与先修

本文把人工审批、提问与 Agent/DAG 暂停恢复接成可操作闭环。先修 [30 Checkpoint 暂停与恢复](30-checkpoint-pause-resume.md)、[41 Agent 节点](41-agent-nodes-and-dag.md)、[05 状态所有权](05-state-ownership.md)。难度偏高：HITL 在生产里不是「弹个确认框」，没有持久化坐标则刷新页面、换 worker 或重启进程就会丢上下文。LeAgent 用 `CheckpointStore`、`WorkflowStateStore` 与统一 `PauseToken` 把 Agent 路径、工具批准路径、工作流路径收成一张地图。

## 目标

完成后你应能：

1. 列出 Agent turn、工具 approval、工作流节点三类 pause 各自的载体与恢复 API；
2. 用 demo `config/demo-workflows/demo-agent-pause-resume.yaml` 复述端到端 pause → resume 故事；
3. 区分 `ask_user`、`needs_approval`、`HumanReviewNode`（`awaiting_review`）的触发点与 UI 语义；
4. 设计「谁在什么界面、用什么 scope 调哪个 resume 端点」；
5. 解释为何纯 prompt「请务必确认」不能代替服务端门禁，以及多 worker 下 durable store 的必要性。

## 心智模型

人是控制流上的 **合法节点**，不是失败兜底：

```text
运行 → 需要人（信息 / 批准 / 审阅）→ 持久化暂停 → UI/API 收集输入 → resume → 继续同一坐标
```

没有持久化的 `input()` 只适用于单进程 demo。产品语义要求：暂停原因可展示、恢复坐标可序列化传递、审计可回放。`PauseToken`（`runtime/execution_run.py`）记录 `scope`（`chat_turn` | `workflow` | `task` | `tool_only`）与 `checkpoint_id` 或 workflow execution 坐标，避免前端猜该调 chat resume 还是 workflow resume。

## 读写数据流

三类暂停汇合，但 owner 不同：

```text
A. Agent turn（聊天 / standalone stream）
   ask_user 或 needs_approval → TerminalReason.AWAITING_USER_INPUT
     → CheckpointStore.save(messages…)
     → result.checkpoint_id + PauseToken(scope=chat_turn)
     → POST /api/v1/chat/sessions/{id}/resume-checkpoint
        或 AgentRuntime.resume(agent, checkpoint_id, answer)

B. Tool approval（执行层）
   ToolExecutor 判定 destructive / policy → needs_approval
     → 不执行副作用，turn 暂停 AWAITING_USER_INPUT
     → 前端审批卡 → 用户允许后带同一 checkpoint 续跑

C. Workflow（DAG）
   HumanReviewNode → block_execution="awaiting_review"
     → WorkflowStatus.WAITING_HUMAN
   Agent 节点 standalone + ask_user → block_execution=awaiting_user_input
     → checkpoint_id 写入 AGENT_OUTPUT_NAMES 槽 + metadata stash
     → POST /api/v1/workflow/prompts/{prompt_id}/resume
        → state.variables["__resume__<node_id>"] = answer
        → run_agent_node → runtime.resume(...)
```

**Agent 节点双路径与 HITL。** 聊天内嵌工作流有 `agent_controller` 时走 `delegate`，暂停语义跟父 chat turn 的 checkpoint 更紧；standalone 工作流跑 Agent 节点时，`awaiting_user_input` 会 **`block_execution`** 暂停整图，并暴露 `checkpoint_id` 供 workflow resume。恢复时 **不是** 新开 `stream`，而是 `__resume__<node>` + `runtime.resume` 续跑同一 kernel turn。

**Chat workflow 同 executor。** 步进 playbook 编译为线性 `WorkflowDocument`，Agent 步骤仍走 `run_agent_node`；HITL 语义与画布 DAG 一致，不是聊天专用旁路。

**统一令牌。** 前端应优先序列化 `PauseToken` / 文档化字段（`scope`、`checkpoint_id`、`workflow_execution_id`），而不是只展示「请继续」。scope 错则 API 错——用 agent resume 字段调 workflow 端点会 load 不到状态。

## 真实实现中的边界

**可恢复 reason 集合。** 以 `sdk/kernel/loop.py` 中 `RESUMABLE_CHECKPOINT_REASONS` 为准；默认只有可恢复 reason 才写入 `CheckpointStore`。`completed` 不应期待总有 `checkpoint_id`。

**Agent 节点常量。** `AWAITING_USER_INPUT = "awaiting_user_input"` 与 `AGENT_OUTPUT_NAMES` 同在 `agent_exec.py`；暂停时六元组仍填充，`success` 在聚合层可仍为 true，但图处于 blocked。

**HumanReview vs Agent 暂停。** `HumanReviewNode` 用 `awaiting_review` → `WAITING_HUMAN`；Agent `ask_user` 用 `awaiting_user_input` → 通常 `PAUSED` 或 blocked 调度。两者都需 workflow resume，但 UI 文案与审批审计字段不同。

**工具层门禁不可被图替代。** 图上的 `HumanReviewNode` 审阅通过后，destructive 工具仍可能触发 `needs_approval`（`tools/approval.py`）——两层门禁叠加是刻意设计，不是重复建设。

**属主校验。** resume 时应校验同一 `user_id` / `session_id` / workflow execution 属主，防止「拿着别人的 checkpoint_id 续跑」。

**多 worker。** `InMemoryCheckpointStore` 与进程内 `ExecutionRunRegistry` 在换 worker 时丢失；生产应用 SQL `CheckpointStore`（`agent_checkpoints` 表）与 PostgreSQL 等 durable 路径。

**与 cron / 后台任务。** `AgentTaskHandler` 等入口走 `AgentRuntime.stream` → `run_loop`，不经过 `run_agent_node`；但 checkpoint 与 `PauseToken(scope=task)` 语义一致。若任务也需要人工输入，应同样持久化 checkpoint 并在任务 UI 暴露 resume，而不是假设「后台一定无人值守」。

**与 [47 安全控制面](47-agent-security-control-plane.md) 的关系。** 权限与审批必须在 `ToolExecutor` enforce；prompt 约束可被模型忽略。

## 示例与验证

**Demo 剧本：** 导入 `config/demo-workflows/demo-agent-pause-resume.yaml`，运行至 Agent 提问 → 确认图 blocked、`checkpoint_id` 非空 → 调用 `POST /api/v1/workflow/prompts/{prompt_id}/resume` 提交答案 → 确认 `__resume__<node>` 路径续跑完成，`output`/`plan` 变量更新。

```bash
cd backend
uv run pytest tests/test_kernel_checkpoint.py tests/test_approval_flow.py \
  tests/workflow/test_executor_resume.py tests/test_chat_checkpoint_resume.py -v
uv run pytest tests/workflow/test_agent_nodes.py -v
```

导入 demo（需运行中服务时）：

```bash
cd backend
uv run python scripts/workflow/import_demo_flows.py
```

**概念流设计（可审报销）：** DAG = 解析单据 `Agent` → 规则引擎节点 → `HumanReviewNode` → 入账工具。Review 拒绝则边回到「补充材料」`Agent`；超时策略发提醒而非静默成功；Trace 记录批准人；入账工具仍带 destructive approval。

**手工回归：** 跑到 `ask_user` → 刷新页面 → 用同一 `checkpoint_id` resume → 确认工具中段状态仍在，而不是模型「根据聊天历史猜」。

## 常见误区

1. **HITL 只弹前端模态、不写 checkpoint** — 刷新即丢，无法审计。
2. **把审批做成纯 prompt「请务必确认」** — 模型可忽略；必须 `ToolExecutor` / `needs_approval` 强制。
3. **resume 时换 session_id** — 对不上 `CheckpointStore` 与属主校验。
4. **workflow resume 与 chat resume 混用字段** — `PauseToken.scope` 决定 API；混用 load 失败。
5. **多 worker + InMemoryCheckpointStore** — 进程飘移检查点消失，必须 SQL durable。
6. **认为 HumanReview 可替代工具 approval** — 图审阅不关闭执行层 destructive 门禁。
7. **Agent 节点 resume 等于重新 stream** — 应走 `runtime.resume` 与同 `checkpoint_id`。
8. **completed 也期待 checkpoint** — 仅可恢复 reason 持久化。
9. **在聊天里嵌工作流就免 workflow resume** — 有 `agent_controller` 时暂停可能跟父 chat checkpoint 合并，但仍需正确 scope 与 API，不能混用字段。

排障顺序：`PauseToken.scope` → 对应 store 能否 load → user/session 属主 → resume 后是否重新进入 `run_loop`/`WorkflowExecutor` → 审计是否记批准人。

## 与 ADK、Anthropic、AutoGen 等方案对照

LangGraph `interrupt` + `Command(resume=...)` 在图层暂停；OpenAI 新版本强调 tool/operation approvals；Google ADK 用 callbacks 拦截敏感步骤——目标一致：**默认不可自动越过某条边界**。LeAgent 把 Agent 与 Workflow 两套暂停坐标收进 `PauseToken`，Agent 节点把 `checkpoint_id` 透出为图输出槽，并坚持执行层 `needs_approval` 而非提示词自觉。代价是应用需理解 scope 与双 API（chat vs workflow），收益是聊天、工作流、cron 可共享同一 kernel checkpoint 语义。

## 总结

可靠 HITL = 明确暂停原因 + durable 持久化 + 同一坐标恢复 + 审计可追溯。人是节点，不是旁路弹窗。Agent 路径靠 `CheckpointStore` 与 chat resume；工作流路径靠 `WorkflowStateStore`、`block_execution` 与 `POST /api/v1/workflow/prompts/{prompt_id}/resume`；工具路径靠 `needs_approval` 与同一 checkpoint 续跑。设计产品时先画清 PauseToken.scope，再选 UI 与 API，可少走一半 resume 联调弯路。延伸阅读：[30](30-checkpoint-pause-resume.md)、[41](41-agent-nodes-and-dag.md)、[47](47-agent-security-control-plane.md)；Demo：[`config/demo-workflows/demo-agent-pause-resume.yaml`](../../../config/demo-workflows/demo-agent-pause-resume.yaml)。
