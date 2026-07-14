# DashScope（Qwen / 通义千问）集成指南

> LeAgent 开发者参考：通过 **OpenAI 兼容** Chat Completions API 接入阿里云
> DashScope（模型工作室 / 百炼）。
>
> 上游官方文档：
> <https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions>

LeAgent 通过 `/compatible-mode/v1/chat/completions` 端点与 DashScope 通信，
因此请求/响应形态与 OpenAI 兼容——所有 DashScope 特有参数通过 `extra_body`
（Python SDK）或以顶层 JSON 字段（HTTP / Node.js）附加。

英文版：[dashscope-guide.md](./dashscope-guide.md)

---

## 1. 按区域划分的端点

DashScope 在四个区域提供 OpenAI 兼容 API。不同区域的 `base_url`
**不可互换**——请选择与 API Key 签发区域一致的端点。

| 区域 | `base_url` |
|------|------------|
| 华北2（北京）— 默认 | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| 新加坡 | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |
| 美国（弗吉尼亚） | `https://dashscope-us.aliyuncs.com/compatible-mode/v1` |
| 德国（法兰克福） | `https://{WorkspaceId}.eu-central-1.maas.aliyuncs.com/compatible-mode/v1` |

`DashScopeProvider` 默认使用北京端点
（`https://dashscope.aliyuncs.com/compatible-mode/v1`）；可通过构造参数
`base_url` 或管理后台「设置 → 模型提供商」页面覆盖。

---

## 2. 模型

LeAgent 的 `PROVIDER_CATALOG`（`leagent/llm/provider_config.py`）在提供商类型
`qwen`（别名 `dashscope`）下预置了以下 Qwen 模型：

| 模型 | LeAgent 档位 | 上下文窗口 | 工具 | 定价（¥ / 百万 tokens，入 / 出） | 说明 |
|------|--------------|------------|------|----------------------------------|------|
| `qwen3-max` | tier1 | 128 000 | 是 | 10.00 / 30.00 | 最强推理，支持思考模式 |
| `qwen3.5-plus` | tier1 | 128 000 | 是 | 2.00 / 8.00 | 性能与成本均衡 |
| `qwen-plus`（默认） | tier2 | 128 000 | 是 | 0.80 / 2.00 | 通用默认模型 |
| `qwen3.5-flash` | tier2 | 128 000 | 是 | 0.30 / 0.60 | 最快 / 最便宜 |
| `qwen-long` | tier1 | 1 000 000 | 是 | 0.50 / 2.00 | 长上下文，支持文件摄入 |

同一端点还暴露其他模型族（未在 LeAgent 预注册，但可在管理后台选用）：

- **视觉** — `qwen-vl-plus`、`qwen-vl-max`、`qwen2.5-vl-*`、`qwen3-vl-*`
- **推理** — `qwq-*`、`qvq-*`
- **多模态（文本 + 音频）** — `qwen-omni`、`qwen3-omni-flash`
- **垂直领域** — `qwen-math`、`qwen-coder`、`qwen-doc-turbo`（PPT）
- **百炼托管的第三方模型** — DeepSeek、Kimi、GLM、MiniMax 等变体

> `qwen-audio` **不支持** OpenAI 兼容协议——如需使用请改用原生 DashScope SDK。

权威模型/定价列表：<https://help.aliyun.com/zh/model-studio/getting-started/models>

---

## 3. 配置

### 环境变量

| 变量 | 默认值 | 用途 |
|------|--------|------|
| `DASHSCOPE_API_KEY` | *（必填）* | 来自百炼控制台的 API Key |
| `LEAGENT_LLM__DASHSCOPE_API_KEY` | — | 同上，显式 Settings 前缀形式 |
| `LEAGENT_LLM__DASHSCOPE_MODEL` | `qwen-max` | 注册表实例化 DashScope 时使用的默认模型 |

`leagent/config/env_bootstrap.py` 会在以下变量未设置时，自动将裸
`DASHSCOPE_API_KEY` 桥接到：

- `LEAGENT_LLM__DASHSCOPE_API_KEY`
- `LEAGENT_LLM__TIER1_API_KEY`
- `LEAGENT_LLM__TIER2_API_KEY`

因此 `.env` 中只需一行即可将 DashScope 作为默认 tier1/tier2 提供商启用。

### 档位映射

