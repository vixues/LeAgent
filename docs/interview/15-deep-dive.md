# 十五、大厂高频深挖题（最容易拉开差距）

> 本章强调 Staff/Principal 级判断：先定义边界与不变量，再讨论质量、成本、延迟、安全、可恢复性和组织演进。OpenAI Deep Research、Claude Computer Use、Cursor、Devin、Manus 等包含闭源产品；相关内容只依据公开可观察能力与通用架构进行设计或推断，**不把推断写成其内部实现事实**。

## 15.1 Agent 和 Workflow 的边界在哪里？

边界不在“是否调用 LLM”，而在控制流的所有权。

- Workflow 的状态、依赖和转移大部分可在运行前定义，追求确定性、可审计、SLA 和可重放。
- Agent 在运行时根据观察选择下一动作，适合目标明确但路径未知、环境变化快的任务。
- 最佳生产形态通常是“Workflow 外壳 + Agent 节点”：确定性系统掌管审批、预算、并发、补偿和交付物；Agent 只在需要语义判断的局部拥有自由度。

判断标准可以是：若 80% 的路径可枚举，就优先 workflow；若主要难点是发现下一步，就使用 Agent；若副作用不可逆，则无论模型多强都应回到受控 workflow gate。

LeAgent 正好体现这条边界：`WorkflowExecutor` 验证 `WorkflowDocument`、拓扑调度、并行执行并持久化 workflow state；Agent 节点通过 `AgentRuntime` 进入同一个 `QueryEngine/run_loop` think-act kernel。两者共享工具执行面，但状态 owner 和 resume token 语义不能混为一谈。

## 15.2 Agent 真正的核心能力是什么？

不是“会调用工具”，而是**在不完整信息下持续缩小目标与现实之间的差距**。可分为五项：

1. 建立任务状态：目标、约束、证据、未知项和完成标准；
2. 选择信息增益或进度最高的下一动作；
3. 把动作参数化并安全执行；
4. 从观察中更新假设、识别失败并修正；
5. 判断何时已完成、何时应升级给人。

模型推理只是决策器。真正的系统能力还包括工具质量、环境反馈、状态持久化、权限、验证器和可观测性。一个聪明模型配上模糊工具和不可恢复 runtime，通常不如中等模型配上清晰契约。

LeAgent 将核心拆开：provider abstraction 允许替换模型，`ToolRegistry/ToolExecutor` 统一动作空间，`QueryEngine` 保持 think-act-observe，checkpoint 保证暂停恢复，trace 提供证据链，`AgentMemory` 让历史经验以受控方式影响后续决策。

## 15.3 为什么很多 Agent Demo 无法上线？

Demo 优化的是一次“惊艳路径”，生产优化的是分布尾部和责任边界。常见断点包括：

- 无完成标准，只展示模型说“做完了”；
- 工具参数和错误语义不稳定，失败后无法自纠；
- 无幂等、事务、补偿，重试产生重复副作用；
- 权限继承过宽，prompt injection 可跨越数据边界；
- 状态只在进程内，重启、超时和人工审批后无法恢复；
- 长任务无进度、取消和预算控制；
- 没有真实任务集、trace 和回归门禁，换模型即行为漂移；
- 成本模型只算 token，漏掉搜索、浏览器、沙箱和人工复核成本。

Staff 级落地路径应先缩窄任务域，定义 SLO 与风险等级，再建立 deterministic baseline、shadow traffic、人工接管和逐级放权。不要用平均成功率掩盖高损失的 1% 尾部。

LeAgent 的单 kernel、多 ingress、统一工具执行、durable checkpoint、`run_id/parent_run_id` 和分层 state owner，解决的是“能治理地运行”，而不只是“模型能跑起来”。

## 15.4 为什么 Deep Research 比普通 Agent 强？

Deep Research 的优势通常来自系统化研究流程，而不只是一个更强 prompt：

