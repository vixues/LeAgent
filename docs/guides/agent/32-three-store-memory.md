# 32. Episodic、Semantic、Procedural 三类记忆

## 定位与先修

本文承接 [31 记忆边界](31-memory-boundaries.md)，进入 LeAgent 认知三存储的具体形态。适合已经能区分 transcript 与长期记忆的读者。先修建议：理解 `AgentMemory` 是 runtime 唯一入口，底层 `EpisodicStore`、`SemanticStore`、`ProceduralStore` 与 `RetrievalPipeline` 不应被 controller 或 tool 直接调用。

## 目标

完成后你应能回答：

1. Episode、Fact、Procedure 各自记住什么，以及 upsert/聚合键如何设计；
2. `AgentMemory` 四个核心方法（`record_episode`、`upsert_fact`、`record_procedure`、`recall`）与辅助治理 API 的分工；
3. 无 Milvus 时三库如何仍通过 SQL 持久化并降级 recall；
4. 为什么 `Episode.transcript` 字段存在，但自动 formation 通常只写 `summary`。

## 心智模型

认知科学里的「经历 / 事实 / 做法」三分法，在 LeAgent 里被落实为三个 durable store，经窄 façade 统一读写：

```text
TurnObservation / 显式 API 调用
        │
        ├─ record_episode  → EpisodicStore（某次 turn 的摘要）
        ├─ upsert_fact     → SemanticStore（稳定偏好与事实）
        └─ record_procedure → ProceduralStore（工具链模式与成败）
        │
        ▼
RetrievalPipeline.recall → RecallBundle → context attachment
```

| Store | 记什么 | 典型问法 | 自然键 |
|-------|--------|----------|--------|
| Episodic | 过去某次交互的截断摘要 | 「上周排查超时那次发生了什么」 | 行 id；recall 可按 user/session 过滤 |
| Semantic | 跨会话稳定的用户/工作区事实 | 「用户偏好简体中文」 | `(user_id, workspace_id, key)` |
| Procedural | 工具链签名与 run 统计 | 「清洗 CSV 再聚合成功率如何」 | `(user_id, workspace_id, signature)` |

`Procedure.signature` 由 `build_procedure_signature()` 对用户意图前 200 字与排序后的工具名做 SHA-256，因此相同意图+工具链会聚合到同一行，`run_count`/`success_count`/`success_rate` 随每次 `record_procedure` 累加。

## 读写数据流

**写路径。** Runtime 不直接构造 SQL 行，而是调用 `AgentMemory` façade。`record_episode(Episode)` 把 `summary`、`importance`、`tags` 等写入 episodic 表；`Episode.transcript` 在类型上可选，但 `observe_turn()` 自动形成时只调用 `build_episode_summary()` 填 `summary`，不复制完整 transcript。`upsert_fact(Fact)` 以 `(user_id, workspace_id, key)` 为逻辑键，同 key 覆盖 value/confidence；自动 semantic 写入使用 `auto.turn.<session_id>`，同会话后续命中会覆盖而非无限增殖。`record_procedure(Procedure, outcome, success, ...)` 按 signature 聚合，description 可含 art 管线的 quality_score 等生产反馈。

三类写入均 **never raises**：异常被吞掉并更新 `memory_write_status()`，必要时 append 到 `memory_failed_writes.wal`（best-effort），避免记忆故障击穿正常 chat turn。

**读路径。** `recall(query, user_id=..., session_id=..., workspace_id=..., limit=8, per_store_limit=4)` 委托 `RetrievalPipeline`：可选向量搜索，失败或空则 lexical；三库并行 gather → `_rerank`（recency 半衰期 14 天等）→ `_deduplicate` → `_collapse_semantic_over_episodic` → 截断到总 limit。Semantic recall **要求** `user_id`，否则 semantic 候选为空。结果经 `RecallSource` 渲染为 `<attachment kind="recall">`，单条约 300 字上限，不是无界拼进 system 全文。

**辅助 API。** `observe_turn` / `observe_feedback` 驱动自动 formation（见 [33](33-memory-formation.md)）；`forget_episode` / `forget_fact`、`export_*`、`delete_user_data` 用于治理（见 [36](36-memory-privacy-retention.md)）。

## 真实实现中的边界

**Façade 刻意收窄。** `agent_memory.py` 文档字符串明确：agent runtime 只应见四个方法 + `RecallHandle`。这防止业务代码绕过 formation、身份过滤与降级逻辑直连 store。

**Episodic 不是聊天备份。** `build_episode_summary()` 截取用户文本最多 400 字、助手最多 800 字，追加最多 32 个工具名，整体再截到 1200 字。长期 episodic 是有损视图；查原文应走 `TieredSessionStore` 或 conversation_history 工具。

**Semantic 与 Procedural 的 scope。** Fact 必须带 `user_id`；Procedure 可带 user/workspace。只读 HTTP `GET .../agent-memory` 返回该 session 的 episodes，却返回 **owner 级** 的 facts 与 procedures——调试时不要误以为 fact 属于单个 session。

