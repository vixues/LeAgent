# 07｜用纯 Python 搭一个最小 Agent

## 定位、难度与先修

- **定位**：脱离框架，亲手写一个教学用 think-act 循环；再映射回 LeAgent。
- **难度**：★★☆☆☆
- **先修**：[02 Think-Act Loop](02-think-act-loop.md)、[01 Agent 与 Chatbot](01-agent-vs-chatbot.md)

> **重要**：本篇最小循环是**教学脚手架**，不是生产路径。生产请用 `AgentRuntime`（[12](12-production-ready-agent.md)）。

本篇的价值是让你「看见骨架」：框架后来补上的安全、预算、持久化、钩子与多入口，全是长在这根骨架上的工程肌肉。

## 学习目标

1. 用约 80 行 Python 写出「调用模型 → 解析工具 → 执行 → 回填 → 终止」循环。  
2. 对照理解 LeAgent 为何拆出 Runtime、QueryEngine、Executor。  
3. 认清最小实现缺失的安全、预算、持久化与可观测能力。  
4. 能解释 `tool_call_id` 与 `max_turns` 为何从第一天就不可省。

## 核心心智模型：先求闭环，再补工程

最小 Agent 只需四个部件：

```text
messages + tools_schema → LLM → (text | tool_calls)
tool_calls → python functions → tool messages → 再送 LLM
```

生产系统还要加：权限、沙箱、上下文配方、记忆、压缩、checkpoint、hooks、追踪、多入口装配。教学上先闭环，才能看清这些层各自解决什么。对照第 03 篇：生产里这些层仍然汇入**一个** `run_loop`，而不是每个教程复制一份循环。

## 数据流：教学循环 vs 生产循环

```text
教学：
  run_min_agent → call_llm → tools dict → messages.append(tool)

生产：
  AgentRuntime.stream/run
    → run_loop
      → QueryEngine.submit_message / query
        → LLMService（StreamChunk）
        → ToolExecutor（权限/并发/approval）
        → Session / Checkpoint / Hooks / Trace 副作用
```

相邻篇：[08](08-model-and-streaming.md) 接真模型与流；[09](09-agent-builder.md) 声明契约；[20](20-build-a-base-tool.md) 把 `echo` 升级为 `BaseTool`。

## 分步实现：教学最小循环

```python
"""teaching_min_agent.py — 教学示例，勿用于生产。"""
from __future__ import annotations

import json
from typing import Any, Callable

ToolFn = Callable[..., Any]


def run_min_agent(
    *,
    call_llm: Callable[[list[dict], list[dict]], dict],
    tools: dict[str, ToolFn],
    tools_schema: list[dict],
    user: str,
    max_turns: int = 6,
) -> str:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "你是会使用工具的助手。任务完成后再用自然语言作答。"},
        {"role": "user", "content": user},
    ]
    for _ in range(max_turns):
        resp = call_llm(messages, tools_schema)
        tool_calls = resp.get("tool_calls") or []
        content = resp.get("content") or ""
        if not tool_calls:
            messages.append({"role": "assistant", "content": content})
            return content
        messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
        for tc in tool_calls:
            name = tc["function"]["name"]
            args = json.loads(tc["function"]["arguments"] or "{}")
            if name not in tools:
                result = {"error": f"unknown tool {name}"}
            else:
                try:
                    result = tools[name](**args)
                except Exception as exc:  # noqa: BLE001 — 教学示例
                    result = {"error": str(exc)}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": json.dumps(result, ensure_ascii=False),
                }
            )
    return "达到 max_turns，未能完成任务。"


def echo(text: str) -> dict[str, str]:
    return {"echo": text}


TOOLS = {"echo": echo}
SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "echo",
            "description": "回显文本，用于验证工具链路",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    }
]
```

把 `call_llm` 接到任意 OpenAI 兼容客户端即可跑通。观察：没有权限模型、没有并行调度、没有 transcript 持久化、工具错误只以字符串回填、没有流式事件协议、没有 pause/resume。

故意做的练习：

1. 去掉 `tool_call_id`，看下一轮模型是否混乱。  
2. 去掉 `max_turns`，对总失败工具形成死循环。  
3. 在工具里执行「任意路径写文件」，体会为何生产要沙箱。

## 映射到 LeAgent

| 教学部件 | LeAgent 生产对应 |
|----------|------------------|
| `run_min_agent` | `query()` + `run_loop` |
| `tools` dict | `ToolRegistry` + `BaseTool` |
| `call_llm` | `LLMService` / providers |
| `messages` 列表 | `QueryEngine.mutable_messages` + `SessionManager` |
| `max_turns` | `RuntimeBudget` / `AgentDefinition.max_turns` |

公共集成面：

```python
from leagent.sdk import AgentRuntime

runtime = AgentRuntime.from_service_manager(service_manager)
result = await runtime.run("default_agent", "用 echo 思路理解工具链后直接回答：你好")
print(result.text, result.reason)
```

## 验证命令

教学脚本可自测；生产路径回归：

```bash
cd backend
uv run pytest tests/test_runtime_sdk.py tests/test_tool_bootstrap_and_factory.py tests/test_executor.py -v
```

离线多轮剧本可参考 `backend/tests/integration/conftest.py` 的 `scripted_turn` / `drive_query_engine`。

## 常见误区与排障

1. **把教学循环直接塞进线上服务**：缺少沙箱与鉴权几乎必然出事。  
2. **工具结果不带回 `tool_call_id`**：多数模型会在下一轮混乱。  
3. **无 max_turns**：单次失败工具会导致死循环烧钱。  
4. **假设框架「只是多写了几行」**：真正成本在上下文治理与恢复语义。  
5. **在业务 handler 里复制一份「稍微增强」的循环**：很快与内核分叉（违背第 03 篇）。  

排障教学循环：打印每轮 messages 长度与 tool 对；排障生产路径：从 `AgentEvent.RESULT.reason` 与追踪切入，而不是在业务里再包一层私有 retry。

## 业内对照

几乎所有入门教程（OpenAI function calling、LangGraph ReAct、ADK quickstart）都从同类最小循环起步，再引入 Session、Memory、Guardrail。LeAgent 把「下一步」标准化进 SDK，并坚持单内核多入口。

## 总结与延伸阅读

最小循环证明 Agent 的骨架极简；工程框架的价值在于把骨架变成可审计、可恢复、可多入口复用的系统。学会骨架是为了**尊重**生产边界，而不是绕过它们。

- [08｜模型与流式输出](08-model-and-streaming.md)
- [09｜AgentBuilder](09-agent-builder.md)
- [20｜实现 BaseTool](20-build-a-base-tool.md)
- [12｜工程化 Agent](12-production-ready-agent.md)
