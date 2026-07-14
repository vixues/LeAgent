# 九、Agent 系统设计

## 9.1 设计一个旅游规划 Agent

**答：**

**目标：**根据预算、日期、出发地、兴趣和约束生成可执行行程；信息不足时询问用户，价格与库存必须标注查询时间，未经确认不下单。

**组件与数据流：**用户需求 → 约束提取 → 目的地/交通/酒店/景点并行检索 → 冲突与预算校验 → 日程优化 → 地图与文档产物 → 用户确认。确定性约束用规则或优化器，LLM 负责解释、补全和权衡；外部数据保留来源、币种、时区与时间戳。

**安全与评估：**预订、支付、取消必须 HITL；第三方网页内容视为不可信输入，个人证件与支付数据最小化保存。评估约束满足率、事实/价格时效性、预算误差、路线可行性、用户修改次数和预订前误操作率。

**LeAgent 可复用模块：**用 workflow DAG 并行检索并按依赖汇总，用 Agent 节点处理开放式规划；`run_loop` 承载工具迭代，checkpoint/PauseToken 等待用户确认，ToolPermissionContext 限制有副作用工具，FileService 管理行程文档。仓库提供通用工具与编排基础，但不应宣称已内置完整旅游供应链。

## 9.2 设计一个招聘 Agent

**答：**

**目标：**辅助职位描述、候选人检索、简历结构化、面试安排与总结；最终录用决定由人负责，不让模型基于受保护属性做决策。

**组件与数据流：**JD 与岗位能力模型 → 简历解析/OCR → 技能与经历证据抽取 → 基于公开标准的匹配 → 招聘人员复核 → 日程与通知 → 面试记录汇总。候选人数据、岗位标准、模型建议分表保存；每条评分必须可回溯到证据。

**安全与评估：**做 RBAC、租户隔离、保留期、删除请求和审计；屏蔽年龄、性别、民族等不应使用的属性，检测代理变量与群体差异。评估抽取准确率、证据引用率、召回率、人工覆盖率、公平性差异和错误通知率，不能只看历史录用标签。

**LeAgent 可复用模块：**文档/文件层负责受控简历引用，RAG/Memory 可存岗位知识但需 ACL，workflow 安排解析—评分—人工复核，pause/resume 等待审批，任务系统承载批量处理。现有通用 Memory 不自动满足招聘合规，需业务数据治理。

## 9.3 设计一个股票分析 Agent

**答：**

**目标：**汇总行情、财报、公告和新闻，形成带来源与不确定性的研究报告；默认提供分析而非自动交易。

**组件与数据流：**标的与时间范围 → 行情/基本面/公告数据适配器 → 数据清洗和时间对齐 → 指标计算 → 新闻事件抽取 → 多情景分析 → 引用校验 → 报告。数值计算交给代码或数据工具，LLM 不直接心算关键指标。

**安全与评估：**区分实时、延迟与历史数据；防止未来信息泄漏、幸存者偏差和来源许可违规。若接交易接口，必须使用账户隔离、额度、风控规则、双重确认和 kill switch。评估数据完整率、数值误差、引用正确率、时点一致性、回测外表现和风险披露覆盖率，而非只看收益。

**LeAgent 可复用模块：**workflow 并行拉取多源数据，Tool 节点执行计算，Agent 做解释与异常追查，FileService 注册图表/报告，checkpoint 支持研究中断恢复。工具权限可默认拒绝交易工具；LeAgent 不提供“保证收益”的能力。

## 9.4 设计一个代码生成 Agent

**答：**

**目标：**理解仓库与需求，制定变更计划，最小化修改，运行测试并给出可审查差异；不能以“代码生成成功”代替验证。

**组件与数据流：**仓库索引和规则加载 → 需求澄清 → 搜索相关代码 → 计划 → 在隔离 workspace 修改 → lint/test/build → 读取失败证据并迭代 → 生成 diff 与验证摘要。读、写、执行命令采用不同权限；每轮记录 changed files 和测试结果。

**安全与评估：**沙箱命令、限制网络和路径、保护 secret、禁止未授权发布/推送；依赖安装与迁移需额外审批。评估任务测试通过率、回归率、diff 大小、无关修改率、安全扫描、人工接受率和恢复成功率。

**LeAgent 可复用模块：**project/code/file 三层提供 workspace、执行和产物边界；工具的 `authorized_roots` 与权限策略限制路径和副作用；subagent 可分派探索或测试，父子通过 `parent_run_id` 追踪；所有 Agent 执行经 `run_loop`，长步骤可进入 Task system。项目层不得绕过文件层规则写 managed blob。

