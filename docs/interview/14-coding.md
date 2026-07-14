# 十四、Coding 高频题

> 本章代码用于说明核心思路，是刻意省略鉴权、持久化、流式协议、限流、完整类型与异常分类的紧凑示例/伪代码，**不能声称可直接复制到生产环境**。生产实现可对照 LeAgent 的 `backend/leagent/agent/`、`tools/`、`sdk/kernel/`、`memory/`、`workflow/engine/` 与 `telemetry/trace/`。

## 14.1 实现 ReAct Loop

**核心思路：**维护消息状态，循环执行“模型决策 → 动作 → 环境观察”，直到模型给出 final answer 或触发轮数、token、时间预算。观察必须结构化写回，错误也应成为可供下一轮修正的 observation。

```python
async def react(question, llm, tools, max_turns=8):
    messages = [{"role": "user", "content": question}]
    for turn in range(max_turns):
        decision = await llm.decide(messages, tool_schemas=tools.schemas())
        if decision.final_answer is not None:
            return {"answer": decision.final_answer, "turns": turn + 1}

        call = decision.tool_call
        result = await tools.execute(call.name, call.arguments)
        messages += [
            {"role": "assistant", "tool_calls": [call.to_dict()]},
            {"role": "tool", "tool_call_id": call.id,
             "content": result.to_json()},
        ]
    raise RuntimeError("turn budget exhausted")
```

面试加分点：不要要求模型输出私有思维链；系统只需可见的 action、observation、停止原因和验证结果。LeAgent 中 `QueryEngine.submit_message()` 持有会话内状态，`leagent.agent.query` 实现 think-act-observe 生成器，`leagent.sdk.kernel.loop.run_loop` 将其统一映射为 `AgentEvent`，并处理 hook 与 checkpoint。

## 14.2 实现 Tool Calling Agent

**核心思路：**把工具暴露为 JSON Schema；校验模型返回的工具名和参数；通过受控 executor 执行；用 `tool_call_id` 关联请求与结果。模型只提议动作，执行器拥有权限和资源控制。

```python
async def tool_agent(prompt, model, registry, executor):
    history = [{"role": "user", "content": prompt}]
    while True:
        reply = await model.chat(history, tools=registry.schemas(limit=20))
        history.append(reply.message)
        if not reply.tool_calls:
            return reply.content

        for call in reply.tool_calls:
            tool = registry.get(call.name)          # 拒绝未知工具
            args = tool.validate_json(call.arguments)
            output = await executor.execute(
                tool.name, args, call_id=call.id, timeout=30
            )
            history.append({
                "role": "tool", "tool_call_id": call.id,
                "content": output.safe_json(),
            })
```

生产还需参数规范化、敏感字段脱敏、审批、幂等键、并发上限和输出尺寸限制。LeAgent 对应实现是 `tools/registry.py::ToolRegistry` 与 `tools/executor.py::ToolExecutor`；后者在执行前做 enabled/permission 检查，并统一返回 `ExecutionResult`。

## 14.3 实现 Multi-Agent Router

**核心思路：**先用确定性硬约束筛选，再用分类器或小模型选择专业 Agent；高风险请求保留人工门禁，低置信度回退到通用 Agent。路由输出必须包含理由和置信度，以便评测。

```python
from dataclasses import dataclass

@dataclass
class Route:
    agent: str
    confidence: float
    reason: str

async def route(task, agents, classifier):
    eligible = [a for a in agents if a.policy.allows(task)]
    if not eligible:
        return Route("human_review", 1.0, "no eligible agent")

    label, confidence = await classifier.predict(
        task.text, labels=[a.name for a in eligible]
    )
    if task.risk == "high" or confidence < 0.7:
        return Route("general_agent", confidence, "risk/low confidence fallback")
    return Route(label, confidence, "intent classification")
```

Router 不应让 Agent 直接共享可变内存或复用同一个权限主体。LeAgent 可由 `AgentDefinition` 声明工具/模型/记忆策略，由 `AgentRuntime.delegate()` 创建子运行；模型层再通过 `TaskResolver` 选择逻辑任务对应 provider/model，并用 `run_id/parent_run_id` 关联父子 trace。

## 14.4 实现 Memory Store

**核心思路：**区分工作记忆、情景记忆、语义事实和程序记忆。写入前做形成决策，读取时做租户过滤、混合召回、重排和 token 预算控制；不要把聊天全文无条件向量化。

