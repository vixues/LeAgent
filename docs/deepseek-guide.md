# DeepSeek Integration Guide

> LeAgent developer reference for the DeepSeek V4 API.
> Canonical API docs: <https://api-docs.deepseek.com>

---

## 1. Models

| Model | Tier | Context window | Tool calling | FIM | Pricing (per 1M tokens) |
|-------|------|----------------|-------------|-----|------------------------|
| `deepseek-v4-flash` | tier2 (fast/cheap) | 1 000 000 | Yes | No | $0.14 in / $0.28 out |
| `deepseek-v4-pro` | tier1 (reasoning) | 1 000 000 | Yes | Yes | $1.74 in / $3.48 out |

### Legacy model migration

Legacy model names `deepseek-chat` and `deepseek-reasoner` are automatically
migrated to `deepseek-v4-flash` and `deepseek-v4-pro` respectively on startup
(via `providers.yaml` auto-migration).  Old configs with a `/v1` base URL suffix
are also normalized automatically.

---

## 2. Configuration

### Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DEEPSEEK_API_KEY` | *(required)* | API key from platform.deepseek.com |
| `DEEPSEEK_MODEL` | `deepseek-v4-flash` | Default model for the DeepSeek provider |
| `DEEPSEEK_BASE_URL` | `https://api.deepseek.com` | API base URL (no `/v1` suffix) |
| `DEEPSEEK_THINKING_TYPE` | `enabled` | `enabled` or `disabled` — thinking mode toggle |
| `DEEPSEEK_REASONING_EFFORT` | `high` | `high` or `max` — controls reasoning depth |

All variables accept the `LLM_DEEPSEEK_*` prefix as well (resolved via
`AliasChoices` in `LLMSettings`).

### Tier mapping

When `DEEPSEEK_API_KEY` is set and no explicit `LLM_TIER1_ENDPOINT` /
`LLM_TIER2_ENDPOINT` is configured, the registry auto-aliases DeepSeek as:

- **tier1** → `deepseek-v4-pro` (reasoning-heavy workloads)
- **tier2** → `deepseek-v4-flash` (fast, cheap)

Override with `LLM_TIER1_MODEL` / `LLM_TIER2_MODEL` if needed.

### Provider config (Admin UI / providers.yaml)

The `PROVIDER_CATALOG` in `leagent/llm/provider_config.py` lists DeepSeek
with its model inventory and pricing. The admin can also configure DeepSeek
via the Settings > Model Providers page.

---

## 3. Thinking Mode

DeepSeek V4 models support a **thinking mode** where the model outputs a
chain-of-thought (`reasoning_content`) before the final answer (`content`).

### Toggle and effort

| Parameter | Values | Default |
|-----------|--------|---------|
| `thinking.type` | `enabled`, `disabled` | `enabled` |
| `reasoning_effort` | `high`, `max` | `high` (auto `max` for complex agent requests) |

Compatibility mapping: `low`/`medium` → `high`, `xhigh` → `max`.

### Parameter restrictions in thinking mode

When thinking is enabled, the following parameters are **silently ignored**
by the API and are stripped from the request by `DeepSeekProvider`:

- `temperature`
- `top_p`
- `presence_penalty` *(also globally deprecated)*
- `frequency_penalty` *(also globally deprecated)*

### `reasoning_content` passback rules

The `reasoning_content` field appears in assistant responses alongside
`content`. Its handling differs based on whether tool calls occurred:

1. **No tool calls between user messages**: `reasoning_content` from
   previous assistant turns is ignored by the API. You may omit it.

2. **Tool calls between user messages**: `reasoning_content` **must** be
   passed back in all subsequent requests. Omitting it causes a **400
   error**. The `ChatMessage.reasoning_content` field and
   `AssistantMessage.to_openai()` handle this automatically.

### Using via OpenAI SDK

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

## 4. Tool Calling

DeepSeek V4 supports OpenAI-compatible function calling. In thinking mode,
the model can perform multiple rounds of reasoning + tool calls before
producing a final answer.

### Multi-turn tool-call flow

```
User message
  → Model thinks (reasoning_content) + emits tool_calls
    → Tool results returned
      → Model thinks again + may emit more tool_calls
        → ... (loop until model produces final content)
```

### Critical: context assembly for tool-call turns

When assembling the message history for a follow-up request after tool
calls, you **must** include `reasoning_content` on the assistant message:

```python
messages.append({
    "role": "assistant",
    "content": response.choices[0].message.content,
    "reasoning_content": response.choices[0].message.reasoning_content,
    "tool_calls": response.choices[0].message.tool_calls,
})
```

LeAgent handles this via `ChatMessage.reasoning_content` and
`AssistantMessage.to_openai()`, which conditionally includes the field.

---

## 5. Context Disk Caching

DeepSeek automatically caches request prefixes on disk. This is enabled
for all users with no code changes required.

### How it works

- Each request triggers cache construction at the input and output
  boundaries.
- Subsequent requests that **exactly match** a cached prefix unit get a
  cache hit for that portion.
- The system also detects common prefixes across multiple requests and
  caches them independently.
