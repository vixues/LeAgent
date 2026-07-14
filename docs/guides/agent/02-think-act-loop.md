# 02｜Think–Act Loop：Agent 如何把回答变成行动

## 定位、难度与先修

- **定位**：从概念进入执行内核，理解一次 Agent 任务为何可能包含多次模型调用。
- **难度**：★★☆☆☆
- **先修**：已读 [01｜Agent 与 Chatbot](01-agent-vs-chatbot.md)；理解异步生成器和工具调用消息。

## 学习目标

1. 能画出 LeAgent 的 Think–Act–Observe 状态迁移。
2. 能解释 `QueryEngine`、`query()` 与 SDK `run_loop()` 的边界。
3. 理解工具结果为何必须作为消息回填，而不能只展示给用户。
4. 能识别完成、等待用户、预算终止和错误等出口。

## 核心概念：循环不是“让模型一直想”

Think–Act Loop 常被简写成：

```text
Think → Act → Observe → Think → ...
```

这里的 “Think” 更准确地说是**让模型基于当前上下文产出下一步决策**。系统不需要、也不应依赖暴露完整思维链。模型可能输出普通文本，也可能输出结构化工具调用。运行时只处理可执行、可审计的结果。

LeAgent 的循环可抽象成：

```text
messages₀
  │  调用模型
  ├─ 无工具调用 ───────────────► completed
  │
  ├─ ask_user ────────────────► awaiting_user_input
  │
  └─ 工具调用
       │ 权限检查、并发执行
       ▼
     tool results
       │ 追加到 messages
       └──────────────────────► 下一轮模型调用
```

循环必须有边界。否则模型可能重复调用失败工具，造成成本、延迟或副作用失控。LeAgent 使用 `max_turns`、`max_tool_calls_per_turn`、token 预算、终止原因和 abort 信号共同约束运行。

## LeAgent 的真实调用链

源码中有两层容易混淆的“loop”：

### 1. 行为循环：`agent/query.py`

`backend/leagent/agent/query.py` 的 `query(params)` 是实际 Think–Act–Observe 生成器。关键步骤是：

1. 整理消息，必要时自动压缩，并修补不完整的工具消息对；
2. `params.deps.call_model(...)` 流式调用模型；
3. 聚合文本、推理增量和工具调用；
4. 产生 `AssistantMessage`；
5. 无工具调用时产生 `Terminal(COMPLETED)`；
6. `ask_user` 或审批门触发 `Terminal(AWAITING_USER_INPUT)`；
7. 普通工具经 `_dispatch_tools(...)` 执行，结果追加为 tool 消息；
8. 构造新的 `QueryState`，`turn_count + 1` 后继续。

它还处理流中断、上下文过长、输出截断恢复和 token 预算。因而这不是简单的 `while True` 演示代码。

### 2. SDK 内核包装：`sdk/kernel/loop.py`

`backend/leagent/sdk/kernel/loop.py` 的 `run_loop()` 不重写上述复杂逻辑，而是驱动 `engine.submit_message()`：

```text
query() 的领域对象
  → QueryEngine._map_item()
  → SDKMessage
  → run_loop()
  → AgentEvent
```

`run_loop()` 同时维护 `RunState`、统计工具调用、派发工具生命周期 hook，并在可恢复终止时快照 `engine.mutable_messages`、保存 checkpoint。这种包装保留了成熟行为循环，又给所有入口统一了 SDK 协议。

### 3. 会话编排：`agent/query_engine.py`

`QueryEngine` 是“一段会话”的可变编排器。它在每次提交前：

- 把用户消息加入 `mutable_messages`；
- 并发准备上下文和筛选工具 schema；
- 建立 `ToolUseContext`，带入 session、user、agent、abort 和执行器；
- 调用 `query(params)`；
- 把领域事件映射为 `system_init`、`stream_delta`、`tool_use`、`tool_result`、`assistant`、`result`。

因此边界应记成：

```text
AgentRuntime：对外门面和依赖物化
run_loop：统一事件、RunState、hook、checkpoint
QueryEngine：会话级上下文与消息编排
query：真正的模型—工具循环
```

## 分步伪代码：对应真实实现

下面不是复制源码，而是保留关键控制点的教学版：

