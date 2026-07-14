# DeepSeek 集成指南

> LeAgent 开发者参考：DeepSeek V4 API。
> 官方 API 文档：<https://api-docs.deepseek.com>

英文版：[deepseek-guide.md](./deepseek-guide.md)

---

## 1. 模型

| 模型 | 档位 | 上下文窗口 | 工具调用 | FIM | 定价（每百万 tokens） |
|------|------|------------|----------|-----|------------------------|
| `deepseek-v4-flash` | tier2（快速/廉价） | 1 000 000 | 是 | 否 | $0.14 入 / $0.28 出 |
| `deepseek-v4-pro` | tier1（推理） | 1 000 000 | 是 | 是 | $1.74 入 / $3.48 出 |

### 旧版模型迁移

旧模型名 `deepseek-chat` 与 `deepseek-reasoner` 会在启动时分别自动迁移为
`deepseek-v4-flash` 与 `deepseek-v4-pro`（经由 `providers.yaml` 自动迁移）。
带有 `/v1` 后缀的旧 base URL 配置也会自动规范化。

---

## 2. 配置

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `DEEPSEEK_API_KEY` | *（必填）* | 来自 platform.deepseek.com 的 API Key |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | DeepSeek 提供商的默认模型 |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API 基址（无 `/v1` 后缀） |
| `DEEPSEEK_THINKING_TYPE` | `enabled` | `enabled` 或 `disabled` — 思考模式开关 |
| `DEEPSEEK_REASONING_EFFORT` | `high` | `high` 或 `max` — 控制推理深度 |

所有变量也接受 `LLM_DEEPSEEK_*` 前缀（通过 `LLMSettings` 中的
`AliasChoices` 解析）。

### 档位映射

当设置了 `DEEPSEEK_API_KEY` 且未显式配置 `LLM_TIER1_ENDPOINT` /
`LLM_TIER2_ENDPOINT` 时，注册表会自动将 DeepSeek 别名为：

- **tier1** → `deepseek-v4-pro`（偏重推理的工作负载）
- **tier2** → `deepseek-v4-flash`（快速、廉价）

如需覆盖，使用 `LLM_TIER1_MODEL` / `LLM_TIER2_MODEL`。

### 提供商配置（管理后台 / providers.yaml）

`leagent/llm/provider_config.py` 中的 `PROVIDER_CATALOG` 列出了 DeepSeek
及其模型清单与定价。管理员也可通过「设置 → 模型提供商」页面配置 DeepSeek。

---

## 3. 思考模式

DeepSeek V4 模型支持**思考模式**：模型先输出思维链（`reasoning_content`），
再给出最终答案（`content`）。

### 开关与努力程度

| 参数 | 取值 | 默认值 |
|------|------|--------|
| `thinking.type` | `enabled`、`disabled` | `enabled` |
| `reasoning_effort` | `high`、`max` | `high`（复杂 Agent 请求会自动升为 `max`） |

兼容映射：`low`/`medium` → `high`，`xhigh` → `max`。

### 思考模式下的参数限制

启用思考时，以下参数会被 API **静默忽略**，并由 `DeepSeekProvider` 从请求中剥离：

- `temperature`
- `top_p`
- `presence_penalty` *（亦已全局弃用）*
- `frequency_penalty` *（亦已全局弃用）*

### `reasoning_content` 回传规则

`reasoning_content` 字段会与 `content` 一同出现在 assistant 响应中。其处理方式取决于中间是否发生了工具调用：

1. **用户消息之间无工具调用**：API 会忽略先前 assistant 轮次的
   `reasoning_content`。可以省略。

2. **用户消息之间有工具调用**：后续所有请求中**必须**回传
   `reasoning_content`。省略会导致 **400 错误**。
   `ChatMessage.reasoning_content` 字段与 `AssistantMessage.to_openai()`
   会自动处理此事。

### 通过 OpenAI SDK 使用