- Cache entries expire after a few hours to a few days of inactivity.

### Optimizing for cache hits

To maximize caching in LeAgent:

1. Keep the system prompt (layers L0–L4) **stable and deterministic** — do
   not embed timestamps, random values, or volatile state in stable layers.
2. Use multi-turn conversations naturally — each turn extends the prefix.
3. For long-document Q&A, keep the document in the same position across
   questions so the common prefix is detected and cached.

### Usage metrics

The API returns cache metrics in the `usage` object:

| Field | Description |
|-------|-------------|
| `prompt_cache_hit_tokens` | Input tokens served from cache |
| `prompt_cache_miss_tokens` | Input tokens computed fresh |

These are captured in `TokenUsage` and surfaced via structured logging
and the SSE token-usage events.

---

## 6. FIM API (Beta)

Fill-In-the-Middle completion for code infill. Only `deepseek-v4-pro`
supports this endpoint.

**Endpoint:** `POST https://api.deepseek.com/beta/completions`

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

In LeAgent, use `DeepSeekProvider.fim_complete()` for programmatic access.

---

## 7. Balance Check

**Endpoint:** `GET https://api.deepseek.com/user/balance`

Returns account availability and balance breakdown. Used by
`deepseek_utils.check_balance()` for admin health checks.

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

## 8. `user_id` for KV Cache Isolation

The `user_id` request parameter (charset `[a-zA-Z0-9\-_]`, max 512 chars)
lets DeepSeek partition its KV cache per user. LeAgent injects a sanitized
`workspace_id:user_id` via `DeepSeekProvider._build_request_body` when the
`_deepseek_user_id` context variable is set by the API layer.

Do **not** include PII in `user_id`.

---

## 9. Deprecated Parameters

| Parameter | Status |
|-----------|--------|
| `frequency_penalty` | Deprecated — silently ignored, stripped by provider |
| `presence_penalty` | Deprecated — silently ignored, stripped by provider |

---

## 10. LeAgent Implementation Details

### Provider class

`leagent/llm/providers/deepseek.py` — `DeepSeekProvider(OpenAIProvider)`:

- Merges `thinking` / `reasoning_effort` from settings + per-request
  contextvar overrides.
- Strips deprecated and thinking-incompatible parameters from requests.
- Overrides `_parse_stream_chunk` for `reasoning_content` and V4 usage
  fields.
- Overrides `_parse_response` for non-streaming `reasoning_content`.
- Injects `user_id` for KV cache isolation.
- Provides `fim_complete()` for FIM code infill.

### Context strategy

`leagent/context/strategies/deepseek.py` — `DeepSeekContextStrategy`:

- Optimizes context ordering for DeepSeek's attention patterns (stable
  prefixes for automatic disk caching, high-priority content at
  boundaries).
- Default budget tuned for V4's 1M token context window.

### Registry wiring

`leagent/llm/registry.py` — `create_default_registry()`:

- Registers `DeepSeekProvider` under `"deepseek"` when API key is set.
- Auto-aliases as `tier1` (`deepseek-v4-pro`) and `tier2`
  (`deepseek-v4-flash`) when no explicit tier endpoints are configured.
- Detects DeepSeek hostnames in tier endpoints via
  `_endpoint_hostname_is_deepseek()`.

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| 400 error mentioning `reasoning_content` | Tool-call turn missing `reasoning_content` passback | Ensure `ChatMessage.reasoning_content` is preserved on assistant messages with tool calls |
| `temperature` / `top_p` have no effect | Thinking mode is enabled (default) | Expected behavior — these params are ignored in thinking mode |
| Empty `content` with `tool_calls` | Model chose to call tools instead of answering | Normal flow — execute tools and continue the loop |
| `content: null` streaming delta | DeepSeek quirk before tool-call deltas | Coalesced to empty string by `_parse_stream_chunk` |
| `finish_reason: insufficient_system_resource` | DeepSeek server overload | Retry with exponential backoff (handled by `max_retries`) |
| `prompt_cache_hit_tokens` always 0 | System prompt changes between requests | Stabilize L0–L4 prompt layers; cache takes seconds to build |
| Import errors from `/opt/ros/*` | `PYTHONPATH` includes ROS paths | Set `PYTHONPATH=""` before running LeAgent |

---

## 12. Running Tests

```bash
# Offline provider tests (no API key needed)
cd backend
uv run python -m pytest tests/test_deepseek_provider.py tests/test_deepseek_context_strategy.py -v

# Live integration test (requires DEEPSEEK_API_KEY)
PYTHONPATH="" DEEPSEEK_API_KEY=sk-... \
  uv run python -m pytest tests/integration/test_deepseek_excel.py -v -m integration
```

---

## References

- DeepSeek API docs: <https://api-docs.deepseek.com>
- DeepSeek V4 announcement: <https://api-docs.deepseek.com/news/news260424>
- Pricing: <https://api-docs.deepseek.com/quick_start/pricing>
- LeAgent AGENTS.md: DeepSeek provider section
- LeAgent context compression guide: `docs/context-compression-and-usage.md`