```python
async def think_act_observe(state, params):
    while state.turn_count < params.max_turns:
        prepared = compact_and_repair(state.messages)

        model_events = params.deps.call_model(
            messages=prepared,
            system_prompt=params.system_prompt,
            tools=params.tools_schema,
        )
        assistant = await collect_stream(model_events)
        yield assistant

        if not assistant.tool_calls:
            yield Terminal("completed")
            return

        if contains_ask_user(assistant.tool_calls):
            yield Terminal("awaiting_user_input")
            return

        calls = assistant.tool_calls[: params.max_tool_calls_per_turn]
        if needs_approval(calls):
            yield Terminal("awaiting_user_input")
            return

        results = await dispatch_tools(calls)
        for result in results:
            yield result

        state.messages += [assistant, *results]
        state.turn_count += 1

    yield Terminal("max_turns")
```

注意四点：

1. assistant 工具调用和 tool result 都必须进入历史，才能形成合法的下一轮模型输入；
2. 每轮最多执行有限工具数；
3. `ask_user` 不是失败，而是有意暂停；
4. 所有出口都应产生可机器判断的终止原因。

## 使用公共 SDK 观察循环

```python
from leagent.sdk import AgentEventType, AgentRuntime

runtime = AgentRuntime.from_service_manager(service_manager)

async for event in runtime.stream(
    "default_agent",
    "先查找 Agent SDK 版本，再读取定义它的源码并给出结论。",
):
    match event.type:
        case AgentEventType.SYSTEM_INIT:
            print("本轮工具：", event.data["tools"])
        case AgentEventType.TOOL_USE:
            print("ACT:", event.data["name"], event.data.get("input"))
        case AgentEventType.TOOL_RESULT:
            print("OBSERVE:", event.data["name"], event.data["success"])
        case AgentEventType.RESULT:
            print("STOP:", event.data["reason"])
```

`stream_delta` 适合实时渲染；判断任务是否结束必须看终态 `result`，不能以“暂时没有 token”代替。

## 验证命令

```bash
cd backend && uv run pytest tests/test_query_engine.py tests/test_kernel_checkpoint.py -v
```

如只想验证内核边界：

```bash
cd backend && uv run pytest tests/test_kernel_checkpoint.py::test_run_loop_preserves_wire_shape_and_forwards_kwargs -v
```

测试固定了几项重要事实：事件顺序保持 wire shape、提交参数透传、工具 hook 在统一位置触发、暂停时消息快照非空、普通完成默认不创建 checkpoint。

## 常见误区

1. **把 `run_loop()` 当作全部行为循环**：它是 SDK 内核包装；具体模型调用与工具回填在 `query()`。
2. **工具执行完就结束**：工具输出是新观察，模型通常还需读取它并决定下一步或组织最终答案。
3. **无限增加 `max_turns` 能提高成功率**：预算过大也会放大重复调用和成本。更应改善工具错误信息、上下文和恢复策略。
4. **并发工具可任意重排**：独立调用可并发，但结果仍需保留各自 `tool_call_id`，与 assistant 的请求正确配对。
5. **`awaiting_user_input` 是异常**：它是正常控制流，`AgentResult.success` 也将其视为可接受状态。
6. **流式 token 就是状态**：文本增量可丢失或重连；权威运行状态来自消息、终态与持久化组件。

## 业内对照

- ReAct 将 reasoning 与 acting 交替作为方法论；工程实现通常只暴露动作和观察，不要求泄露完整推理文本。
- OpenAI Agents SDK 的 runner loop、Anthropic 工具使用循环，都可映射到“模型决策—应用执行—结果回填”；具体事件和会话 API 不等价。
- LangGraph 将循环表达为图上的节点和边，适合显式分支与持久状态；LeAgent 的普通 Agent 路径以代码循环为核心，复杂确定性流程另由 workflow DAG 承担。

## 总结与延伸阅读

可靠 Agent 循环的关键不是“多想几次”，而是让每次决策都基于真实观察，并被预算、权限、终止语义和持久化约束。LeAgent 保留 `query()` 的成熟循环，再由 `run_loop()` 统一 SDK 事件和恢复能力。

继续阅读：

- [03｜一个内核，多种入口](03-one-kernel-many-ingresses.md)
- [04｜Agent 事件流](04-agent-event-stream.md)
- 源码：[`backend/leagent/agent/query.py`](../../../backend/leagent/agent/query.py)
- 源码：[`backend/leagent/sdk/kernel/loop.py`](../../../backend/leagent/sdk/kernel/loop.py)
- 测试：[`backend/tests/test_kernel_checkpoint.py`](../../../backend/tests/test_kernel_checkpoint.py)
