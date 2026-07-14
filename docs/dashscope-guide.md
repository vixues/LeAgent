# DashScope (Qwen / 通义千问) Integration Guide

> LeAgent developer reference for Alibaba Cloud DashScope (Model Studio /
> 百炼) via the **OpenAI-compatible** Chat Completions API.
>
> Canonical API docs (上游参考):
> <https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions>

LeAgent talks to DashScope through the `/compatible-mode/v1/chat/completions`
endpoint, so the request/response shape is OpenAI-compatible — every
DashScope-specific knob is added on top via `extra_body` (Python SDK) or as a
top-level JSON field (HTTP/Node.js).

---

## 1. Endpoints by Region

DashScope serves the OpenAI-compatible API from four regional endpoints. The
`base_url` is **not** interchangeable across regions — pick the one your API
key was issued in.

| Region | `base_url` |
|--------|------------|
| 华北2（北京）— default | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 新加坡 | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |
| 美国（弗吉尼亚） | `https://dashscope-us.aliyuncs.com/compatible-mode/v1` |
| 德国（法兰克福） | `https://{WorkspaceId}.eu-central-1.maas.aliyuncs.com/compatible-mode/v1` |

`DashScopeProvider` defaults to Beijing
(`https://dashscope.aliyuncs.com/compatible-mode/v1`); override via the
`base_url` constructor arg or the admin Settings → Model Providers page.

---

## 2. Models

LeAgent's `PROVIDER_CATALOG` (`leagent/llm/provider_config.py`) advertises
the following Qwen models under provider type `qwen` (alias `dashscope`):

| Model | LeAgent tier | Context window | Tools | Pricing (¥ / 1M tokens, in / out) | Notes |
|-------|--------------|----------------|-------|-----------------------------------|-------|
| `qwen3-max` | tier1 | 128 000 | Yes | 10.00 / 30.00 | Strongest reasoning, supports thinking mode |
| `qwen3.5-plus` | tier1 | 128 000 | Yes | 2.00 / 8.00 | Balanced performance/cost |
| `qwen-plus` (default) | tier2 | 128 000 | Yes | 0.80 / 2.00 | General-purpose default |
| `qwen3.5-flash` | tier2 | 128 000 | Yes | 0.30 / 0.60 | Fastest / cheapest |
| `qwen-long` | tier1 | 1 000 000 | Yes | 0.50 / 2.00 | Long-context, supports file ingestion |

Additional model families exposed by the same endpoint (not pre-registered in
LeAgent but selectable via the admin UI):

- **Vision** — `qwen-vl-plus`, `qwen-vl-max`, `qwen2.5-vl-*`, `qwen3-vl-*`
- **Reasoning** — `qwq-*`, `qvq-*`
- **Multimodal (text + audio)** — `qwen-omni`, `qwen3-omni-flash`
- **Domain** — `qwen-math`, `qwen-coder`, `qwen-doc-turbo` (PPT)
- **Third-party hosted on 百炼** — DeepSeek, Kimi, GLM, MiniMax variants

> `qwen-audio` does **not** support the OpenAI-compatible protocol — use the
> native DashScope SDK if you need it.

Authoritative model/pricing list: <https://help.aliyun.com/zh/model-studio/getting-started/models>

---

## 3. Configuration

### Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `DASHSCOPE_API_KEY` | *(required)* | API key from 百炼控制台 |
| `LEAGENT_LLM__DASHSCOPE_API_KEY` | — | Same as above, explicit Settings-prefixed form |
| `LEAGENT_LLM__DASHSCOPE_MODEL` | `qwen-max` | Default model used when the registry instantiates DashScope |

`leagent/config/env_bootstrap.py` automatically bridges a bare
`DASHSCOPE_API_KEY` to:

- `LEAGENT_LLM__DASHSCOPE_API_KEY`
- `LEAGENT_LLM__TIER1_API_KEY`
- `LEAGENT_LLM__TIER2_API_KEY`

…when those are unset, so a single `.env` line is enough to bring DashScope
up as the default tier1/tier2 provider.

### Tier mapping

