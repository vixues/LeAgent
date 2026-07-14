# 04｜理解 AgentEvent 流式事件协议

## 定位、难度与先修

- **定位**：掌握 Agent 运行时如何把内部进度对外表达为可消费事件流。
- **难度**：★★☆☆☆
- **先修**：[03 一套 Kernel，多个入口](03-one-kernel-many-ingresses.md)

## 学习目标

1. 列出 `AgentEventType` 的主要类型及其出现时机。
2. 解释为何 `{type, data}` 线缆形态必须保持稳定。
3. 用 SDK 消费流式事件并聚合为 `AgentResult`。
4. 区分 `stream_delta`、`tool_use` / `tool_result` 与终态 `result`。

## 核心心智模型：增量可见，终态可信

对 UI 来说，用户要实时看到文字与工具状态；对持久化与评测来说，必须以终态为准。因此事件流分成两类：

- **增量事件**：`stream_delta`、`tool_call_delta`——可断开、可重放不完整，适合展示。
- **结构事件**：`assistant`、`tool_use`、`tool_result`、`workspace_attachments`——推进对话与工具状态。
- **终态事件**：`result`——携带 `reason`、`error`、`usage`，可选 `checkpoint_id` / `pause_token`。

```text
模型吐 token → stream_delta*
完整助手消息 → assistant / assistant_tools
发起工具 → tool_use → 执行 → tool_result
产出文件 → workspace_attachments
结束 → result（completed | awaiting_user_input | aborted | ...）
```

## LeAgent 的真实实现

定义在 `backend/leagent/sdk/events.py`：

```python
class AgentEventType(StrEnum):
    SYSTEM_INIT = "system_init"
    STREAM_DELTA = "stream_delta"
    TOOL_CALL_DELTA = "tool_call_delta"
    ASSISTANT = "assistant"
    ASSISTANT_TOOLS = "assistant_tools"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    WORKSPACE_ATTACHMENTS = "workspace_attachments"
    RESULT = "result"
```

`AgentEvent.from_sdk_message()` 直接复制 `SDKMessage.type` 与 `data`。内核 `run_loop`（`backend/leagent/sdk/kernel/loop.py`）在此处：

- 翻译事件
- 在 `TOOL_USE` / `TOOL_RESULT` 单点派发 hooks
- 在可恢复 `reason` 上写入 checkpoint，并把 `checkpoint_id` 放入 `result.data`

`AgentResult.success` 把 `completed` 与 `awaiting_user_input` 都视为可接受终态——暂停等人不是失败。

Chat SSE 与 WebSocket 序列化器依赖稳定线缆形状；因此改内核时优先在翻译层适配，而不是改前端协议。

## 分步示例：消费流并拼装结果

```python
from leagent.sdk import AgentRuntime, AgentEventType

runtime = AgentRuntime.from_service_manager(service_manager)
parts: list[str] = []

async for event in runtime.stream("default_agent", "分析这份 CSV", session_id=sid):
    data = event.data or {}
    if event.type == AgentEventType.STREAM_DELTA:
        parts.append(str(data.get("content") or ""))
    elif event.type == AgentEventType.TOOL_USE:
        print("tool →", data.get("name"))
    elif event.type == AgentEventType.RESULT:
        print("reason:", data.get("reason"))
        print("checkpoint:", data.get("checkpoint_id"))

# 非流式聚合
result = await runtime.run("default_agent", "一句话总结", session_id=sid)
print(result.text, result.tool_calls, result.reason)
```

`run_to_result()`（同在 `loop.py`）展示了官方如何把 delta 拼成最终文本：优先用完整 `assistant.content`，否则拼接 `stream_delta`。

## 验证命令

```bash
cd backend
uv run pytest tests/test_kernel_checkpoint.py tests/test_chat_sse_wire_contract.py tests/test_tool_call_delta_stream.py -v
```

重点观察：事件顺序、`result` 必含 reason、tool 流式参数组装不破坏 `tool_call_id`。

## 常见误区

1. **把所有 `stream_delta` 写入数据库**：transcript SSOT 应以结构化消息为准，delta 只服务 UI。
2. **忽略 `tool_call_delta`**：部分模型边生成边补全工具参数，前端要缓冲到可解析再展示。
3. **认为没收到 `result` 也能安全结束**：异常中断可能无终态；客户端应有超时与 abort 语义。
4. **自定义 event type 却不更新序列化器**：会破坏多入口一致性。

## 业内对照

- OpenAI Agents SDK / Responses 流式事件、Anthropic `content_block_delta`、ComfyUI WebSocket progress——都是「增量可见 + 生命周期事件」。LeAgent 选择保持 `{type, data}` 以兼容既有 SSE 客户端。
- LangGraph 更偏状态快照推送；事件模型不同，但「中途可观察」目标相同。

## 数据流：事件如何穿越门面

```text
query() 产出 SDKMessage
  → run_loop：翻译为 AgentEvent、派发 hooks、可恢复时写 checkpoint
  → AgentRuntime.stream 直接把事件交给调用方
  → Chat：Controller/SSE 适配器保持 {type,data} 线缆
  → Workflow Agent 节点：聚合为 text/success/checkpoint_id 等槽
```

理解这条链之后，排障顺序就清楚了：若 UI 抖动但库里正确，多半是把 delta 当真相；若 SDK 正常但聊天异常，查序列化器；若终态缺 `reason`，先查是否中途 abort 而未发 `RESULT`。相邻篇 [03](03-one-kernel-many-ingresses.md) 解释为何多入口必须共用协议，[08](08-model-and-streaming.md) 解释 provider chunk 如何变成这些事件，[30](30-checkpoint-pause-resume.md) 解释 `RESULT` 里的 `checkpoint_id` 从何而来。

### 常见排障剧本

1. **只看到 STREAM_DELTA 就断线**：客户端超时或服务端异常；应补 abort 语义与重连策略，并以是否落盘结构化消息为准。  
2. **TOOL_CALL_DELTA 很热闹却从未 TOOL_USE**：参数 JSON 组装失败或模型中断；不要执行半截参数。  
3. **RESULT.reason=awaiting_user_input 但前端当失败**：按成功可接受终态处理并展示 Continue。  
4. **自定义事件类型**：必须同步 SSE/WS 序列化与测试契约，否则「单内核」在传输层分裂。

### 路径速查

- 事件枚举与 `from_sdk_message`：`backend/leagent/sdk/events.py`  
- 翻译与 checkpoint 挂钩：`backend/leagent/sdk/kernel/loop.py`  
- 聚合辅助：同文件 `run_to_result`  
- 线缆测试：`tests/test_chat_sse_wire_contract.py`、`tests/test_tool_call_delta_stream.py`

## 总结与延伸阅读

协议的价值不在事件数量，而在跨 Chat / SDK / Workflow 保持同一形状，使前端、追踪与恢复共享一套词汇。

- [05｜状态所有权](05-state-ownership.md)
- [45｜Trace 与 OTel](45-tracing-and-otel.md)
- 源码：[`sdk/events.py`](../../../backend/leagent/sdk/events.py)、[`sdk/kernel/loop.py`](../../../backend/leagent/sdk/kernel/loop.py)
