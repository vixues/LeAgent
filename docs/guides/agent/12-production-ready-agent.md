# 12｜把最小 Agent 补成工程化 Agent

## 定位与先修

[07](07-minimal-python-agent.md) 的教学 loop 足以解释「模型决定、程序执行、结果回流」，但不能直接上线。本篇把「最小可跑」补成「可治理」：统一入口、声明式定义、上下文装配、预算、会话与 checkpoint、hooks，以及测试闭环。建议先修 07–11，并回顾 [01](01-agent-vs-chatbot.md)、[02](02-think-act-loop.md)。提示词分层从下一章 [13](13-layered-prompts.md) 展开。

所谓工程化，不是把 Prompt 写得更长，而是让权限、状态、预算与观测都有明确所有者。

## 学习目标

完成本篇后，你应该能：

1. 对照教学 loop，列出生产路径多出来的工程面。
2. 按 `ServiceManager` → `RuntimeContext` → `AgentRuntime` 的顺序装配依赖。
3. 为领域 Agent 配齐 tools、memory、recipe、`max_turns` 与 hooks。
4. 区分会话 transcript、checkpoint 与 prompt fingerprint 各自解决的问题。

## 心智模型：从「会调用工具」到「可长期运行」

教学 Agent 常可缩写为：

```text
while True:
    决策 = 模型(消息)
    若有工具: 执行并把结果追加后再循环
    否则: 返回最终答复
```

工程化 Agent 至少还要具备：

```text
声明契约（AgentDefinition）
  + 依赖单例（RuntimeContext：LLM、工具、hooks、checkpoint、memory）
  + 统一内核（run_loop → QueryEngine → query）
  + 上下文治理（ContextManager / recipe / budget / RelevanceGate）
  + 状态所有权（TieredSessionStore vs CheckpointStore）
  + 事件与追踪（AgentEvent、ExecutionRun、可选 OTel）
  + 测试与回归（SDK surface、context、runtime）
```

缺少任一层，系统会在真实会话长度、权限审批或并发入口下露出缺口。这也是为何业务代码不应复制教学 loop，而应复用同一内核。

## 真实实现路径

1. **不要手搓 ServiceManager 生命周期。** 使用 `AgentRuntime.from_service_manager(...)`，让 `RuntimeContext` 成为工具表、LLM、`prompt_builder`、session、hooks、checkpoint 的单一工厂出口。
2. **用 Definition 表达策略。** Builder 或 YAML 写清 allow/deny、温度、recall、`resolved_recipe()`、轮次上限。
3. **所有业务入口走 Runtime。** Chat SSE、SDK、后台任务、子 Agent、工作流节点最终都应进入 `run_loop`；保留给测试与内核内部的才是直接 `QueryEngine.submit_message()`。
4. **上下文必须有 ContextManager。** `PromptBuilder.build()` 在缺少 `context.context_manager` 时抛出 `ValueError`——旧的「仅 registry」 fallback 已删除。
5. **区分两类状态。** 聊天 transcript 归 session store；单轮暂停恢复归 checkpoint；两者相关但不是同一张表。
6. **补齐验证。** 至少覆盖 SDK 导出、定义物化、context prepare，以及关键 deny/fallback。

## 分步示例：检查清单式装配

### 第 1 步：写出契约

```python
from leagent.sdk import AgentBuilder

ops = (
    AgentBuilder("ops_agent")
    .describe("值班运维助手")
    .variant("default_agent")
    .tools(allow=["web_search", "code_execution", "bash_*"], deny=["email_*"], max_tools=20)
    .model(task="chat", temperature=0.1)
    .memory(enabled=True, recall_limit=6, formation=True)
    .runtime(profile="standard", max_turns=20, max_tool_calls_per_turn=8)
    .build()
)
```

### 第 2 步：注册并以会话方式运行

```python
from leagent.sdk import AgentRuntime, get_agent_registry

get_agent_registry().register(ops, replace=True)
runtime = AgentRuntime.from_service_manager(service_manager)
session = runtime.session("ops_agent", session_id=sid, user_id=uid)
r1 = await session.turn("梳理昨天失败任务的摘要需求。")
r2 = await session.turn("根据刚才结果给出复盘提纲。")
```

### 第 3 步：需要过程可见性时改用 stream

```python
from leagent.sdk import AgentEventType

async for event in runtime.stream("ops_agent", "汇总本周 cron 失败"):
    if event.type == AgentEventType.TOOL_USE:
        print("tool", event.data["name"])
    elif event.type == AgentEventType.RESULT:
        print("reason", event.data["reason"])
```

### 第 4 步：对照工程缺口清单

- 长对话：session 压缩与 context budget（第 16、28 篇）。
- 重型域手册：`RelevanceGate` 按需注入（第 17 篇）。
- 稳定前缀：关注 `stable_hash` / prefix hash（第 18 篇）。
- 人机协同：hooks 与 checkpoint resume（第 30、43 篇）。

把这份清单当成上线前的门禁，而不是读完教程的点缀。

## 验证命令

```bash
cd backend && uv run pytest \
  tests/test_sdk_surface.py \
  tests/test_runtime_sdk.py \
  tests/test_context/test_prompt_builder_integration.py \
  tests/test_prompts_package.py -q
```

这些用例能在无真实模型密钥时兜住公开契约；端到端模型调用另开集成环境。

## 常见误区

1. **复制教学 loop 进生产。** 会丢失权限、流式 tool-call 合并、恢复与遥测。
2. **以为注册了 Definition 就自动有了 ContextManager。** 仍需走 RuntimeContext 装配路径。
3. **把全部政策塞进 `system_prompt`。** 应拆到 recipe source 与 gated policies。
4. **把会话与 checkpoint 混为一谈。** 一个管 transcript SSOT，一个管 pause/resume token。
5. **只测 happy path。** 至少覆盖重复注册、无 ContextManager 的 builder、工具 deny、未知 agent fallback。

## 业内对照

Anthropic 的 computer-use / agent 示例强调工具循环与人机批准，对应 hooks、`permission_context` 与 checkpoint。OpenAI Agents SDK 强调 tracing 与 handoff，对应 `ExecutionRun` 与 subagents。LangGraph 强调可持久化图状态；LeAgent 对话路径以 query 循环加多层 store 分担状态，DAG 则走独立 workflow 引擎。对照的意义是选型，而不是 API 对齐。

## 总结与延伸

工程化 = 契约 + 单一内核入口 + 上下文治理 + 清晰状态边界。完成 01–12 后进入提示词与上下文工程：[13｜分层提示词](13-layered-prompts.md) → [14｜Persona 与 Recipe](14-persona-and-context-recipe.md)。