When DashScope is the only configured cloud key, the registry
(`leagent/llm/registry.py → create_default_registry()`) wires it as both
`tier1` and `tier2` endpoints (defaulting to `qwen-max`). Override with
`LLM_TIER1_MODEL` / `LLM_TIER2_MODEL` if you want a different split (e.g.
`qwen3-max` for tier1 and `qwen3.5-flash` for tier2).

### Provider config (Admin UI / `providers.yaml`)

The provider entry in `providers.yaml` is created/edited from the admin
**Settings → Model Providers** page. Either `type: qwen` or
`type: dashscope` instantiates `DashScopeProvider`
(`provider_config.py:_create_llm_provider`).

```yaml
providers:
  - name: qwen
    type: qwen
    enabled: true
    api_key: sk-xxx
    base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
    models:
      - name: qwen-plus
        tier: tier2
      - name: qwen3-max
        tier: tier1
```

---

## 4. Basic Usage (OpenAI-compatible)

Because the endpoint is OpenAI-compatible, every official OpenAI SDK works.
LeAgent uses the Python SDK pattern internally.

### Python (non-stream)

```python
import os
from openai import OpenAI

client = OpenAI(
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

completion = client.chat.completions.create(
    model="qwen-plus",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "你是谁？"},
    ],
)
print(completion.choices[0].message.content)
```

### Python (streaming with usage)

```python
completion = client.chat.completions.create(
    model="qwen-plus",
    messages=[{"role": "user", "content": "你是谁？"}],
    stream=True,
    stream_options={"include_usage": True},
)
for chunk in completion:
    delta = chunk.choices[0].delta if chunk.choices else None
    if delta and delta.content:
        print(delta.content, end="", flush=True)
    if chunk.usage:
        print("\n", chunk.usage)
```

> Non-streaming calls that exceed **300 s** are terminated by the server,
> which returns whatever has been generated so far. Always use streaming for
> long outputs.

### curl

```bash
curl -X POST https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions \
  -H "Authorization: Bearer $DASHSCOPE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen-plus",
    "messages": [{"role": "user", "content": "你是谁？"}]
  }'
```

---

## 5. Thinking Mode (`enable_thinking`)

Qwen3 and QwQ-family hybrid models can return a chain-of-thought before
the final answer. LeAgent's `DashScopeProvider` injects this automatically.

### Auto-injection in LeAgent

```python
# leagent/llm/providers/dashscope.py
_THINKING_CAPABLE_PREFIXES = ("qwen3", "qwq")

def _build_request_body(...):
    if enable_thinking is None and self._is_thinking_model(model):
        enable_thinking = True   # opt-in by default for thinking-capable models
    ...
    body["enable_thinking"] = enable_thinking
```

If the model name starts with `qwen3` or `qwq`, `enable_thinking=True` is
sent unless the caller overrides it. To disable explicitly:

```python
provider.complete(..., enable_thinking=False)
```

### Reading `reasoning_content`

Thinking output is surfaced both ways:

| Mode | LeAgent surface |
|------|-----------------|
| Non-streaming | `LLMResponse.reasoning_content` (extracted from `choices[0].message.reasoning_content`) |
| Streaming | `StreamChunk.raw_delta["reasoning_content"]` |