1. 把开放问题分解成可验证的研究子问题；
2. 多轮检索并根据证据缺口改写查询；
3. 对来源做质量、时效、独立性和冲突判断；
4. 提取带 provenance 的 claim，而不是只保存网页摘要；
5. 在撰写前进行覆盖度与矛盾检查；
6. 输出可追溯引用，并区分事实、推断与未知。

普通 Agent 常在找到第一批相关结果后过早停止，或者把搜索结果的相关性误当作真实性。Deep Research 的关键指标应是 claim-level citation correctness、source coverage、contradiction handling 和 freshness，而不只是答案风格。

架构上可用 `WorkflowExecutor` 固化“规划—并行检索—抽取—交叉验证—综合—引用审计”，仅在查询扩展和证据判断节点使用 Agent。研究进度和中间证据放 workflow state，跨任务偏好与已验证事实才进入 `AgentMemory`。

## 15.5 Manus 的核心创新是什么？

基于公开可观察能力，可以把 Manus 类产品的价值理解为：把通用模型、浏览器/代码/文件工具、长任务执行、产物交付和用户可见进度整合成完整产品体验。其创新未必是某个单独算法，更可能是系统工程与交互闭环：用户给目标，Agent 在云端环境持续工作，最后交付文件、网页或研究结果。

必须明确：关于其模型编排、训练数据、内部 planner、sandbox 和 memory 的具体实现，若没有官方公开证据，都只能是架构推断，不能陈述为内部事实。

从可复用的设计原则看，重点是：

- 任务以 artifact 和验收标准结束，而不是以聊天文本结束；
- 长运行有可观察进度、可中断、可恢复；
- 工具环境与用户设备隔离；
- Agent 能根据真实执行反馈自纠；
- 产品隐藏多模型和基础设施复杂度，但保留关键审批。

## 15.6 如果 Context Window 无限大，还需要 RAG 吗？

仍然需要。无限窗口只消除了容量上限，没有消除检索的其他职责：

- **权限过滤**：模型不应看到无权访问的数据；
- **新鲜度**：事实需要在查询时从权威源读取；
- **相关性与信噪比**：无限内容会增加干扰而非自动提高答案；
- **provenance**：需要知道结论来自哪个版本、哪段证据；
- **成本与延迟**：实际计算仍不是免费的；
- **删除与合规**：数据生命周期不能依赖模型“忘记”。

更准确地说，RAG 会从“绕过窗口限制”演化为 context query planner 和证据控制面。它可能动态决定读取数据库、搜索、知识图谱、文件切片或缓存，而非固定向量 Top-K。

LeAgent 的 relevance-gated context source 和 `AgentMemory.recall()` 都体现了“按需组装工作集”；即使模型窗口变大，这种可解释、可审计的上下文选择仍有价值。

## 15.7 如果模型足够强，还需要 Planning 吗？

需要规划，但未必需要模型先输出一份冗长、静态、用户可见的计划。规划有三种形态：

- 隐式局部规划：每步根据最新观察选择下一动作；
- 显式动态计划：保留里程碑和依赖，执行后持续修订；
- 确定性 workflow：高风险步骤、审批和交付流程预先编码。

模型越强，简单任务越可以边做边想；但长时任务的资源协调、并发、预算、人工接口和跨进程恢复仍需要外部计划结构。静态 upfront planning 的风险是环境一变就失效，过度动态则难以估算成本和审计。

LeAgent 的合理分工是：`QueryEngine` 做局部 think-act，`WorkflowExecutor` 管全局 DAG 和并行依赖，checkpoint 保留暂停点，trace 检查计划偏离。Planning 是控制问题，不应被等同于一段自然语言。

## 15.8 Agent 的 Scaling Law 存在吗？

可能存在，但不是单一“参数越大，Agent 成功率越高”的平滑定律。Agent 是模型与环境组成的闭环，端到端成功率受多项乘法约束：

`P(success) ≈ Π P(step_i correct | history) × P(runtime reliable) × P(validation catches error)`

