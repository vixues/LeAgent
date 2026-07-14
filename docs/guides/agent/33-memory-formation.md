# 33. Memory Formation：决定什么值得记住

## 定位与先修

本文讲解 LeAgent 如何把 turn 完成后的观察信号路由到三库，而不是「每轮全记」或「什么都不记」。先修：[32 三存储](32-three-store-memory.md)、[31 记忆边界](31-memory-boundaries.md)、[27 消息生命周期](27-message-lifecycle.md)。Formation 不替代 session transcript，也不负责 pause/resume；关闭 formation 时聊天历史仍在，只是长期认知平面不再自动生长。

## 目标

完成后你应能回答：

1. `TurnObservation` → `FormationPolicy.evaluate()` → `FormationDecision` → 各 store 写入的完整路径；
2. `observe_turn` 幂等键的实际行为，以及 `FormationPolicy` 三类阈值如何分流；
3. `EXPLICIT_REMEMBER`、`PREFERENCE_DETECTED` 等 trigger 如何影响 targets；
4. `observe_feedback` 与 controller/hook 双路径调用时如何避免重复写入恐慌。

## 心智模型

每个 turn 产生大量信号：用户话、助手话、工具成败、步骤数、标签、art 质量分等。Formation 回答三个问题：**suppress 吗？写哪些 store？importance/confidence 多少？**

```text
Controller 收尾 / Hook 构造 TurnObservation
        │
        ▼
AgentMemory.observe_turn
  · 幂等键已见 → FormationDecision(suppress=True)
  · FormationPolicy.evaluate（确定性打分，无 LLM）
        │
        ├─ importance ≥ 0.10 → episodic（build_episode_summary）
        ├─ 有工具且成功且 ≥ 0.35 → procedural（build_procedure_signature）
        └─ 显式语义意图且 ≥ 0.25 → semantic（auto.turn.<session_id>）
        │
        ▼
record_episode / record_procedure / upsert_fact（never raises）
```

没有门控的系统会迅速变成昂贵噪音库；门控过严则跨会话助手「什么都记不住」——应调 `FormationPolicy` 阈值或 `AgentDefinition.memory.formation`，而不是绕过 façade 手写 `record_episode`。

## 读写数据流

**观察输入。** `TurnObservation` 携带 `session_id`，可选 `user_id`、`workspace_id`，以及 `user_text`、`assistant_text`、`tool_names`、`tool_success_count`/`tool_failure_count`、`total_steps`、`trigger`、`tags`、`duration_ms`、`error`、`extra`（可含 `art_run`）。它读的是**结构化观察**，不是把 SSOT transcript blob 直接塞进向量库。

**策略打分。** `detect_triggers()` 从文本检测 `EXPLICIT_REMEMBER`（「请记住」「remember」等）、`PREFERENCE_DETECTED`、`CORRECTION`，并结合工具成败、`MULTI_STEP_SUCCESS`（≥3 工具且无失败）等。`raw_score = sum(TRIGGER_WEIGHTS)`，再按工具数、步骤数微调，`importance`  clamp 到 [0,1]。默认阈值：**episodic 0.10、semantic 0.25、procedural 0.35**。Semantic 仅当 trigger 含显式语义类（`EXPLICIT_REMEMBER`、`PREFERENCE_DETECTED`、`CORRECTION`、`FACT_STATED`）且过阈值才写入。

**写入构造。** Episodic：`build_episode_summary()` 生成 Q/A 摘要 + 工具列表，**不填** `transcript`。Procedural：signature = SHA256(意图 + 工具名)，description 含意图、输出、工具链；若有 `extra.art_run` 则 `build_art_run_note()` 折入 quality_score/refine/graph_digest；art 未过 quality gate 时 `success=False`。Semantic：`key=auto.turn.<session_id>`，`value=user_text[:2000]`，`confidence=0.3+importance*0.7`。

**幂等与门控。** 注释写按 `(session_id, turn_id)` 去重，LRU 最多 2048 键；但 `TurnObservation` **未声明** `turn_id`，代码用 `getattr(obs, "turn_id", "")`，实际 key 退化为 `session_id:`——同一会话第二次 `observe_turn` 会被 suppress。Controller 与 hook 都可能调用，这是预期行为。`decision.suppress` 或 `targets` 空则直接返回，不写库。全程 **never raises**。

**反馈路径。** `observe_feedback(is_like, has_tools, ...)` 调用 `score_feedback()`，**只返回** `FormationDecision`，不自动写库；dislike 时 caller 决定是否降权或删除。Like 可促 episodic + 条件 procedural。

## 真实实现中的边界

**Formation 可读 AgentDefinition。** `memory.enabled=False` 或 formation 关闭时，observe 可能仍被调用但策略层不写；recall 可独立开关。CLI 未注入 `AgentMemory` 时 formation 不工作——勿与「无会话」混淆。

**Semantic 不是结构化抽取。** 自动 Fact 的 value 是用户原文切片（最多 2000 字），不是 `language=zh-CN` 这类字段；recall 依赖字面或向量重叠。

**Procedural 需要工具链。** 无 `tool_names` 时即使 decision 含 procedural 也不会写。多步成功 + 阈值是主要入口；art 管线通过 `extra.art_run` 增强 description 与 success 判定。

