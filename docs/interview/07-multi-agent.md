# 七、Multi-Agent

## 7.1 什么是 Multi-Agent？

**答：**Multi-Agent 是多个具有独立角色、上下文或能力边界的 Agent，为同一目标分工协作的系统。它不等于“多调用几次模型”：至少要有任务分解、职责边界、通信协议、调度策略和结果汇总。

通用实现通常包含协调器、Agent 注册表、消息或任务队列、共享状态、预算与终止条件。每个 Agent 可以拥有不同模型、Prompt、工具和权限，也可以只是同一运行时的不同配置实例。

**在 LeAgent 中：**通用子任务可通过 subagent fork 执行；子 Agent 使用独立会话历史、受过滤的工具注册表，并可继承父任务的取消信号。所有入口最终仍经过统一 `run_loop` think-act kernel。`ExecutionRun.run_id` 与 `parent_run_id` 表达父子执行关系，但它主要是关联和可观测性契约，不应被夸大为完整的分布式 Multi-Agent 编排平台。

## 7.2 为什么需要 Multi-Agent？

**答：**核心原因是隔离复杂度，而不是单纯追求“更多智能”。它适合：

- 将研究、编码、审查等异构任务交给不同角色；
- 缩短可并行子任务的关键路径；
- 用较小上下文减少相互干扰；
- 对高风险角色配置更窄的工具权限；
- 让产出经过独立检查或交叉验证。

代价是 token、延迟、状态同步和失败组合显著增加。若任务不可分、共享上下文高度耦合，多个 Agent 反而会重复读写和互相误导。

**在 LeAgent 中：**subagent 的独立历史和 scoped tool registry 可用于隔离；workflow DAG 可并行执行就绪节点并限制 `max_parallelism`。这两种能力可以支撑多角色协作，但“为什么拆分、如何分配”仍需要上层策略或显式工作流定义。

## 7.3 单 Agent 和 Multi-Agent 如何选择？

**答：**先判断任务是否存在清晰、低耦合、可验收的子任务。

- 选择单 Agent：任务短、上下文共享强、步骤频繁相互依赖、预算敏感；
- 选择 Multi-Agent：角色能力不同、子任务可并行、需要独立审查，或必须隔离权限；
- 折中方案：单 Agent 作为主控，仅在搜索面过大或需要专家能力时委派。

可用一个工程判据：并行节省的时间与专业化收益，是否大于协调、重复上下文和结果合并成本。上线前应以完成率、P95 延迟、token 成本、重复工具调用率做 A/B 测试，而非按架构潮流选型。

**LeAgent 对照：**默认路径是单一 `run_loop` 驱动一个 Agent；需要委派时使用 subagent，需要确定性依赖和并行时使用 workflow DAG。这是可组合能力，不代表每个请求都会自动转成多 Agent。

## 7.4 Supervisor 模式是什么？

**答：**Supervisor 是一个中心协调 Agent：理解总目标、拆分任务、选择 worker、检查中间结果，并决定继续、重试或结束。worker 通常只处理限定子任务并返回结构化结果。

关键设计包括：

1. Supervisor 维护任务账本和全局预算；
2. 每次委派包含目标、输入、允许工具、验收条件和截止时间；
3. worker 只返回证据与产物，不直接修改全局结论；
4. Supervisor 使用最大深度、最大委派数和终止状态防止递归。

**LeAgent 对照：**父 Agent 调用通用 subagent 可形成轻量 Supervisor；父子执行可用 `parent_run_id` 关联，子执行走同一 kernel。仓库没有宣称一个通用、自治的 Supervisor 调度器，复杂依赖更适合显式 DAG 或业务层协调。

## 7.5 Router 模式是什么？

**答：**Router 根据输入特征把请求发送给一个或少数专家，重点是“选路”，而不是持续管理全过程。路由可基于规则、分类模型、embedding、LLM 判断或历史质量/成本统计。

可靠 Router 应输出 `route + confidence + reason`，低置信度时回退到通用 Agent；还要限制 fan-out，防止每个问题都广播给全部专家。评估指标包括路由准确率、回退率、专家负载和端到端收益。

