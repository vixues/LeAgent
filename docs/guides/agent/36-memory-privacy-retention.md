# 36. 记忆隐私、遗忘与保留策略

## 定位与先修

本文从「能记、能召回」转向「能删、能过期、能导出」。先修 [31 记忆边界](31-memory-boundaries.md) 至 [35 预取降级](35-recall-prefetch-degradation.md)。长期记忆一旦跨会话复用，就是个人数据处理面：要分清 transcript 治理与 cognitive memory 治理，以及哪些能力在 `AgentMemory` façade / cron maintenance，哪些还没有完整 HTTP 删除曲面。

## 目标

完成后你应能回答：

1. `forget_*`、`export_*`、`delete_user_data` 各覆盖哪些 store；
2. `maintenance` 如何用 `retention_score` 做低价值遗忘、consolidation 与 importance decay；
3. 只读 agent-memory API 能看到什么、缺什么；
4. 设计产品「忘记我」开关时，应切断哪些写入与读取路径。

## 心智模型

三层治理彼此独立，**删一层不等于删全部**：

| 层 | Owner | 典型动作 |
|---|---|---|
| Transcript | `TieredSessionStore` | 删会话消息、导出聊天 |
| Cognitive memory | `AgentMemory` + SQL | 点删 episode/fact、用户级 `delete_user_data` |
| Retention jobs | `memory/maintenance.py` | 低价值遗忘、digest 提升、importance 衰减 |

```text
用户请求「忘掉我」/ GDPR erasure
        │
        ├─ 删除/匿名化 chat sessions（另一条链路）
        └─ AgentMemory.delete_user_data(user_id)
              → 枚举 episodes / facts / procedures（limit 10_000）并 delete
              → 返回各 store 删除计数
```

`retention_score(importance, recall_count, age_days, confidence?, success_rate?)` 把「旧、低 importance、少被召回」的内容打成低分，供 cron 清理与 formation 权重体系同源思想复用。

## 读写数据流

**点删。** `forget_episode(episode_id)` / `forget_fact(fact_id)` 委托对应 store 的 delete。Procedure 可通过 store 路径删除；用户级擦除统一走 `delete_user_data`。

**导出。** `export_episodes(user_id, limit≤500)`、`export_facts(user_id, limit≤500)` 支持数据可携带请求。`delete_user_data` 内部用 `limit=10_000` 枚举；超大账户需分批或运维脚本。

**维护任务（cron 设计，非每 turn 内联）。**

- `forget_low_value_episodes`：SQL 先过滤（够旧、低 importance、低 recall_count），再算 `retention_score`，低于阈值则删行。
- `consolidate_notable_episodes`：把够长、够重要的 episode summary **upsert 成 Fact**，key=`digest.episode.<uuid>`，confidence 由 importance 推导；`dedup_existing` 时跳过已有更高 confidence 的同 key。
- `decay_episode_importance`：按 `decay_rate` 下调旧 episode importance；高 `recall_count` 获得保护；`floor` 防止 importance 无意义触底。

**只读 HTTP。** `GET /api/v1/chat/sessions/{id}/agent-memory?limit=1–100` 返回 `enabled` 与三类快照：该 session 的 episodes + **owner 级** facts/procedures。校验 session owner 与项目访问令牌；memory 未启用时 `enabled=false` 与空数组。**不提供**通用 DELETE body，不替代 `delete_user_data`。

**WAL 与写入健康。** 写入失败可能 append 到 `LEAGENT_HOME/memory_failed_writes.wal`（截断 detail）；运维需纳入磁盘权限与轮转，勿把 WAL 当用户可删界面。

## 真实实现中的边界

**删 transcript ≠ 删 memory。** 关掉聊天记录后，`auto.turn.<session_id>` Fact 与 Procedure 可能仍在。产品若承诺「清除聊天即忘记偏好」，必须额外调 memory 擦除。

**Consolidation 把摘要升格为更稳 Fact。** 只删 episode、不处理 `digest.episode.*`，用户以为已忘的内容仍可能被 semantic recall 命中。对称清理要覆盖派生 key。

**向量副本。** 无 Milvus 时主要矛盾在 SQL；启用向量后，delete 路径需确认 store 是否同步删 collection 点——以当前 store 实现与测试为准，勿假设「删 SQL 行向量自动净空」而不验证。

**Formation 关闭不清理历史。** `memory.enabled=False` 或 `memory_formation=False` 减少新写入，不擦旧数据；隐私开关应同时管写与擦。

**workspace 隔离 ≠ 用户级擦除。** `delete_user_data` 按 `user_id` 枚举；错误依赖 workspace 过滤不能替代 GDPR 式用户删除。

**decay 不等于 delete。** `decay_episode_importance` 只降 importance，帮后续 `forget_low_value_episodes` 更容易命中，行仍在 until 维护任务删除。

**suppress ≠ 遗忘。** `observe_turn` 的 duplicate suppress 只阻止当次写入，不删已有行。

## 示例与验证

场景：用户要求「删除我的所有记忆」。

1. 调用 `delete_user_data(user_id)`，记录返回的 `episodes`/`facts`/`procedures` counts；
2. `export_*` 再查应为空（在 limit 内）；
3. 同 user 的 session agent-memory 快照三类数组为空；
4. 若启用 Milvus，再 `recall` 确认无命中。

Retention 演练：造低 importance、老 `created_at`、`recall_count=0` 的 episode，跑 `forget_low_value_episodes`，removed 计数应上升；高 importance 或高 recall 行应保留。Consolidation 后查 semantic 是否存在 `digest.episode.<id>`。

```bash
cd backend
uv run pytest tests/test_agent_memory.py -k "delete_user or export" -v
```

## 常见误区

- **「只读 agent-memory API 能删记忆。」** 它主要是观测与调试。
- **「衰减等于删除。」** decay 只调 importance。
- **「consolidation 与 privacy 无关。」** 它复制内容到另一 store，扩大擦除面。
- **「删 session 等于删 fact。」** facts 是 owner 级，跨 session 共享。
- **「formation suppress 就是遗忘。」** 仅阻止当次 observe 写入。
- **「export limit 500 等于全量。」** 大账户需分页或提高 limit 的运维路径。

## 与 ADK、Anthropic、AutoGen 等方案对照

GDPR/CCPA 下，云厂商 API 很少内建「Agent 记忆橡皮擦」；义务落在应用。OpenAI/Anthropic 数据保留政策主要谈训练与 API logs，与你的 Episode 表无关。Mem0、Zep 等托管记忆常提供 user-scoped delete；自托管 LeAgent 把原语留在 `AgentMemory` + `maintenance`，HTTP 治理面需产品自己补齐。LangGraph checkpoint 删除也不等于 cognitive memory 删除——再次印证 [05 状态所有权](05-state-ownership.md) 的分裂。

## 总结

隐私与保留要分三条线：聊天 transcript、三 store 点删与用户级 `delete_user_data`、基于 `retention_score` 的 maintenance（forget / consolidate / decay）。公开只读快照便于调试，不是治理全家桶；consolidation 与向量副本会放大「以为删了其实还在」的风险。设计擦除流程时务必串联 transcript + memory + `digest.episode.*` 派生 fact。下一章进入子 Agent：[37 何时使用子 Agent](37-when-to-use-subagents.md)。
