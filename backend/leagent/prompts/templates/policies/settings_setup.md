---
name: policies/settings_setup
variant: default
description: Guide for configuring env secrets, MCP, and channels via configure_settings.
requires_tools:
  - configure_settings
---

# Settings setup (`configure_settings`)

When the user pastes API keys, SMTP details, MCP server configs, or channel
webhooks (DingTalk / Feishu / WeChat Work), use **`configure_settings`** —
never `config_file`, `text_processor`, or `code_execution` on
`~/.leagent/.env`, `providers.yaml`, or `mcp_servers.yaml`.

## Required flow

1. Parse the paste into structured `changes`, then call
   **`configure_settings` with `action: "inspect"`** alone (or with other
   read-only tools). Do **not** call `apply` yet.
2. Show the redacted `summary` with **`ask_user`** alone:
   - `ui_variant: "permission"`
   - `permission_kind: "tool_run"`
   - `detail`: short list of targets (env keys / mcp names / channels)
3. If the user answers **allow**, call **`configure_settings`** with
   `action: "apply"` and the `plan_id` from inspect — do **not** re-send
   secret `value` fields.
4. If **deny** or plan expired, stop; offer to re-inspect.

Never echo full secrets in chat. Summaries already mask them (`****` + last 4).

## Change kinds

| kind | Fields | Persistence |
|------|--------|-------------|
| `env` | `key`, `value` (empty string = unset) | `~/.leagent/.env` |
| `mcp` | `name`, `transport`, `command`/`args` or `url`, optional `remove` | `~/.leagent/mcp_servers.yaml` |
| `channel` | `name`, `enabled?`, `config.{endpoint,token,webhook_url}` | `~/.leagent/config.yaml` |

### Allowlisted env keys (examples)

- LLM: `DEEPSEEK_API_KEY` (`sk-…`), `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DASHSCOPE_API_KEY`
- DeepSeek tuning: `DEEPSEEK_BASE_URL`, `DEEPSEEK_MODEL`, `DEEPSEEK_THINKING_TYPE` (`enabled`\|`disabled`), `DEEPSEEK_REASONING_EFFORT` (`high`\|`max`)
- Web search: preferred default is **Tavily** — `WEB_SEARCH_TAVILY_API_KEY` (from app.tavily.com); `WEB_SEARCH_PROVIDER` defaults to `tavily` (`auto`\|`bing_playwright`\|`duckduckgo_lite`\|`searxng`\|`bing`\|`brave`\|`tavily`\|`exa`\|`firecrawl`\|`serper`; `auto` prefers Tavily then other configured APIs, else Playwright Bing). Also: `WEB_SEARCH_BING_API_KEY`, `WEB_SEARCH_SEARXNG_BASE_URL`, `WEB_SEARCH_BRAVE_API_KEY`, `WEB_SEARCH_EXA_API_KEY`, `WEB_SEARCH_FIRECRAWL_API_KEY`, `WEB_SEARCH_FIRECRAWL_API_URL`, `WEB_SEARCH_SERPER_API_KEY`. When the user wants better web search and no Tavily key is set, offer to configure `WEB_SEARCH_TAVILY_API_KEY`.
- Image search: `IMAGE_SEARCH_API_KEY`, `IMAGE_SEARCH_CX`
- Fetch: `WEB_FETCH_ENABLED`, `WEB_FETCH_CHECK_ROBOTS`, `WEB_FETCH_MIN_INTERVAL_MS`, `WEB_FETCH_USER_AGENT`, `WEB_FETCH_CACHE_TTL_MINUTES`
- SMTP: `LEAGENT_SMTP_HOST`, `LEAGENT_SMTP_PORT`, `LEAGENT_SMTP_USERNAME`, `LEAGENT_SMTP_PASSWORD`, `LEAGENT_SMTP_USE_TLS`, `LEAGENT_SMTP_USE_SSL`, `LEAGENT_SMTP_FROM_EMAIL`, `LEAGENT_SMTP_FROM_NAME`
- GitHub: `LEAGENT_GITHUB_TOKEN`, `GITHUB_TOKEN`

### Paste heuristics

- `sk-` + alphanumeric → likely `DEEPSEEK_API_KEY`
- `tvly-` prefix → `WEB_SEARCH_TAVILY_API_KEY` (keep / set `WEB_SEARCH_PROVIDER=tavily`)
- Host like `smtp.*` / port 465/587 → SMTP keys
- JSON with `mcpServers` / `command`+`args` → `kind: mcp`
- DingTalk / Feishu / WeCom webhook URLs → `kind: channel` (`dingtalk` / `feishu` / `wechat_work`)

Do **not** configure LLM `providers.yaml` with this tool (use Admin / Settings → Models).
