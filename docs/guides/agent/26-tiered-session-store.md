# 26. Tiered Session Store：热缓存与持久化如何共同守住 transcript

> 本篇目标：读懂 LeAgent 的两层会话存储、SSOT 与 UI projection，理解锁、缓存淘汰和数据库降级的实际语义。结论先行：**`chat_sessions.session_metadata` 中的 `session_state_v1` JSON 是 durable transcript 的单一事实来源；进程内 LRU 只是读穿缓存，`messages` 表主要是 UI 查询投影。**

## 一、三类状态仍要分开

在讨论 store 前先明确边界：

- **transcript / session**：完整聊天状态，含 messages、attachments、file state、usage、prompt fingerprint、metadata、todos。
- **checkpoint**：一次可恢复 Agent run 的消息快照，写入 `agent_checkpoints`，不参与普通聊天列表加载。
- **长期 memory**：episodic / semantic / procedural 存储，按策略形成与召回，不由 `TieredSessionStore` 保存。

所以，给 session store 增加缓存不会让长期 memory 更快，也不会让暂停后的 run 自动可恢复；那是另外两个子系统的责任。

## 二、两层并不是“两份真相”

真实实现位于 `backend/leagent/services/session/store.py`：

```text
load(session_id)
  ├─ L1: 进程内 OrderedDict LRU 命中 → 返回 SessionState
  └─ L2: 数据库
       ├─ chat_sessions.session_metadata.session_state_v1 → 反序列化
       └─ 若 blob 缺失 → 从 messages 表兼容性重建

save(state)
  ├─ 写入 L1
  └─ 写入 chat_sessions.session_metadata.session_state_v1
       └─ 仅补写缺失的 tool/system projection 行
```

`_LRUCache` 最小容量会被钳制到 8，并在 `put()` 时淘汰最久未使用项。它不做跨进程同步，也不是 Redis；构造函数虽然保留 `cache` 参数，当前实现实际使用的是本地 LRU + database。部署多个 worker 时，每个 worker 都有自己的 L1，因此正确性必须来自数据库，而不能依赖缓存一致性。

## 三、为什么 JSON blob 才是 SSOT

`SessionState` 不只有消息。`backend/leagent/services/session/state.py` 中还包括附件引用、文件读取缓存、累计 token、todo 和系统提示词指纹。若仅从 `messages` 表恢复，这些字段无法完整重建。因此 store 优先读取：

```json
{
  "session_state_v1": {
    "session_id": "...",
    "messages": [],
    "attachments": [],
    "file_state": [],
    "usage": {},
    "todos": [],
    "version": 1
  }
}
```

`messages` 表仍然有价值：聊天 UI 要分页、筛选、统计，关系表比每次解析大 JSON 更合适。但它是 projection，不应反过来覆盖 SSOT。用户和 assistant 行由 `ChatService.add_message` 在 HTTP/stream 边界各写一次；`TieredSessionStore` 保存时跳过这两个 role，只为缺失的 tool/system 行补 projection，并用稳定消息 UUID 去重。这一设计避免历史上的双写重复。

对于老数据，如果 `session_state_v1` 不存在，`_rehydrate_from_messages()` 会按 `created_at, id` 排序重建 transcript，并汇总 usage。这是迁移兼容路径，不代表新写入也应以消息表为准。

## 四、SessionManager 如何提供并发边界

`backend/leagent/services/session/manager.py` 为每个 `session_id` 维护一把 `asyncio.Lock`：

```python
async with session_manager.locked(session_id) as state:
    state.append_message(SessionMessage(role="user", content="你好"))
    # 离开上下文时自动 store.save(state)
```

完整时序如下：

```text
协程 A                         协程 B
  │ lock(session X)              │ 等待同一把锁
  │ load L1/L2                   │
  │ 修改 SessionState            │
  │ finally: save L1 + DB         │
  │ unlock                        ▼
  └──────────────────────────→ load 最新状态并修改
```

