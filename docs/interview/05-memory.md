# 五、Memory

## 5.1 Agent 为什么需要 Memory？

模型调用本身通常无状态；没有 Memory，Agent 无法跨轮次保持任务进度、记住用户偏好，也不能复用过去成功或失败的执行经验。Memory 的价值不是“存下所有内容”，而是把值得长期保留的信息结构化，并在相关时刻以有限预算召回。

LeAgent 通过 `AgentMemory` 统一封装三类长期记忆：Episodic（历史回合摘要）、Semantic（稳定事实/偏好）和 Procedural（工具链结果）。当前对话全文的单一事实源则由 `TieredSessionStore` 持久化，不应与这三类长期 Memory 混为一谈。

## 5.2 Memory 和 Context 的区别？

Memory 是可持久化、可检索的历史信息库；Context 是某一次模型调用实际可见的输入，包括系统指令、当前对话、附件、工具结果和召回记忆。Memory 可以很大，Context 必须受窗口和相关性预算约束；“存储”与“注入”是两个独立决策。

LeAgent 的 `ContextManager` 按 recipe 组装本轮上下文，`RecallSource` 只把召回结果压缩为 attachment 注入。`RelevanceGate` 控制重型领域提示是否进入 Context，它不负责写入 Memory。

## 5.3 Short-term Memory 是什么？

Short-term Memory 是当前任务或会话内、短时间有效的工作状态，例如最近消息、当前目标、工具结果、scratchpad 和 todo。它强调连续性与低延迟，通常随会话结束、压缩或任务完成而淘汰。

在 LeAgent 中，聊天 transcript 由 `TieredSessionStore` 持久化，`QueryEngine` 持有会话级消息与 ContextManager；`todo_write` 将结构化 todo 写入 session，并强制最多一个 `in_progress`。这些属于会话工作状态，而不是三存储长期记忆。

## 5.4 Long-term Memory 是什么？

Long-term Memory 是跨会话仍可保留的信息，通常需要持久化、用户隔离、检索、更新、遗忘和审计。它不应保存完整原始交互的无界副本，而应按用途拆分并设置形成与保留策略。

LeAgent 以 `AgentMemory` 为唯一运行时入口，对外提供记录 episode、upsert fact、记录 procedure 和 recall；底层向量能力可选，缺少 Milvus 时仍可通过词法后端降级。

## 5.5 Episodic Memory 是什么？

Episodic Memory 记录“过去发生过什么”，通常包含任务、过程、结果、时间和重要性，适合回答“上次怎么做的”。它与 Semantic Memory 的区别是：前者保留事件上下文，后者抽取稳定事实。

LeAgent 的 `Episode` 保存会话、用户/工作区、回合摘要、重要性、标签、召回次数与时间。`observe_turn` 默认用用户和助手文本构建受限长度摘要，而不是无条件保存完整推理链。

## 5.6 如何实现用户偏好记忆？

先检测显式表达和纠正，如“我偏好中文”“以后不要生成表格”；将偏好规范化为稳定 key/value，附带 user_id、适用 workspace、来源、置信度和更新时间。写入时应 upsert、处理冲突，召回时按作用域过滤；敏感偏好需征得同意并支持删除。

LeAgent 的 `FormationPolicy` 能识别“记住”、偏好和纠正模式，满足阈值后写入 Semantic `Fact`；`Fact` 带 `user_id`、可选 `workspace_id`、`confidence` 和 `source`。当前自动 key 以会话生成，仍不等于完善的偏好 schema 或冲突消解系统。

## 5.7 如何做 Memory Retrieval？

典型流程是：用当前问题或独立 recall anchor 构造查询，按 user/session/workspace 做硬过滤，从不同记忆类型取候选，融合语义与词法信号，按新近度、重要性、置信度和成功率重排，去重后按预算注入 Context。

LeAgent 对三个存储并发召回：Milvus 可用时做语义搜索，否则或无有效结果时走 SQL `ILIKE` 词法降级；随后规则重排、去重、过滤本轮已可见文件，并优先保留覆盖相同内容的 Semantic fact。默认总量 8 条，`RecallSource` 还有约 2 秒软预算，超时则本轮不注入但不取消底层任务。

## 5.8 Memory 会污染推理吗？

会。错误、过期、越权或与当前任务无关的记忆会形成错误先验；重复注入还会挤占上下文并放大确认偏差。治理手段包括形成门槛、来源与时间戳、作用域过滤、置信度/新近度衰减、TopK 限制、冲突检测，以及把记忆明确标成“可疑参考”而非系统事实。

