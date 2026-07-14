# 30. Checkpoint 暂停与恢复

## 定位与先修

当 Agent 调用 `ask_user`、触发工具审批，或因 `max_turns`、中止、预算耗尽等原因停下时，系统需要**从同一次执行的位置继续**，而不是让用户从头把故事再讲一遍。LeAgent 用 `Checkpoint` 与 `CheckpointStore` 表达这种可恢复点。先修：[25](25-session-identity.md)、[27](27-message-lifecycle.md)。代码：`backend/leagent/sdk/kernel/checkpoint.py`、`loop.py`，以及 `AgentRuntime.resume`（`backend/leagent/runtime/runtime.py`）。

开始前再次背诵边界——做错身份键比写错摘要更常见：

| 平面 | 用途 | 标识 |
|------|------|------|
| transcript | 可持续聊天 | `session_id` |
| checkpoint | 可恢复 run | `checkpoint_id` |
| 长期 memory | 跨会话认知 | user / workspace 等键 |

普通多轮闲聊只靠 session；“问完用户再继续工具”靠 checkpoint；“记住我喜欢简洁回答”靠 memory。

## 学习目标

列出哪些结束 `reason` 会落盘可恢复 checkpoint；说明 `InMemoryCheckpointStore` 与 `SQLCheckpointStore`（表 `agent_checkpoints`）的差异与多 worker 含义；会用 SDK `resume(checkpoint_id, prompt)`；理解事件里的 `checkpoint_id` / `pause_token` 如何连到聊天 resume API；避免用 session_id 或 memory 冒充恢复。

## 心智模型：暂停是 run 的分支点

```text
run_loop 收到 RESULT
  reason ∈ RESUMABLE_CHECKPOINT_REASONS？
    （awaiting_user_input、max_turns、token_budget_exceeded、
      prompt_too_long、aborted*、blocking_limit、model_error …）
      → _snapshot_messages(engine.mutable_messages)
      → create_checkpoint(...)
      → checkpoint_store.save
      → event.data["checkpoint_id"]
      → 可选 ExecutionRun.pause → pause_token
  正常 completed（默认）
      → 不强制写 checkpoint（除非 checkpoint_on_complete）
```

恢复路径：

```text
store.load(checkpoint_id)
  → build_engine(initial_messages=checkpoint.messages)
  → 再进入 stream / run_loop，prompt = 用户答复或续跑指令
```

快照必须包含当时的消息工作集；早期若只存元数据、消息为空，resume 会名存实亡。当前 `run_loop` 在 RESULT 时主动 snapshot，正是为了堵住这个坑。

## 真实实现

`create_checkpoint` 生成 hex `checkpoint_id`，附带 `session_id`、`agent_name`、`turn`、`reason`、`messages`、`usage`、`metadata`。有数据库时 `build_checkpoint_store` 返回 `SQLCheckpointStore`，经 repository upsert；无 DB 时 runtime 回退内存实现——**重启即丢**，只适合单进程与测试。

`AgentRuntime.resume` 校验 checkpoint 存在，解析其中的 `session_id`，用 `initial_messages` 重建 engine，再驱动新一轮流式事件。聊天侧还有 `POST .../resume-checkpoint`；工作流暂停则使用 workflow execution / state id，**不要把两套 pause 混为一谈**（见执行拓扑文档）。

审批场景下，`ToolExecutor.approval_requirement` 先让 UI 出示 Allow/Deny；用户允许后应携带同一 `checkpoint_id` 恢复，而不是新开 session 让模型“回忆刚才想干什么”。

## 示例：SDK 恢复

```python
async for event in runtime.resume(
    "default_agent",
    checkpoint_id,
    "用户选择：允许发送邮件",
    user_id=uid,
):
    data = event.data or {}
    if "checkpoint_id" in data:
        print("paused again", data["checkpoint_id"])
```

恢复时务必继续传递正确的 `user_id`，否则后续只读跨会话工具与权限检查会漂移到错误属主。

## 验证命令

```bash
cd backend
uv run pytest tests/test_kernel_checkpoint.py tests/test_chat_checkpoint_resume.py -q
```

断言建议覆盖：save/load 后 messages 非空；resume 能消费用户答复；同一 session 可存在多个历史 checkpoint；内存 store 与 SQL store 行为差异符合预期。

## 常见误区

1. **用 session_id 当 checkpoint_id。** 一条聊天可暂停多次。
2. **以为 completed 也总有 checkpoint。** 默认没有。
3. **多 worker 依赖 InMemoryCheckpointStore。** 必须 durable SQL（或等价存储）。
4. **resume 丢掉 user_id。** 权限与跨工具上下文错位。
5. **把 memory recall 当 resume。** 偏好召回 ≠ 恢复工具中途状态。
6. **工作流 pause 与 agent checkpoint 混用 API。** 状态 owner 不同。

## 业内对照

LangGraph checkpointer、Claude / Codex 可恢复 rollout、部分 Assistants run 状态，都在表达执行可挂起。LeAgent 将其收拢进 SDK kernel，并与 `ExecutionRun` 的 pause token 关联，让 SSE/UI 能展示统一的 Continue 体验，同时保持 transcript 与 checkpoint 分表分责。

## 产品与运维清单

上线暂停恢复能力前，确认以下几项。第一，生产环境是否使用 durable 的 `SQLCheckpointStore`，而不是误用内存默认值。第二，前端是否在 `awaiting_user_input` 或审批卡片上保存并回传 `checkpoint_id`，而不是只回传 `session_id`。第三，resume 请求是否继续携带鉴权得到的 `user_id`。第四，超时与用户取消是否落入可恢复原因集合，产品文案是否区分“继续未完成任务”与“开新话题”。第五，工作流暂停入口是否与 agent checkpoint 入口分开，避免运维手册写混。第六，定期清理过期 checkpoint 的策略是否存在，以免表无限增长。把这份清单并入发布检查后，暂停恢复才会从演示功能变成可靠能力。

## 总结

Checkpoint 让 **run** 可暂停；Session 让 **对话** 可延续；Memory 让 **认知** 可跨会话。实现暂停恢复时做到三点即可抓住主线：快照完整消息、选择 durable 存储、按 `checkpoint_id` 重建 engine 并带着正确身份继续。其它都是入口适配。只要身份键分得清，用户就不会再经历“点了继续却像重开一局”的错觉。
