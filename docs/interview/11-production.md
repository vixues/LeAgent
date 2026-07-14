# 十一、Agent Production

## 11.1 Agent 上线后监控什么？

上线后应从结果、链路、依赖和安全四层监控：

- **结果**：任务成功率、部分完成率、人工接管率、用户重试/撤销率。
- **链路**：端到端 P50/P95/P99、首 token 时间、LLM/工具调用次数、各阶段耗时、队列深度。
- **依赖**：模型错误、限流、超时、fallback、熔断状态，工具/API/数据库可用性。
- **资源与成本**：输入/输出 token、缓存命中、单任务费用、工具费用、并发和存储增长。
- **安全**：认证失败、403、限流、审批触发/拒绝、沙箱拒绝和异常文件访问。

监控必须按模型、provider、任务类型、工具、版本、用户层级和风险等级切片。聚合指标用于发现异常，Trace 用于解释单个异常，结构化日志用于检索上下文，三者不能互相替代。

LeAgent 的 Prometheus 指标已覆盖 HTTP、LLM、工具、Agent、工作流、session、memory、database、cache 和 sandbox；EventManager 发布 `FLOW_*`、`TASK_*`、`AGENT_*` 生命周期事件；持久 Trace 保存延迟、token、成本、调用数和 span 树。生产告警可围绕成功率、P95、错误率、队列深度和单位成功成本建立 SLO。

## 11.2 如何记录 Trace？

一条可调试的 Agent Trace 应包含：

1. 根运行标识和父子关系：`trace_id/run_id`、`parent_run_id`、session、user、scope。
2. 有序 span：LLM、工具、审批、压缩、子 Agent、错误的开始/结束、状态和耗时。
3. 资源统计：token、成本、调用次数、模型/provider、缓存读写。
4. 终止状态：完成、超时、错误、等待用户，以及错误分类。
5. 受控 payload：默认只存摘要或哈希，完整输入输出需要显式开关、脱敏、权限和保留期。

LeAgent 在 `begin_execution`/`end_execution*` 建立和关闭根 `agent` span，`run_loop` 从统一 `AgentEvent` 追加 tool/result/error span，`TraceHook` 记录 compact/subagent 边界，LLM 请求日志再关联 `run_id` 并写 `llm` span。Recorder 采用 best-effort、fire-and-forget 和批量落库，避免追踪故障阻塞执行热路径。

当前配置默认启用 Trace，但 `capture_payloads` 默认关闭；preview 也有独立开关和长度上限。完整 payload 可写到 trace 目录并由 `payload_ref` 引用。Trace API 支持列表、过滤、span 树、JSONL 导出、按模型统计和同提示词实验。文档中配置的 retention days 是计划保留参数，清理任务仍待完善，因此生产环境必须另行落实生命周期删除。

## 11.3 LangSmith 是什么？

LangSmith 是 LangChain 团队提供的外部 LLM/Agent 工程平台，公开能力主要围绕运行追踪、数据集、评测、Prompt/实验和线上观测。它适合希望快速获得托管式 Trace UI、评测工作流和团队协作能力的项目；选型时要评估数据驻留、费用、供应商绑定、SDK 接入和敏感 payload 合规。

LeAgent 当前没有把 LangSmith 作为规范运行平面，而是使用自有 `leagent.telemetry.trace`、Trace API/UI、Prometheus 和 OpenTelemetry。两者可以从职责上对照：

- LangSmith 提供外部产品化观测与评测体验。
- LeAgent 的持久 Trace 更贴合自身 `ExecutionRun`、tool、approval、compact、subagent 语义。
- OTel 提供厂商中立的跨服务 span/metric 导出，便于接入 Collector 和现有 APM。

若要同时接入 LangSmith，应避免双重埋点造成重复计费和 ID 割裂，并以 LeAgent 的 `run_id/parent_run_id` 为统一关联键；还要在发送外部平台前执行脱敏和用户授权。

## 11.4 OpenTelemetry 如何接入？

标准接入步骤是：

1. 在服务入口配置 `service.name`、环境、采样率和 OTLP endpoint。
2. 初始化 `TracerProvider`、批量 span exporter；需要时初始化 metric exporter。
3. 自动 instrument HTTP、数据库、Redis/gRPC，再对 LLM、工具、工作流等业务边界手工建 span。
4. 通过 W3C Trace Context 或等价传播机制跨 HTTP、队列和子任务传递上下文。
5. 控制属性基数与敏感数据，建立 head/tail sampling 和错误全采样策略。

