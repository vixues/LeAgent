# 10｜设计一个领域 Agent

## 定位与先修

有了 Builder，下一步是按业务域设计「完整契约」，而不是只加长系统提示词。本篇假设你已读 [09｜AgentBuilder](09-agent-builder.md)，并理解 `AgentRuntime` 如何把定义物化成 `QueryEngineConfig`。领域 Agent 的目标是：同一份配置能在聊天、后台任务与工作流节点中给出可预期、可审计的行为边界。

权威类型定义在 [`runtime/definition.py`](../../../backend/leagent/runtime/definition.py)；内置领域样例在 [`runtime/registry.py`](../../../backend/leagent/runtime/registry.py) 的 `_builtin_definitions()`（`default_agent` / `coding_agent` / `script_agent` / `subagent`）。这些内置定义本身就是「如何为子域收紧策略」的活教材。

## 学习目标

完成本篇后，你应该能：

1. 把领域 Agent 拆成 persona、上下文 recipe、工具策略、模型路由、记忆策略与运行预算六块。
2. 读懂 `ToolPolicy` / `ModelPolicy` / `MemoryPolicy` 的默认值与语义差异。
3. 用 `resolved_recipe()` 复用人设或复用装配清单，而不必复制整份配置。
4. 对照 coding/script 子 Agent，为自己的域写出可注册、可测试的定义。

## 心智模型：领域边界写进契约，而不是写进一句口号

Chatbot 往往只有一段 system prompt。领域 Agent 还必须回答「它能看见什么、能动什么、能跑多久、记不记得住」。

| 维度 | 问题 | 落在 `AgentDefinition` |
|------|------|------------------------|
| 身份 | 它扮演谁？ | `prompt_variant`、`system_prompt`、`append_system_prompt` |
| 上下文 | 本轮装哪些 source？ | `context_recipe` → `resolved_recipe()` |
| 动作空间 | 能用哪些工具？ | `tools.allow` / `deny` / `max_tools` |
| 推理成本 | 用哪条模型路由？ | `model.task` / `provider` / `model` / 温度与输出上限 |
| 记忆 | 是否召回、是否写入？ | `memory.enabled` / `recall_limit` / `formation` |
| 预算 | 最多几轮、每轮几次工具？ | `runtime_profile`、`max_turns`、`max_tool_calls_per_turn` |
| 协作 | 能委派谁、挂哪些 hooks？ | `subagents`、`hooks` |

契约不含 LLM、session 或 abort 事件。因此同一份定义可以被聊天 SSE、SDK、`AgentTaskHandler` 与工作流 Agent 节点共享，这正是「领域模型一次定义、多处入口」的关键。

## 真实实现路径

物化入口是 `AgentRuntime._materialize_config()`，阅读时可按以下顺序对照：

1. `resolve_runtime_budget(definition.runtime_profile)` 给出默认轮次；字段级 `max_turns` / `max_tool_calls_per_turn` 可覆盖。
2. 非空 `tools.allow` → `ToolRegistry.scoped(..., match="glob")` 并重建 `ToolExecutor`；这是领域隔离最硬的一层。
3. `tools.deny` → `QueryEngineConfig.tools_deny_patterns`，即使 allow 放宽也仍隐藏危险工具。
4. `memory.enabled is False` → 不注入 `AgentMemory`；`formation` 控制是否对 episodic/semantic/procedural 写回。
5. `hooks` 非空 → `hook_manager.filter_by_names(...)`，实现按 Agent 裁剪守卫。
6. `prompt_variant`、`prompt_template_variant`、`context_recipe=definition.resolved_recipe()` 进入引擎，驱动 `ContextManager`。

`resolved_recipe()` 规则：显式 `context_recipe`，否则用 `prompt_variant`。于是「财务专家文案」可以复用 `default_agent` 的完整上下文装配，而不必复制二十多个 source id。

## 分步示例：设计「发票核对」领域 Agent

### 第 1 步：写清边界

假设需求是：读 PDF/表格、查知识库、禁止发邮件；温度偏低求稳；召回条数受限；本域不写程序性记忆；最多十五轮。把「不要什么」与「要什么」写成清单，再映射到字段，比先写一大段角色扮演更可靠。

### 第 2 步：落成定义

```python
from leagent.sdk import AgentBuilder, AgentDefinition

invoice_agent: AgentDefinition = (
    AgentBuilder("invoice_agent")
    .describe("核对发票金额、销方与合同条款")
    .variant("default_agent")
    .recipe("default_agent")
    .tools(
        allow=["pdf_*", "docx_*", "knowledge_*", "code_execution"],
        deny=["email_*"],
        max_tools=16,
    )
    .model(task="chat", temperature=0.1, max_output_tokens=4096)
    .memory(enabled=True, recall_limit=4, formation=False)
    .runtime(profile="standard", max_turns=15, max_tool_calls_per_turn=6)
    .metadata(domain="finance", kind="domain")
    .build()
)

assert invoice_agent.resolved_recipe() == "default_agent"
```

### 第 3 步：对照内置子 Agent 取舍

内置 `coding_agent` 使用 `DEFAULT_CODING_AGENT_TOOLS` 白名单、`memory.formation=False`、`runtime_profile="coding_long"` 且 `max_turns=40`；`script_agent` 关闭记忆、轮次更短。领域 Agent 也应显式写出收紧项，而不是继承「几乎全开」的默认空 allow。

### 第 4 步：注册并运行

```python
from leagent.sdk import AgentRuntime, get_agent_registry

reg = get_agent_registry()
reg.register(invoice_agent, replace=True)
runtime = AgentRuntime.from_service_manager(service_manager, registry=reg)
result = await runtime.run("invoice_agent", "核对本期三张发票与合同总价是否一致。")
```

## 验证命令

```bash
cd backend && uv run pytest \
  tests/test_sdk_surface.py \
  tests/test_runtime_sdk.py \
  tests/workflow/test_agent_nodes.py -q
```

关注：definition 字段是否完整传到引擎与 Agent 节点；`replace=False` 时重复注册是否抛错；未知 agent 名的 fallback 行为是否符合预期。

## 常见误区

1. **只写更长的 system_prompt。** 工具面、记忆与预算才是硬边界；文案只能表达倾向。
2. **照搬 `default_agent` 的空 allow。** 空 allow 表示几乎全部可见工具，对财务/客服等高风险域通常过宽。
3. **混淆 `formation` 与 `enabled`。** `enabled=False` 跳过召回接线；`formation=False` 仍可召回但不写回。
4. **`prompt_variant` 与模板文件名不一致。** `IdentitySource` 按 variant 取 markdown；名字写错会得到空正文或异常日志。
5. **把 `metadata` 当运行时开关。** 元数据服务于展示与编排标签，不驱动内核。

## 业内对照

AutoGen / CrewAI 常把 role 与 tools 绑在实例上；LangGraph 更常把领域逻辑拆进节点函数。LeAgent 选择可序列化的 Pydantic 契约：同一对象既能进 YAML，也能生成工作流节点。OpenAI Assistants 的 instructions + tools 与此类似，但此处把 memory、recipe、runtime profile 一并一等公民化，方便评审「这个域到底被授予了什么」。

## 总结与延伸

领域 Agent = 可序列化的权限与预算契约 + 可装配的 persona/recipe。下一篇用配置文件批量注册同一契约：[11｜从 YAML 加载和注册 Agent](11-yaml-agent-registration.md)。工程化清单见 [12](12-production-ready-agent.md)。