**LeAgent 对照：**可用工具或工作流条件节点实现路由，也可按 AgentDefinition、Prompt variant 和工具集实例化专家。LeAgent 的 relevance gate、模型能力路由等是相邻能力，但不等同于已经提供通用 Multi-Agent Router。

## 7.6 Manager-Agent 架构是什么？

**答：**Manager-Agent 架构把管理职责显式化：Manager 管目标、计划、资源、进度和验收，执行 Agent 负责产出。它与 Supervisor 接近，但更强调持久任务生命周期、资源分配和状态管理。

典型数据流是：用户目标 → Manager 建立任务图 → 分配 Agent → worker 写入任务结果 → Manager 验收/重排 → 汇总。生产实现应把任务状态持久化，而不能只存在 Manager 的上下文窗口中。

**LeAgent 对照：**Task system 提供后台任务、进度、取消和输出日志；workflow DAG 提供确定性的依赖调度；AgentRuntime 提供统一执行入口。可用这些模块构建 Manager-Agent，但现有 TaskHandler 本身是执行设施，不等同于自治 Manager。

## 7.7 Swarm 架构是什么？

**答：**Swarm 是去中心化或弱中心化的协作方式，Agent 根据局部状态相互交接、竞争或协商任务。它适合开放式探索和故障容忍，但全局一致性、可解释性和成本控制更难。

工程上仍需“最小中心”：任务租约、幂等键、共享黑板、心跳、全局预算和终止检测。否则容易出现两个 Agent 同时处理同一任务、消息风暴或无人负责最终答案。

**LeAgent 对照：**LeAgent 当前更接近父子委派与中心化 DAG 调度。`parent_run_id` 可表达谱系，但不提供去中心化共识、Agent 发现或 swarm membership，因此不应把现有能力描述为完整 Swarm。

## 7.8 Debate Agent 是什么？

**答：**Debate Agent 让多个 Agent 针对同一问题给出独立论证，再由裁判或聚合器比较证据。它适用于高不确定性推理、方案评审和事实核验，不适合每个普通请求。

好的 Debate 要求：

- 首轮独立作答，避免锚定；
- 后续只质疑可验证的假设和证据；
- 裁判看到来源、置信度与分歧，而非只看措辞；
- 设置固定轮数和“无新增证据即停止”条件；
- 对裁判也做偏差评估，必要时使用规则或外部测试。

**LeAgent 对照：**可用并行 workflow 节点运行多个 Agent 节点，再接聚合/评审节点；这是可构建模式，不是仓库默认启用的 Debate 协议。

## 7.9 Agent Collaboration 如何实现？

**答：**协作应围绕任务契约，而不是自由聊天。每个子任务至少包含：

```text
task_id、goal、inputs、allowed_tools、expected_output、
acceptance_criteria、deadline、budget、dependency_ids
```

执行过程采用“分解—认领—执行—提交证据—验收—重试/合并”。写操作应单写者或按资源加锁；只读研究可并行。结果最好是结构化数据和文件引用，避免把整段上下文反复复制。

**LeAgent 对照：**subagent 返回文本、成功状态、步骤数、活动和产物等结构；workflow DAG 表达依赖并并发运行 ready batch；统一 runtime wiring 提供工具、Memory、checkpoint 和 hook。跨 Agent 的业务级冲突合并策略仍需具体应用实现。

## 7.10 Agent Communication 如何设计？

**答：**常见通信模型有直接消息、发布订阅、任务队列和共享黑板。生产系统通常优先异步、结构化、可追踪的消息：

- envelope：`message_id/trace_id/sender/receiver/type/schema_version`；
- payload：任务、状态、证据或产物引用；
- delivery：至少一次投递配合幂等消费；
- ordering：只在同一任务或资源分区内保证；
- security：鉴权、最小披露、敏感字段脱敏；
- observability：记录延迟、重试、因果关系。

**LeAgent 对照：**AgentEvent 是运行时统一事件形态，`run_id/parent_run_id` 用于关联，EventManager 传播生命周期事件。subagent 目前主要以调用—返回方式通信；这不等于具备跨进程 Agent 消息总线。

## 7.11 多 Agent 如何共享 Memory？

**答：**不要让所有 Agent 无限制共享全部上下文。通常分三层：

