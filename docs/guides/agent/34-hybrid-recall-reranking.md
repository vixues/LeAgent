# 34. 混合召回、去重与重排

## 定位与先修

本文进入记忆的**读路径**：数据库里有行，如何变成当前 turn 的少量相关条目。先修 [32 三存储](32-three-store-memory.md) 与 [33 Memory Formation](33-memory-formation.md)。核心实现是 `RetrievalPipeline.recall()`：向量优先、lexical 兜底、recency/质量重排、多键去重、semantic-over-episodic 折叠，以及 `FileState` 过滤。

## 目标

完成后你应能回答：

1. 一次 recall 如何从三库扇出候选、合并、截断；
2. 无 Milvus 或 embedding degraded 时 lexical 如何接力，semantic 为何硬性要求 `user_id`；
3. `_rerank`、`_deduplicate`、`_collapse_semantic_over_episodic` 各自裁掉什么；
4. 为何 store 里明明有行，却可能进不了最终 `RecallBundle` 或 prompt attachment。

## 心智模型

Recall 不是「把记忆库倒给模型」，而是**预算化的相关附件**：

```text
query / recall_anchor
        │
        ├─ _vector_search_enabled? → embed_one（degraded 则 vector=None）
        ▼
  asyncio.gather 并行：
    episodic_candidates | semantic_candidates | procedural_candidates
        │（有 vector 先 semantic_search；空则 lexical_search）
        ▼
  合并 → _rerank（半衰期 14d 等 boost）
       → _deduplicate（id / 文本指纹 / FileState 路径）
       → _collapse_semantic_over_episodic
       → [:limit]（默认 total 8，per_store 4）
        ▼
  RecallBundle；episodic 命中后台 note_recall（不阻塞返回）
```

默认 knobs 在 `RecallOptions`：`limit=8`，`per_store_limit=4`，`RECENCY_HALF_LIFE_DAYS=14.0`。

## 读写数据流

**入口与空 query。** `AgentMemory.recall()` 构造 `RecallOptions` 并委托 pipeline；pipeline 层再包 try/except，失败返回空 bundle。query 与 `recall_anchor` 皆空时直接返回空 `RecallBundle`，不访问 store。

**向量门控。** `_vector_search_enabled()` 检查各 store 的 vector collection 是否 `can_search`；全部不可用则跳过 embed（无 collection 的 fake store 仍可能尝试 embed，属测试兼容）。embed 成功但 `embeddings.last_degraded=True` 时强制 `vector=None`，避免占位向量产生假 cosine 相似度。

**每库候选（vector then lexical）。** 三任务 `asyncio.gather` 并行。Episodic：可按 `user_id`、`session_id` 过滤。Semantic：**无 `user_id` 直接返回空列表**（include 也无效）。Procedural：按 user/workspace。每库先 `semantic_search(vector, limit=per_store_limit)`，结果为空再 `lexical_search(query, ...)`。Lexical 在 Postgres 用 `to_tsvector`/`plainto_tsquery`，SQLite 等用 `%query%` 的 ILIKE/大小写不敏感匹配。

**重排 `_rerank`。** 对每条 `RecallEntry` 用 `_apply_boosts` 修正 score：
- 时间：半衰期 14 天的指数衰减 `0.5 + 0.5*exp(-age/14)`；
- Semantic：`confidence` 缩放 × **1.15**；
- Procedural：`success_rate` 缩放；`run_count=0` ×0.8，`≥3` ×1.1；
- Episodic：`importance` 加成 + `recall_count` 小幅加成（最多约 +0.6 因子）。

**去重 `_deduplicate`。** 按 `kind:source_id` 去重；若 `file_state.paths()` 中某路径**字面包含**于 entry.text 则丢弃（避免重复注入刚读过的文件）；再按 `_text_signature`（小写截断 300 字）去近重。

**折叠 `_collapse_semantic_over_episodic`。** 若 semantic 与 episodic 文本签名相同，**丢掉 episodic**，保留更稳定的事实；不压 procedure。

**截断与副作用。** `bundle.extend(collapsed[:limit])`；进入 bundle 的 episodic id 会 `create_task(note_recall)` 更新 `recall_count`，强引用 `_BACKGROUND_NOTE_TASKS` 防 GC；bundle **立即返回**，不等待书签写入。

