# 八、LangGraph / Agent Framework

## 8.1 为什么 LangGraph 出现？

**答：**早期 LLM 应用多是线性链：输入经过若干 Prompt 或工具后输出。Agent 场景则需要循环、条件分支、人工审批、并行、失败恢复和长时间状态保存，普通 Chain 很难清晰表达这些控制流。LangGraph 因此用“有状态图”建模执行：节点负责计算，边负责控制流，状态贯穿整个运行。

它解决的是编排与状态问题，而不是让模型本身更聪明。即便采用图框架，工具安全、数据权限、幂等、评估和运维仍需应用负责。

**LeAgent 对照：**LeAgent 没有基于 LangGraph。它有两种互补控制面：AgentRuntime 的 `run_loop` 承载动态 think-act 循环，WorkflowExecutor 承载显式 DAG、条件路由、并行和 pause/resume。两者属于自研 runtime/workflow，可用于比较设计取舍，但不能称为 LangGraph 的封装。

## 8.2 LangChain 和 LangGraph 的区别？

**答：**概念上，LangChain 更侧重模型、Prompt、工具、检索器等组件的连接与调用；LangGraph 更侧重有状态、可循环、可中断的执行图。两者可以组合，也可以独立使用。

- 线性或短流程：组件链通常更简单；
- 多分支、循环、人工介入、恢复：图模型更自然；
- 生产选型不能只看名称，应核对目标版本的持久化、并发、调试、部署和 API 稳定性。

这些项目迭代较快，面试中应说明设计差异，不宣称某个短期版本的具体默认行为。

**LeAgent 对照：**`run_loop` 统一处理 AgentEvent、hook 和 checkpoint；workflow DAG 处理节点与边。LeAgent 可复用自己的 LLMService、ToolRegistry、Memory 和文件层，不依赖 LangChain/LangGraph 组件体系。

## 8.3 StateGraph 是什么？

**答：**StateGraph 是“围绕共享状态运行的图”。节点读取状态的一部分，返回状态更新；图运行时根据边选择下一节点，并按预定义的合并规则处理更新。

设计重点不是画图，而是定义：

- 状态 schema 及字段所有者；
- 更新是覆盖、追加还是 reducer 合并；
- 哪些状态需要 checkpoint；
- 并行分支如何避免写冲突；
- 状态版本如何迁移。

**LeAgent 对照：**LeAgent 的 WorkflowDocument、WorkflowState 与 WorkflowExecutor 提供相似的“定义 + 状态 + 调度器”职责，但类型和语义是 LeAgent 自己的实现。Agent kernel 的 RunState 则记录 turn、messages、usage、工具调用和产物，不应与 LangGraph StateGraph 类型混为一谈。

## 8.4 Node 是什么？

**答：**Node 是图中的最小执行单元，可以是纯函数、工具调用、LLM 调用、Agent、人工审批或子图。理想 Node 应有清晰输入输出、超时、重试和幂等语义。

生产 Node 还应声明副作用与权限。只读节点可以安全重试；支付、发信、写文件等节点必须使用幂等键或补偿事务。节点不应偷偷依赖不可追踪的进程内全局状态。

**LeAgent 对照：**workflow Node 由节点注册表和 NodeRunner 执行，运行时会做输入验证、超时/重试等控制；任意工具还能映射为 `Tool.<name>` 节点，Agent 节点可通过 AgentRuntime 执行。文件产物应经 FileService/工具产物注册路径持久化，而不是让节点随意写 managed blob。

## 8.5 Edge 是什么？

**答：**Edge 表示节点间的数据依赖或控制流。普通边意味着上游完成后，下游获得执行资格；图调度器还要确认其他依赖是否满足。

边设计要区分：

- 数据边：传递哪个输出到哪个输入；
- 控制边：决定是否触发目标；
- 错误边：失败、超时或补偿时走向；
- 回边：允许循环，但必须有边界和进度条件。

**LeAgent 对照：**workflow DAG 根据节点和连接关系 stage ready batch，并将并行节点结果汇总后再更新共享调度状态。工作流允许的循环是受控例外，不应把任意有环图当作安全。

## 8.6 Conditional Edge 如何实现？

**答：**Conditional Edge 在节点执行后，根据状态或结构化输出选择目标边。实现通常是：

