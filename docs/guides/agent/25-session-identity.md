# 25. Session Identity：先把“谁在和谁对话”说清楚

> 本篇目标：理解 LeAgent 中 `session_id`、`user_id`、`agent_name`、`run_id` 的职责边界，并能为 HTTP、SDK、IM 通道设计稳定的会话身份。核心原则是：**session 标识一条可持续的对话线程，run 标识一次执行，user 标识数据所有者；三者不能互相替代。**

## 一、先建立三层状态地图

Agent 系统里最常见的“失忆”并不一定是模型问题，而是身份键选错了。LeAgent 至少有三类状态：

1. **transcript / session**：一条聊天线程的消息、附件、todo、用量等，主键是 `session_id`，由 `backend/leagent/services/session/` 管理。
2. **checkpoint**：某次尚未正常结束的 Agent 执行快照，主键是 `checkpoint_id`，内容含执行当时的消息、turn、usage、reason。它用于“从暂停处继续”，不是聊天列表。
3. **长期 memory**：跨轮甚至跨 session 的 episodic / semantic / procedural 记忆，由 `backend/leagent/memory/` 管理，召回时可带 `user_id`、`session_id`、`workspace_id` 过滤。

因此，“同一个用户”不等于“同一个 session”，“同一个 session”也不等于“同一次 run”。用户可以有多个聊天；一个聊天可执行很多轮；某一轮又可能因 `ask_user` 或中止产生 checkpoint。

## 二、真实实现中的身份字段

`backend/leagent/services/session/state.py` 定义的 `SessionState` 是聊天状态边界：

```python
@dataclass(slots=True)
class SessionState:
    session_id: UUID
    user_id: UUID | None = None
    workspace_id: UUID | None = None
    flow_id: UUID | None = None
    messages: list[SessionMessage] = field(default_factory=list)
```

其中 `session_id` 决定加载哪条 transcript；`user_id` 决定所有权和跨会话查询范围；`workspace_id`、`flow_id` 是可选关联。`SessionManager.get_or_create()` 只会在已有字段为空时补齐这些身份，不会把已有会话悄悄改绑到另一个用户。

SDK 的 `backend/leagent/sdk/session.py` 则提供 `AgentSession`。它把 `runtime + agent + session_id + user_id` 包装成多轮句柄，并复用同一个懒加载 engine：

```python
session = runtime.session("default_agent", session_id=sid, user_id=uid)
first = await session.turn("读取项目结构")
second = await session.turn("继续分析刚才的结果")
```

这里 `turn_count` 只是该 Python 句柄发起了多少轮，不是数据库中的权威消息数；进程重启后它会归零，但 transcript 可凭同一个 `session_id` 重新加载。

## 三、一轮请求的身份时序

```text
客户端 / 通道
  │ 提交 user_id + session_id
  ▼
AgentController.run / run_stream
  │ 创建 AgentContext(task_id)
  │ 从 SessionManager.load(session_id) 载入 transcript
  ▼
AgentRuntime.build_engine
  │ 注入 session_id / user_id / agent definition
  ▼
sdk.kernel.run_loop
  │ ExecutionRun.run_id 关联本次执行
  │ 产生 tool / assistant / result 事件
  ▼
SessionManager.locked(session_id)
  └─ 保存该聊天的新 transcript
```

`backend/leagent/runtime/execution_run.py` 中的 `ExecutionRun.run_id` 是一次执行单元的关联 ID，`parent_run_id` 用于工作流步骤、子 Agent、后台任务的父子链路。它适合日志与追踪，不适合作为聊天主键，因为下一轮会产生新的 run。

若接入微信、Slack 或自定义通道，应把稳定 peer 映射为稳定 UUID，例如：

```python
from uuid import NAMESPACE_URL, uuid5

session_id = uuid5(NAMESPACE_URL, f"my-channel:{account_id}:{peer_id}")
```

不要每条消息都 `uuid4()`；那会把连续对话切成多个 session。多人群聊还应把 channel、account、conversation/peer 一起纳入命名空间，避免不同入口碰撞。

## 四、所有权不是可选的安全装饰

持久层可以在部分内部入口缺失 `user_id` 时回退本地用户，但面向用户的数据读取不能依赖这个兜底。跨会话工具 `backend/leagent/tools/util/conversation_history.py` 会先通过 `resolve_effective_user_id()` 得到有效用户，再校验目标 session 所有权。也就是说，知道 `session_id` 不应自动获得读取权限。

建议入口层遵守以下不变量：

- 外部请求先鉴权得到 `user_id`，再接受或创建 `session_id`。
- 查询、删除、恢复前都同时校验 session 与 user 的关系。
- 工具上下文继续传递 `session_id` 和 `user_id`，不要只传一个字符串标签。
- `agent_name` 决定运行哪份 Agent 定义，不是用户身份，也不是 session 身份。

## 五、离线验证

无需连接模型或外网即可验证身份与持久化：

```bash
cd /home/yqc/Desktop/LeAgent-github/backend
uv run pytest tests/test_session_manager.py -v
uv run pytest tests/test_agent_session_tasks.py -v
```

重点观察 `test_append_roundtrip`：相同 `sid` 下 user、assistant、tool 按顺序恢复；`test_postgres_survives_lru_eviction` 实际使用 SQLite 假服务模拟“新进程、新 LRU”，证明身份落在 durable session，而非某个 engine 对象中。

还可以用纯 Python 检查确定性映射：

```bash
cd /home/yqc/Desktop/LeAgent-github/backend
uv run python -c "from uuid import NAMESPACE_URL,uuid5; a=uuid5(NAMESPACE_URL,'demo:u1'); print(a, a==uuid5(NAMESPACE_URL,'demo:u1'))"
```

结果应为同一 UUID 且 `True`。

## 六、常见误区

- **“保留 engine 就等于保留会话”**：engine 是运行对象；权威 transcript 在 `SessionManager`。
- **“user_id 可以当 session_id”**：这样一个用户只能拥有一条聊天，主题隔离、删除与并发都会出问题。
- **“run_id 能用于下一轮继续”**：run 是观测关联；普通多轮靠 session，暂停恢复靠 checkpoint。
- **“session 就是长期记忆”**：session 保存明确消息；长期 memory 是筛选、形成、召回后的独立存储。
- **“拿到 session UUID 就能读”**：仍必须执行所有权校验，尤其是跨 session 工具和 API。

## 七、业内对照

OpenAI Assistants/Threads、LangGraph `thread_id` 与 LeAgent `session_id` 的目标相近：都表示可持续对话线程。LangSmith trace、OpenTelemetry trace/run 更接近 `run_id`。LangGraph checkpoint 或 Claude/Codex 的可恢复执行记录更接近这里的 `checkpoint_id`。许多框架把 thread、checkpoint、memory 都笼统叫 “memory”，实现方便但运维时难以回答“删除聊天是否应删除用户偏好”。LeAgent 将它们分层后，生命周期与权限边界更清晰。

## 八、小结

设计身份时先问三个问题：这是“哪位用户的数据”、属于“哪条对话”、还是“哪一次执行”？答案分别落到 `user_id`、`session_id`、`run_id`；若要恢复一次未完成执行，再增加 `checkpoint_id`。只有把身份键分开，持久化、多入口、跨会话历史和长期 memory 才不会互相污染。
