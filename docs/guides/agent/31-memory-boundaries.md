# 31. 记忆边界：先分清 transcript、上下文与长期记忆

## 定位与先修

本文是记忆系列的入口，适合已经理解一次 agent turn、system prompt、tool call 和会话持久化的读者。先修建议是能区分“模型当前看到的消息”与“应用数据库里保存的数据”。本篇不把 memory 当成万能聊天记录，而是从 LeAgent 的真实边界出发：`TieredSessionStore` 拥有 chat transcript，`AgentMemory` 只负责经过选择的长期认知记忆，`RecallBundle` 只是下一轮上下文的一种候选附件。

## 目标

完成后你应能回答四个问题：

1. 一条消息何时属于 transcript，何时可能形成 Episode、Fact 或 Procedure；
2. 为什么“写入记忆”不等于“保存对话”，也不保证下一轮一定被召回；
3. user、session、workspace 三种标识分别约束什么；
4. 当前公开治理能力能读什么、删什么，哪些能力还没有 HTTP API。

## 心智模型

把系统想成三条相互连接但所有权不同的管道：

```text
用户/助手消息 ──> 会话 transcript（完整对话的 SSOT）
                    │ turn 完成后的 observation
                    ▼
              FormationPolicy（筛选与路由）
                    ▼
       Episode / Fact / Procedure（长期记忆）
                    │ recall + 排序 + 去重 + 预算
                    ▼
           当前 turn 的 recall attachment
```

第一条管道回答“说过什么”；第二条回答“哪些内容值得跨轮次复用”；第三条回答“此刻哪些旧信息与问题相关”。三者不能互换。尤其是 `Episode.transcript` 虽然在类型和 SQL 行中存在，但 `observe_turn()` 自动形成 Episode 时只填写 `summary`，没有复制 transcript。`build_episode_summary()` 只截取用户文本最多 400 字、助手文本最多 800 字并追加最多 32 个工具名，整体再截到 1200 字。因此长期记忆天然是有损、选择性的视图。

## 读写数据流

写路径从 turn 完成后的 `TurnObservation` 开始。它携带 `session_id`，可选 `user_id`、`workspace_id`，以及用户文本、助手文本、工具成功/失败数、总步骤、标签和扩展字段。`FormationPolicy.evaluate()` 给出目标 store、importance、confidence 与 provenance；`AgentMemory.observe_turn()` 再构造具体对象并调用 `record_episode()`、`upsert_fact()` 或 `record_procedure()`。这些 façade 方法吞掉 store 异常，记录最近写入健康和 best-effort WAL，而不会让记忆故障击穿正常请求。

读路径由 query 驱动。`AgentMemory.recall()` 把身份范围、每库上限、总上限和可选 `FileState` 交给 `RetrievalPipeline`。结果经过三库候选收集、重排、按来源 ID/文本去重、过滤当前已知文件，以及“相同文本时 semantic 胜过 episodic”的折叠。最后 `RecallSource` 将每类有限条目渲染成 `<attachment kind="recall">`，单条内容最多 300 字。也就是说，数据库中存在不代表进入 prompt；召回命中也不代表在预算竞争后一定保留。

## 真实实现中的边界

身份边界并不完全对称。Episodic recall 可按 `user_id` 和 `session_id` 过滤；Semantic recall 要求 `user_id`，可进一步按 `workspace_id`；Procedural recall 可按 user/workspace 约束。事实的自然 upsert 键是 `(user_id, workspace_id, key)`，过程的聚合键是 `(user_id, workspace_id, signature)`。自动 semantic 写入使用 `auto.turn.<session_id>` 作为 key，因此同一会话后续命中该路径时会覆盖，而不是生成无限事实。

