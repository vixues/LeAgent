# 27. 消息生命周期：从用户输入到持久化 transcript

## 定位与先修

本文串起一轮聊天里消息如何被创建、流式露出、写入 session，以及何时与 checkpoint、长期 memory 交叉。先修：[25. Session Identity](25-session-identity.md)、[26. Tiered Session Store](26-tiered-session-store.md)。开始任何实现或排障前，请先钉死三分法——这也是本教程系列反复强调的不变量：

| 概念 | 存什么 | 主键 | 典型问题 |
|------|--------|------|----------|
| **session transcript** | 完整对话线程（SSOT） | `session_id` | “我上周说过什么？” |
| **checkpoint** | 某次可恢复执行快照 | `checkpoint_id` | “从提问处继续跑” |
| **长期 memory** | 筛选后的认知条目 | user / workspace 等 | “我偏好中文吗？” |

删聊天不等于删偏好事实；恢复 pause 也不等于重放聊天开场白。把三者塞进同一个 `messages` 数组，短期省事，长期无法回答权限与生命周期问题。

## 学习目标

画出一轮 turn 的角色序列；说明 `SessionManager.locked` 与 `ChatService.add_message` 的分工；理解 SSE/SDK 事件如何最终沉淀为 `SessionMessage`；知道 compaction 改写的是模型工作集视图（见 [28](28-history-compaction.md)），产品层的“用户可见历史”不应与之混淆；并能在排障时判断丢的是事件、blob 还是投影表。

## 心智模型：事件流瞬态，transcript 持久，checkpoint 与 memory 是旁路

```text
入口（HTTP/SSE · SDK · IM）
  → 鉴权得到 user_id，绑定稳定 session_id
  → SessionManager.load → 既有 transcript
  → run_loop → QueryEngine.submit_message
       ├─ 瞬态：assistant deltas / tool_use / tool_result 事件
       ├─ 工作集：engine.mutable_messages
       └─ 结束 reason：completed | awaiting_user_input | ...
  → SessionManager.locked：追加并保存 session_state_v1（SSOT）
  →（可恢复 reason）CheckpointStore.save —— 另一生命周期
  →（turn 观察后）AgentMemory.observe_turn —— 再另一生命周期
```

`messages` 表多是 UI 投影；权威状态在 `chat_sessions.session_metadata.session_state_v1`（详见第 26 篇）。双写用户/助手行时，store 会特意避免把投影反客为主覆盖 SSOT。

## 真实实现线索

- `SessionState.append_message` / `replace_messages`：`services/session/state.py`
- 热 LRU + durable blob：`services/session/store.py`
- 结束时快照：`sdk/kernel/loop.py` 在 `RESULT` 上调用 `_snapshot_messages`
- HTTP 边界的用户/助手投影：`services/chat/service.py` 的 `add_message`

典型序列：`user` → 可能多轮 `assistant(tool_calls)` → `tool` → 最终 `assistant`。工具失败也通常应留下 tool 消息，否则下一轮缺少配对，压缩与续跑都会出错。暂停时 transcript 可能已有部分痕迹，同时 `agent_checkpoints` 保存可恢复工作集；用户“继续”应走 resume，而不是新开 session 让模型猜前文。

跨入口（微信 / Slack / CLI）必须映射到稳定 `session_id`，否则生命周期被切断，表现像“失忆”，根因却是身份键。

## 示例：锁定保存

```python
async with session_manager.locked(session_id) as state:
    state.append_message(SessionMessage(role="user", content="总结上周进度"))
    # 离开上下文：store.save → session_state_v1
```

同进程两轮并发写同一 session 时，`locked` 提供串行化；多 worker 仍需 sticky session 或未来的版本控制，否则最后写入者获胜。

## 验证命令

```bash
cd backend
uv run pytest tests/test_session_manager.py -q
uv run pytest tests/test_chat_checkpoint_resume.py -q
```

观察：相同 `session_id` 多轮后顺序稳定；pause 后出现 `checkpoint_id` 但聊天主键仍是 session；重建进程后（SQLite durable）transcript 仍在，而内存 checkpoint 可能已丢——这正好说明两者生命周期不同。

## 常见误区

1. **把 SSE 事件日志当 SSOT。** 事件可丢、可重放不全；transcript 才是聊天真相。
2. **混淆 checkpoint 与 transcript。** 前者服务 resume，后者服务“聊过什么”。
3. **混淆 memory 与消息。** Episode 摘要不会自动替代完整 tool trace。
4. **无锁并发写同一 session。** 同进程靠 `locked`；跨进程另议。
5. **工具错误不落库。** 破坏 tool_call / tool_result 配对。
6. **每条消息新建 session_id。** 连续对话被切碎，跨会话工具也失去意义。

## 业内对照

OpenAI Threads、LangGraph thread state、Claude 本地会话文件都在解决“瞬态流 → 持久序列”。很多框架把 thread、checkpoint、memory 笼统叫 memory，运维时难以回答“删除聊天是否删除偏好”。LeAgent 刻意分 owner：`TieredSessionStore`、`CheckpointStore`、`AgentMemory`（以及工作流 state）各管一段，代价是集成方要学会选对人。

## 排障叙事模板

当用户反馈“消息丢了”或“刷新后内容不一致”时，建议按叙事模板收集证据，而不是先改模型提示词。第一，确认请求携带的 `user_id` 与 `session_id` 是否稳定，通道映射是否每条消息都换了新 UUID。第二，查看 `session_state_v1` 是否包含该轮 user/assistant/tool 序列，必要时对照 messages 投影表是否只缺 tool 行。第三，若该轮曾暂停，检查是否存在 `checkpoint_id`，用户点继续时是否走了 resume 而不是新 turn。第四，若模型表现出遗忘，区分是 compaction 摘要、召回未命中，还是根本没写入 transcript。第五，多 worker 场景确认是否发生跨进程无锁覆盖。按这个顺序写出复现报告，通常能把“模型不行”改写成可修复的状态问题。

## 总结

消息生命周期主线是：**鉴权身份 → 加载 transcript → 内核事件 → 锁定写入 SSOT**。Checkpoint 与长期 memory 是旁路，服务恢复与认知，而不是替代聊天记录。排障时先问：丢的是流、blob、投影，还是一开始就写错了 `session_id`？把这个问题答对，再谈模型好不好用。
