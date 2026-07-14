# 35. 异步预取、超时与无向量降级

## 定位与先修

本文处理 recall 在真实 turn **临界路径**上的工程约束：不能拖垮 TTFT（time-to-first-token），也不能在 Milvus/embedding 缺失时让记忆整条挂掉。先修 [34 混合召回](34-hybrid-recall-reranking.md)。核心类型是 `RecallHandle`：turn 早期 `start()` 并行预取，组装 system prompt 前 `consume(timeout=...)` 取结果或放弃等待。

## 目标

完成后你应能回答：

1. 为何用 fire-and-forget 的 `RecallHandle`，而不是在 prompt 前同步阻塞 `recall()`；
2. **timeout 到期为何不 cancel 底层任务**，以及为何**不 cache** 空结果；
3. 无 Milvus / embedding degraded 时系统具体怎么降级；
4. 降级后的产品语义：可用字面检索，没有语义近邻。

## 心智模型

QueryEngine 希望在模型生成与其它准备并行时就开始 recall，避免 embedding + 三库搜索挤在首 token 之前：

```text
turn 早期
  RecallHandle.start(query, user_id, session_id, file_state=...)
        │  create_task(AgentMemory.recall(...))，同 handle 幂等
        ▼
prompt 组装前
  consume(timeout=T)
        ├─ 按时完成 → 写入 _result cache → 注入 RecallSource
        ├─ asyncio.TimeoutError → 返回空 RecallBundle(query="")，不 cancel，不 cache
        └─ 其它异常 → 空 bundle 并 cache（warning 日志）

显式 cancel() 才真正取消后台 task
```

`asyncio.wait_for(asyncio.shield(self._task), timeout)` 的含义：`wait_for` 超时时**只放弃等待**，被 shield 包裹的 recall task **继续运行**（例如仍可完成 note_recall），但本 turn prompt 不再等它。

## 读写数据流

**预取 start。** `RecallHandle.start()` 若 `_task` 已存在则直接 return（幂等）。参数透传 `query`、`recall_anchor`、`user_id`、`session_id`、`workspace_id`、`limit=8`、`per_store_limit=4`、`file_state`。底层 `asyncio.create_task(self._memory.recall(...))`。

**消费 consume。** 若 `_result` 已有，直接返回（同 handle 二次 consume 便宜）。若从未 `start`，合成空 bundle 并 cache。带 `timeout` 时 `wait_for(shield(task))`；无 timeout 则 await task。成功或非超时异常写入 `_result`。**TimeoutError 路径**：log `recall_handle_consume_timeout`，返回**新鲜**空 `RecallBundle(query="")`，**不**写入 `_result`——避免同 handle 再次 consume 永远空，也避免把「迟到半拉子」当成功结果。

**façade 级降级。** `AgentMemory.recall()` 自身 try/except：pipeline 抛错 → warning + 空 bundle。与 handle 超时语义一致：**记忆读失败不打断 turn**。

**无向量路径。** ServiceManager 可用 `MilvusConnectionConfig(enabled=False)` 建三 store。`_vector_search_enabled()` 见不到 `can_search` collection 时不 embed（或 embed 后仍无向量搜索）。SQL 仍是 SSOT；recall 走 [34](34-hybrid-recall-reranking.md) 所述 lexical：`to_tsvector` 或 `ILIKE` 子串。

**Embedding degraded。** `NullEmbeddingProvider` 等路径设 `last_degraded=True` 时，即使调用了 `embed_one`，pipeline 也会 `vector=None`，强制 lexical，防止 poison 向量 cosine 搜索。

**Memory 策略关闭。** `AgentDefinition.memory.enabled=False` 或子 agent 委派时 `agent_memory=None`，根本不会 `start` recall——这与「超时降级」不同，是策略性关闭。

**Shield 与资源。** 超时后 task 仍会跑完；极慢 Milvus 仍占连接。向量模块有 `connect_timeout_seconds` 等可限制爆炸半径；应用层应监控 timeout 率而非假设每 turn 都 attach 成功。

## 真实实现中的边界

**超时空结果是有意产品选择。** 本 turn 可能「库里有偏好却像没召回」；下一 turn 新建 handle 且检索已暖，才可能命中。观测应看 `recall_handle_consume_timeout` 与 TTFT，不是只看 bundle 非空。