```python
response = client.chat.completions.create(
    model="deepseek-v4-pro",
    messages=messages,
    reasoning_effort="high",
    extra_body={"thinking": {"type": "enabled"}},
)
reasoning = response.choices[0].message.reasoning_content
content = response.choices[0].message.content
```

---

## 4. 工具调用

DeepSeek V4 支持 OpenAI 兼容的 function calling。在思考模式下，模型可在产出最终答案前进行多轮推理 + 工具调用。

### 多轮工具调用流程

```
User message
  → Model thinks (reasoning_content) + emits tool_calls
    → Tool results returned
      → Model thinks again + may emit more tool_calls
        → ... (loop until model produces final content)
```

### 关键：工具调用轮次的上下文组装

在工具调用之后组装后续请求的消息历史时，**必须**在 assistant 消息上包含
`reasoning_content`：

```python
messages.append({
    "role": "assistant",
    "content": response.choices[0].message.content,
    "reasoning_content": response.choices[0].message.reasoning_content,
    "tool_calls": response.choices[0].message.tool_calls,
})
```

LeAgent 通过 `ChatMessage.reasoning_content` 与
`AssistantMessage.to_openai()` 处理此事（按条件包含该字段）。

---

## 5. 上下文磁盘缓存

DeepSeek 会自动将请求前缀缓存到磁盘。对所有用户默认开启，无需改代码。

### 工作原理

- 每次请求会在输入与输出边界触发缓存构建。
- 后续请求若与某个已缓存前缀单元**精确匹配**，该部分会命中缓存。
- 系统也会检测多个请求之间的公共前缀并独立缓存。
- 缓存条目在数小时到数天无活动后过期。

### 优化缓存命中率

在 LeAgent 中最大化缓存：

1. 保持系统提示词（L0–L4 层）**稳定且确定**——不要在稳定层嵌入时间戳、随机值或易变状态。
2. 自然使用多轮对话——每一轮都会延长前缀。
3. 对长文档问答，跨问题保持文档位置不变，以便检测并缓存公共前缀。

### 用量指标

API 在 `usage` 对象中返回缓存指标：

| 字段 | 说明 |
|------|------|
| `prompt_cache_hit_tokens` | 来自缓存的输入 token |
| `prompt_cache_miss_tokens` | 新计算的输入 token |

这些指标会写入 `TokenUsage`，并通过结构化日志与 SSE token-usage 事件暴露。

---

## 6. FIM API（Beta）

用于代码补全的 Fill-In-the-Middle。仅 `deepseek-v4-pro` 支持该端点。

**端点：** `POST https://api.deepseek.com/beta/completions`

```python
from openai import OpenAI

client = OpenAI(
    api_key="<key>",
    base_url="https://api.deepseek.com/beta",
)
response = client.completions.create(
    model="deepseek-v4-pro",
    prompt="def fib(a):",
    suffix="    return fib(a-1) + fib(a-2)",
    max_tokens=128,
)
print(response.choices[0].text)
```

在 LeAgent 中，可通过 `DeepSeekProvider.fim_complete()` 以编程方式访问。

---

## 7. 余额查询

**端点：** `GET https://api.deepseek.com/user/balance`

返回账户可用性与余额明细。由 `deepseek_utils.check_balance()` 用于管理端健康检查。

```json
{
  "is_available": true,
  "balance_infos": [
    {
      "currency": "CNY",
      "total_balance": "10.00",
      "granted_balance": "0.00",
      "topped_up_balance": "10.00"
    }
  ]
}
```

---

## 8. 用于 KV 缓存隔离的 `user_id`

请求参数 `user_id`（字符集 `[a-zA-Z0-9\-_]`, 最长 512 字符）
可让 DeepSeek 按用户分区 KV 缓存。当 API 层设置了 `_deepseek_user_id`
上下文变量时，LeAgent 会通过 `DeepSeekProvider._build_request_body`
注入经过净化的 `workspace_id:user_id`。

`user_id` 中**不要**包含个人身份信息（PII）。

---