**Context 二次预算。** `RecallSource` 把条目渲染为 `<attachment kind="recall">`，单条约 300 字；pipeline 输出不是 prompt 终态。

## 真实实现中的边界

**写入成功 ≠ 召回命中。** Formation 用原文切片存 Fact；lexical 依赖子串重叠。用户换说法 query，整句可能对不上——验证应用共享关键词或 SDK 直接 `recall(query)`。

**总上限会丢掉高分库外条目。** 每库最多 4，合并重排后最多 8；三库都很「满」时，某一库可能为零条进入 bundle。

**FileState 过滤是字符串包含。** 路径巧合出现在摘要里会被误杀；`file_state` 为空则不过滤。

**Background note 失败只 debug 日志。** 不影响 bundle；`recall_count` 偶尔滞后是预期。

**跨库 score 不可直接比原始值。** 最终排序看 boost 后 score；semantic 1.15 倍是设计选择。

**Semantic 无 user_id 全空。** 匿名或未传身份的 turn 只能召回 episodic/procedural（若 scope 允许），facts 不会出现。

**候选 gather 的并行语义。** 三库 `asyncio.gather` 彼此独立失败：某一库 lexical 异常只 log debug，其它库仍贡献条目。Episodic 向量有结果时**不会**再跑 lexical（`if not results` 才 fallback）；向量空或失败才字面搜。这意味向量能命中时，字面完全不重叠的长尾 query 仍可能靠 cosine 召回。

**RecallEntry.metadata 驱动 boost。** `_apply_boosts` 读 `created_at`、`last_run_at`、`confidence`、`success_rate`、`run_count`、`importance`、`recall_count` 等键；store 的 search 实现负责填充。调试「为何 A 排在 B 前」应 dump metadata 而非只看原始 vector score。

**与 RecallHandle 的衔接。** Pipeline 本身不知道 timeout；`RecallHandle.consume` 在 turn 层截断等待。Pipeline 内部的 `note_recall` 后台任务与 handle 超时并行存在——超时 turn 无 attachment，但 episodic 的 recall_count 仍可能在稍后更新。

## 示例与验证

写入含「中文」的偏好 Fact 后：

1. `recall("中文偏好")` 在无 Milvus 下更易 lexical 命中；
2. `recall("回答风格")` 可能落空——说明依赖字面重叠；
3. 若同时有近文 Episode 与 Fact，折叠后 bundle 中 kind 应为 semantic。

离线可构造带 metadata 的 `RecallEntry` 列表，单测 `_rerank` 是否抬高高 `success_rate` procedure、压低陈旧低分 episode。对 FileState，放入刚读文件路径，断言含该路径的 entry 被滤掉。

```bash
cd backend
uv run pytest tests/test_recall_pipeline.py tests/test_lexical_backend.py -v
```

## 常见误区

- **「hybrid 等于必须有 Milvus。」** 向量优先，lexical 是始终可用的 SQL 底板。
- **「score 原始值可跨库直接比。」** 看 boost 后 score。
- **「去重只看 UUID。」** 还有文本指纹与文件路径子串。
- **「semantic 总压过一切。」** 仅在文本签名冲突时压 episodic；不压 procedure。
- **「bundle 长度 = prompt 记忆长度。」** 还有 attachment 渲染截断。
- **「note_recall 阻塞 recall。」** 明确 fire-and-forget。

## 与 ADK、Anthropic、AutoGen 等方案对照

向量产品常标榜 hybrid BM25+dense；LeAgent 默认不引入独立 BM25 服务，用 SQL `ilike`/tsvector 做可移植兜底。LangChain/LlamaIndex 可接 cross-encoder reranker；LeAgent 用确定性 boost，可测、无额外模型费用。Mem0 等托管记忆把 recall 外包；LeAgent pipeline 与 `FileState`、身份 scope 同进程，降级路径清晰。Anthropic 无内置三库 recall；应用需自建 RAG 或 memory tool。

## 总结

混合召回 = 可选向量 + 必有 lexical，再经 recency/质量重排、多键去重与 semantic-over-episodic 折叠，最后总数截断。设计验证用例时分别断言候选收集、排序、去重、折叠四层，不要只看「库里有没有」。预取与超时如何避免挡住首 token，见 [35](35-recall-prefetch-degradation.md)。