```python
route = router(state)
next_node = route_map.get(route, "fallback")
```

`router` 应尽量纯函数化；若由 LLM 决策，应使用枚举 schema、置信度、默认分支和最大重试，避免模型返回任意节点名。条件必须可记录、可重放，否则恢复后可能走不同路径。

**LeAgent 对照：**可通过工作流条件节点和分支路由表达类似语义；Agent 内也可由模型动态选择工具。前者更确定、可审计，后者更灵活。LeAgent 的具体路由不等于 LangGraph 的 conditional edge API。

## 8.7 Checkpoint 是什么？

**答：**Checkpoint 是可恢复执行的持久快照，至少包含执行标识、状态、消息/上下文、当前进度、版本和终止原因。它的目标是进程崩溃、人工等待或预算中断后无需从头执行。

合格的 checkpoint 设计还要回答：

- 何时保存：节点边界、turn 边界或关键副作用前后；
- 保存什么：足以确定性继续，但避免敏感数据泛滥；
- 如何并发控制：版本号、CAS 或事务；
- 如何迁移：代码/schema 变化后的兼容策略；
- 如何处理外部副作用：checkpoint 不能替代幂等。

**在 LeAgent 中：**`run_loop` 在可恢复原因下快照 live messages、turn、usage 等并写入 CheckpointStore；有数据库时可使用 SQLCheckpointStore，否则回退内存实现。workflow 有独立 WorkflowStateStore。两类状态所有者不同，不应把 Agent checkpoint 和 workflow state 混成一个对象。

## 8.8 Human-in-the-loop 如何实现？

**答：**在高风险节点前或信息不足时，执行器产生 interrupt：保存状态，返回待审批内容和稳定恢复 token，然后停止占用 worker。用户答复后，服务校验身份、作用域和状态版本，再把决定注入原执行并恢复。

安全要点包括审批内容不可被模型模糊描述、审批只能作用于当前参数、过期后重新确认、拒绝也是显式分支，并完整记录审计日志。

**在 LeAgent 中：**Agent 可因 `awaiting_user_input` 保存 checkpoint，并生成带 `checkpoint_id` 的 `PauseToken`；workflow HumanReview 节点可进入等待状态，恢复数据写入对应节点。工具层还有 ask rules、destructive confirmation 和 session approval。它们构成 HITL 基础，但业务系统仍需定义哪些动作必须审批。

## 8.9 State 如何设计？

**答：**State 应最小化、类型化、分层和可版本化。一个常见划分是：

- 输入与不可变身份：tenant、user、request、run；
- 控制状态：current node、status、retry、budget；
- 业务状态：结构化事实和中间结果；
- 产物状态：文件 ID、数据库记录 ID，而不是大块二进制；
- 可观测状态：错误、usage、时间戳。

不要把完整模型上下文、业务数据库和执行器内部状态塞进同一个 JSON。并行写字段要有 reducer 或单写者；敏感字段要加密和设置保留期。

**LeAgent 对照：**chat transcript 由 TieredSessionStore 持有，Agent pause 由 CheckpointStore 持有，workflow run 由 WorkflowStateStore 持有，后台任务日志由 TaskManager 持有。这种“每类状态一个 durable owner”是通用设计原则在仓库中的明确实现。

## 8.10 如何实现 Agent Resume？

**答：**Resume 的标准流程是：

1. 加载 checkpoint 并校验用户、租户、Agent 和状态版本；
2. 获取运行租约，防止同一 checkpoint 被并发恢复；
3. 重建消息、预算、工具权限和外部引用；
4. 注入用户答复或审批结果；
5. 从安全边界继续，副作用节点使用幂等键；
6. 原 checkpoint 标记 consumed 或生成下一版本。

Resume 不是“把旧 Prompt 再发一次”，否则会重复调用工具和产生副作用。

**在 LeAgent 中：**AgentRuntime 可从 checkpoint 恢复，kernel checkpoint 保存消息历史；统一 PauseToken 区分 chat、workflow、task 等 scope。WorkflowExecutor 从持久 state 加载状态，将 `resume_data` 放入被阻塞节点，并借助输出缓存跳过已完成节点。多 worker 下仍要关注运行注册表的进程内属性和并发恢复控制。

## 8.11 LangGraph vs CrewAI