```python
class MemoryStore:
    def __init__(self, rows, vectors, embed):
        self.rows, self.vectors, self.embed = rows, vectors, embed

    async def remember(self, item):
        if not formation_policy(item):       # 价值、稳定性、敏感性、重复度
            return None
        item.embedding = await self.embed(item.search_text)
        await self.rows.upsert(item.id, item.metadata, item.content)
        await self.vectors.upsert(item.id, item.embedding)
        return item.id

    async def recall(self, query, *, tenant_id, limit=6):
        q = await self.embed(query)
        dense = await self.vectors.search(q, filter={"tenant": tenant_id})
        lexical = await self.rows.search_text(query, tenant_id=tenant_id)
        return rerank_and_pack(dense + lexical, limit=limit, token_budget=2000)
```

生产需处理删除传播、数据保留、embedding 版本、事实冲突、时间衰减和降级路径。LeAgent 的 `memory/agent_memory.py::AgentMemory` 是统一门面，提供 episode、fact、procedure 三类写入和混合 recall；向量后端不可用时应允许词法降级，而不是阻塞主 Agent。

## 14.5 实现 Agent State Machine

**核心思路：**把隐含在循环里的状态显式化，使超时、人工审批、恢复和错误路径可验证。状态转换由事件驱动；终态不可再次执行；每个副作用都携带幂等键。

```python
from enum import Enum

class S(Enum):
    THINKING = "thinking"
    ACTING = "acting"
    WAITING = "waiting"
    DONE = "done"
    FAILED = "failed"

TRANSITIONS = {
    (S.THINKING, "tool"): S.ACTING,
    (S.THINKING, "answer"): S.DONE,
    (S.ACTING, "observed"): S.THINKING,
    (S.ACTING, "approval_required"): S.WAITING,
    (S.WAITING, "resume"): S.ACTING,
}

def apply(state, event):
    if event.type == "fatal":
        return S.FAILED
    try:
        return TRANSITIONS[(state, event.type)]
    except KeyError:
        raise ValueError(f"illegal transition: {state} + {event.type}")
```

实际系统还应持久化 `state_version` 并用 CAS/事务防止重复 resume。LeAgent 将不同状态分给不同 owner：聊天 transcript 属于 session store，Agent 暂停属于 `CheckpointStore`，工作流运行属于 workflow state store；`PauseToken` 统一表达恢复入口，但不混淆三类数据。

## 14.6 实现 LangGraph Workflow

**核心思路：**用有类型的 state 在节点间传递数据，通过条件边表达“继续调用工具还是结束”。LangGraph 适合显式图编排；开放式思考仍应限制在某个 Agent 节点内。以下是 API 风格伪代码，具体签名以安装版本为准。

```python
from typing import TypedDict
from langgraph.graph import StateGraph, END  # 示意导入，具体 API 以版本为准

class State(TypedDict):
    messages: list
    attempts: int

async def think(state):
    reply = await model.chat(state["messages"], tools=tool_schemas)
    return {"messages": state["messages"] + [reply],
            "attempts": state["attempts"] + 1}

async def act(state):
    call = state["messages"][-1].tool_calls[0]
    obs = await executor.execute(call.name, call.arguments)
    return {"messages": state["messages"] + [obs]}

def next_step(state):
    last = state["messages"][-1]
    return "act" if last.tool_calls and state["attempts"] < 8 else "end"

graph = StateGraph(State)
graph.add_node("think", think)
graph.add_node("act", act)
graph.add_conditional_edges("think", next_step, {"act": "act", "end": END})
graph.add_edge("act", "think")
app = graph.compile(checkpointer=checkpointer)
```

如果不依赖 LangGraph，LeAgent 的 `WorkflowExecutor` 提供原生 DAG：先验证 `WorkflowDocument`，再拓扑调度 ready nodes，支持并行、缓存、进度、取消和 resume；`Agent` 节点内部仍通过统一 `AgentRuntime/run_loop`，避免出现第二套 think-act kernel。

## 14.7 实现 Retry Mechanism

**核心思路：**只重试瞬态且幂等的失败；指数退避加入 jitter；遵守服务端 `Retry-After`；设置总预算和熔断。参数错误、权限拒绝和业务校验失败通常不应原样重试。

```python
import asyncio, random

async def retry(op, *, attempts=4, base=0.2, retryable):
    last = None
    for n in range(attempts):
        try:
            return await op()
        except Exception as exc:
            last = exc
            if not retryable(exc) or n == attempts - 1:
                raise
            delay = base * (2 ** n) + random.uniform(0, base)
            await asyncio.sleep(delay)
    raise last

result = await retry(
    lambda: provider.complete(request, idempotency_key=run_id),
    retryable=lambda e: e.status in {408, 429, 500, 502, 503, 504},
)
```