**无 Milvus 不等于记忆关闭。** ServiceManager 常以 `MilvusConnectionConfig(enabled=False)` 建 store；SQL 仍是 SSOT，向量 collection 不可搜索时跳过 embed，recall 走 PostgreSQL `to_tsvector`/`plainto_tsquery` 或 SQLite 的 `ILIKE` 子串匹配。能字面命中，不具备语义近邻。

**Procedure 向量可选。** `procedure_write_status()` 中 `vector_optional=True` 时，未写 Milvus 不算硬失败；SQL 行仍持久化，lexical recall 仍可用。

**类型与 ORM 隔离。** `types.py` 中的 `Episode`、`Fact`、`Procedure` 是 runtime 可见的 flat dataclass；agent 永远不见 SQLModel 行。这保证 store 实现可换（SQLite/PG/Milvus 组合）而不污染 controller。`Procedure.success_rate` 由 `success_count/run_count` 派生，recall 重排时会读 metadata 里的同名字段。

**与 checkpoint 的分工。** Episodic 记「发生过什么摘要」，checkpoint 记「turn 执行到哪一步可 resume」。用户问「暂停前工具跑到哪」应查 checkpoint，不是 episodic recall。Workflow state 又是第三个 owner，三库不保存 DAG 节点中间态。

**observe_turn 是主要写入口。** 除测试或运维脚本外，业务不应绕过 formation 直接 bulk `record_*`；否则 importance、confidence、signature 聚合与 provenance 会不一致，后续 maintenance 的 `retention_score` 也会失真。

## 示例与验证

```python
from leagent.memory.types import Episode, Fact, Procedure

await memory.record_episode(
    Episode(session_id=sid, user_id=uid, summary="排查 Gunicorn worker 打满", importance=0.6)
)
await memory.upsert_fact(
    Fact(user_id=uid, key="pref.locale", value="偏好简体中文与表格", confidence=0.9)
)
await memory.record_procedure(
    Procedure(name="csv tidy", signature="clean→agg", description="清洗后聚合"),
    outcome="ok", success=True,
)
bundle = await memory.recall("用户偏好与 CSV 清洗", user_id=uid, session_id=sid)
```

验证分层：

1. `GET /api/v1/chat/sessions/{id}/agent-memory?limit=50` 看三库快照；
2. `uv run pytest tests/test_agent_memory.py tests/test_recall_pipeline.py tests/test_lexical_backend.py -v`；
3. prompt preview 或 SDK `session.memory.recall()` 确认 attachment 是否注入。

| 用户问题 | 不该查 | 该查 |
|----------|--------|------|
| 昨天原话 | procedure store | session transcript |
| 暂停在 ask_user | episodic | checkpoint |
| 习惯先 lint 再提交 | 整段 transcript | procedural recall |

## 常见误区

- **把整段聊天 upsert 成 Fact**：噪声高、难治理；应走 formation 摘要与门控。
- **没有向量就认为记忆全坏**：lexical/SQL 回退始终可用，只是无近邻语义。
- **recall limit 过大**：默认 total 8、per_store 4，过大挤占 context 预算。
- **跨用户 recall 不加 user_id**：semantic 直接空或可能泄露 scope 设计失误。
- **Episode.transcript 有值**：自动路径通常为空；勿假设 episodic 含完整对话。

## 与 ADK、Anthropic、AutoGen 等方案对照

Google ADK 的 Memory Bank 也区分 session state 与长期 memory service，但具体 store 形态取决于所选 backend。Anthropic Messages API 无内置用户记忆，跨轮靠应用侧消息历史或外部检索；不要把 prompt caching 当长期 Fact 存储。AutoGen 提供可插拔 Memory protocol，开发者仍需决定何时 write/query。Mem0 等外部服务托管 embedding 与 recall；LeAgent 把三库与 pipeline 留在进程内，与 `FileState`、workspace 范围紧耦合，好处是可测、可降级、边界清晰。

LeAgent 的鲜明选择是：**窄 façade + 三库分责 + SQL 真源 + 可选 Milvus**。代价是应用必须理解写入与可见之间的 formation、排序、预算与降级，不能假设「调了 record 下一轮必见」。

## 总结

Episodic、Semantic、Procedural 让「记得什么」结构化，从而可评测、可删除、可降级。Runtime 只通过 `AgentMemory` 的 `record_episode`、`upsert_fact`、`record_procedure`、`recall` 读写；辅以 `observe_turn` 自动 formation 与 `delete_user_data` 等治理 API。自动 formation 写截断摘要而非 transcript 镜像；recall 是预算化附件而非全库浏览。Fact 键 `(user_id, workspace_id, key)`、Procedure 键 `(user_id, workspace_id, signature)` 决定 upsert 与聚合语义。无 Milvus 时 SQL 仍是真源，lexical 兜底。选对 store 后再谈 embedding；读路径见 [34](34-hybrid-recall-reranking.md)，formation 见 [33](33-memory-formation.md)，边界入口见 [31](31-memory-boundaries.md)。
