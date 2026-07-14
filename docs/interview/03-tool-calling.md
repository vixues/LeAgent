# 三、Tool Calling

## 3.1 Function Calling 原理是什么？

Function Calling 是让模型在普通文本之外生成结构化的“函数名 + 参数”。应用把可用函数 schema 随上下文发给模型，模型选择调用后，运行时解析、校验并执行真实函数，再把结果作为工具消息返回模型。模型只提出调用意图，不直接执行代码。

LeAgent 的 `BaseTool.to_openai_schema()` 生成 function schema，`ToolRegistry` 负责暴露，`ToolExecutor` 执行调用，结果再由查询循环追加为 `tool` 消息。

## 3.2 OpenAI Tool Calling 如何工作？

请求在 `tools` 中传入一组 `type: function` 定义，并可通过 `tool_choice` 允许自动选择、禁止、强制至少一个或指定函数。模型返回带唯一 ID 的 `tool_calls`；应用必须逐个执行，并以匹配 `tool_call_id` 的 tool 消息回传，然后再次请求模型生成后续调用或最终答案。

LeAgent 的 OpenAI provider 按该格式构造请求；查询循环保留调用 ID 和原始顺序，确保工具结果与 assistant 的 tool calls 正确配对。

## 3.3 Tool Schema 为什么重要？

Schema 是模型理解工具能力和运行时验证输入的共同契约。模糊 schema 会增加误选、漏参和类型错误；过宽 schema 会把歧义推迟到执行阶段，也扩大攻击面。名称、描述、类型、必填项和限制必须一致。

在 LeAgent 中，`parameters` 是唯一权威定义，不允许依赖静默别名修正。注册表还要求工具名、描述和顶层 `type: object` 合法。

## 3.4 JSON Schema 有什么作用？

JSON Schema 用机器可读方式描述对象结构、字段类型、必填项、枚举、范围、嵌套结构和额外字段策略。它既帮助模型构造参数，也让执行器在产生副作用前拒绝非法输入；但它不能替代文件存在性、业务权限等语义校验。

LeAgent 先检查未知键和按 operation 条件必填字段，再调用 `jsonschema.validate()`；工具还可通过 `validate_input()` 实施语义检查，通过 path sandbox 检查路径权限。

## 3.5 Tool Description 应该怎么写？

应说明“何时使用、完成什么、何时不要使用、关键输入和结果含义”，使用具体动词和领域术语，避免多个工具出现近义且无边界的描述。副作用、前置条件和限制应明确，但不要把整份操作手册塞进描述。

LeAgent 还提供 `search_hint` 参与工具检索与排序，因此 description 面向模型决策，search hint 可补充用户常用关键词。

## 3.6 Agent 如何选择 Tool？

模型综合用户目标、system 指令、对话历史、候选工具名称、描述和 schema 预测下一动作。应用可先通过策略或检索缩小候选集，再用 `tool_choice` 控制模型是否可调用或必须调用。

LeAgent 先应用 `AgentDefinition.tools` 的 allow/deny，再由 `ToolRegistry.get_tools_for_llm()` 按上下文关键词选择 Top-N，并保留核心工具和必要伴随工具。

## 3.7 Tool Selection 错误怎么办？

先判断是候选集过大、工具描述重叠、上下文缺失还是模型能力不足。优化名称和边界描述，增加负例，按领域缩小工具池；执行后若发现工具不适用，应返回明确、可纠正的错误，而不是伪成功。

LeAgent 对未找到或禁用工具返回失败 `ToolResult`，结果进入下一轮供模型纠正；allow/deny、类别和上下文排序可从源头减少冲突。

## 3.8 Tool 参数填错怎么办？

必须先解析，再做 schema、业务和权限校验；错误信息应指出错误字段、期望类型或规范键，让模型只修正参数后重试。不要自动猜测高风险字段，也不要为历史错名长期保留隐式别名。

LeAgent 会拒绝未知键、缺失的条件字段和 JSON Schema 违规，并建议规范键。畸形 JSON 只做保守恢复，`recover_raw_args()` 也只提取 schema 中的规范键。

## 3.9 Tool 返回异常怎么办？

统一使用包含 success、data、error、duration 和 metadata 的结果信封，区分业务失败与执行器异常；记录可诊断信息，但向模型和日志暴露数据时应脱敏、限长。上层根据错误类型决定重试、换工具、澄清或终止。

LeAgent 使用单一 `ToolResult`；失败会序列化为明确错误并回到模型，超大结果按工具预算截断，执行指标与 trace 记录耗时和成功状态。

## 3.10 Tool Timeout 怎么处理？

为每个工具设置符合业务的超时，并支持取消底层任务；超时结果应明确标识，不应让后台副作用继续失控。批量调用还需要整体超时，避免某个慢工具拖住整轮。

LeAgent 的 `BaseTool._invoke_execute()` 使用 `asyncio.wait_for` 或执行任务与 abort signal 竞速；`ToolExecutor.execute_parallel()` 还有批次超时，并取消未完成任务。