## 9.5 设计一个客服 Agent

**答：**

**目标：**识别意图，基于可信知识回答，完成查询、退款申请等操作，并在低置信度或高风险场景转人工；保持多轮上下文但不泄露其他客户信息。

**组件与数据流：**渠道消息 → 身份与租户校验 → 意图/情绪识别 → KB 检索 → 生成带证据答案或调用业务工具 → 权限/审批 → 更新工单 → 满意度收集。会话记录与业务事实分开，业务状态以 CRM/订单系统为准。

**安全与评估：**防提示注入、越权查单、PII 泄露和退款滥用；写操作需二次确认和幂等键。评估一次解决率、正确转人工率、引用准确率、平均处理时间、重复联系率、越权率和人工抽检，而非单看语气满意度。

**LeAgent 可复用模块：**channels 作为入口，TieredSessionStore 保存对话，RAG/context 组装知识，ToolExecutor 透传身份并做权限检查，checkpoint/PauseToken 支持澄清或审批，Task system 处理异步工单。现成模块不替代 CRM 侧授权。

## 9.6 设计 Deep Research Agent

**答：**

**目标：**对开放问题进行多轮检索、阅读、交叉验证和综合，输出可追溯的结论、分歧与研究空白。

**组件与数据流：**研究问题 → 子问题树 → 搜索与来源去重 → 页面/文档抽取 → claim-evidence 图 → 缺口分析 → 定向再检索 → 引用校验 → 报告。可让多个 researcher 并行，但应共享任务账本和已访问来源，最终由 synthesizer 按证据汇总。

**安全与评估：**网页内容均为不可信数据，不能把页面指令当系统指令；遵守 robots、许可、速率和隐私要求。用最大深度、来源数、token 和截止时间控制成本。评估 claim 支持率、引用可访问性、来源多样性、时间覆盖、矛盾识别、重复检索率与专家评分。

**LeAgent 可复用模块：**subagent 适合隔离研究子题，workflow DAG 适合并行搜索和聚合；AgentMemory 可沉淀经验证知识，任务系统支持长研究，checkpoint 支持预算或人工中断，FileService 保存报告。LeAgent 提供积木，不代表默认研究策略已达到任意专业领域的专家质量。

## 9.7 设计 Manus 类 Agent

**答：**

**目标：**这里将“Manus 类”视为公开产品能力启发的通用自主任务 Agent：接受目标后规划，操作浏览器/代码/文件等工具，持续产出可交付结果。闭源产品内部实现未知，不能反推为事实。

**组件与数据流：**目标 → 可编辑计划/任务树 → 能力路由 → 浏览器、代码、文档等隔离执行器 → 观察与自纠错 → 产物汇总 → 用户验收。控制面维护状态、预算、租约和审批；执行面采用短生命周期 sandbox；产物通过对象存储引用。

**安全与评估：**外部发送、购买、删除、发布和凭证使用必须显式授权；网络、文件系统和 secret 按任务隔离。评估跨域任务成功率、恢复率、人工介入次数、不可逆误操作、成本、P95 时长和产物可用性。

**LeAgent 可复用模块：**`run_loop` 提供统一 think-act 自纠错路径，runtime wiring 注入工具/Memory/checkpoint，workflow 支持确定性子流程，task system 承载后台运行，PauseToken 支持审批，文件层管理产物。当前进程内 run registry 和默认本地部署不能被描述为互联网规模自治云平台。

## 9.8 设计 Cursor Agent

**答：**

**目标：**这里讨论通用 IDE coding agent，而非断言 Cursor 的内部架构：基于当前仓库、编辑器状态和用户约束完成检索、编辑、验证，并保持差异可审查。

**组件与数据流：**IDE 上下文/规则 → 语义与文本搜索 → 计划或直接修改 → patch 应用 → diagnostics/test → 根据运行证据修复 → diff handoff。前端负责交互和审批，Agent service 负责模型循环，workspace service 负责隔离文件与命令，索引服务负责代码检索。

**安全与评估：**根目录 allowlist、命令沙箱、secret redaction、网络策略和高风险操作确认；并发编辑用文件版本或 patch precondition。评估仓库级测试通过、编辑精度、无关 diff、命令失败恢复、延迟、token 和用户撤销率。