Raw OpenAI-compatible API shape:

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "reasoning_content": "Let me think... the user is asking ...",
      "content": "Final answer."
    },
    "finish_reason": "stop"
  }]
}
```

### Related thinking knobs

| Parameter | Where | Purpose |
|-----------|-------|---------|
| `enable_thinking` | `extra_body` (Python) / top-level (HTTP, Node) | Toggle thinking mode |
| `thinking_budget` | `extra_body` | Hard cap on thinking-stage tokens (Qwen3 / Qwen3-VL) |
| `preserve_thinking` | `extra_body` | Replay historical `reasoning_content` back into context (supported by `qwen3.7-max`, `qwen3.6-plus`, `kimi-k2.6` …) |
| `reasoning_effort` | `extra_body` | `high` / `max` — only meaningful for DeepSeek-V4 hosted on 百炼 |

> `max_tokens` does **not** cap thinking-stage tokens. Use `thinking_budget`.

---

## 6. DashScope-specific Parameters

These are **not** part of the OpenAI spec. With the Python SDK pass them in
`extra_body`; with HTTP / Node.js SDKs put them at the top level.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `enable_thinking` | model-dependent | Thinking mode toggle |
| `thinking_budget` | model max | Cap chain-of-thought tokens |
| `preserve_thinking` | `false` | Pass previous `reasoning_content` back into context |
| `enable_search` | `false` | Built-in web search |
| `search_options` | — | `{forced_search, search_strategy, enable_search_extension}` |
| `enable_code_interpreter` | `false` | Built-in code interpreter |
| `tool_stream` | `false` | Stream `tool_call.arguments` incrementally (GLM-series only) |
| `top_k` | per model | Sampling candidate count (set `null` or `>100` to disable) |
| `repetition_penalty` | per model | Repetition penalty (`1.0` = none) |
| `vl_high_resolution_images` | `false` | Lift image pixel cap to 16 384 tokens (VL models) |
| `skill` | — | Skill modules, e.g. `[{"type":"ppt", "mode":"general", "template_id":"news_01"}]` for `qwen-doc-turbo` |

### Example — web search

```python
client.chat.completions.create(
    model="qwen-plus",
    messages=[{"role": "user", "content": "中国队在巴黎奥运会获得了多少枚金牌"}],
    extra_body={"enable_search": True},
)
```

### Example — strict / forced web search

```python
extra_body={
    "enable_search": True,
    "search_options": {
        "forced_search": True,
        "search_strategy": "max",
    },
}
```

`search_strategy` values: `turbo` (default), `max`, `agent`, `agent_max`.
The `agent*` strategies are only supported by the latest `qwen3.x-max` /
`qwen3.5-plus/flash` snapshots.

### Example — DashScope safety inspection

```python
client.chat.completions.create(
    model="qwen-plus",
    messages=[...],
    extra_headers={
        "X-DashScope-DataInspection": '{"input":"cip","output":"cip"}'
    },
)
```

> Not supported via the Node.js SDK.

---

## 7. Multimodal Inputs

### Image input (Qwen-VL)

```python
client.chat.completions.create(
    model="qwen-vl-plus",
    messages=[{
        "role": "user",
        "content": [
            {"type": "image_url",
             "image_url": {"url": "https://example.com/cat.jpg"}},
            {"type": "text", "text": "这是什么？"},
        ],
    }],
)
```

URLs may be either public HTTPS or `data:` Base64 URLs.

### Image-list "video" input (Qwen-VL / QVQ / Qwen-Omni)

```python
{"type": "video",
 "video": [
     "https://.../frame1.jpg",
     "https://.../frame2.jpg",
     "https://.../frame3.jpg"
 ],
 "fps": 2}
```

### Video-file input (`video_url`)

```python
{"type": "video_url",
 "video_url": {"url": "https://.../clip.mp4"},
 "fps": 2}
```

Pixel-budget knobs (`min_pixels`, `max_pixels`, `total_pixels`,
`vl_high_resolution_images`) follow the upstream docs; see
[处理高分辨率图像](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)
for the full per-model defaults.

---

## 8. Tool Calling (Function Calling)

Tool calling is fully OpenAI-compatible — no `extra_body` needed for the
basics.

```python
tools = [{
    "type": "function",
    "function": {
        "name": "get_current_weather",
        "description": "当你想查询指定城市的天气时非常有用。",
        "parameters": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "城市或县区"}
            },
            "required": ["location"],
        },
    },
}]

