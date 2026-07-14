# 十二、安全

## 12.1 Prompt Injection 是什么？

Prompt Injection 是攻击者构造输入，诱导模型忽略系统或开发者指令、泄露上下文、错误调用工具或改变既定目标。它与传统 SQL 注入不同：模型会把自然语言指令和数据都放入同一推理上下文，无法仅靠字符串转义彻底解决。

防御应采用纵深策略：

- 明确指令优先级，把用户内容和外部内容标记为不可信数据。
- 不把秘密放进模型不需要的上下文。
- 用确定性的权限、schema、沙箱和审批控制真实副作用，不能依赖模型“自觉拒绝”。
- 对高风险动作验证目标、参数、用户意图和当前授权。
- 建立注入测试集，覆盖直接越狱、编码混淆、多轮诱导和工具结果注入。

LeAgent 的工具执行器有独立于 Prompt 的 deny/allow/ask、破坏性确认、Plan Mode 和工具自身权限检查，文件路径还受 allow-list sandbox 约束。因此即使模型被诱导，危险动作仍可在执行层拦截或暂停审批。

但当前仓库并没有一套可证明完备的通用 Prompt Injection 检测器。系统 Prompt、相关性门控和审批是防线的一部分，不应宣传为“已经解决 Prompt Injection”。

## 12.2 Indirect Prompt Injection 是什么？

Indirect Prompt Injection 是恶意指令不直接来自用户，而是藏在网页、邮件、PDF、知识库、代码注释、工具结果或 MCP resource 中。Agent 为完成正常任务读取这些内容后，可能把其中的文字误当成上级指令。

它更难发现，因为用户请求可能完全无害，例如“总结这个网页”，真正攻击载荷存在于网页中。防御重点是：

1. 对每段上下文保留 provenance，区分 system、user、retrieved document 和 tool output。
2. 告诉模型外部内容只能作为事实证据，不能授权新目标或工具调用。
3. 让读取与执行分阶段；从不可信内容推导出的写操作必须再次确认。
4. 对外发、删除、凭据、系统配置等动作做参数级策略和人工审批。
5. 清洗主动内容并限制渲染环境，但不能把 HTML 清洗当作语义注入防御。

在 LeAgent 中，工具结果会进入统一 think-act loop，外部 MCP 工具也可作为 `mcp__<server>__<tool>` 代理工具注册，因此网页、文档和第三方工具输出都应视为不可信。现有 executor 权限、approval、PathSandbox 和文件所有权能限制副作用；仍需在具体检索/浏览工具与 Prompt 中落实来源标记和内容隔离。

## 12.3 Tool Poisoning 是什么？

Tool Poisoning 是攻击者操纵工具的名称、描述、schema、返回值或工具服务器，使模型选择恶意工具、传出敏感参数，或相信伪造结果。MCP 场景尤其需要关注：远程服务器同时提供工具元数据和执行结果，描述本身就可能含注入文本。

防御措施包括：

- 只接入受信服务器，对配置和工具清单做管理员审批、版本锁定和签名校验。
- 将工具描述视为不可信元数据，限制长度和允许字段，不让其覆盖系统策略。
- 使用稳定内部工具 ID，不仅依赖可混淆的显示名称。
- 调用前执行 schema、权限、目的地和参数检查；返回后验证数据类型和业务不变量。
- 对工具服务器使用网络隔离、短期凭据、最小 scope、超时、限流和审计。
- 工具清单或 schema 变化时使缓存和既有授权失效。

LeAgent 的 MCP proxy 使用带 server 名的命名空间，降低同名冲突；所有代理工具仍应经过统一 ToolExecutor 的权限与审批。现有命名空间不是供应链验证，也不能证明远程描述和结果可信。高风险 MCP 接入还需要部署侧 allow-list、凭据隔离和变更审核。

## 12.4 Agent 为什么更容易被攻击？

与普通聊天模型相比，Agent 具有更大的攻击面：

- 它能读取私有上下文、文件、Memory 和凭据。
- 它能调用外部工具并产生真实副作用。
- 它跨多轮保留状态，恶意内容可能持续存在。
- 它会读取不可信网页、文档和工具结果。
- 子 Agent、工作流和 MCP 扩大了信任边界。
- 自动重试和长程计划可能放大一次错误。