轨迹越长，单步小误差越容易累积；工具反馈、可恢复性和 verifier 又可能改变曲线。因此至少有四个 scaling 轴：

- 模型训练与测试时计算；
- 工具数量、质量和可观测反馈；
- rollout 数量、搜索宽度和 verifier 强度；
- 任务时长、状态容量和组织知识。

研究 Agent scaling law 时应固定工具与环境版本，按轨迹长度分桶，报告 pass@k、成本归一化成功率和恢复率，并警惕 benchmark contamination。LeAgent 的 trace 与多模型实验接口可提供模型、token、工具 span 和结果数据，但因果结论仍需随机分流和版本化评测。

## 15.9 Agent 未来会演化成什么形态？

可能从“聊天机器人加工具”演化为受治理的长期数字执行者：

- 多模态感知与多环境操作；
- 由短会话变为跨天、事件驱动的持续任务；
- 从单 Agent 变成专业 Agent 与 deterministic service 的组织；
- 从回答导向变为 artifact、业务状态变化和可验证结果导向；
- 从一次性 prompt 变为版本化 policy、memory、skill 和 eval；
- 默认最小权限、沙箱、审批、审计和成本配额。

Principal 级判断是：未来不太像一个“全能人格”，更像操作系统上的进程模型。每次运行有身份、能力、预算、状态、父子关系和生命周期；模型只是可热切换的计算资源。

LeAgent 的 `ExecutionRun`、`AgentRuntime`、`ToolExecutor`、`CheckpointStore`、`WorkflowExecutor` 和 trace 平面已经接近这种拆分，但多 worker 下的 durable run registry、分布式 event bus 和更强资源隔离仍是平台演进重点。

## 15.10 AI Agent 的护城河在哪里？

基础模型和通用 ReAct loop 会逐渐商品化。可持续护城河通常来自组合：

1. **高价值工作流与分发**：嵌入真实业务系统，拥有触发点和交付渠道；
2. **专有反馈闭环**：积累可合法使用的任务、轨迹、失败和人工修正；
3. **工具与权限图谱**：对企业系统语义、身份和副作用有深度集成；
4. **可靠性工程**：评测、恢复、审计、SLO 和安全认证；
5. **组织记忆**：版本化事实、流程和决策，而非简单向量库；
6. **切换成本**：来自可验证的业务成果与治理集成，不应来自数据绑架。

反过来，prompt 模板、模型 API 转发和炫酷 Demo 都是弱护城河。平台应保持 provider abstraction，避免把自己的差异化错误地绑定在某个暂时领先的型号上。

## 15.11 设计 OpenAI Deep Research

以下是基于公开产品形态与通用研究系统的设计，不代表 OpenAI 内部架构。

**目标与 SLO：**输入开放研究问题，输出带逐项引用的报告；核心 SLO 是事实正确、引用支持、来源覆盖、时效和预算内完成。

**架构：**

1. Intake 将问题规范化为范围、时间、地区、来源限制和交付格式；
2. Planner 生成研究树和 claim checklist；
3. Search workers 并行查询网页、文件和结构化数据；
4. Extractor 将来源转换为 `{claim, evidence_span, url, timestamp}`；
5. Evidence graph 合并重复来源、标注依赖与冲突；
6. Gap analyzer 选择下一轮最高信息增益查询；
7. Synthesizer 只基于证据图撰写；
8. Citation auditor 检查 entailment、引用位置和来源质量；
9. Human gate 处理医疗、法律、金融等高风险输出。

可用强推理模型做 planner/冲突分析，快速模型做抽取与去重，视觉模型处理图表/PDF。LeAgent 中可用 task routing 实现 multi-model tier，用 `WorkflowExecutor` 并行研究分支，用 Agent 节点动态扩展查询；所有来源和模型调用进入 trace，checkpoint 支持长任务恢复。