resp = client.chat.completions.create(
    model="qwen-plus",
    messages=[{"role": "user", "content": "杭州天气怎么样"}],
    tools=tools,
)
print(resp.choices[0].message.tool_calls)
```

| Field | Purpose |
|-------|---------|
| `tool_choice` | `"auto"` (default) / `"none"` / `{"type":"function","function":{"name":"..."}}` |
| `parallel_tool_calls` | `false` by default; allow concurrent tool calls when `true` |
| `tool_stream` (extra_body) | Stream `arguments` incrementally — GLM-5/4.6/4.7 only |

> Thinking-mode models do **not** support forced tool choice via
> `{"type": "function", ...}` — use `auto`.

The standard multi-turn flow (`assistant.tool_calls` → `tool` messages →
next `assistant` reply) is identical to OpenAI.

---

## 9. Long-document Q&A (`qwen-long` + Files API)

DashScope exposes the OpenAI Files API for `qwen-long`'s file-extract
workflow:

```python
file_object = client.files.create(
    file=Path("百炼系列手机产品介绍.docx"),
    purpose="file-extract",
)
completion = client.chat.completions.create(
    model="qwen-long",
    messages=[
        {"role": "system", "content": f"fileid://{file_object.id}"},
        {"role": "user", "content": "这篇文章讲了什么？"},
    ],
)
```

`qwen-long` accepts the special `fileid://{id}` system-message format to
reference uploaded documents.

---

## 10. PPT Generation (`qwen-doc-turbo`)

PPT generation is exposed via the `skill` extra-body field. **`stream` must
be `true`** when using `skill`.

```python
client.chat.completions.create(
    model="qwen-doc-turbo",
    messages=[
        {"role": "system", "content": "you are a helpful assistant."},
        {"role": "system", "content": "您的文档内容"},
        {"role": "user", "content": "生成一个10到20页的ppt"},
    ],
    extra_body={"skill": [
        {"type": "ppt", "mode": "general", "template_id": "news_01"}
    ]},
    stream=True,
    stream_options={"include_usage": True},
)
```

| Field | Values |
|-------|--------|
| `type` | `ppt` |
| `mode` | `general` (template-based HTML, default) / `creative` (image-per-page) |
| `template_id` | `news_01`, `summary_01`, `internet_01`, `thesis_01` (used with `mode=general`) |

---

## 11. Response Shapes

### Non-streaming

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion",
  "created": 1735120033,
  "model": "qwen-plus",
  "choices": [{
    "index": 0,
    "finish_reason": "stop",
    "message": {
      "role": "assistant",
      "content": "我是阿里云开发的一款超大规模语言模型，我叫千问。",
      "reasoning_content": null
    },
    "logprobs": null
  }],
  "usage": {
    "prompt_tokens": 3019,
    "completion_tokens": 104,
    "total_tokens": 3123,
    "prompt_tokens_details": {"cached_tokens": 2048}
  }
}
```

`finish_reason` values: `stop`, `length` (hit `max_tokens`), `tool_calls`.

### Streaming chunk

```json
{
  "id": "chatcmpl-...",
  "object": "chat.completion.chunk",
  "choices": [{
    "index": 0,
    "delta": {"role": "assistant", "content": "我是"},
    "finish_reason": null
  }],
  "usage": null
}
```

The final chunk (when `stream_options.include_usage=true`) carries an empty
`choices` array and a populated `usage` object.

### Useful `usage` sub-fields

| Field | Meaning |
|-------|---------|
| `prompt_tokens_details.cached_tokens` | Tokens served from Context Cache |
| `prompt_tokens_details.image_tokens` / `video_tokens` / `audio_tokens` | Per-modality input breakdown |
| `completion_tokens_details.reasoning_tokens` | Thinking-stage tokens (Qwen3 / QwQ) |
| `cache_creation.ephemeral_5m_input_tokens` | Tokens written into explicit cache |

LeAgent maps these into `TokenUsage` (see
`OpenAIProvider._parse_response` + `DashScopeProvider._parse_response` /
`_parse_stream_chunk`).

---

## 12. LeAgent Implementation Details

### Provider class

`leagent/llm/providers/dashscope.py` — `DashScopeProvider(OpenAIProvider)`:

- Pins `base_url` to `https://dashscope.aliyuncs.com/compatible-mode/v1`
  by default, `default_model` to `qwen-plus`.
- Auto-enables `enable_thinking=True` for any model whose name starts with
  `qwen3` or `qwq`.