## 9. 已弃用参数

| 参数 | 状态 |
|------|------|
| `frequency_penalty` | 已弃用 — 静默忽略，由提供商剥离 |
| `presence_penalty` | 已弃用 — 静默忽略，由提供商剥离 |

---

## 10. LeAgent 实现细节

### 提供商类

`leagent/llm/providers/deepseek.py` — `DeepSeekProvider(OpenAIProvider)`：

- 合并来自 settings 与按请求 contextvar 覆盖的 `thinking` / `reasoning_effort`。
- 从请求中剥离已弃用及与思考模式不兼容的参数。
- 覆盖 `_parse_stream_chunk` 以处理 `reasoning_content` 与 V4 usage 字段。
- 覆盖 `_parse_response` 以处理非流式 `reasoning_content`。
- 注入 `user_id` 以实现 KV 缓存隔离。
- 提供 `fim_complete()` 用于 FIM 代码补全。

### 上下文策略

`leagent/context/strategies/deepseek.py` — `DeepSeekContextStrategy`：

- 针对 DeepSeek 的注意力模式优化上下文排序（稳定前缀以利于自动磁盘缓存，高优先级内容放在边界）。
- 默认预算按 V4 的 100 万 token 上下文窗口调优。

### 注册表接线

`leagent/llm/registry.py` — `create_default_registry()`：

- API Key 已设置时，以 `"deepseek"` 注册 `DeepSeekProvider`。
- 未显式配置档位端点时，自动别名为 `tier1`（`deepseek-v4-pro`）与
  `tier2`（`deepseek-v4-flash`）。
- 通过 `_endpoint_hostname_is_deepseek()` 检测档位端点中的 DeepSeek 主机名。

---

## 11. 故障排查

| 现象 | 原因 | 修复 |
|------|------|------|
| 400 错误提到 `reasoning_content` | 工具调用轮次缺少 `reasoning_content` 回传 | 确保带工具调用的 assistant 消息保留 `ChatMessage.reasoning_content` |
| `temperature` / `top_p` 无效 | 思考模式已启用（默认） | 预期行为 — 这些参数在思考模式下被忽略 |
| 空 `content` 但有 `tool_calls` | 模型选择调用工具而非直接作答 | 正常流程 — 执行工具并继续循环 |
| 流式 delta 中 `content: null` | DeepSeek 在 tool-call delta 前的特性 | 由 `_parse_stream_chunk` 合并为空字符串 |
| `finish_reason: insufficient_system_resource` | DeepSeek 服务端过载 | 指数退避重试（由 `max_retries` 处理） |
| `prompt_cache_hit_tokens` 始终为 0 | 系统提示词在请求间变化 | 稳定 L0–L4 提示词层；缓存需要数秒构建 |
| 来自 `/opt/ros/*` 的导入错误 | `PYTHONPATH` 包含 ROS 路径 | 运行 LeAgent 前设置 `PYTHONPATH=""` |

---

## 12. 运行测试

```bash
# Offline provider tests (no API key needed)
cd backend
uv run python -m pytest tests/test_deepseek_provider.py tests/test_deepseek_context_strategy.py -v

# Live integration test (requires DEEPSEEK_API_KEY)
PYTHONPATH="" DEEPSEEK_API_KEY=sk-... \
  uv run python -m pytest tests/integration/test_deepseek_excel.py -v -m integration
```

---

## 参考资料

- DeepSeek API 文档：<https://api-docs.deepseek.com>
- DeepSeek V4 公告：<https://api-docs.deepseek.com/news/news260424>
- 定价：<https://api-docs.deepseek.com/quick_start/pricing>
- LeAgent AGENTS.md：DeepSeek 提供商章节
- LeAgent 上下文压缩指南：`docs/context-compression-and-usage.md`
- 姊妹提供商指南：[`dashscope-guide_zh.md`](./dashscope-guide_zh.md)
- 英文版：[`deepseek-guide.md`](./deepseek-guide.md)