关键权衡：搜索广度与成本、来源多样性与质量、实时性与可复现性。缓存必须带抓取时间和内容哈希；被引用内容应保留允许范围内的快照或证据片段。

## 15.12 设计 Claude Computer Use

以下设计依据公开的 Computer Use 交互范式和通用 GUI Agent 架构，不代表 Anthropic 内部实现。

**控制环：**截图/可访问性树 → 感知与目标定位 → 提议鼠标键盘动作 → policy gate → 在隔离桌面执行 → 获取新观察 → 验证状态变化。

**关键组件：**

- VM/container 隔离的浏览器或桌面，每任务独立身份与文件空间；
- 视觉模型结合 OCR、DOM/AX tree，坐标统一到稳定 viewport；
- 动作集合限制为 click/type/scroll/key/screenshot，并带前置条件；
- 凭证 broker 只在允许域名和字段注入秘密，模型永远看不到明文；
- 下载、上传、支付、发送、删除等动作触发审批；
- 每步截图、动作、目标元素和结果写 trace，可回放但需脱敏。

GUI 操作脆弱且慢，能调用 API 时优先 API；Computer Use 是兼容无 API 系统的最后一公里。失败恢复应基于“页面是否达到预期状态”，而不是机械重放坐标。LeAgent 可把 GUI 操作封装为受控工具，由 `ToolExecutor` 承担权限/超时，`QueryEngine` 处理观察自纠，checkpoint 在验证码或审批处暂停。

## 15.13 设计 Cursor Agent

以下是依据公开可观察的 IDE Agent 能力和通用 coding-agent 架构进行的设计，不代表 Cursor 内部实现。

**核心闭环：**理解用户意图 → 构建代码库上下文 → 提出/应用最小变更 → 运行诊断与测试 → 根据失败修正 → 展示 diff 和证据。

**架构要点：**

- Repository index：符号、引用、文件摘要和语义检索，增量更新；
- Context planner：结合打开文件、诊断、git diff 和任务选择最小相关上下文；
- Edit engine：优先结构化 patch，检测 stale context 与冲突；
- Tool sandbox：搜索、读取、编译、测试、git 操作分级授权；
- Model routing：快速模型做补全/检索，强模型做跨文件设计和调试；
- Checkpoint/undo：每个编辑批次可恢复，用户改动永不被静默覆盖；
- Eval：repo-level issue、build pass、test pass、diff quality 与人工接受率。

Principal 级风险是本地代码、密钥、命令执行和供应链。默认应只读探索，写入限定 workspace，网络和 destructive git 命令单独审批。LeAgent 的 coding project/file/code 三层边界、`ToolRegistry/Executor` 和单 `run_loop` 可作为类似系统的 runtime 基础。

## 15.14 设计 Devin

以下是依据公开展示的自主软件工程 Agent 形态和通用架构推断，不代表 Devin 内部实现。

目标不是“生成代码”，而是完成 issue 的软件交付闭环：理解仓库、制定里程碑、修改代码、运行测试、查看应用、处理反馈并交付可审查变更。

建议架构：

- 每任务一个可持久化 dev sandbox，包含 shell、编辑器、浏览器和端口代理；
- issue parser 生成验收标准、未知项和风险；
- coding Agent 维护工作树状态，不把完整终端日志塞回上下文；
- test/debug loop 将失败归因到代码、环境、依赖或 flaky test；
- milestone checkpoint 支持跨小时恢复；
- PR gate 检查测试、lint、安全、变更范围和用户未提交改动；
- 人在环节点处理需求歧义、架构选择、凭证和生产操作。

关键权衡是自治时长与错误漂移。应按阶段设置 budget，并在连续无进展、diff 过大或测试恶化时停止。LeAgent 可让 `AgentRuntime` 负责开放式 coding loop，让 `WorkflowExecutor` 固化“准备环境—实现—验证—审查—交付”，trace 关联 shell/tool/subagent，checkpoint 保存可继续的消息与任务元数据。