- Extracts `reasoning_content` from both `_parse_response`
  (non-streaming) and `_parse_stream_chunk` (streaming, surfaced via
  `StreamChunk.raw_delta["reasoning_content"]`).
- Defaults `embed()` to `text-embedding-v3` so the same provider can serve
  embeddings.
- Marks `supports_streaming = supports_tools = supports_embeddings = True`.

### Registry wiring

`leagent/llm/registry.py → create_default_registry()`:

- Registers `DashScopeProvider` under the name `"dashscope"` whenever
  `settings.llm.dashscope_api_key` is set.
- Includes the DashScope key in the fallback chain for `tier1_api_key`
  and `tier2_api_key` resolution.

### Provider config catalog

`leagent/llm/provider_config.py`:

- `PROVIDER_CATALOG["qwen"]` lists the curated model inventory used by the
  admin UI.
- `_create_llm_provider()` accepts both `type: qwen` and `type: dashscope`
  in `providers.yaml`.

### Environment bootstrap

`leagent/config/env_bootstrap.py → _bridge_dashscope_key()` ensures a bare
`DASHSCOPE_API_KEY=...` in `.env` populates the LeAgent-prefixed settings
and the tier1/tier2 API key slots.

---

## 13. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `401 InvalidApiKey` | Wrong region for the key, or expired | Confirm the key region matches `base_url`; rotate from 百炼控制台 |
| Non-stream call hangs ~300 s then returns truncated text | Server-side timeout, not an error | Switch to streaming (`stream=True`) |
| `enable_thinking` parameter rejected | Used as top-level kwarg via Python SDK | Wrap inside `extra_body={"enable_thinking": True}` |
| Missing `reasoning_content` on Qwen3 model | Thinking mode disabled (model snapshot variant) | Pass `extra_body={"enable_thinking": True}` explicitly |
| `400` for `{"type":"function","function":{...}}` on Qwen3 | Forced tool choice not allowed in thinking mode | Use `tool_choice="auto"` |
| `skill` rejected | `stream` was `false` | Set `stream=True` when using `skill` |
| Web search not actually triggered | Model decided it wasn't needed | Set `extra_body={"enable_search": True, "search_options": {"forced_search": True}}` |
| Empty `tool_call.arguments` in early chunks | Provider streams arguments incrementally for GLM models | Concatenate all `delta.tool_calls[i].function.arguments` chunks |
| `cached_tokens` always `0` | Volatile content (timestamps, IDs) at the start of the prompt invalidates the prefix | Stabilize L0–L4 prompt layers; cache prefix takes seconds to warm up |
| `qwen-audio` requests fail with 4xx | OpenAI-compatible protocol unsupported | Use native DashScope SDK |

---

## 14. Running Tests

```bash
# Offline provider tests (no API key needed)
cd backend
uv run python -m pytest tests/test_dashscope_provider.py -v
```

To smoke-test against the live endpoint:

```bash
DASHSCOPE_API_KEY=sk-... \
  uv run python -c "
import asyncio
from leagent.llm.providers.dashscope import DashScopeProvider
from leagent.llm.base import ChatMessage

async def main():
    p = DashScopeProvider(api_key='${DASHSCOPE_API_KEY}')
    r = await p.complete(
        [ChatMessage(role='user', content='你是谁？')],
        model='qwen-plus',
    )
    print(r.content)

asyncio.run(main())
"
```

---

## References

- OpenAI-compatible Chat API (上游官方):
  <https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions>
- OpenAI-compatible Responses API:
  <https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-responses>
- Model list & pricing:
  <https://help.aliyun.com/zh/model-studio/getting-started/models>
- 百炼控制台: <https://bailian.console.aliyun.com/>
- LeAgent provider source: `backend/leagent/llm/providers/dashscope.py`
- LeAgent model catalog: `backend/leagent/llm/provider_config.py` (`PROVIDER_CATALOG["qwen"]`)
- Sibling provider guide: [`deepseek-guide.md`](./deepseek-guide.md)
- 中文版: [`dashscope-guide_zh.md`](./dashscope-guide_zh.md)
