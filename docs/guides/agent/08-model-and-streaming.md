# 08｜接入模型与流式输出

## 定位、难度与先修

- **定位**：理解 LLM 调用如何进入 Agent 循环，以及流式事件如何形成。
- **难度**：★★☆☆☆
- **先修**：[07 最小 Agent](07-minimal-python-agent.md)、[04 AgentEvent](04-agent-event-stream.md)、[03 单内核](03-one-kernel-many-ingresses.md)

模型提供商会变、传输细节会变，但 Agent 循环需要的契约相对稳定：消息列表、工具 schema、流式增量、用量与终止。本篇说明 LeAgent 如何把「厂商流」折成「产品事件」。

## 学习目标

1. 指出 `LLMService`、provider 插件与 transport 的分层。  
2. 区分 provider `StreamChunk` 与 SDK `AgentEvent`。  
3. 说明工具参数流式增量如何组装成完整 `tool_calls`。  
4. 选择 `model.task`（如 chat / fast）而非到处硬编码模型名（在策略允许时）。  
5. 能解释 reasoning 流与普通 content 流为何要分开适配。

## 核心心智模型：模型是可替换引擎，循环才是产品

Agent 不该把 OpenAI SDK 调用散落在业务里。正确边界：

```text
Agent 循环需要：messages + tools_schema + stream
LLM 层负责：路由 provider、重试、用量、把原始流折成统一 chunk
```

换 DeepSeek / DashScope / Ollama 时，循环与工具契约应保持稳定。前端与评测只依赖 `AgentEvent`，不要直接耦合某一厂商的 SSE 字段名。

## 数据流：从厂商 token 到 UI 与状态机

```text
ModelPolicy（task/provider/model/...）
        │  _materialize_config
        ▼
LLMService → 具体 provider（entry-point 插件）
        │  StreamChunk*
        ▼
query() 组装 assistant / tool_calls
        │  SDKMessage
        ▼
run_loop → AgentEvent
  · STREAM_DELTA / TOOL_CALL_DELTA（展示）
  · TOOL_USE / TOOL_RESULT（状态机）
  · RESULT（终态 + usage + 可选 checkpoint）
```

相邻篇：[04](04-agent-event-stream.md) 定义事件枚举；[09](09-agent-builder.md) 在定义里写 `model(...)`；[45](45-tracing-and-otel.md) 说明请求日志与 span 如何挂用量。

## LeAgent 的真实实现

- 服务：`backend/leagent/llm/service.py`（`LLMService`）  
- Provider：`backend/leagent/llm/providers/` + entry-point 插件  
- 流：provider 产出 `StreamChunk`；`query()` 消费后再经 `run_loop` 变成 `AgentEvent`  
- Agent 侧模型策略：`ModelPolicy`（`task` / `provider` / `model` / `temperature` / `max_output_tokens`）在 `_materialize_config` 落地  
- 用量与请求日志：可挂到 Trace / `llm_request_logs`  

DeepSeek 等 provider 还有专门的 context strategy 测试（如 `test_deepseek_context_strategy.py`），说明「同一循环、不同模型口味」需要策略而不是改内核。Admin → Providers 与 `providers.yaml` 是密钥与端点真相；环境变量多在首次导入时写入，之后以配置存储为准。

路径解释：教学最小循环可以直接打 OpenAI 兼容 `chat.completions`；生产必须走 `LLMService`，以便统一超时、重试、记账、追踪与模型别名（例如 DeepSeek 自动 tier1/tier2）。离线测试常用 scripted LLM，见集成测试夹具，不必每次烧钱。

## 分步：流式消费

```python
from leagent.sdk import AgentRuntime, AgentEventType

runtime = AgentRuntime.from_service_manager(service_manager)

async for event in runtime.stream(
    "default_agent",
    "用三句话解释流式输出对工具调用的影响",
    session_id=sid,
):
    if event.type == AgentEventType.STREAM_DELTA:
        print(event.data.get("content") or "", end="", flush=True)
    elif event.type == AgentEventType.TOOL_CALL_DELTA:
        # 参数可能分片到达；完整校验以 TOOL_USE 为准
        pass
    elif event.type == AgentEventType.TOOL_USE:
        print("\n工具确认:", event.data.get("name"))
    elif event.type == AgentEventType.RESULT:
        print("\n[", event.data.get("reason"), "]")
        print("usage:", event.data.get("usage"))
```

非流式：`runtime.run(...)` 内部仍走同一循环语义，只是调用方拿到聚合后的 `AgentResult`。`run_to_result` 优先完整 `assistant.content`，否则拼接 delta——前端持久化应学同一规则。

## 验证命令

```bash
cd backend
uv run pytest tests/test_tool_call_delta_stream.py tests/test_agent_controller_reasoning_stream.py -v
# 可选 live（需密钥）：
# uv run pytest tests/integration/ -m live -k deepseek -v
```

重点：工具 JSON 分片最终可解析；reasoning 字段不会误写入用户可见 assistant 正文（以实现与适配测试为准）；`RESULT` 必达或客户端有超时 abort。

## 常见误区与排障

1. **前端把未完成的 tool JSON 当最终参数执行**：必须等组装完成。  
2. **为每个 Agent 写死模型名**：优先 `ModelPolicy.task` 与 Admin providers。  
3. **以为流式关闭就没有 tool calls**：非流式仍应走同一循环语义。  
4. **忽略多模态/推理字段**：部分 provider 有 reasoning 流，需看控制器适配测试。  
5. **把 provider 错误直接当 Agent 崩溃**：应映射为可恢复/可重试 reason，并写 usage。  
6. **本地 Ollama 通了就以为云厂商策略相同**：上下文截断与 tool 协议细节可能不同。  

排障：先看 Admin 里 provider 是否可达 → 再看 `LLMService` 日志的请求 id → 再看事件流是否出现 `TOOL_CALL_DELTA` 却从未 `TOOL_USE`（组装失败）→ 最后才怀疑 Agent 循环本身。

## 业内对照

OpenAI Responses/Agents 流、Anthropic messages stream、Ollama generate——传输不同，应用层都应归一。LeAgent 选择两层边界：provider chunk → SDK event。这与「单内核多入口」一致：Chat SSE 与 SDK `stream()` 共用翻译结果。

## 总结与延伸阅读

流式是体验；完整消息与 tool_call_id 才是状态机燃料。选模型用策略，接厂商用插件，对外只暴露稳定事件。

- [09｜AgentBuilder](09-agent-builder.md)
- [45｜追踪](45-tracing-and-otel.md)
- `docs/deepseek-guide_zh.md`、`docs/dashscope-guide_zh.md`