**答：**通常可按抽象重点比较：LangGraph 偏有状态图和细粒度控制流；CrewAI 偏角色、任务、团队协作的高层抽象。前者通常更适合需要显式状态机、分支和恢复的系统，后者更适合快速表达角色分工的原型。

选型应实测目标版本的 checkpoint、一致性、并发、HITL、可观测性、部署形态和扩展点。不能只凭“图更生产”或“角色更智能”下结论。

**LeAgent 对照：**LeAgent 的 subagent 提供角色委派原语，workflow 提供 DAG 控制，runtime wiring 统一工具与服务，因此兼有两类关注点，但采用自己的契约。它不是 CrewAI 或 LangGraph 的二次封装。

## 8.12 LangGraph vs AutoGen

**答：**LangGraph 主要以状态图表达控制流；AutoGen 常以可对话 Agent、消息交互和群组协作为核心心智模型。图适合确定性边界较多的编排；对话式抽象适合开放协商、代码执行实验和多角色探索。

风险也不同：图的复杂度来自状态和分支；对话群组的复杂度来自终止条件、消息膨胀和不可预测交接。生产系统经常将开放式 Agent 限定在一个节点内，外围仍用确定性状态机约束。

**LeAgent 对照：**subagent 是父调用子并返回结构化结果，并非默认的 Agent 群聊；workflow DAG 是中心调度。若需要群组对话协议，需要另行实现消息、成员和终止策略。

## 8.13 LangGraph vs OpenAI Agents SDK

**答：**可从抽象层比较，而不依赖短期 API：LangGraph 强调通用图状态编排；OpenAI Agents SDK 一类厂商 SDK 往往强调 Agent、tool、handoff、guardrail、trace 以及与其模型平台的顺畅集成。

选择维度包括模型供应商可移植性、handoff 与图控制的表达力、持久化、HITL、trace、工具协议、部署锁定和团队已有基础设施。具体能力变化快，应以候选版本官方文档和故障注入测试为准。

**LeAgent 对照：**LeAgent 也公开 Agent SDK，但其 `AgentRuntime`、`run_loop`、CheckpointStore 和协议是本仓库自研接口，支持多个 provider，并与 LeAgent 的工作流、任务、文件和权限系统集成；不要因名称相似而视为 OpenAI Agents SDK。

## 8.14 哪种框架适合生产环境？

**答：**没有脱离场景的唯一答案。生产选型至少评估：

- **正确性：**状态一致性、幂等、重试、取消、恢复；
- **安全：**身份透传、工具最小权限、审批、文件隔离；
- **运维：**trace、metrics、日志、限流、队列和水平扩展；
- **工程：**类型、测试、API 稳定性、升级成本、可替换性；
- **业务：**延迟、成本、团队熟悉度和上市时间。

POC 应包含崩溃恢复、重复投递、模型超时、工具部分成功、人工等待和跨版本恢复，而不仅是 happy path demo。框架生态变化快，结论必须绑定目标版本与实测。

**LeAgent 对照：**对本项目而言，自研 runtime wiring 让所有 ingress 复用 ToolRegistry/Executor、hooks、checkpoint、Memory 和 LLMService；`run_loop` 统一 Agent 语义，workflow 管 DAG。它减少内部集成摩擦，但仍有边界：默认 SQLite 单写者、进程内 ExecutionRunRegistry 与事件总线不天然支持任意多 worker。

## 8.15 为什么很多公司最终不用框架？

**答：**常见原因不是框架“无用”，而是业务成熟后需要更窄、更稳定的抽象：

- 框架状态模型与既有数据库、队列和权限体系重复；
- 隐式 Prompt、自动重试或回调让故障难定位；
- 高频升级带来 API 和序列化兼容成本；
- 核心流程其实是少量状态机加工具调用，自研更直接；
- 供应商锁定、性能开销或合规要求不可接受。

更稳妥的做法通常不是一次性重写，而是把模型、工具、状态、trace 封装在自己的端口后，再决定哪些框架能力值得保留。

**LeAgent 对照：**LeAgent 采用自研 Agent runtime/workflow，原因可从仓库结构理解为需要统一 chat、SDK、task、subagent 和 workflow ingress，并直接复用文件层、权限、Memory 与服务 wiring。这说明一种工程取舍，不证明自研普遍优于成熟框架；维护协议、恢复兼容和调度器同样需要长期成本。