LeAgent 的 `setup_otel()` 使用 `Resource` 写入 service name 与 deployment environment，使用 `TraceIdRatioBased` 采样、`BatchSpanProcessor` 和 gRPC `OTLPSpanExporter`；`OTEL_EXPORTER_OTLP_ENDPOINT` 指定 Collector，`OTEL_EXPORTER_OTLP_INSECURE` 控制非 TLS 连接。metrics 可通过 `PeriodicExportingMetricReader` 导出。FastAPI、SQLAlchemy、Redis 和 gRPC 的 instrumentation 在相应可选包存在时启用，不存在则降级为 no-op。

业务层的 LLM service/transport、QueryEngine、ToolExecutor 和 workflow executor 已创建 OTel span。结构化日志处理器会在当前 span 有效时注入 OTel `trace_id` 和 `span_id`。需要区分：LeAgent 持久 Trace 的 `trace_id` 约定为 `run_id`，OTel 自身也有标准 trace/span ID；两套数据通过运行关联字段和日志上下文对齐，而不是假设其底层 ID 格式完全相同。

## 11.5 如何定位 Agent Bug？

建议按“结果 → 首个异常 span → 输入证据 → 状态所有者”逆向定位：

1. 用 session、run、模型、时间和错误过滤 Trace，先确认终止原因。
2. 在 span 树中找到第一个错误或明显超时，而不是只看最后一个报错。
3. 检查该步输入、工具 schema、输出摘要、审批和前后模型调用。
4. 根据状态类型查看唯一所有者：聊天历史看 `TieredSessionStore`，Agent 暂停看 `CheckpointStore`，工作流运行看 `WorkflowStateStore`。
5. 用相同 prompt、配置和工具桩回放；外部环境不可固定时，使用已记录结果模拟。
6. 将根因归类为模型、Prompt、检索、工具、权限、状态、并发或依赖故障，并补回归样本。

LeAgent 的 Trace 瀑布图和 JSONL 导出适合还原单次执行；EventManager 的生命周期事件说明运行发生了什么，OTel 说明跨组件时间花在哪里，Prometheus 判断它是个例还是系统性回归。`run_id`、`parent_run_id`、`session_id` 和 `prompt_id` 可关联聊天、子运行和工作流。

注意 Trace 捕获是 best-effort，缺少 span 不必然表示业务步骤未执行。还应交叉检查结构化日志、数据库状态和工具真实副作用。

## 11.6 如何降低 Token Cost？

主要手段包括：

- 缩短 always-on system prompt，把大体积领域说明改成按相关性加载。
- 检索只返回足够的 top-k 证据，并压缩重复片段和大型工具结果。
- 对长会话做分层摘要，保留近期关键消息和不可丢约束。
- 按任务路由模型：标题、压缩等简单任务使用更便宜/更快的模型。
- 限制 `max_tokens`，要求结构化、短答案，避免失败后的无界重试。
- 统计输入、输出、cache-read 和 cache-miss token，以单个成功任务成本优化。

LeAgent 的 context pipeline 使用 recipe 与 `RelevanceGate`，重型 canvas/chart/document/email/art 指南按查询或 opt-in 加载；query 路径包含 microcompact、渐进压缩和 autocompact，并按模型上下文窗口选择阈值。`TaskResolver` 对 FAST、COMPRESSION、TITLE 等逻辑任务设置更小预算，并通过 `clamp_max_tokens` 防止超过模型上下文。

优化后必须做质量回归。简单删上下文可能降低单次 token，却提高重试和失败率，最终使 cost per successful task 更高。

## 11.7 如何减少 Tool Cost？

先对工具建立成本模型：调用价格、平均延迟、限流、失败概率和副作用风险。然后：

- 调用前验证参数和前置条件，减少必然失败的请求。
- 合并批量查询，避免 N+1；相互独立的只读调用可并行。
- 对幂等、稳定结果使用带 TTL 和版本键的缓存。
- 先用廉价本地索引/元数据过滤，再调用昂贵外部 API。
- 为每轮设置调用预算，对重复同参调用、循环和低收益工具触发停止条件。
- 有副作用的工具不要盲目自动重试；使用幂等键和审批。