**LeAgent 可复用模块：**project 工具承担仓库文件操作，code 层执行命令，ToolPermissionContext 和 `authorized_roots` 做边界，subagent 可独立探索/测试，run checkpoint 支持继续，FileService 管理导出产物。LeAgent 是可构建此类能力的后端栈，不等同于 Cursor 产品本身。

## 9.9 设计 Devin

**答：**

**目标：**这里把 Devin 作为“长时程软件工程 Agent”设计题，依据公开能力抽象，不声称知道其内部实现。系统应从 issue 到代码、测试和可审查变更持续工作。

**组件与数据流：**issue intake → 仓库/环境初始化 → 里程碑计划 → 编辑器与 shell/browser 工具循环 → 测试和调试 → checkpoint → PR 草稿或补丁 → 人工评审。控制器维护任务图与预算，workspace 保持可恢复快照，队列为长任务提供租约，日志流向用户。

**安全与评估：**每任务隔离 VM/容器、最小权限凭证、默认不部署、不合并；外部副作用需审批。评估真实 issue 解决率、测试回归、平均人工修正、恢复后重复工作、环境成本、超时率及安全事件。

**LeAgent 可复用模块：**TaskManager/AgentTaskHandler 运行后台 Agent 并流式记录进度，AgentRuntime 统一 kernel 语义，checkpoint 保存可恢复对话，project workspace 与文件层管理代码和产物，`parent_run_id` 关联子任务。跨机器 workspace snapshot、分布式 lease 和完整 PR 机器人仍需部署层建设。

## 9.10 设计 Operator

**答：**

**目标：**这里讨论通用浏览器操作 Agent：在网页中完成表单、搜索、预订等任务，同时对页面变化和高风险动作保持可控。闭源 Operator 产品的内部实现不在假设范围。

**组件与数据流：**用户目标 → 浏览器会话隔离 → DOM/可访问性树与截图感知 → action planner → 点击/输入/滚动 → 页面状态验证 → 关键动作前确认 → 完成证据。优先结构化 DOM，视觉定位作为补充；每步保留前后状态和稳定元素标识。

**安全与评估：**网页提示注入隔离、域名 allowlist、下载扫描、凭证保险库、支付/提交前确认、验证码转人工；动作需防重复提交。评估任务完成率、步骤效率、页面变化鲁棒性、危险动作阻止率、恢复率和误点击率。

**LeAgent 可复用模块：**web 工具可作为受控动作面，`run_loop` 处理观察—行动循环，权限和 PauseToken 管关键确认，workflow 固化稳定流程，FileService 注册截图/下载。浏览器级隔离、凭证注入和视觉 grounding 的质量取决于具体工具实现，不能由 runtime 自动保证。

## 9.11 如何支持百万用户？

**答：**

**目标：**“百万用户”首先要转成峰值 QPS、并发运行数、平均工具时长、租户数、SLO 与预算；注册用户数本身不能决定架构。

**组件与数据流：**全球/区域入口 → 鉴权与租户限流 → 无状态 API → durable queue → 弹性 Agent/Workflow workers → 模型网关与工具网关 → 分片数据库、对象存储和缓存 → 事件/指标平台。长连接 SSE/WebSocket 与执行解耦，客户端用 cursor 重连；按 tenant/run 分区并实施背压。

**安全与评估：**租户数据和密钥隔离、配额、滥用检测、区域合规、审计和灾备。压测关注 admission rate、queue lag、P50/P95/P99、模型限流、数据库热点、成本/请求、恢复时间和降级效果。

**LeAgent 映射与边界：**ServiceManager runtime wiring 可保证各入口复用同一执行依赖，ExecutionRun 提供关联，Task/Workflow 服务提供执行抽象，文件层适合产物外置。但默认 SQLite 是单写者，ExecutionRunRegistry 与 event bus 是进程内组件；扩到百万级需要 PostgreSQL/分片、外部消息总线、durable run registry、分布式队列、对象存储和多区域设计，这些不能说成当前仓库已完成。

## 9.12 如何支持长任务？

**答：**

**目标：**任务运行数分钟到数天时，应允许用户离线、进程重启、暂停、取消、查看进度和获取部分结果，同时不长期占用 HTTP 请求或数据库事务。

**组件与数据流：**API 创建任务 → durable queue → worker 获取 lease → 分阶段执行 → 周期性 checkpoint/heartbeat/progress → 产物外置 → 完成事件通知。任务模型至少包含 status、attempt、lease owner/expiry、progress、checkpoint ref、output refs 和 error。