这能防止**同一进程**内两个 turn 互相覆盖 transcript。它不是分布式锁：多 worker 同时写同一 session 时仍可能发生最后写入者覆盖。默认 SQLite 单 worker 正好与该模型匹配；扩展到 PostgreSQL 多 worker 时，需要 sticky session 或未来的版本号/乐观并发控制。

另一个细节是 `locked()` 的 `finally`：即使调用方抛异常，当前 state 仍会尝试保存。因此进入锁后应避免写入一半语义不完整的数据；若需要事务式多步变更，应先在局部变量准备好，再一次性替换字段。

## 五、delete 与“硬删除”不要混淆

当前 `TieredSessionStore.delete(session_id)` 只执行 `self._lru.drop(session_id)`，它是缓存失效，不是数据库硬删除。真正删除聊天、消息、文件等需要走聊天服务/API 的所有权与级联逻辑。把 cache drop 当作数据删除会导致下一次 `load()` 又从数据库恢复出来。

类似地，长期 memory 是否随聊天删除是产品策略问题；它不在这个 store 内自动处理。checkpoint 也有自己的 `CheckpointStore.delete()`。

## 六、离线验证

会话存储测试完全不需要模型：

```bash
cd /home/yqc/Desktop/LeAgent-github/backend
uv run pytest tests/test_session_manager.py -v
```

关注三组断言：

1. `test_append_roundtrip`：user / assistant / tool 与 usage 能回读。
2. `test_replace_messages_swaps_transcript`：在 manager 锁内可以原子替换 transcript。
3. `test_postgres_survives_lru_eviction`：测试名保留历史叫法，实际 fake 使用内存 SQLite；重新创建 `TieredSessionStore` 后 L1 为空，仍从数据库恢复 `"persist me"`。

还可验证附件与 session 同步：

```bash
uv run pytest tests/test_session_attachments.py tests/test_session_artifacts.py -v
```

若某路径不存在，以仓库现有测试列表为准；核心附件覆盖也在 `tests/test_session_manager.py` 的 `test_attach_files_persists_and_signs`。

## 七、常见误区

- **“两层存储意味着最终一致的两份数据库”**：L1 是可丢缓存，L2 JSON 才是 durable SSOT。
- **“messages 表就是模型看到的全部历史”**：它主要服务 UI，完整模型 transcript 以 `SessionState.messages` 为准。
- **“LRU 命中后可以不写数据库”**：写路径仍同步保存数据库；否则进程退出就丢状态。
- **“每 session 一把锁支持多 worker”**：`asyncio.Lock` 只在当前进程有效。
- **“store.delete 会永久删聊天”**：它目前只丢 LRU。
- **“session store 也保存用户长期偏好”**：长期 memory 是独立存储与生命周期。

## 八、业内对照

这种结构类似常见的 write-through/read-through cache，但比“Redis + SQL 双主”更保守：缓存从不拥有数据库没有的状态。`session_state_v1` 类似 event-sourced 系统中的聚合快照，而 `messages` 表像查询侧 projection，接近 CQRS 的读模型。不过 LeAgent 并非完整 event sourcing，因为 JSON 会被整体覆盖，消息表也不是可重放的唯一事件日志。

LangGraph 常把 thread state 和 checkpoint 统一放进 checkpointer；LeAgent 则将“聊天 SSOT”和“可恢复执行快照”拆开。代价是要维护边界，收益是 UI 历史、普通多轮与中断恢复不必共享同一生命周期。

## 九、小结

判断一条数据该放哪里，可以问：它是否描述“这条聊天现在是什么样”？若是，进入 `SessionState`，经 `SessionManager.locked()` 写入 `session_state_v1`；若只是 UI 查询字段，进入 projection；若描述未完成 run，则进入 checkpoint；若是可跨聊天复用的经验，则进入长期 memory。理解这条分界线，才能安全地加缓存、做迁移和处理删除。