因此安全目标不能只是“模型不输出有害文字”，而应是即使模型被操纵，攻击者仍无法越过认证、授权、所有权、沙箱、审批、速率和审计边界。这就是把 LLM 当作不可信决策建议者，把策略执行放在确定性控制平面的原因。

LeAgent 的统一执行拓扑有利于集中防守：聊天、SDK、任务、子 Agent 和工作流 Agent 节点都汇聚到 `run_loop → QueryEngine → ToolExecutor`。但工作流、直接 API、文件服务等非模型入口也必须分别做认证和所有权校验，不能只保护聊天入口。

## 12.5 越权调用工具怎么办？

处理越权调用应遵循“执行前拦截、默认拒绝、可审计审批”：

1. 从认证主体得到 user、role、tenant 和当前 session，而不是相信模型参数中的身份。
2. 根据工具、资源、动作和参数计算有效权限。
3. 明确 deny 优先；高风险调用暂停并要求有资格的审批者确认。
4. 工具内部再次做资源所有权检查，防止只在路由层鉴权。
5. 拒绝时不执行副作用，返回最少必要错误，并记录主体、目标、规则和关联 run。

LeAgent 的 `check_tool_permission()` 顺序包含全局 deny、Plan Mode gate、allow、always-ask、破坏性确认、`untrusted` 策略和工具自己的 `check_permissions`。审批可 `allow_once`、`allow_session` 或 `deny`，模糊回复按 deny 处理；等待审批时暂停轮次并通过 checkpoint 恢复。

需要注意，当前 session grant 以工具名匹配，参数摘要主要用于 pending/audit，并不是通用的参数级 grant。极高风险工具应在自身 `check_permissions` 中校验资源和参数，或把批准绑定到精确参数，不能只依赖“本会话允许该工具”。

## 12.6 如何限制 Tool 权限？

Tool 权限应从四个维度收敛：

- **能力**：每个 Agent 只注册或暴露必要工具，使用 allow/deny 规则。
- **动作**：标注 read-only、destructive，写操作要求审批，Plan Mode 禁止副作用。
- **资源**：限制文件根目录、项目、数据库 schema、API 域名和用户所有权。
- **运行时**：设置 timeout、并发、速率、调用次数和成本预算，凭据按工具单独注入。

LeAgent 的工具基类支持 `is_read_only`、`is_destructive` 和工具自定义 `check_permissions`；ToolPermissionContext 支持 glob deny/allow/ask 和 approval policy。`PathSandbox` 将模型路径解析到全局 roots、session roots、attachments、project roots 或显式 authorized roots，并使用统一 containment 检查阻止目录逃逸。

文件型工具产生的受管输出还应通过 FileService 注册并继承用户/session 范围。对于网络、数据库和第三方集成，应继续实现域名、连接、语句和凭据 scope 限制；文件沙箱不能替代这些资源级策略。

## 12.7 如何实现 RBAC？

RBAC 的基本模型是 User → Role → Permission，API 或工具声明所需 permission。生产实现还应叠加资源所有权或 ABAC 条件，例如“可以读取自己创建的文件”，而不是只有全局角色。

LeAgent 在启用认证时从 HMAC JWT 解出 `sub`、role、username 和过期时间，构造 `UserPrincipal`。`RoleChecker` 检查角色，`PermissionChecker` 支持 all/any permission；管理员拥有 `*` 以及 admin panel/users/tasks/providers、workflow admin 等权限，普通用户默认没有这些管理权限。管理 API 使用 `require_admin`，文件和部分工作流路径另做 user ownership 校验。

当前实现是轻量 RBAC：主要角色是 admin/user，权限集合不是完整的动态策略库；`require_dept_head` 目前也映射到 admin。面试时不能把它描述成成熟的多租户 IAM。若扩展，应将角色/权限持久化，加入 tenant 和资源条件，统一 API、tool、workflow、webhook 的策略，并测试横向越权。