**Evaluate 失败 suppress。** `formation_evaluate_failed` 时返回 suppress decision，不抛异常，流式路径不受影响。

**与 transcript 的生命周期分离。** 用户骂工具不一定变 Fact；dislike 走 feedback 决策。Episode 是摘要不是备份；查原文走 session。

**Trigger 权重可预期。** 例如 `EXPLICIT_REMEMBER` 权重 0.55、`PREFERENCE_DETECTED` 0.40、`TURN_COMPLETE` 仅 0.15——普通闲聊往往只过 episodic 阈值；要稳定进 semantic 需显式偏好或记住类措辞。`USER_DISLIKE` 为 -0.10，且当 importance 被压到 ≤0 时 `suppress=True`，避免差评 turn 继续污染三库。

**AgentDefinition.memory.formation 是总闸。** 关闭后 `observe_turn` 仍可能被调用，但策略层不写；这与关闭整个 `memory.enabled`（连 recall 也停）不同。调试 formation 时应确认 agent YAML 里两项开关各自含义，勿混为一谈。

**Trigger 权重表（节选）。** `EXPLICIT_REMEMBER` +0.55、`PREFERENCE_DETECTED` +0.40、`MULTI_STEP_SUCCESS` +0.35、`CORRECTION` +0.30、`TOOL_SUCCESS` +0.20、`TURN_COMPLETE` +0.15、`USER_DISLIKE` -0.10。多 trigger 累加后再 clamp；纯 `TURN_COMPLETE` 往往只够 episodic 门槛，不会单独触发 semantic。

**AgentDefinition 开关组合。** `memory.enabled=False` 关闭整个记忆平面；仅关闭 formation 时 observe 可能 no-op 但历史 recall 仍可用。子 agent 委派若 `agent_memory=None`，既不 observe 也不 prefetch——与主 agent 记忆隔离，设计多 agent 产品时需显式决定是否共享 `user_id` 下的 facts。

**Art 管线特殊路径。** `obs.extra["art_run"]` 含 `quality_score`、`quality_passed`、`refine_iteration`、`graph_digest` 时，procedure description 与 outcome 会附加 `build_art_run_note()` 一行；`quality_passed=False` 强制 `success=False`，便于 planner  recall 时避开低分图。

## 示例与验证

```text
用户：「以后请用简体中文，表格优先。」
  → PREFERENCE_DETECTED + EXPLICIT_REMEMBER 权重
  → 可能同时 episodic + semantic（过各自阈值）

用户 + 工具链：清洗 CSV → 聚合 → 画图，全成功
  → MULTI_STEP_SUCCESS + TOOL_SUCCESS
  → procedural 候选（signature 聚合）

用户：「请记住我偏好中文回答」
  → semantic key=auto.turn.<session_id>，同 session 再次命中覆盖

同一 session 连续两次 observe_turn（无 turn_id）
  → 第二次 reasoning="duplicate observe_turn"
```

```bash
cd backend
uv run pytest tests/test_memory_formation.py tests/test_procedure_promotion.py -v
uv run pytest tests/test_agent_memory.py -k observe -v
```

调试时看 `FormationDecision.reasoning` 与 `provenance`（逗号连接的 trigger 列表），比直接查 Milvus 更有效：先确认是否 suppress，再看 targets。

## 常见误区

- **每轮强制 `record_episode`**：绕过策略制造垃圾，recall 变噪声。
- **把 formation 关闭当「无会话」**：transcript 仍在 TieredSessionStore。
- **忽略幂等**：日志两次 observe 不代表双写；当前无 turn_id 时会话级 dedupe。
- **dislike 未处理**：`observe_feedback` 只给决策，caller 要落实删/降权。
- **把 stderr 全文当 episode**：应靠 `build_episode_summary` 限长。
- **期待 LLM 参与 formation**：当前 policy 完全确定性，权重可子类或 env 扩展。

## 与 ADK、Anthropic、AutoGen 等方案对照

Google ADK 常用 callback 把状态写入 Memory Bank，写入时机由应用定义。Anthropic 的 memory tool 让**模型主动**记笔记；LeAgent 偏**策略自动形成** + 可选用户反馈，优点是稳定可测、无额外 LLM 成本，代价是必须认真调门控否则「自动」变「自动污染」。AutoGen 的 memory 组件通常由开发者显式 `add`；LeAgent 在 turn 收尾统一 `observe_turn`，与 controller/hook 集成。LangGraph checkpoint 保存执行状态，不等于 semantic fact formation。

## 总结

Formation 是记忆系统的质量控制闸门：确定性打分、三阈值（episodic 0.10 / semantic 0.25 / procedural 0.35）、`observe_turn` 幂等与 never raises 保证流式路径安全。Episodic 写截断摘要，Semantic 写 `auto.turn.*` 原文切片 Fact，Procedural 按 signature 聚合工具链模式。`EXPLICIT_REMEMBER` 等 trigger 决定是否进 semantic；dedupe key 在无 `turn_id` 时退化为会话级。排查时先看 suppress 与 reasoning，再查 store 写入 warning 与 WAL。召回侧见 [34](34-hybrid-recall-reranking.md)，预取降级见 [35](35-recall-prefetch-degradation.md)，隐私见 [36](36-memory-privacy-retention.md)。