**不 cache 超时结果 vs 异常 cache。** Timeout 返回空且不写 `_result`；其它异常写空 `_result`。再次 consume 无 timeout 时，若 task 仍在跑，可能仍 await 原 task——实践上**每 turn 新建 RecallHandle** 更清晰。

**空 query。** pipeline 在 query 与 recall_anchor 皆空时直接空 bundle；预取应用真实用户文本或稳定 anchor。

**Semantic 无 user_id。** 与 [34](34-hybrid-recall-reranking.md) 相同：预取也传不齐 identity 则 semantic 候选为空，容易被误判为「降级失败」。

**cancel() 与 shield。** 只有显式 `cancel()` 才 `task.cancel()` 并清 `_task`；consume 超时不会触发 cancel。

**双层空结果。** handle 超时 + façade recall 异常 + pipeline 空 query 都表现为空 bundle，排障需看日志区分。

**与 QueryEngine 时序。** 典型 turn 里，用户消息到达后尽早 `RecallHandle.start(用户文本, user_id=...)`，与 tool 准备、hook 等并行；在 `ContextAssembler` 拉取 recall attachment 前 `consume(timeout=预算秒数)`。预算过小则本 turn 无记忆附件但 chat 仍继续——这是 latency 与 memory 命中率的可调 trade-off。

**procedure_write_status 与预取无关但共用 degraded 信号。** 写入侧 `embedding_degraded` 与读取侧 `last_degraded` 同源 embedding provider；运维面板应同时看 write health 与 recall timeout，避免只修一端。

**Milvus 关闭时的用户预期。** 产品文案应区分「记忆功能不可用」与「无语义近邻、仍可按关键词回忆」；后者是 LeAgent 默认单机模式的正常态，不是 partial outage。

## 示例与验证

测试里让 `AgentMemory.recall` sleep 超过 timeout：

```python
handle = RecallHandle(memory)
handle.start("用户偏好", user_id=uid)
bundle = await handle.consume(timeout=0.05)
assert not bundle.entries  # 空 bundle
# 底层 task 未被 cancel，可能稍后 done()
```

无 Milvus：写入含「中文」的 fact，用 `recall("中文")` 断言 lexical 命中；用同义改写 query 断言可能失败——演示降级能力边界。

手工：debug 日志抓 `recall_handle_consume_timeout`、`recall_embed_failed`；看 `memory_write_status()` / `procedure_write_status()` 的 `vector_optional`、`embedding_degraded`。

```bash
cd backend
uv run pytest tests/test_agent_memory.py -k "recall_handle or prefetch" -v
```

## 常见误区

- **「timeout 会 cancel 检索。」** 不会；只有 `cancel()` 会。
- **「空 bundle 等于 memory 坏了。」** 也可能是超时、无 query、无 user_id（semantic）、或 memory.enabled=False。
- **「无 Milvus 必须报错。」** 默认本地路径刻意可跑；只是无语义近邻。
- **「降级后 recall 质量与有向量一样。」** 字面匹配 ≠ embedding 近邻。
- **「prefetch 可跨 turn 复用同一 handle。」** 优先每 turn 新实例，避免 `_result`/task 状态纠缠。
- **「shield 防止内存泄漏。」** 只防 cancel；慢 task 仍占资源直到完成。

## 与 ADK、Anthropic、AutoGen 等方案对照

许多 RAG 管道在 LLM 调用前**同步** retrieval，简单但伤首字延迟。LeAgent `RecallHandle` 属于**并行预取 + 超时放弃等待**，与「先答后检索」的边缘方案不同：本 turn 仍尝试在 budget 内注入 recall，只是超时不阻塞。Anthropic prompt caching 优化重复**前缀**成本，不是用户长期 memory 检索。向量 SaaS 故障时若无 lexical 底板，整条记忆链硬失败——LeAgent 把 SQL lexical 当默认安全网，适合桌面/单机零依赖部署。

## 总结

`RecallHandle` 把 recall 移出 TTFT 关键路径：`asyncio.shield` + `wait_for` 超时返回空 bundle、**不 cancel**、**不 cache** 超时结果；显式 `cancel()` 才停任务。无 Milvus 时记忆不关闭，只降级为 SQL 字面检索；embedding degraded 强制跳过向量。生产观测应同时看 timeout 率、degraded 标志与 lexical 命中率。隐私与遗忘见 [36](36-memory-privacy-retention.md)。