还要注意当前快照中的一个实现细节：`observe_turn()` 注释说按 `(session_id, turn_id)` 去重，并维护最多 2048 个 LRU key；但 `TurnObservation` 目前没有声明 `turn_id`，代码用 `getattr(..., "")` 取值。因此实际 key 会退化为 `session_id:`。理解或排查“同一会话只观察到一次”的行为时，必须以代码而非注释为准。

无 Milvus 时，长期记忆并未整体关闭。ServiceManager 当前明确以 `MilvusConnectionConfig(enabled=False)` 建立三个 store，SQL 仍是持久化真源，recall 直接跳过 query embedding 和向量搜索，转向 SQL lexical 路径：PostgreSQL 用英文 `to_tsvector/plainto_tsquery`，SQLite 等方言用 `%query%` 的 `ILIKE`/等价大小写不敏感匹配。它能按字面检索，但不具备语义近邻能力。

## 示例与验证

设用户说：“请记住我偏好中文回答”，助手回复确认。transcript 会照常保存完整两条消息；formation 检测到 `EXPLICIT_REMEMBER` 或 `PREFERENCE_DETECTED`，通常同时形成 Episode 和 Fact。自动 Fact 的 value 是原始用户文本的前 2000 字，而不是结构化抽取出的 `language=zh-CN`。下一轮问“回答风格是什么”时，在无 Milvus 的默认路径下，整句 lexical 查询未必命中该 value；改问包含“中文”或“偏好”的短语更容易验证。

可用三层验证法：

1. 会话消息接口验证 transcript 是否完整；
2. `GET /api/v1/chat/sessions/{id}/agent-memory?limit=50` 查看只读快照；
3. SDK 的 `session.memory.recall()` 或 prompt preview 验证是否真正注入上下文。

第二步返回该 session 的 episodes，却返回该 owner 的 facts 和 procedures，后二者不是 session 专属。接口会先校验 session owner 及项目访问令牌，`limit` 范围是 1–100；memory 未启用时返回 `enabled=false` 和三个空数组。

## 常见误区

- **“数据库有消息，所以 agent 有长期记忆。”** transcript 与三库是不同 owner；只有 formation 写入后才有长期记忆。
- **“Episode 就是聊天备份。”** 自动 Episode 是截断摘要，`transcript` 通常为空。
- **“记住了就必定召回。”** 还要经过查询匹配、范围过滤、排序、去重和上下文预算。
- **“workspace_id 自动隔离所有数据。”** 各 store 的过滤方式不同；调用方必须正确传递 user/session/workspace。
- **“memory failure 应该让 turn 失败。”** 当前设计相反：写与 recall 都以降级为空结果为主，并暴露健康状态供观测。

## 与 ADK、Anthropic、AutoGen 等方案对照

Google ADK 常把 session state、memory service 和 artifact 分开；这与 LeAgent 强调 transcript 所有权和长期记忆筛选相近，但具体持久化与检索取决于所选 service。Anthropic 的 Messages API 本身是无状态请求接口，跨轮记忆通常由应用保存消息、压缩摘要或检索外部存储；不要把 prompt caching 误认为用户长期记忆。AutoGen 提供 agent/team 上下文与可扩展 memory 组件，开发者仍需决定何时 `add`、何时 `query`、如何清理。LangGraph/类似 checkpoint 方案更擅长保存执行状态，但 checkpoint 也不自动等于可检索的长期事实。

LeAgent 的鲜明选择是：transcript、checkpoint、workflow state 与 cognitive memory 分属不同 durable owner，再通过 context source 汇合。好处是边界清楚、可独立治理；代价是应用必须接受“写入”和“可见”之间存在异步、过滤与降级。

## 总结

长期记忆不是第二份 transcript，而是从 turn observation 中选择出的 Episode、Fact、Procedure。SQL 保存真值，recall 只把少量相关条目带回当前 prompt；默认无 Milvus 仍可运行，但退化为字面检索。设计、调试和治理时应分别检查 transcript、formation 写入、store 范围和最终 recall attachment，不能用其中任一层替代其他层。