## 3.11 Tool Retry 如何设计？

只重试瞬时错误，如超时、限流和临时网络失败；参数错误、权限拒绝和确定性业务失败不应重试。采用有限次数、指数退避和抖动，并考虑幂等键，防止重复创建订单或重复扣款。

LeAgent 工具默认有有限 `max_retries`，失败后指数退避；`NonRetryableToolError` 会立即停止重试。当前退避是 `2 ** attempt`，高副作用工具仍应自身保证幂等性。

## 3.12 Tool 并行调用怎么实现？

先确认调用之间无数据依赖、共享状态冲突或顺序副作用，再用异步任务并发执行；设置并发信号量、整体超时和结果 ID 映射，最终按原调用顺序回传。并行不是“模型一次返回多个调用”就自动安全。

LeAgent 只并行执行声明 `is_concurrency_safe = True` 的工具，其他调用串行；执行器用 semaphore 限制最大并发，并支持 wait-all 与 fail-fast。

## 3.13 Tool 串行调用怎么实现？

按顺序执行每个调用，将前一步结果用于构造后一步参数；若前置步骤失败，应根据策略停止、补偿或重规划。存在显式依赖时可构建 DAG，每轮执行所有已满足依赖的节点。

LeAgent 提供 `run_tools_sequential()` 和 `execute_sequential()`，可在失败时停止；`execute_with_dependencies()` 根据依赖选择 ready batch，并检测无法推进的依赖环。

## 3.14 Agent 如何决定停止调用 Tool？

当目标已满足且证据足够时，模型应输出最终答案而非 tool call。运行时还必须在达到轮次、token、调用数、时间预算，收到取消，等待用户输入或遇到不可恢复错误时强制停止。

LeAgent 在模型没有返回 tool calls 时完成当前运行；同时用 `max_turns`、`max_tool_calls_per_turn`、token 预算和 abort 状态兜底，`ask_user` 则以 awaiting-user-input 暂停并保存检查点。

## 3.15 如何避免无限循环调用 Tool？

同时使用硬限制和语义检测：限制总轮次、总调用数和时间；记录调用签名与结果摘要，检测相同参数重复失败或状态无进展；要求失败后改变策略，超过阈值就澄清或终止。仅在 Prompt 中说“不要循环”不够。

LeAgent 已有轮次与单轮调用上限，并将每次工具结果加入历史；工具自身也有限重试。若需更强去重，可在上层增加重复调用指纹和无进展判定。

## 3.16 Tool Ranking 如何实现？

可先做硬过滤，再对候选按名称、描述、关键词或 embedding 与当前任务的相关性打分，并结合成功率、延迟、成本、权限和用户偏好重排。核心工具可固定保留，相关工具组应成套加入。

LeAgent 当前使用轻量关键词评分：命中名称、`search_hint`、描述和类别获得不同分值，再选择 Top-N；核心工具始终保留，GenUI 等工具还会自动加入 companion tools。

## 3.17 多工具冲突如何解决？

优先通过设计消除冲突：工具职责正交、命名清晰、输入输出不同。仍有重叠时，用路由规则、领域 allowlist、成本与风险排序、必需前置条件和少量选择示例决定；高风险冲突应请求用户确认。

LeAgent 可按 Agent 构建 scoped registry，先 allow 后 deny，并支持 exact 或 glob 匹配；工具名称别名只用于查找兼容，不应让两个工具共享同一模糊职责。

## 3.18 MCP 和 Tool Calling 的区别？

Tool Calling 是模型与应用之间表达“调用某能力”的交互机制；MCP 是客户端与外部能力提供方之间的协议，规范工具、资源、Prompt 的发现与调用，以及连接和传输。MCP 工具最终仍可转换成模型的 function schema，因此两者是互补关系。

LeAgent 的 `MCPClientManager` 连接服务器并发现 tools/prompts/resources，再用 `MCPProxyTool` 注册为 `mcp__<server>__<tool>`，随后复用普通 `ToolRegistry` 与 `ToolExecutor`。

## 3.19 MCP 为什么火？

因为它把“每个 Agent 框架为每个数据源写一套私有插件”转为标准化客户端—服务器接口，降低集成和复用成本；能力提供方可独立发布，客户端可动态发现 schema。它解决的是连接标准化，不自动解决权限、安全、质量和可靠性。

LeAgent 对 MCP 连接提供配置加载、健康检查、重连和命名空间隔离，但代理工具仍要经过本地注册和执行边界。

## 3.20 Agent 如何动态发现 Tool？

运行时可从本地注册表、插件入口或远程协议端点获取工具清单，读取名称、描述和 schema，再按权限与相关性选择一小部分暴露给模型。发现结果要缓存和版本化，连接变化时刷新，并避免名称碰撞。

LeAgent 的 `ToolRegistry` 可扫描模块、包和目录注册 `BaseTool`；MCP 连接时调用 `list_tools()`，将远程工具包装并带服务器命名空间注册。管理器还能监听配置变更、健康检查并尝试重连。