LeAgent 的工具指标记录每个 `tool_name` 的调用量、失败类型和耗时，Trace 记录每次 tool span，适合找出高频、慢和重复调用。Workflow engine 能并发执行独立分支，并对节点输出提供 input-signature cache；但该缓存只适用于满足幂等和签名正确性的节点，不能泛化为所有外部工具结果缓存。

## 11.8 如何减少推理次数？

减少推理次数的关键是降低不必要的 think-act 循环：

- 让工具返回结构化且足够完整的结果，避免模型反复追问。
- 对固定业务流程使用 DAG/模板，而非每一步都让模型重新规划。
- 将独立工具并行执行，聚合后一次交给模型。
- 设置最大迭代、token 和时间预算，检测同工具同参数循环。
- 在执行前做 schema 校验和确定性路由；简单任务直接走专用逻辑。
- 对可恢复的人机交互保存 checkpoint，不要用户回复后从头推理。

LeAgent 把聊天步骤卡编译成线性 `WorkflowDocument`，并与保存的 DAG 共享 `WorkflowExecutor`；固定流程因此不必每步重新规划。Agent 配置有 `max_iterations`，query loop 具有明确的终止/继续原因。等待用户时，规范 `run_loop` 保存消息、usage 和 turn 到 CheckpointStore，恢复时延续状态。

降低轮次不能以跳过验证为代价。应同时观察成功率、平均 LLM 调用数和每成功任务成本。

## 11.9 如何做 Cache？

Cache 设计首先回答五个问题：缓存什么、键是什么、何时失效、允许多旧、谁可访问。常见层次包括模型响应、embedding、检索结果、工具结果、工作流节点输出和静态 Prompt 片段。

安全的 key 通常包含规范化输入、模型/Prompt/工具版本、租户或用户作用域、权限、数据版本和影响输出的配置。带副作用、强实时、权限敏感或非确定性结果默认不缓存。必须监控 hit/miss、陈旧命中、节省成本和缓存导致的错误。

LeAgent 当前明确实现的是工作流节点输出缓存：`classic`、`lru`、`ram`、`hierarchical` 和 `none` 模式；`CacheKeySetInputSignature` 把直接输入、上游签名和 `IS_CHANGED` 纳入哈希，非幂等节点另作处理。基础缓存还可快照/恢复以支持持久工作流 resume。Prometheus 定义了通用 cache hit/miss、entry 和 size 指标。

这不代表 LeAgent 已实现通用 LLM 响应缓存。生产接入模型缓存时仍需补齐 TTL、用户隔离、Prompt/模型版本和敏感数据策略。

## 11.10 Semantic Cache 是什么？

Semantic Cache 不按完全相同的 key 命中，而是对请求做 embedding，在向量空间寻找语义相近的历史请求，并在相似度、作用域和策略满足时复用答案。它可提高自然语言变体的命中率，但比精确缓存风险更高。

关键设计包括：

- 相似度阈值必须按任务校准，“退款政策”和“替我退款”语义相关但动作完全不同。
- key/过滤条件要包含用户、权限、语言、时间、模型和知识版本。
- 只缓存可复用的只读回答；个性化、实时数据和副作用请求默认禁用。
- 命中后仍可做轻量验证，并保留来源、年龄和置信度。
- 评测误命中率、漏命中率、成本节省和安全泄漏率。

LeAgent 有向量/词法 memory recall，但 Memory recall 不等于 Semantic Cache：前者把相关记忆作为上下文，后者直接复用历史响应。当前仓库没有通用 Semantic Cache 实现；若新增，应作为独立能力设计，不能把 memory 命中直接当作可返回答案。

## 11.11 如何保证 SLA？

保证 SLA 需要从目标倒推预算与降级策略：

1. 定义 SLI/SLO：可用率、端到端 P95/P99、TTFB、成功率和数据正确性。
2. 将总时延预算分配给排队、模型、工具、数据库和输出。
3. 对每个外部调用设置 timeout、有限重试和指数退避，并配置全局 deadline。
4. 使用并发隔离、限流、背压、熔断和容量规划，避免雪崩。
5. 建立 fallback、只读/简化模式和人工接管。
6. 用 checkpoint 和幂等机制恢复长任务；用演练验证，而非只写预案。

LeAgent 的 TaskBinding timeout 在非流式调用上由 `asyncio.wait_for` 统一执行，流式调用使用 per-chunk stall timeout；可重试错误有有限重试和退避。provider circuit breaker、fallback chain、工具/工作流超时、队列深度指标和 SQL checkpoint 共同提升可靠性。