另外，认证关闭的本地/桌面模式会以本地管理员身份宽松运行，这是单机便利模式，不是多用户安全边界。网络暴露时必须启用强制认证。

## 12.8 如何保护用户隐私？

隐私保护应覆盖数据最小化、用途限制、访问控制、保留和删除：

- 只收集任务必需数据；敏感字段在进入 Prompt、日志、Trace 和外部 provider 前脱敏。
- 按用户/tenant 隔离 transcript、文件、Memory、checkpoint 和 trace。
- 传输使用 TLS，静态数据和备份按风险加密，密钥独立管理和轮换。
- 明确第三方模型、MCP、webhook 的数据出境与保留政策。
- 支持导出、删除和保留期清理，并记录管理员访问。

LeAgent 默认关闭完整 Trace payload 捕获，preview 也可关闭并截断；这是正确的最小化默认值。结构化日志绑定 user/session/run 等关联字段，便于调查，但当前通用日志管线没有自动证明所有业务字段都已脱敏，因此调用方不应记录 token、密码、文件正文或完整 Prompt。

安全控制面使用哈希后的实例访问密码和有过期时间的 HMAC JWT；网络暴露时应使用强 `LEAGENT_SECRET_KEY`、反向代理 TLS 和限定 CORS。Memory、Trace 和日志的保留/删除仍需部署者制定策略，不能仅依赖默认配置。

## 12.9 如何防止数据泄漏？

防泄漏要同时控制入口、上下文、出口和观测面：

1. 入口：认证、RBAC、资源所有权和 session/tenant 隔离。
2. 上下文：不要把无关秘密、其他用户数据或全量环境变量交给模型。
3. 工具：限制文件 roots、网络目的地、数据库权限和外发工具；高风险外发需审批。
4. 出口：对响应、附件、webhook 和生成 HTML 做权限检查及必要的 DLP。
5. 观测：Trace/log 默认不捕获完整 payload，导出和诊断端点也必须鉴权。

LeAgent 的文件 preview/download 支持 Bearer JWT 或短期 HMAC signed URL。签名 payload 绑定 file ID、`preview/download` scope、user ID 和过期时间；服务端同时检查 scope、文件 ID和文件 owner。认证强制时拒绝弱签名 secret 回退。PathSandbox 则防止工具通过 `../` 或任意绝对路径读取不在授权 roots 中的文件。

Signed URL 是 bearer capability，拿到链接的人在过期前可能使用，因此 TTL 要短、避免写入日志和 Referer，并用 HTTPS。它也不能替代 owner 检查；LeAgent 的文件服务同时执行两者。

需诚实说明控制边界：安全文档描述的是轻量多用户隔离，所有 API 都仍应持续做横向越权测试。尤其诊断、Trace、导出、webhook 和管理端点应验证 user/role/owner 过滤，而不能只检查“存在某个登录用户”。

## 12.10 如何做审计日志？

审计日志应回答“谁在何时，以什么权限，对什么资源，做了什么，结果如何”，并包含：

- actor user/role、session、request、run/trace 和 parent run。
- action/tool/API、目标资源、参数摘要或哈希、策略决定和审批者。
- 开始/结束时间、结果、错误分类、实际 provider/工具。
- 版本、来源 IP 等必要上下文；敏感值只记摘要，不记秘密。

审计记录应追加写、限制访问、设置保留期，并通过哈希链、WORM 存储或外部 SIEM 提高防篡改性。审计写入失败对高风险动作应有明确策略；“best effort 后继续执行”未必满足合规要求。

LeAgent 当前可组合三类证据：

- 持久 Agent Trace：run、父子关系以及 llm/tool/approval/compact/subagent/error span。
- 结构化日志：request、user、session 关联字段和活动 OTel trace/span ID。
- `approval_decisions`：session、user、tool call、工具名、参数摘要哈希、理由、决定、scope 和决定者。

EventManager 的 `FLOW_*`、`TASK_*`、`AGENT_*` 是生命周期事件总线，适合实时订阅和 webhook，不应自动等同于不可篡改审计库。当前审批审计写入也是 best-effort，完整合规方案仍需统一 audit schema、可靠投递、访问审计、防篡改存储和保留/删除政策。