**安全与评估：**每租户并发/成本配额，取消信号向工具和子任务传播；副作用阶段必须幂等，checkpoint 加密并设置保留期。评估任务成功率、取消延迟、checkpoint 开销、worker 崩溃恢复时间、重复副作用和陈旧任务比例。

**LeAgent 映射与边界：**AgentTaskHandler 通过 AgentRuntime.stream 进入统一 `run_loop`，写任务输出和进度，并传播 abort event；workflow 有持久状态与 pause/resume。当前能力适合本地/单进程后台任务；跨节点 lease、心跳接管和队列高可用需要外部基础设施。

## 9.13 如何做任务恢复？

**答：**

**目标：**从最近安全点继续，而不是重放整个 Prompt；恢复后结果必须与“至多一次业务副作用”兼容。

**组件与数据流：**检测 worker 失联或收到 resume → 读取任务元数据和最新 checkpoint → 校验版本/权限 → 获取恢复租约 → 重建运行上下文 → 跳过已完成步骤 → 重试可重试步骤 → 提交新 checkpoint。外部工具调用用 operation id 查询既有结果，不能盲目重发。

**安全与评估：**checkpoint 包含敏感对话时需加密和 ACL；代码升级后做 schema migrator 或拒绝不兼容恢复；人工答复绑定原 run、scope 和参数摘要。故障注入测试进程崩溃、网络分区、重复 resume、checkpoint 写一半和外部成功但本地超时。

**LeAgent 映射与边界：**kernel 在可恢复 reason 下保存消息快照与 usage，SQLCheckpointStore 可持久化 Agent checkpoint；WorkflowExecutor 可从 WorkflowStateStore 加载并用输出缓存跳过已完成节点；PauseToken 统一引用两类恢复入口。进程内 ExecutionRun 只是活跃句柄，durable checkpoint/state 才是重启恢复依据。

## 9.14 如何做任务队列？

**答：**

**目标：**削峰、隔离租户、调度优先级并可靠投递长任务。队列语义通常选择至少一次投递，再由消费者实现幂等；追求“exactly once”往往只是把去重转移到别处。

**组件与数据流：**producer 写任务记录与 outbox → broker topic/partition → scheduler 做优先级、公平和配额 → worker lease/heartbeat → 成功 ack，临时错误指数退避，永久错误进入 DLQ。任务带 `task_id、tenant_id、type、priority、not_before、attempt、idempotency_key`。

**安全与评估：**消息不直接携带大文件或长期 secret，只放受控引用；防止某租户饿死其他租户；取消与重试必须可竞态安全。评估 queue lag、redelivery、DLQ、lease timeout、吞吐、公平性和单位任务成本。

**LeAgent 映射与边界：**Task system 定义任务类型、handler、状态、进度、取消和输出，WorkflowService 也暴露 queue-aware 操作，可作为业务契约。若目标是多机高可用，应在其外接 durable broker、分布式 lease 和 worker autoscaling，而不是把进程内异步执行当作完整分布式队列。

## 9.15 如何做状态管理？

**答：**

**目标：**保证对话、Agent 暂停、workflow、任务和业务数据各有明确所有者，并能在并发、恢复和版本升级下保持一致。

**组件与数据流：**请求只携带身份和状态引用 → 对应 repository/store 事务读取 → 执行器产生事件与状态变更 → 使用版本号/CAS 提交 → 大产物写对象存储/文件层 → trace 通过 run ID 关联。热状态可缓存，但数据库或 durable store 是恢复依据。

状态应按生命周期拆分：

- chat transcript：用户会话事实；
- Agent RunState/checkpoint：think-act 恢复；
- workflow state：节点进度、变量和输出缓存；
- task state：排队、租约、进度与结果；
- business state：订单、工单等领域事实；
- artifact：文件元数据和受控存储引用。

**安全与评估：**租户键参与所有查询；敏感字段加密、最小保留；并发更新使用乐观锁或事务；状态 schema 显式版本化。测试并发 resume、重复事件、缓存失效、跨版本迁移、部分写失败与删除合规。

**在 LeAgent 中：**TieredSessionStore、CheckpointStore、WorkflowStateStore 与 TaskManager 分别拥有不同 durable state；ExecutionRun 的 `run_id/parent_run_id` 负责执行关联而不是替代数据库；RuntimeContext 从 ServiceManager 统一注入 registry、executor、hooks、Memory、LLM 与 checkpoint；文件产物通过 FileService 和 `register_tool_artifact` 管理。默认部署仍需遵守 SQLite 单 worker 和进程内 registry/event bus 的边界。