1. 私有工作记忆：单 Agent 的推理草稿和临时状态；
2. 任务共享记忆：结构化事实、任务账本、产物引用；
3. 长期组织记忆：经验证、带来源和权限标签的知识。

共享写入要带 `author、source、timestamp、confidence、scope、version`，通过事件或版本控制解决冲突；检索时按用户、任务、租户和角色做 ACL。未经验证的模型结论不应直接成为全局事实。

**LeAgent 对照：**LeAgent 有 session transcript、AgentMemory 与 working scratchpad 等不同状态面；subagent 默认新建对话历史，但共享父级文件状态缓存。哪些记忆允许跨 Agent 写入应由 Memory policy 和业务权限决定，不能仅靠共享对象自动保证一致性。

## 7.12 多 Agent 如何避免死循环？

**答：**需要同时限制图、时间和预算：

- 委派深度、每 Agent turn 数、总工具调用数；
- wall-clock timeout、token/金额预算；
- 禁止或严格限制子 Agent 再次委派同类任务；
- 每轮必须减少未完成任务或产生新证据；
- 对重复状态计算摘要哈希，连续命中则终止；
- `completed/failed/blocked/cancelled` 使用显式终态。

**LeAgent 对照：**运行配置支持 max turns、工具调用和超时预算；取消信号可传给子 Agent；workflow 有总超时、并行上限，并仅对明确允许的节点支持有界回边。checkpoint 原因也可暴露 `max_turns`、预算超限等可恢复终止，但系统仍需要调用方决定是否恢复，不能无限自动重试。

## 7.13 多 Agent 如何避免重复工作？

**答：**关键是持久任务账本和幂等性：

- 分解时给任务稳定 `task_id` 和输入摘要；
- worker 通过租约原子认领任务；
- 提交结果使用幂等键，重复提交不产生副作用；
- 共享“已查来源、已生成产物、已修改资源”索引；
- 调度前检查缓存与正在进行的相同任务；
- 写操作按文件、记录或业务实体划分 ownership。

语义相似不能直接等价于任务相同；高风险写操作应使用精确输入版本和资源版本判断。

**LeAgent 对照：**workflow 的节点依赖、状态和输出缓存可减少恢复时的重复节点执行；subagent 可返回 changed files/produced files 供父 Agent 汇总。通用跨请求语义去重和分布式租约并非由 subagent 自动提供。

## 7.14 多 Agent 如何调度？

**答：**调度可分为三层：任务图决定先后关系，资源调度决定在哪运行，Agent 策略决定交给谁。常用策略包括 FIFO、优先级队列、关键路径优先、能力匹配、成本感知和公平配额。

调度器应考虑依赖、并发配额、模型限流、工具互斥、租户公平、失败重试和取消传播。长任务采用 durable queue + lease；进程内 `asyncio` 只适合单进程局部并发。

**LeAgent 对照：**WorkflowExecutor 会分批 stage 当前 ready 节点，以 `max_parallelism` 限制并发；Task system 承载后台 Agent/Workflow 任务；所有 Agent 路径经 AgentRuntime/`run_loop`。默认 SQLite 与进程内运行注册表适合本地单进程，若做分布式多 worker 调度，还需外部队列、分布式租约和持久 run registry。

## 7.15 多 Agent 的成本如何控制？

**答：**成本控制必须在调用前、调用中和调用后闭环：

- 调用前：只在收益明确时拆 Agent，选择合适模型，裁剪上下文，限制 fan-out；
- 调用中：设置每任务 token、工具、时间、并发和递归预算，低价值分支提前停止；
- 调用后：记录每个 `run_id` 的 usage、缓存命中、重复调用和结果质量，按任务类型优化路由。

可将预算分配给父任务，再由父任务为子任务预留额度；任何子 Agent 超支都应返回结构化原因，而非静默继续。Debate、Swarm 等模式尤其要用固定轮数和边际收益终止。

**LeAgent 对照：**runtime profile 可限制 turn、工具超时等，run event 携带 usage，`parent_run_id` 可用于归集父子执行成本；workflow 控制并发与总超时。完整的租户账单、分布式全局预算和自动成本最优路由仍属于需要在部署层补充的能力。