当 DashScope 是唯一配置的云端密钥时，注册表
（`leagent/llm/registry.py → create_default_registry()`）会将其同时挂为
`tier1` 与 `tier2` 端点（默认模型为 `qwen-max`）。如需不同拆分，可用
`LLM_TIER1_MODEL` / `LLM_TIER2_MODEL` 覆盖（例如 tier1 用 `qwen3-max`，
tier2 用 `qwen3.5-flash`）。

### 提供商配置（管理后台 / `providers.yaml`）

`providers.yaml` 中的提供商条目可通过管理后台
**设置 → 模型提供商** 页面创建或编辑。`type: qwen` 或
`type: dashscope` 都会实例化 `DashScopeProvider`
（`provider_config.py:_create_llm_provider`）。

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

## 4. 基本用法（OpenAI 兼容）

由于端点与 OpenAI 兼容，所有官方 OpenAI SDK 均可使用。LeAgent 内部采用
Python SDK 模式。

### Python（非流式）

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

### Python（流式，含 usage）

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

> 非流式调用超过 **300 秒** 会被服务端终止，并返回已生成的内容。长输出请始终使用流式。

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

## 5. 思考模式（`enable_thinking`）

Qwen3 与 QwQ 系列混合模型可在最终答案前返回思维链。LeAgent 的
`DashScopeProvider` 会自动注入该参数。

### LeAgent 中的自动注入

```python
# leagent/llm/providers/dashscope.py
_THINKING_CAPABLE_PREFIXES = ("qwen3", "qwq")

def _build_request_body(...):
    if enable_thinking is None and self._is_thinking_model(model):
        enable_thinking = True   # opt-in by default for thinking-capable models
    ...
    body["enable_thinking"] = enable_thinking
```

若模型名以 `qwen3` 或 `qwq` 开头，除非调用方覆盖，否则会发送
`enable_thinking=True`。要显式关闭：

```python
provider.complete(..., enable_thinking=False)
```

### 读取 `reasoning_content`

思考输出有两条表面通道：

| 模式 | LeAgent 表面 |
|------|--------------|
| 非流式 | `LLMResponse.reasoning_content`（从 `choices[0].message.reasoning_content` 提取） |
| 流式 | `StreamChunk.raw_delta["reasoning_content"]` |

原始 OpenAI 兼容 API 形态：

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

### 相关思考参数

| 参数 | 位置 | 用途 |
|------|------|------|
| `enable_thinking` | `extra_body`（Python）/ 顶层（HTTP、Node） | 开关思考模式 |
| `thinking_budget` | `extra_body` | 思考阶段 token 硬上限（Qwen3 / Qwen3-VL） |
| `preserve_thinking` | `extra_body` | 将历史 `reasoning_content` 回放进上下文（`qwen3.7-max`、`qwen3.6-plus`、`kimi-k2.6` 等支持） |
| `reasoning_effort` | `extra_body` | `high` / `max` — 仅对百炼托管的 DeepSeek-V4 有意义 |

> `max_tokens` **不会**限制思考阶段 token。请使用 `thinking_budget`。

---

## 6. DashScope 特有参数

