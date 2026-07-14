# 01｜Agent 与 Chatbot：差别不只是“会不会调用工具”

## 定位、难度与先修

- **定位**：系列入门篇，建立阅读 Agent 代码前最重要的心智模型。
- **难度**：★☆☆☆☆
- **先修**：了解一次普通大模型对话包含 system、user、assistant 消息；会阅读基础 Python `async/await`。

## 学习目标

完成本篇后，你应该能：

1. 区分“生成一条回复”的 Chatbot 与“持续推进任务”的 Agent。
2. 用目标、状态、动作、观察、终止条件五个要素描述 Agent。
3. 找到 LeAgent 中公共 SDK、运行门面、查询引擎和会话状态各自的职责。
4. 解释为什么工具调用只是 Agent 的一个部件，而不是完整定义。

## 核心心智模型：从函数调用到受控状态机

最简单的 Chatbot 可以近似为一个函数：

```text
reply = model(system_prompt, conversation, user_message)
```

输入一次，输出一次。应用层可以保存聊天记录，但模型本身不负责判断“接下来是否要查询网页、读取文件、等待批准、重试或结束”。

Agent 更接近一个受预算约束的状态机：

```text
while 未达到终止条件:
    observation = 组装上下文(历史、文件、记忆、上一轮工具结果)
    decision = 模型决定(直接回答 或 发起工具调用)
    if decision 是工具调用:
        result = 执行工具并形成新观察
        将 result 放回状态，继续循环
    else:
        返回最终答案
```

因此，判断一个系统是不是 Agent，不应只问“能否 function calling”，而要问：

- **目标**：它是否围绕任务结果，而非单轮文本续写？
- **状态**：它是否保留对话、工具结果、文件和运行进度？
- **动作**：它是否能对外部环境产生受控影响？
- **观察**：动作结果是否会反馈给下一次决策？
- **终止**：它是否明确区分完成、等待用户、预算耗尽和错误？

一个只把天气 API 结果拼进模板的机器人“用了工具”，但未必拥有循环、恢复和状态治理。反过来，一个 Agent 即使某次任务无需工具，也仍通过同一套运行协议完成该轮。

## LeAgent 的真实实现

LeAgent 将上述职责拆成几层，而不是放进一个“万能 Agent 类”：

1. **公共入口**：`backend/leagent/sdk/__init__.py` 暴露 `AgentRuntime`、`AgentSession`、`AgentEvent`、`AgentResult` 等稳定接口。新调用方应优先从 `leagent.sdk` 导入。
2. **运行门面**：`backend/leagent/runtime/runtime.py` 的 `AgentRuntime` 将 Agent 定义、共享服务和本次调用参数组合成 `QueryEngine`，并提供 `run()`、`stream()`、`resume()`、`session()`。
3. **会话级编排**：`backend/leagent/agent/query_engine.py` 的 `QueryEngine` 持有可变消息历史、上下文管理器、累计用量和终止映射。每次 `submit_message()` 都会准备上下文和工具 schema。
4. **Think–Act–Observe 循环**：`backend/leagent/agent/query.py` 的 `query()` 负责流式调用模型、收集工具调用、执行工具、把工具结果放回消息列表，再进入下一轮。
5. **统一内核包装**：`backend/leagent/sdk/kernel/loop.py` 的 `run_loop()` 把 `QueryEngine` 产生的 `SDKMessage` 转成统一 `AgentEvent`，维护 `RunState`，并在可恢复终止时保存检查点。
6. **会话持久化**：`backend/leagent/services/session/manager.py` 与 `store.py` 负责持久会话状态；这与单次暂停恢复的 checkpoint 是两个不同概念。

这套分层说明：模型不是 Agent 的全部，`QueryEngine` 也不是对外 API 的全部。Agent 是模型、上下文、工具、循环、状态和治理共同形成的运行系统。

## 分步体验：先聚合结果，再观察事件

生产环境通常由 `ServiceManager` 完成依赖装配。最小公共 SDK 用法如下：

```python
from leagent.sdk import AgentRuntime

runtime = AgentRuntime.from_service_manager(service_manager)

result = await runtime.run(
    "default_agent",
    "查找项目中 Agent SDK 的版本，并说明依据。",
)

print(result.text)
print(result.reason)
print(result.tool_calls)
```