## 15.15 设计一个企业级 Agent Platform

先区分控制面与数据面。

**控制面：**Agent/工具/模型注册，版本化 prompt 与 policy，租户配置，身份权限，预算，发布审批，eval gate，审计和密钥管理。

**数据面：**接收 chat/API/cron/event ingress，创建 execution run，组装上下文，路由模型，执行工具/workflow，持久化状态，流式返回事件。

关键不变量：

- 每次执行有全局 `run_id`、tenant、user、agent version 和 policy version；
- 模型不能绕过 ToolExecutor 访问外部副作用；
- transcript、checkpoint、workflow state、trace、memory 各有唯一 owner；
- 所有外部写操作可审计，关键操作可审批、幂等或补偿；
- provider 可替换，能力与任务路由不依赖品牌字符串。

LeAgent 的 `ServiceManager.runtime_context` 已集中装配 registry/executor/hooks/checkpoint/session/memory/LLM，所有 ingress 汇入 SDK kernel。企业化扩展应优先补充分布式 run store/event bus、KMS、租户隔离、配额、数据区域、策略即代码和灾难恢复，而不是再造第二套 Agent loop。

组织上要设平台 paved road，同时允许领域团队注册工具和 AgentDefinition；平台团队负责协议与治理，领域团队对业务 eval 和工具语义负责。

## 15.16 如何建设 Agent Evaluation 平台？

Eval 平台应覆盖四层，而不是只做最终答案打分：

1. **单元层**：tool schema、参数解析、router、memory recall、policy；
2. **轨迹层**：工具选择、步骤数、重试、无效循环、引用与恢复；
3. **任务层**：真实环境中的结果、artifact 和状态变化；
4. **系统层**：延迟、成本、安全、稳定性和人工介入率。

数据集包含黄金任务、历史匿名失败、对抗样本和环境仿真；每个 case 固定输入、初始状态、允许工具、验收器和风险标签。优先使用确定性 verifier（测试、SQL、文件 diff、API 状态），LLM judge 只用于难以形式化的维度，并做校准、双盲和人工抽检。

发布流程应支持 baseline、candidate、分层报表、置信区间、回归阈值和 canary。模型、prompt、tool、policy、数据集都要版本化，不能只记录“用了 GPT/Claude”。

LeAgent 的 trace span、按模型统计和 experiment API 可作为数据源；还应把 checkpoint resume success、workflow node 结果、`AgentMemory` 命中与污染率纳入评测。离线指标最终需与线上业务 KPI 对齐。

## 15.17 如何建设 Agent Observability 平台？

Observability 要回答四个问题：它在做什么、为什么这样做、花了多少、哪里失败。建议采用 logs + metrics + traces + replay：

- trace 根为 execution run，子 span 包含 LLM、tool、workflow node、subagent、memory recall 和 compact；
- metrics 包含成功率、P50/P95/P99、TTFB、token/成本、工具错误、重试、暂停和人工接管；
- logs 保留结构化事件与 correlation ID；
- replay 保存可允许范围内的版本、输入摘要、动作与 observation，但秘密和敏感 payload 默认不落盘。

采集必须 best-effort，不能因 trace store 故障阻塞 Agent；高基数字段不应进入 metric label。采样应风险感知：错误、高成本、高风险动作全采，普通成功运行抽样。数据保留、访问审计和删除请求是平台的一部分。

LeAgent 的 `TraceRecorder` 用 fire-and-forget、批量 flush、可选 preview/payload，`trace_id = run_id`；`TraceHook` 捕获 compact/subagent。需继续关注跨进程 context propagation、event ordering、掉数率和 trace 与业务结果的 join。

## 15.18 如何建设 Agent Runtime？

Runtime 是 Agent 的“进程与系统调用层”，不应只是 while loop。核心模块包括：