这些参数**不属于** OpenAI 规范。使用 Python SDK 时放入 `extra_body`；
使用 HTTP / Node.js SDK 时放在顶层。

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enable_thinking` | 视模型而定 | 思考模式开关 |
| `thinking_budget` | 模型上限 | 限制思维链 token |
| `preserve_thinking` | `false` | 将先前的 `reasoning_content` 传回上下文 |
| `enable_search` | `false` | 内置联网搜索 |
| `search_options` | — | `{forced_search, search_strategy, enable_search_extension}` |
| `enable_code_interpreter` | `false` | 内置代码解释器 |
| `tool_stream` | `false` | 增量流式返回 `tool_call.arguments`（仅 GLM 系列） |
| `top_k` | 按模型 | 采样候选数（设为 `null` 或 `>100` 可关闭） |
| `repetition_penalty` | 按模型 | 重复惩罚（`1.0` = 无惩罚） |
| `vl_high_resolution_images` | `false` | 将图像像素上限提升至 16 384 tokens（VL 模型） |
| `skill` | — | 技能模块，例如 `[{"type":"ppt", "mode":"general", "template_id":"news_01"}]`（用于 `qwen-doc-turbo`） |

### 示例 — 联网搜索

```python
client.chat.completions.create(
    model="qwen-plus",
    messages=[{"role": "user", "content": "中国队在巴黎奥运会获得了多少枚金牌"}],
    extra_body={"enable_search": True},
)
```

### 示例 — 严格 / 强制联网搜索

```python
extra_body={
    "enable_search": True,
    "search_options": {
        "forced_search": True,
        "search_strategy": "max",
    },
}
```

`search_strategy` 取值：`turbo`（默认）、`max`、`agent`、`agent_max`。
`agent*` 策略仅最新的 `qwen3.x-max` / `qwen3.5-plus/flash` 快照支持。

### 示例 — DashScope 内容安全检测

```python
client.chat.completions.create(
    model="qwen-plus",
    messages=[...],
    extra_headers={
        "X-DashScope-DataInspection": '{"input":"cip","output":"cip"}'
    },
)
```

> Node.js SDK 不支持该方式。

---

## 7. 多模态输入

### 图像输入（Qwen-VL）

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

URL 可以是公开 HTTPS，也可以是 `data:` Base64 URL。

### 图像列表式「视频」输入（Qwen-VL / QVQ / Qwen-Omni）

```python
{"type": "video",
 "video": [
     "https://.../frame1.jpg",
     "https://.../frame2.jpg",
     "https://.../frame3.jpg"
 ],
 "fps": 2}
```

### 视频文件输入（`video_url`）

```python
{"type": "video_url",
 "video_url": {"url": "https://.../clip.mp4"},
 "fps": 2}
```

像素预算参数（`min_pixels`、`max_pixels`、`total_pixels`、
`vl_high_resolution_images`）遵循上游文档；完整按模型默认值见
[处理高分辨率图像](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)。

---

## 8. 工具调用（Function Calling）

工具调用完全兼容 OpenAI——基础用法无需 `extra_body`。

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

| 字段 | 用途 |
|------|------|
| `tool_choice` | `"auto"`（默认）/ `"none"` / `{"type":"function","function":{"name":"..."}}` |
| `parallel_tool_calls` | 默认 `false`；为 `true` 时允许并发工具调用 |
| `tool_stream`（extra_body） | 增量流式返回 `arguments` — 仅 GLM-5/4.6/4.7 |

> 思考模式模型**不支持**通过 `{"type": "function", ...}` 强制选定工具——请使用 `auto`。

标准多轮流程（`assistant.tool_calls` → `tool` 消息 → 下一条 `assistant` 回复）与 OpenAI 相同。

---

## 9. 长文档问答（`qwen-long` + Files API）

DashScope 为 `qwen-long` 的文件抽取工作流暴露了 OpenAI Files API：

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

`qwen-long` 接受特殊的 `fileid://{id}` system 消息格式来引用已上传文档。

---

## 10. PPT 生成（`qwen-doc-turbo`）

PPT 生成通过 `skill` extra-body 字段暴露。使用 `skill` 时 **`stream` 必须为 `true`**。

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

| 字段 | 取值 |
|------|------|
| `type` | `ppt` |
| `mode` | `general`（基于模板的 HTML，默认）/ `creative`（每页一张图） |
| `template_id` | `news_01`、`summary_01`、`internet_01`、`thesis_01`（配合 `mode=general`） |

---

## 11. 响应形态

### 非流式

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

`finish_reason` 取值：`stop`、`length`（触及 `max_tokens`）、`tool_calls`。

### 流式 chunk

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

最后一个 chunk（当 `stream_options.include_usage=true` 时）的 `choices` 为空数组，并带有填充好的 `usage` 对象。

### 有用的 `usage` 子字段

| 字段 | 含义 |
|------|------|
| `prompt_tokens_details.cached_tokens` | 来自 Context Cache 的 token |
| `prompt_tokens_details.image_tokens` / `video_tokens` / `audio_tokens` | 按模态的输入分解 |
| `completion_tokens_details.reasoning_tokens` | 思考阶段 token（Qwen3 / QwQ） |
| `cache_creation.ephemeral_5m_input_tokens` | 写入显式缓存的 token |

LeAgent 将这些字段映射到 `TokenUsage`（见
`OpenAIProvider._parse_response` 以及 `DashScopeProvider._parse_response` /
`_parse_stream_chunk`）。

---

