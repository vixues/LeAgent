# 09｜使用 AgentBuilder 声明 Agent

## 定位与先修

本文属于「从零搭建 Agent」中，把最小可跑脚本推进到可评审、可注册契约的一步。建议先完成 [07｜最小 Python Agent](07-minimal-python-agent.md) 与 [01｜Agent 与 Chatbot](01-agent-vs-chatbot.md)，并清楚对外执行入口是 `AgentRuntime` 而非散落的 `QueryEngineConfig`。你需要会阅读基础 Python 类型注解与链式调用。

实现落点分别是：[`runtime/builder.py`](../../../backend/leagent/runtime/builder.py)、[`runtime/definition.py`](../../../backend/leagent/runtime/definition.py)、[`runtime/runtime.py`](../../../backend/leagent/runtime/runtime.py)。公共导出可从 `leagent.sdk` 导入 `AgentBuilder`。

## 学习目标

完成本篇后，你应该能：

1. 说明 `AgentBuilder` 只负责产出 `AgentDefinition`，本身不会启动 think–act 循环。
2. 用链式 API 配置描述、人设变体、上下文 recipe、工具、模型、记忆与运行预算。
3. 区分 `from_definition()` 的增量覆盖与 `build()` 返回深拷贝的出站契约。
4. 把构建结果交给 `AgentRuntime.resolve()` / `run()` / `build_engine()` 完成物化执行。

## 心智模型：声明 What，运行时再物化 How

很多教程把 Agent 写成「带着 LLM 客户端的大类」。在 LeAgent 里职责被切开：

```text
AgentBuilder（可变草稿）
  → build() → AgentDefinition（纯声明契约）
    → AgentRuntime.resolve / build_engine
      → QueryEngineConfig + ContextManager
        → run_loop / query
```

| 契约 | 回答的问题 |
|------|------------|
| `AgentDefinition` | Agent **是什么**：策略、预算、委派对象 |
| `RuntimeContext` | **如何**取得 LLM、工具表、hooks、记忆、session |
| `AgentRuntime` | **如何跑**：把定义物化并进入统一内核 |

`AgentDefinition` 刻意不含 session_id、abort_event 这类每次调用才有的运行细节。Builder 的价值在于用可读的 fluent API 写出同一份可 YAML 化、可注册、可进工作流节点的契约，而不是在业务处理器里反复手搓配置字典。

## 真实实现路径

1. **构造**：`AgentBuilder(name)` 要求非空名称，内部持有可变的 `AgentDefinition`。
2. **Persona / 上下文**：`describe`、`variant(prompt_variant, template=...)`、`recipe(context_recipe)`、`system_prompt` / `append_system_prompt`。未设 recipe 时，`resolved_recipe()` 回落到 `prompt_variant`，因此「角色文案」与「上下文源清单」可以解耦（详见第 14 篇）。
3. **策略**：`tools(allow / deny / max_tools)`、`model(task / provider / model / temperature / max_output_tokens)`、`memory(enabled / recall_limit / formation)`、`runtime(profile / max_turns / max_tool_calls_per_turn)`。
4. **组合**：`hooks(*names)`、`subagents(*names)`、`metadata(**values)`。
5. **出站**：`build()` 返回 `model_copy(deep=True)`，避免之后改草稿污染已注册定义；`from_definition()` 适合基于内置定义做增量收紧。

`AgentRuntime.resolve()` 接受三种引用：已有 `AgentDefinition`、尚未 `build` 的 `AgentBuilder`（内部会调用 `build()`）、或注册表中的名字字符串。未知名字会打 warning 并回落到仅带该 `name` 的默认定义——实验方便，生产环境仍应显式 `register`。

物化阶段（`_materialize_config`）会把非空 `allow` 变成 scoped 工具表，把 `deny` 映射为每轮 deny patterns，按 `memory.enabled` 决定是否挂上 `AgentMemory`，并按 `hooks` 过滤共享 HookManager。

## 分步示例

### 第 1 步：声明客服域 Agent

```python
from leagent.sdk import AgentBuilder, get_agent_registry

support = (
    AgentBuilder("support_agent")
    .describe("客户支持专家")
    .variant("default_agent")
    .tools(allow=["web_search", "knowledge_*"], max_tools=12)
    .model(task="chat", temperature=0.3)
    .memory(recall_limit=8)
    .runtime(profile="standard", max_turns=12)
    .subagents("script_agent")
    .build()
)

get_agent_registry().register(support, replace=True)
assert support.resolved_recipe() == "default_agent"
```

### 第 2 步：在已有定义上增量收紧

```python
strict = (
    AgentBuilder.from_definition(support)
    .tools(deny=["web_search"], max_tools=8)
    .runtime(max_turns=6)
    .build()
)
```

### 第 3 步：交给 Runtime 执行

```python
from leagent.sdk import AgentRuntime

runtime = AgentRuntime.from_service_manager(service_manager)
result = await runtime.run(support, "用户询问退货时限，先查知识库再摘要。")
print(result.text, result.reason)
```

也可传入已注册名字 `"support_agent"`。工作流侧已注册定义可被提升为 `Agent.<name>` 节点，详见后续 DAG 教程。

## 验证命令

```bash
cd backend && uv run pytest tests/test_sdk_surface.py tests/test_runtime_sdk.py -v
```

重点看 fluent chain、policy 字段保留、以及 registry 注册语义。相关内置样例也在 `registry._builtin_definitions()` 中用同一套 Builder 写法生成。

## 常见误区

1. **以为 `build()` 会启动 Agent。** 它只返回定义；执行必须走 `AgentRuntime`。
2. **长期持有并反复修改同一 builder 草稿。** 应保存 `build()` 结果，或每次 `from_definition` 再改。
3. **把空 `allow` 理解成「禁用全部工具」。** 语义是可见注册表中的全部工具（仍受 `deny` 约束）；领域 Agent 通常应显式收紧。
4. **混用深层 `QueryEngine` 构造绕过 Runtime。** 会丢掉统一事件、checkpoint 与关联 run_id。
5. **写了 `subagents` 却不去审阅子定义自己的 tools/memory。** 委派名单不等于继承父策略。

## 业内对照

OpenAI Agents SDK 的 `Agent(...)` 构造器、Google ADK 的 agent 配置对象、Anthropic 示例里的 instruction+tools 打包，本质都是「先声明能力边界」。LeAgent 额外把 `context_recipe` 与 `prompt_variant` 拆开，并把同一 `AgentDefinition` 提升到工作流节点，使声明式契约横跨聊天、SDK 与 DAG。

## 总结与延伸

`AgentBuilder` 是代码优先的定义作者；稳定真相始终是 `AgentDefinition`。接下来把这份契约按业务域补全：[10｜设计一个领域 Agent](10-domain-agent-definition.md)。也可对照 [11｜YAML 注册](11-yaml-agent-registration.md) 与技术参考中的 Runtime 文档。