- ExecutionRun：身份、父子关系、scope、budget、deadline、cancel token；
- Context assembler：相关性门控、权限过滤、压缩与 token 预算；
- Model gateway：provider abstraction、能力校验、task routing、熔断与计费；
- Think-act kernel：单一状态机和统一事件协议；
- Tool executor：schema、权限、审批、超时、并发、幂等和 artifact；
- Checkpoint/resume：durable snapshot、版本迁移和 pause token；
- Scheduler：长任务、优先级、公平性和 backpressure；
- Observability/eval hooks：不能分叉主语义。

设计原则是“一条 canonical path”。聊天、SDK、任务、子 Agent 和 workflow Agent node 若各有一套循环，会产生无法统一修复的安全与恢复差异。

LeAgent 的 `leagent.sdk.kernel.loop.run_loop` 是单 kernel，`QueryEngine` 是每会话编排器，`ServiceManager.runtime_context` 是统一 wiring。当前架构下 in-process execution registry 与 event bus 在多 worker 部署时需要 sticky session；演进到分布式 runtime 时应把 run ownership、lease、事件序列和恢复协议持久化。

## 15.19 如何建设 Agent Memory Platform？

Memory Platform 不是一个 vector database。它至少包含：

- 工作记忆：当前运行的可丢弃 scratchpad；
- 情景记忆：过去发生过什么；
- 语义记忆：相对稳定的用户/组织事实；
- 程序记忆：哪些工具链在什么条件下有效；
- provenance 与治理：来源、时间、置信度、owner、TTL、删除状态。

写入管线需做 formation：抽取候选、敏感性检查、去重、冲突检测、置信度与批准策略。读取管线需做 scope filter、hybrid retrieval、rerank、时间衰减、冲突呈现和 token packing。高风险事实不应因模型重复一次就覆盖权威数据源。

多租户隔离必须在存储查询层强制，不依赖 prompt。embedding/model 升级需要双写或后台重建；向量服务故障应降级到词法/关系查询。还要评估 memory 的负收益：错误召回率、过期事实率、prompt 注入传播和因记忆造成的任务退化。

LeAgent 的 `AgentMemory` 以 episode/fact/procedure 三存储和 `RetrievalPipeline` 提供窄门面，并有 formation policy、写入健康和可选向量降级。平台化后应补充事实版本图、用户可见编辑/删除、跨区域策略和 memory eval。

## 15.20 如何建设 Agent Operating System？

“Agent OS”应被定义为一组资源与生命周期抽象，而不是营销名称。可以类比传统 OS：

- Process → `ExecutionRun`，有 PID 式 run_id、父子关系、状态和退出原因；
- Syscall → 受控工具调用；
- Scheduler → 模型、CPU、浏览器、沙箱与并发配额调度；
- Memory → context 工作集、durable memory 与 checkpoint；
- File system → versioned artifact、权限与 lineage；
- IPC → 类型化事件、消息队列与子 Agent 协议；
- User/kernel mode → 模型提议动作，runtime 验证并执行；
- Security principal → tenant/user/agent identity 与 capability token。

关键取舍是通用性与可治理性。若允许任意 Agent、任意工具、任意共享状态，平台会迅速失去隔离和可预测性；若所有流程都要求预定义，又退化成普通 BPM。合理方案是小而稳定的 kernel、版本化能力接口、领域扩展包，以及 Agent 自由度随风险动态收缩。

LeAgent 可作为这一方向的雏形：provider abstraction 是可替换计算设备，`QueryEngine/run_loop` 是执行 kernel，`ToolRegistry/Executor` 是 syscall table，checkpoint 是进程快照，trace 是审计/调试，`AgentMemory` 是长期知识层，`WorkflowExecutor` 是确定性调度器。

Principal 级路线图应优先解决：durable distributed run registry、租约与抢占、事件顺序、跨租户资源隔离、能力令牌、沙箱镜像供应链、全局成本调度和灾难恢复。只有这些不变量成立后，多 Agent 市场、自动技能学习等上层能力才值得扩展。