## 12. LeAgent 实现细节

### 提供商类

`leagent/llm/providers/dashscope.py` — `DashScopeProvider(OpenAIProvider)`：

- 默认将 `base_url` 固定为 `https://dashscope.aliyuncs.com/compatible-mode/v1`，
  `default_model` 为 `qwen-plus`。
- 对名称以 `qwen3` 或 `qwq` 开头的模型自动启用 `enable_thinking=True`。
- 从 `_parse_response`（非流式）和 `_parse_stream_chunk`（流式，经由
  `StreamChunk.raw_delta["reasoning_content"]` 暴露）提取 `reasoning_content`。
- `embed()` 默认使用 `text-embedding-v3`，使同一提供商也可提供嵌入。
- 标记 `supports_streaming = supports_tools = supports_embeddings = True`。

### 注册表接线

`leagent/llm/registry.py → create_default_registry()`：

- 当 `settings.llm.dashscope_api_key` 已设置时，以名称 `"dashscope"` 注册
  `DashScopeProvider`。
- 将 DashScope 密钥纳入 `tier1_api_key` 与 `tier2_api_key` 的回退链。

### 提供商配置目录

`leagent/llm/provider_config.py`：

- `PROVIDER_CATALOG["qwen"]` 列出管理后台使用的精选模型清单。
- `_create_llm_provider()` 同时接受 `providers.yaml` 中的 `type: qwen` 与
  `type: dashscope`。

### 环境引导

`leagent/config/env_bootstrap.py → _bridge_dashscope_key()` 确保 `.env` 中的裸
`DASHSCOPE_API_KEY=...` 会填充带 LeAgent 前缀的设置以及 tier1/tier2 API Key 槽位。

---

## 13. 故障排查

| 现象 | 原因 | 修复 |
|------|------|------|
| `401 InvalidApiKey` | Key 区域不匹配，或已过期 | 确认 Key 区域与 `base_url` 一致；在百炼控制台轮换 |
| 非流式调用卡住约 300 秒后返回截断文本 | 服务端超时，非错误 | 改用流式（`stream=True`） |
| `enable_thinking` 参数被拒绝 | 作为 Python SDK 顶层关键字传入 | 包进 `extra_body={"enable_thinking": True}` |
| Qwen3 模型缺少 `reasoning_content` | 思考模式被关闭（模型快照变体） | 显式传入 `extra_body={"enable_thinking": True}` |
| Qwen3 上对 `{"type":"function","function":{...}}` 返回 `400` | 思考模式下不允许强制工具选择 | 使用 `tool_choice="auto"` |
| `skill` 被拒绝 | `stream` 为 `false` | 使用 `skill` 时设置 `stream=True` |
| 联网搜索实际未触发 | 模型判定不需要 | 设置 `extra_body={"enable_search": True, "search_options": {"forced_search": True}}` |
| 早期 chunk 中 `tool_call.arguments` 为空 | 提供商对 GLM 模型增量流式返回参数 | 拼接所有 `delta.tool_calls[i].function.arguments` chunk |
| `cached_tokens` 始终为 `0` | 提示词开头的易变内容（时间戳、ID）使前缀失效 | 稳定 L0–L4 提示词层；缓存前缀需要数秒预热 |
| `qwen-audio` 请求以 4xx 失败 | 不支持 OpenAI 兼容协议 | 使用原生 DashScope SDK |

---

## 14. 运行测试

```bash
# Offline provider tests (no API key needed)
cd backend
uv run python -m pytest tests/test_dashscope_provider.py -v
```

对线上端点做冒烟测试：

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

## 参考资料

- OpenAI 兼容 Chat API（上游官方）：
  <https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions>
- OpenAI 兼容 Responses API：
  <https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-responses>
- 模型列表与定价：
  <https://help.aliyun.com/zh/model-studio/getting-started/models>
- 百炼控制台：<https://bailian.console.aliyun.com/>
- LeAgent 提供商源码：`backend/leagent/llm/providers/dashscope.py`
- LeAgent 模型目录：`backend/leagent/llm/provider_config.py`（`PROVIDER_CATALOG["qwen"]`）
- 姊妹提供商指南：[`deepseek-guide_zh.md`](./deepseek-guide_zh.md)
- 英文版：[`dashscope-guide.md`](./dashscope-guide.md)