工具 retry 与模型 retry 不能混为一谈：写操作若无幂等语义，重试可能重复扣款或发两封邮件。LeAgent 的 provider registry 带健康状态与 circuit breaker；`ToolExecutor` 和 workflow `NodeRunner` 分别在各自边界治理工具和节点执行，trace 应记录每次 attempt，而不是只记录最终结果。

## 14.8 实现 Tool Registry

**核心思路：**注册表负责名称唯一性、别名、元数据与 schema；executor 负责执行。注册时做严格校验，生成 schema 时应用 allow/deny 和上下文筛选，避免把上百个工具全部塞给模型。

```python
class ToolRegistry:
    def __init__(self):
        self._tools, self._aliases = {}, {}

    def register(self, tool):
        if not tool.name or tool.name in self._tools:
            raise ValueError("invalid or duplicate tool")
        validate_json_schema(tool.parameters)
        self._tools[tool.name] = tool
        for alias in tool.aliases:
            if alias in self._aliases:
                raise ValueError("duplicate alias")
            self._aliases[alias] = tool.name

    def get(self, name):
        canonical = self._aliases.get(name, name)
        return self._tools[canonical]

    def schemas(self, allow=None):
        selected = (t for t in self._tools.values() if t.enabled)
        return [t.to_function_schema() for t in selected if matches(t, allow)]
```

生产注册表还需版本、缓存失效、插件隔离、描述质量检查和租户策略。LeAgent 的 `ToolRegistry` 已包含 category、alias、deny filtering、enabled gating、搜索 hint 和 schema cache；工作流工具节点也复用同一注册表，而不是复制一份工具目录。

## 14.9 实现 Agent Checkpoint

**核心思路：**checkpoint 保存“继续执行所需的最小充分状态”，而不是仅保存最终文本。至少包括消息快照、turn、usage、暂停原因、版本和恢复所需 metadata；保存后返回不可猜测的 ID。

```python
from dataclasses import asdict
from uuid import uuid4

async def pause(run, store, reason):
    checkpoint = {
        "checkpoint_id": uuid4().hex,
        "session_id": run.session_id,
        "agent_name": run.agent_name,
        "turn": run.turn,
        "messages": list(run.messages),
        "usage": dict(run.usage),
        "reason": reason,
        "schema_version": 1,
    }
    await store.upsert(checkpoint["checkpoint_id"], checkpoint)
    return checkpoint["checkpoint_id"]

async def resume(checkpoint_id, answer, store):
    cp = await store.load(checkpoint_id)
    assert cp and cp["reason"] == "awaiting_user_input"
    cp["messages"].append({"role": "user", "content": answer})
    return rebuild_run(cp)
```

生产需校验 owner/tenant、单次消费或版本冲突、过期时间、加密和 schema migration。LeAgent 的 `InMemoryCheckpointStore` 用于测试/单进程，`SQLCheckpointStore` 持久化到 `agent_checkpoints`；`run_loop` 在 awaiting input、预算耗尽、模型错误等可恢复原因上快照 `QueryEngine.mutable_messages`，并生成 `PauseToken`。

## 14.10 实现 Agent Trace System

**核心思路：**以 `run_id` 为 trace_id，模型、工具、子 Agent、压缩和 workflow node 为 span；事件只追加，主路径写入应 best-effort、可批量、可脱敏。trace 与聊天记录、checkpoint 是不同数据平面。

```python
from contextlib import asynccontextmanager
from time import monotonic
from uuid import uuid4

@asynccontextmanager
async def span(store, trace_id, kind, attrs=None, parent_id=None):
    span_id, started = uuid4().hex, monotonic()
    await store.append({"event": "start", "trace_id": trace_id,
                        "span_id": span_id, "parent_id": parent_id,
                        "kind": kind, "attrs": redact(attrs or {})})
    try:
        yield span_id
    except Exception as exc:
        await store.append({"event": "end", "span_id": span_id,
                            "status": "error", "error": safe_error(exc)})
        raise
    else:
        await store.append({"event": "end", "span_id": span_id,
                            "status": "ok",
                            "duration_ms": int((monotonic()-started)*1000)})
```

关键指标包括端到端成功率、各 span 延迟、TTFB、token/费用、工具错误分类、重试、人工介入和恢复成功率。LeAgent 的 `TraceRecorder` 采用 fire-and-forget 与批量 flush，`trace_id = run_id`，可选截断 preview/外置 payload；`TraceHook` 补充 compact 和 subagent 边界，API 支持 span tree、JSONL 导出和按模型统计。
