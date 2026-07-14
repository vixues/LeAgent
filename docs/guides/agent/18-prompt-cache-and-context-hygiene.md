# 18｜Prompt Cache、Fingerprint 与上下文卫生

## 定位、难度与先修

- **定位**：让稳定前缀可缓存，并防止提示词污染与失控漂移。
- **难度**：★★★☆☆
- **先修**：[16 预算](16-context-budget-and-compaction.md)、[17 门控](17-relevance-gated-prompts.md)、[13 分层提示词](13-layered-prompts.md)

便宜与安全在这里相遇：前缀越稳，provider prompt cache 越容易命中；动态资料越靠后、越标记为「数据而非指令」，间接注入面越小。卫生措施不能替代应用层权限——后者在工具执行层 enforce。

## 学习目标

1. 解释为何稳定前缀有利于 provider prompt caching。  
2. 了解仓库内 prompt fingerprint 相关能力用于何。  
3. 实践「上下文卫生」：不信任工具返回与检索文本中的指令。  
4. 区分卫生措施与应用层权限（后者不可被提示词替代）。  
5. 能用「稳定 / 半稳 / 高变」三槽检查一次 prepare_turn 结果。

## 核心心智模型：分槽与防投毒

现代上下文常分槽：

1. 稳定系统指令与政策（可缓存）  
2. 工具 schema（相对稳定）  
3. 动态召回 / 附件 / 工具结果（高变）  
4. 近期对话  

卫生原则：**检索与工具输出是数据，不是指令**。模型可能遵循其中的隐藏指令；因此敏感操作必须由工具执行层 enforce。门控（第 17 篇）减少「无关轮次也改 system 哈希」；配方与 identity 拆分（第 14 篇）避免为人设小改重排整份前缀。

## 数据流：什么应钉死在前缀

```text
Identity +  thrifty policies（always-on 薄层）
        │  顺序稳定、内容少变
        ▼
（可选）仍偏稳定的 capabilities / environment
        │
        ▼
高变：gated 手册、recall、working set、tool stdout、附件
        │  更宜 ATTACHMENT_USER / 截断 / 来源标记
        ▼
对话 messages（含 tool 对）
```

指纹（fingerprint）服务变更检测与调试：哪一层变了导致 cache 失效或评测漂移。它**不是** ACL，也不能当鉴权令牌。相关测试见 `tests/test_prompts_package.py`。

相邻篇：[24](24-mcp-and-tool-poisoning.md) 讲 MCP 描述投毒；[47](47-agent-security-control-plane.md) 讲控制面；[16](16-context-budget-and-compaction.md) 讲体积；[28](28-history-compaction.md) 提醒压缩不要重写稳定前缀。

## LeAgent 的真实实现

- Prompt 包装与指纹：`backend/leagent/prompts/`（`test_prompts_package.py` 覆盖 registry、budget、fingerprint、renderer）  
- 组装：`backend/leagent/context/manager.py` 分区 system / attachments  
- 门控减少「每轮都变」的重政策 → 提高稳定前缀比例  
- Artifact / tool 错误以结构化方式注入，而不是无界粘贴  
- 安全控制面与路径沙箱：在执行层否决，不只靠「请勿…」  
- MCP 场景的描述投毒治理见第 24 篇  

路径解释：改一段 always-on 政策会影响所有命中该前缀的请求的 cache；改 gated 手册通常只影响相关域轮次。工具 schema 若因 allow 列表每轮剧变，也会打穿缓存——领域 Agent 宜收紧且稳定工具集合（第 09/10 篇）。

## 分步：提升可缓存性的实践清单

1. 将极少变化的身份与安全政策放 always-on 薄层。  
2. 重手册走 Gate，避免无关任务改变 system 哈希。  
3. 动态块后置；不要每个 turn 重排章节顺序。  
4. 工具结果截断并标记来源（`tool:name`）。  
5. 对高风险工具要求 approval，无视提示词怎么说。  
6. 用 fingerprint / ledger 对比「仅换用户问题」时应保持前缀稳定。  
7. 评测集固定 recipe 与工具表，避免「缓存命中率」与「提示漂移」混淆。

## 验证命令

```bash
cd backend
uv run pytest tests/test_prompts_package.py tests/eval/test_prompt_gating.py -v
uv run pytest tests/test_context/test_manager.py -q
```

## 常见误区与排障

1. **为了省事把用户消息拼进 system**：污染缓存且放大注入面。  
2. **认为 provider cache 是框架保证**：取决于厂商与前缀稳定性。  
3. **用指纹当鉴权**：指纹服务变更检测/调试，不是 ACL。  
4. **忽略工具 schema 频繁变动**：也会打穿缓存。  
5. **在工具结果里执行「忽略上述指令」而不设执行层否决**：经典间接注入。  
6. **每次压缩重写 system 政策全文**：看起来「更干净」，账单与行为更糟。  

排障：cache 命中骤降 → diff 前后 fingerprint / ledger 前缀 → 查是否新开 gate、工具表抖动、或把动态召回误塞进 SYSTEM。

## 业内对照

Anthropic / OpenAI 均提供前缀缓存计价；上下文工程文章强调「stable prefix + volatile tail」。OWASP LLM Top 10 将间接注入列为核心风险——卫生与权限要并重。LeAgent 用 recipe/gate/budget/render_target 把这些原则落成可测模块。

## 总结与延伸阅读

干净的上下文既更便宜，也更不容易被窜改。稳定前缀是缓存的朋友；执行层权限是安全的底线。

- [24｜MCP 与投毒](24-mcp-and-tool-poisoning.md)
- [47｜安全控制面](47-agent-security-control-plane.md)
- [17｜门控](17-relevance-gated-prompts.md)