第 1 步，`runtime.run()` 适合只关心最终结果的调用方。它内部仍消费事件流，只是把文本、工具调用数、产物路径和终止原因聚合成 `AgentResult`。

第 2 步，改用 `stream()` 观察 Agent 的过程：

```python
from leagent.sdk import AgentEventType, AgentRuntime

runtime = AgentRuntime.from_service_manager(service_manager)

async for event in runtime.stream("default_agent", "读取 README 并概括项目定位"):
    if event.type == AgentEventType.STREAM_DELTA:
        print(event.data.get("content", ""), end="")
    elif event.type == AgentEventType.TOOL_USE:
        print("\n调用工具：", event.data["name"])
    elif event.type == AgentEventType.TOOL_RESULT:
        print("工具成功：", event.data.get("success"))
    elif event.type == AgentEventType.RESULT:
        print("\n终止原因：", event.data["reason"])
```

你看到的不是“模型内部思维”，而是系统允许公开的运行事件：文本增量、工具请求、工具结果与终止状态。这个区分对安全和可观测性都很重要。

第 3 步，多轮任务使用 `AgentSession`：

```python
session = runtime.session(
    "default_agent",
    session_id=session_id,
    user_id=user_id,
)

first = await session.turn("记住：本次只分析 backend。")
second = await session.turn("现在找出 Agent 的统一入口。")
print(session.turn_count, second.text)
```

`AgentSession` 会复用同一个 `QueryEngine`；其实现位于 `backend/leagent/sdk/session.py`。它是便捷句柄，不等于持久存储本身。

## 验证命令

在仓库根目录运行：

```bash
cd backend && uv run pytest tests/test_sdk_surface.py tests/test_runtime_sdk.py -v
```

重点观察：

- `AgentEvent` 与底层 `SDKMessage` 的 `{type, data}` 形状保持一致；
- `AgentResult.success` 对 `completed` 与 `awaiting_user_input` 的语义；
- SDK 公共导出是否完整；
- Agent 定义、工具策略和内存策略能否正确物化。

## 常见误区

1. **“用了工具就是 Agent”**：工具只是动作空间；没有观察回流和循环控制，仍可能只是一次编排。
2. **“Agent 就是超长 Prompt”**：Prompt 定义行为倾向，运行时负责状态、权限、预算、重试和持久化。
3. **“直接调用 `QueryEngine.submit_message()` 最灵活”**：在 LeAgent 中它保留给内核和测试。业务调用应走 `AgentRuntime`，否则会绕过统一事件、运行关联和 checkpoint。
4. **“多轮会话等于模型记住了过去”**：历史由系统保存并重新送入上下文；还要面对压缩、权限和 token 预算。
5. **“流式事件就是完整思维链”**：事件是产品协议，不应把不可见推理与可观测运行步骤混为一谈。

## 业内对照

- 普通 Chat Completions 风格接口主要完成“消息 → 回复”；Agent SDK 通常在其上增加工具、循环、交接、追踪和状态。
- Anthropic 的 tool use、OpenAI 的 function calling 都提供模型表达动作意图的机制，但应用仍需决定如何执行、回填与终止。
- LangGraph 更强调显式图状态与节点迁移；LeAgent 的基础对话路径则以 `query()` 循环为中心，并另有工作流 DAG。两者是架构取向映射，不是 API 等价。

## 总结与延伸阅读

Chatbot 的核心产物是一条回复；Agent 的核心产物是一个受控、可观察、可恢复的任务运行。LeAgent 通过 `leagent.sdk` 暴露稳定入口，以 `AgentRuntime → run_loop → QueryEngine → query()` 将“目标—动作—观察—终止”串起来。

继续阅读：

- [02｜Think–Act Loop](02-think-act-loop.md)
- [03｜一个内核，多种入口](03-one-kernel-many-ingresses.md)
- [Agent SDK 技术参考](../../technical/agent_sdk_zh.md)
- [执行拓扑](../../technical/execution-topology_zh.md)
- 源码：[`backend/leagent/sdk/__init__.py`](../../../backend/leagent/sdk/__init__.py)
- 测试：[`backend/tests/test_runtime_sdk.py`](../../../backend/tests/test_runtime_sdk.py)