但 checkpoint 解决的是可恢复性，不等于高可用。默认 SQLite 应保持单 worker；多 worker 需 PostgreSQL 和粘性会话，因为 `ExecutionRunRegistry` 与审批热状态当前是进程内的。生产 SLA 还需负载均衡、持久队列、备份、容量测试和灾备。

## 11.12 如何处理模型降级？

模型降级有两类：供应商故障降级和能力/成本降级。策略应为每个逻辑任务定义候选链，并明确：

- 哪些错误可降级：超时、限流、网络、服务端错误、模型不可用。
- 哪些错误不应降级：坏请求、非法 schema 等客户端错误应立即修复。
- 替代模型是否支持图像、工具调用、上下文窗口和结构化输出。
- 降级后是否降低质量、关闭非关键功能或请求用户确认。
- 如何记录原 provider、fallback provider、失败原因和质量变化。

LeAgent 的 `TaskResolver` 为逻辑任务解析 primary，并在 `routing.failover.enabled` 时按 `fallbacks` 生成候选，数量受 `failover_max_retries + 1` 限制。错误经 `classify_llm_error` 决定是否可重试/切换；registry 会跳过不可用或熔断打开的 provider。

流式调用有重要边界：若已经向用户产出 chunk，再切模型会造成内容拼接和重复，因此当前实现一旦 `yielded` 后失败就抛错，不继续 fallback；只有首 chunk 前的可重试故障才安全切换。

## 11.13 如何实现 Fallback？

一个可靠的 Fallback 流程是：

1. 按任务能力过滤候选，再按优先级排序。
2. 给 primary 设置 timeout，统一分类错误。
3. 只对 retryable 故障尝试下一个候选，并限制总次数和总 deadline。
4. 对每次失败记录 provider、模型、分类和耗时；成功后标记实际使用模型。
5. 验证备用模型输出契约，尤其是 tool schema 和结构化 JSON。
6. 没有候选时返回明确的可恢复错误，而不是静默伪造结果。

LeAgent 的 `LLMService._complete_resolved()` 遍历 `candidate_providers()`，先检查 circuit/availability，再调用 provider；成功调用 `record_success`，计入 provider 的失败调用 `record_failure`，不可重试错误立即抛出。外层 transient retry 最多尝试三次并指数退避，限流可尊重 `retry_after`。

应注意“同 provider 重试”和“跨 provider fallback”是两层机制，配置不当会放大调用次数。SLA 设计必须限制两层组合后的最坏时延和费用。

## 11.14 如何实现 Circuit Breaker？

Circuit Breaker 通常有三态：

- **Closed**：正常放行并统计请求。
- **Open**：失败达到阈值后暂时拒绝，避免持续打击故障依赖。
- **Half-open**：冷却后放少量探测；连续成功则关闭，失败则重新打开。

LeAgent 为每个 provider 维护内存熔断器。默认连续失败阈值为 4；累计请求至少 10 且错误率达到 0.6 也会打开；60 秒后转为 half-open，连续成功 2 次后关闭。registry 的可用性检查和路由会跳过 open provider，并可向 API/UI 暴露 snapshot。

生产中还需考虑窗口衰减、half-open 并发上限、错误权重和多实例共享。LeAgent 当前熔断状态是进程内的，各 worker 不共享；多实例部署若要求全局一致熔断，需要外部状态或服务网格支持。

## 11.15 如何做灰度发布？

灰度发布应把少量、可识别的流量稳定分配到候选版本，并设置自动回滚护栏：

- 按 user/session 哈希做粘性分桶，避免同一会话来回切换。
- 同时版本化模型、Prompt、工具 schema、检索配置和 Agent 定义。
- 先 shadow/offline replay，再 1% canary，逐步扩大。
- 比较成功率、P95、单位成功成本、安全事件和人工接管率。
- 预先定义最小样本量、显著性标准和回滚阈值。
- Trace 写入版本、cohort 和实验标签，确保可归因。

LeAgent 的 Trace 模型支持 `experiment_id`、tags、`prompt_hash` 和同提示词多模型对比，可作为离线/shadow 比较的数据基础；EventManager、Prometheus 和按模型 trace stats 可观察候选表现。

当前仓库没有完整的在线流量分桶、渐进放量和自动回滚控制器，因此不能把 Trace experiments 说成已实现灰度发布。生产落地还需网关或特性开关系统负责分桶，并把 cohort/版本传入 `ExecutionRun` 和 Trace。