LeAgent 已有形成阈值、作用域参数、规则重排、去重和 Context 预算，但并未自动证明记忆真实。尤其自动生成的回合摘要和事实仍可能失真，应用层应允许用户纠正。

## 5.9 如何删除 Memory？

要同时删除主存储、向量索引、缓存和派生摘要，并保证删除幂等、可审计；按法规需求还要支持按条删除、按用户导出和彻底擦除。仅从提示中“不再召回”不等于物理删除。

LeAgent 提供 `forget_episode`、`forget_fact` 和 `delete_user_data`；后者遍历删除用户的 episode、fact、procedure，并返回计数。具体 store 负责同步其持久化与向量侧删除。当前接口没有独立的 facade 级 `forget_procedure`，但用户级擦除会覆盖 procedure。

## 5.10 如何做用户隔离？

用户隔离必须在查询和存储层做强制过滤，不能依赖模型提示。每条记录应绑定 tenant/user，必要时再绑定 workspace/session；向量检索也要带同样过滤条件，并在缓存键、日志、导出和删除路径保持隔离。

LeAgent 的记忆类型携带 `user_id`，并可携带 `workspace_id` 或 `session_id`；recall 将这些条件传入各 store。Semantic recall 在没有 `user_id` 时直接禁用。知识库检索也按 `user_id` 和 library scope 过滤，并在回读文件时再次校验所有权。

## 5.11 Reflection Memory 是什么？

Reflection Memory 是 Agent 对经历进行二次抽象后形成的经验，例如“失败原因是什么”“下次应采用什么策略”，重点不是原始事件，而是可迁移的教训。可靠实现应把反思与原始证据关联，并通过后续结果验证，避免模型把错误归因固化。

LeAgent 的 Procedural Memory 会记录工具链签名、结果、错误、耗时、运行次数和成功率，能承担部分经验复用；艺术工作流还可记录质量与 refine 信息。但仓库没有通用的、由 LLM 自动生成并验证 Reflection Memory 的完整闭环，不应把 procedural store 直接等同于已实现的反思系统。

## 5.12 Semantic Memory 如何实现？

Semantic Memory 将稳定事实或偏好建模为实体/键值及其作用域、来源、置信度和版本。写入通常采用抽取、规范化、去重/upsert、冲突检测；读取采用精确 key、词法或向量检索，并优先选择高置信且较新的事实。

LeAgent 用 `Fact(user_id, key, value, workspace_id, confidence, source)` 表示 Semantic Memory，由 `upsert_fact` 写入。召回时支持 Milvus 语义搜索和词法降级，规则重排会按 confidence 加权，并在内容重合时优先于 episodic entry。

## 5.13 Memory Compression 如何做？

Memory Compression 是降低长期存储与召回成本：去重相似记录、合并重复事件、衰减低价值内容、裁剪低分项、对旧记录重新摘要，并保留来源指针。压缩应可测量信息损失，关键事实不能只存在于不可追溯的摘要中。

LeAgent 的 `MemoryConsolidator` 已提供重要性衰减、按 retention score 裁剪，以及会话 episode 超量后的合并入口；retention 综合重要性、召回次数、新近度等信号。当前合并只是将若干旧摘要截断后串接成 consolidated episode，并非高质量语义压缩。

## 5.14 Memory Summarization 如何做？

先确定摘要用途，再抽取目标、关键事实、决策、工具结果、失败原因和待办；对事实保留来源与时间，对不确定内容标注置信度。可采用分层摘要：回合摘要 → 会话摘要 → 长期事实/经验，并用原文回归测试检查遗漏与歪曲。

LeAgent 的 episode 摘要目前由 `build_episode_summary` 确定性拼接用户文本、助手文本和工具名，并限制长度；它速度快、行为稳定，但不具备 LLM 抽象、事实核验或层次化总结能力。

## 5.15 如何评估 Memory 效果？

应拆成四层：写入质量（该记的是否记、错误记忆率）、检索质量（Recall@K、MRR、作用域泄漏率）、生成收益（有/无 Memory 的任务成功率和事实一致性）、系统成本（延迟、token、存储、删除完整性）。还要用跨会话偏好、纠正、过期事实、用户切换和恶意记忆等场景做端到端回归。

LeAgent 可观测到 recall 延迟、记忆写入降级状态、procedure 成功率和 episode recall_count；评测时应特别验证 Milvus 不可用时的词法降级，以及 `RecallSource` 超时不注入对答案质量的影响。
