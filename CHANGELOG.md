# Changelog

All notable changes to LeAgent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.1] - 2026-05-21

Patch release: **blob ingest** and **canvas capture** improvements, **SQLite task-kill** stability, **output-token truncation** fixes for HTML and large tool args, **Windows NSIS** desktop build fix, README/docs i18n, and unified **1.1.1** versioning across backend, frontend, and desktop installers.

### Added — Platform technical docs — 2026-05-17

- **`docs/technical/`** — Seven maintainer guides: agent runtime (`QueryEngine`, transitions, subagents), context & compression, file sandbox & attachments, memory (three-store + recall), session management, skill system, and tool registry / execution tiers.

### Added — DeepSeek balance, Python env tooling, dashboard workflow stats — 2026-05-17

- **DeepSeek balance** (`api/v1/models.py`, `llm/providers/deepseek_utils.py`, `types/admin.ts`, `admin.ts`, `ModelProviderConfig.tsx`, `SettingsPage`, `settings.json` en/zh) — **`GET /api/v1/models/providers/{name}/balance`** proxies DeepSeek **`GET /user/balance`** (normalizes `/v1` base URLs); balance shown inline on the provider subtitle in **Settings → Models** and **Admin → Providers** detail (refreshes when the page or focused provider loads); insufficient-balance hint when `is_available` is false.
- **Python environment** (`services/python_env/manager.py`, `api/v1/python_env.py`, Settings **Python packages** tab) — **`GET /outdated`**, **`POST /upgrade`**, direct-dependency flags on list (`is_direct`), uv project sync/lock awareness; install/uninstall error surfacing.
- **Dashboard / tasks** (`api/v1/stats.py`, `api/v1/tasks.py`, `api/v1/activities.py`, dashboard components) — Home stats and task lists include **workflow executions** alongside background tasks; due-this-week and activity feed alignment.

### Changed — DeepSeek setup nudge, Settings, MCP, docs — 2026-05-17

- **DeepSeek setup nudge** (`DeepSeekApiKeyDialog.tsx`, `deepseekSetupNudge.ts`) — Modal-based first-run provider setup (preset picker, models, enable toggle) when no providers exist; nudge keyed off provider list instead of `DEEPSEEK_API_KEY` token row alone.
- **Settings** (`SettingsPage/index.tsx`, locale bundles) — Expanded models/tokens copy, DeepSeek V4 env hints, Python packages filters (all / direct / outdated) and refresh UX.
- **MCP / Tools** (`MCPPage/index.tsx`, `ToolsPage/index.tsx`) — Layout and i18n polish for integrations pages.
- **Docs** (`AGENTS.md`, `README.md`, `backend/README.md`, `docs/architecture.md`, `docs/codebase.md`, guides) — Align with QueryEngine-first stack, technical doc index, and deployment notes.

### Fixed — Coding Projects Git panel — 2026-05-17

- **Refresh control** (`GitPanel.tsx`) — Icon and label use `Button` `leftIcon` so they stay on one row (block SVG no longer stacks under text).
- **Working-tree status** (`GitPanel.tsx`, `codingProjects.json` en/zh) — Porcelain codes (`??`, ` M`, …) map to localized labels (**未跟踪** / **New**, etc.) with tooltip showing the raw Git code.

### Changed — Chat empty-state suggestion cards — 2026-05-17

- **Empty chat suggestions** (`frontend/src/styles/chat.css`, `ChatMessages.tsx`) — Portrait suggestion cards are ~20% smaller (narrower width clamp, scaled icons and label/hint typography, tighter padding); card row gap `gap-4` → `gap-3`.

### Changed — Coding Projects sidebar colors — 2026-05-17

- **Project list selection** (`frontend/src/pages/CodingProjects/index.tsx`) — Active row uses nav-aligned primary tokens (`bg-primary-100`, `border-primary-200`, subtle ring) with primary-tinted title and template text instead of faint `bg-primary/10`.
- **Status badge** (`CodingProjectStatusBadge.tsx`) — **Idle** state uses primary sky tints; starting / running / stopping / crashed keep semantic amber / emerald / orange / rose colors.
- **Runtime tag** (`index.tsx`, `CodingProjectRunPanel.tsx`) — `frontend` → primary badge; `fastapi` → success badge (replaces flat outline muted styling).

## [1.1.0] - 2026-05-15

LeAgent **1.1.0** is a minor release focused on a **QueryEngine-first** agent stack, a **much larger tool and context surface**, **session-backed memory and prompts**, **GenUI and workflow polish**, and **desktop-grade reliability** (attachments, cron, providers, SQLite). Run `alembic upgrade head`, rebuild the frontend, and skim [`AGENTS.md`](AGENTS.md) for new environment variables before upgrading from **1.0.x**.

### Release highlights

- **Agent core** — `QueryEngine` orchestration, explicit transitions, injectable `QueryDeps`, streaming tool-call round-trips (incl. DeepSeek `reasoning_content`), unified tool bootstrap, dual-tier code execution, and optional split-service entrypoints (`leagent_core/`, gRPC, Redis-backed workflow and task fan-out).
- **Context & prompts** — Source-driven `ContextManager` + recipes, layered `leagent.prompts` (L0–L7), budget and fingerprinting, provider-aware render; session compression pipeline, manual `POST …/compact-context`, composer **context-usage ring** and KV cache telemetry where supported.
- **Memory & skills** — Cognitive three-store `AgentMemory`, signed attachment URLs, non-null `File.session_id`, **Agent Skills v1.0** (`SKILL.md`, HTTP registry, progressive-disclosure tools); pluggable extensions and RTSP proxy for canvas.
- **Tools (80+)** — New categories: chart, image, code (`code_execution`, `syntax_validator`), db, canvas (GenUI emit/publish), project / coding_project, skills, workflow tools; PPTX/style registry enhancements; path sandbox for file-touching tools.
- **Product & workspace** — RBAC v2, workspaces and JWT claims, notifications and todos, folder **code-project** mode with git APIs, knowledge root under `LEAGENT_HOME/knowledge`, authorized session directories; SMTP defaults and **`/api/v1/settings/mail`**.
- **Long-running coding** — Runtime profiles (`coding_long` / `coding_extended`), **`POST /api/v1/tasks/agent-runs`** with JSONL logs, task timeouts and subprocess reap; Tasks UI launcher.
- **Web & Playwright** — Polite outbound HTTP, robots checks, scholarly `web_search` modes, lazy `BrowserPool`, extension-pack `playwright install`, env secrets for `WEB_*` keys; default `start.sh` browser extra.
- **GenUI** — Inline floating toolbar, full-area PNG capture, print-emulation PDF (A4 / slides), PPTX export server route.
- **UX** — Floating NavRail, chat right-panel chrome, workflow template gallery (`TPL-01`…`TPL-10`) with input schema defaults, Settings **Python packages** tab and **`/api/v1/python-env`**, provider `api_key_set` accuracy, chat authorized-folder paste/drag UX.
- **CJK** — Shared font discovery cache, subprocess env injection, matplotlib + chart hooks, `LEAGENT_CJK_FONT` docs.
- **Session artifacts** — Unified registration so tool outputs map to managed attachments with stable preview/download URLs in follow-up turns.
- **Fixes** — Chat history attachment re-signing and authenticated preview; SQLite-safe hard delete of sessions; cron UI ↔ API parity; Flow schedule modal `mode="create"`; model provider cards when API keys live only in env.

### 中文要点（发布公告用）

- **核心**：以 `QueryEngine` 为主会话编排，工具流式调用与 DeepSeek 等提供商对齐；统一工具引导与代码执行沙箱。
- **上下文与提示词**：配方化上下文组装、八层 Prompt 预算与指纹；支持会话压缩 API、Composer 用量环与缓存命中展示。
- **记忆与技能**：三库认知记忆、会话附件签名 URL、Skills v1.0 与可插拔扩展。
- **工具与自动化**：80+ 工具（图表、画布 GenUI、工程目录、工作流等）；长时编码任务与任务管理器超时/收割。
- **协作与数据面**：RBAC / 工作区、通知与待办、文件夹工程模式与知识库根目录；SMTP 与邮件工具默认合并。
- **体验与稳定性**：GenUI 导出与模板库焕新、导航与聊天布局、定时任务与模型提供商界面修复、CJK 字体与附件路径统一。

_Subsections below keep `— YYYY-MM-DD` on each heading for maintainers (commit date or editorial batch)._

### Added — Agent semantic tool errors, DeepSeek FIM, richer syntax validation, SMTP defaults, chat authorized-folder UX — 2026-05-13

- **Tool results** (`tools/base.py`, `agent/query.py`, `agent/recovery.py`) — `ToolResult.fail(..., data=…)`; `BaseTool.coerce_tool_result()` so in-band failures map to `success=false`; LLM-facing failures with structured JSON `{"tool_ok": false, "error", "detail"}` when `data` is a dict.
- **`code_execution`** (`tools/code/execution.py`) — AST presubmit (opt out via `skip_syntax_check`); `coerce_tool_result` marks sandbox `status != ok` as failed tool results.
- **`project_shell`** (`tools/project/shell.py`) — `coerce_tool_result` treats non-zero exit, timeout, and early `{error: …}` payloads as failed results.
- **Subagents** (`agent/subagent.py`) — `coding_agent` runs with `changed_files` but no `project_shell` set `verification_gap` + `partial`; tool activity / produced-file parsing understands `tool_ok` + `detail` envelopes.
- **`deepseek_fim` tool** (`tools/code/deepseek_fim.py`, `bootstrap/tools.py`, `tools/code/__init__.py`) — DeepSeek `/beta/completions` FIM plus session-scoped `buffer_*` protocol; whitelisted for `script_agent` / `coding_agent` (`agent/script_agent.py`, `agent/coding_agent.py`).
- **Syntax engine** (`services/syntax_validation.py`) — **YAML** (`safe_load`), **JSONC** (BOM strip, whole-line `//`, trailing commas), improved `auto` detection (`.yaml`/`.yml`/`.jsonc`, `---` / `%YAML` heuristics), JSON BOM strip.
- **`syntax_validator` tool** (`tools/code/syntax_validator.py`, v1.1.0) — `jsonc` / `yaml` modes, `hint_filename` for inline auto-detect, `max_content_chars` cap + `input_too_large`, UTF-8-SIG file reads.
- **SMTP / outbound mail** (`config/settings.py`, `services/smtp_defaults.py`, `api/v1/settings_mail.py`, `api/v1/settings_tokens.py`, `api/router_deferred.py`, `tools/integration/email_send.py`) — `LEAGENT_SMTP_*` settings and token allowlist; `merge_smtp_defaults` fills `email_send` tool args from server config; **GET/POST `/api/v1/settings/mail`** status and connection or test-send endpoints.
- **Chat authorized folders** (`frontend/src/lib/localFolderPath.ts`, `ChatInput.tsx`, `chat.json` en/zh) — Normalize pasted/dropped `file://` paths, quotes, multi-line clips, and bidi marks before granting; drag-and-drop onto the path field; updated help copy.
- **Tests** — `test_deepseek_fim_tool.py`; expanded `test_syntax_validation.py`, `test_code_execution.py`, `test_subagent.py`, `test_project_tools.py`, `test_tools.py`; `frontend/src/lib/localFolderPath.test.ts`.

### Changed — Coding / script agent prompts — 2026-05-14

- **`coding_agent.md` / `script_agent.md`** — Verification gap note, `syntax_validator` / `deepseek_fim` / `code_execution` semantics and tool routing table updates.

### Changed — Playwright defaults, extension packs, polite web outbound & settings env tokens — 2026-05-13

- **`start.sh`** — Default `UV_SYNC_EXTRAS` includes **`browser`**; **`ensure_playwright_browsers`** runs `playwright install chromium` (optional `install-deps` on Linux); env **`LEAGENT_SKIP_PLAYWRIGHT_INSTALL`**, **`LEAGENT_PLAYWRIGHT_MIRROR`**, **`PLAYWRIGHT_DOWNLOAD_HOST`** documented in `--help`.
- **Extension packs** (`extensions/manager.py`, `official_registry.json`) — Browser pack runs **`playwright install`** (and optional **`install-deps`**) after `uv`/`pip` install; install API returns **`playwright_install_ok`** and **`needs_backend_restart: false`** when lazy-import path applies.
- **`web_search` tool** (`tools/web/web_search_tool.py`, `tools/web/web_search/`) — API-first scholarly modes (**arxiv**, **wikipedia**, **crossref**, **pubmed**); general search via **DuckDuckGo lite**, **SearxNG**, or **Bing**; **`trust_env`** for proxies; graceful degradation when keys or hosts fail (**`degraded`**, **`degraded_reasons`**, **`next_step`**).
- **Polite outbound HTTP** (`tools/web/polite_http.py`) — Per-host lock, minimum interval + jitter, limited **429/5xx** retries with **`Retry-After`** / backoff; shared **`public_fetch_user_agent`** (**`WEB_FETCH_USER_AGENT`** / **`WEB_SEARCH_USER_AGENT`**).
- **Robots policy** (`tools/web/robots_policy.py`) — Optional **`robots.txt`** check before **`web_scraper`** and **`web_image_download`** (missing/404 robots fails open); cached per host (**`WEB_FETCH_ROBOTS_CACHE_TTL_SEC`**).
- **Config** (`config/settings.py`) — **`WebSearchSettings`**, **`WebBrowserSettings`**, **`WebFetchSettings`** (`WEB_FETCH_*` pacing, robots, Playwright pre-**goto** delay).
- **Integrations** — **`web_search`** uses **`polite_get`**; **Google CSE** image search uses **`polite_get`**; **`web_image_download`** uses **`polite_stream`** + robots.
- **Settings → Environment secrets** (backend `settings_tokens.py`, frontend `SettingsPage`) — Allowlist **`WEB_SEARCH_*`**, **`IMAGE_SEARCH_*`**, **`WEB_FETCH_*`**; validation + **`get_settings.cache_clear()`** on updates; browser-pack install warning toast when Playwright download fails.
- **Deploy** (`deploy/Dockerfile`) — **`pip install -e ".[ocr,browser]"`** before **`playwright install chromium`**.
- **Docs** — **`AGENTS.md`** env notes for Playwright mirror, web search, web fetch, and settings UI.
- **Tests** — `test_extension_playwright_install.py`, `test_polite_http_robots.py`, `test_settings_tokens_api.py` (web search / web fetch validation), **`test_web_image_search`** updated for **`client.request`** mock.

### Changed — Browser pool, scraper, image tools, and default agent copy — 2026-05-13

- **`BrowserPool`** (`tools/web/browser_pool.py`) — **Lazy** `playwright.async_api` import so runtime extension install can work without process restart; config from **`WebBrowserSettings`**.
- **`web_image_search`** — Returns empty results + **`next_step`** when CSE is unconfigured or the API errors, instead of hard-failing the turn.
- **`web_scraper`** — **`assert_fetch_allowed`** + configurable pre-navigation delay (**`WEB_FETCH_PRE_NAVIGATION_DELAY_MS`**).
- **Persona** (`prompts/templates/default_agent.md`) — **`web_search`** vs **`web_scraper`** vs image tools when keys or results are missing.

### Fixed — Chat history signed file URLs & Flow schedule modal — 2026-05-14

- **Frontend** (`GenUiImage.tsx`, `ChatImage.tsx`, `chatMediaUtils.ts`) — Managed `/api/v1/files/{uuid}/preview` images refetch via authenticated `GET …/preview` even when persisted URLs include an expired `?token=`; added `extractApiFileDownloadId` for download paths.
- **Attachments & downloads** (`AttachmentCard.tsx`, `ChatView/index.tsx`, `ArtifactCard.tsx`) — Video previews use the same authenticated preview fetch; download actions resolve file UUIDs and use `downloadAuthenticatedFile` instead of stale signed `href`s; the chat `download` / `下载` filename command avoids expired `download_url` tokens.
- **Backend** (`SessionManager.list_attachments`, `GET /chat/sessions/{id}/attachments`) — Optional `user_id` refresh re-signs `preview_url` / `download_url` when listing attachments so history reload does not return only expired tokens from stored session state.
- **Flow editor** (`frontend/src/pages/FlowPage/index.tsx`) — Passes `mode="create"` to `CronJobModal` when scheduling a workflow (required by `CronJobModalProps`).

### Added — CJK font discovery cache, subprocess env, and generation prompt hint — 2026-05-13

- **`leagent/utils/cjk_font_discovery.py`** — Broader OS font roots (incl. macOS, `XDG_DATA_HOME/fonts`), process-level discovery cache, `resolve_cjk_bold_path`, and `build_cjk_generation_turn_extra` for PDF/DOCX/PPTX/chart/code tools.
- **Code execution** (`subprocess_sandbox.py`) — Allowlists `LEAGENT_CJK_FONT` / `LEAGENT_CJK_FONT_BOLD` and injects resolved font via `ExecutionPolicy.extra_env`.
- **Query engine** (`agent/query_engine.py`) — Appends CJK generation guidance to turn extras when relevant tools are registered.
- **Matplotlib** (`matplotlib_cjk.py`, `runner.py`) — Still registers discovered or env font and sets `font.sans-serif` / `axes.unicode_minus` when user code references matplotlib.
- **Chart tool** (`chart_generator.py`) — Generated scripts call the same CJK hook after `Agg` backend selection.
- **Docs / deploy** — `document_fonts` policy and deploy env examples note `LEAGENT_CJK_FONT` for PDF and matplotlib.
- **Tests** — `backend/tests/test_matplotlib_cjk.py` (cache, subprocess env, turn-extra gating).

### Changed — Unified session artifact path management — 2026-05-13

- **Artifact registration** (`backend/leagent/services/session/artifacts.py`) — Added a shared extractor/registrar for tool outputs, code-execution files, `file://` artifacts, nested `result.saved_to`, and subagent-style `produced_files`, converting internal paths into managed session attachments.
- **Session paths** (`backend/leagent/services/session/paths.py`) — Centralized session upload directory resolution and reused it across uploads, path sandboxing, code-execution scan roots, image generation/download, and screenshot output.
- **Agent runtimes** (`backend/leagent/agent/query_engine.py`, `backend/leagent/agent/controller.py`) — Both QueryEngine and AgentController now use the same artifact registrar; tool results are augmented with `managed_artifacts` so follow-up assistant turns cite signed `preview_url` / `download_url` instead of relative filenames.
- **Chat media** (`frontend/src/components/chat/media/*`, `frontend/src/components/canvas/genUi/GenUiImage.tsx`) — Unified managed-file preview parsing: UUID preview paths fetch authenticated blobs, signed URLs render directly, and non-UUID `/files/name/preview` links fail clearly instead of silently rendering broken images.
- **Tests** — `backend/tests/test_session_artifacts.py` and `frontend/src/components/chat/media/chatMediaUtils.test.ts`.

### Fixed — Cron (scheduled jobs) UI ↔ `/api/v1/cron` — 2026-05-12

- **Payload & validation** (`frontend/src/pages/CronPage/cronJobPayload.ts`) — Trims strings, omits empty `target_id` (avoids Pydantic UUID **422**); validates **flow** has a workflow id and **webhook** has `payload.url`.
- **Cron page** (`frontend/src/pages/CronPage/index.tsx`) — Edit path loads **`GET /api/v1/cron/{id}`** via `useCronJob` before opening the modal; **degraded** banner when jobs list, stats, or health queries fail; **`failed` / `disabled`** map to `StatusBadge`; pause/resume invalidate **stats** as well as the job list.
- **Cron modal** (`frontend/src/pages/CronPage/components/CronJobModal.tsx`) — Explicit **`create` / `edit`** mode, detail **loading** and **error** UI (no empty “new job” form on fetch failure), **structured Webhook** (URL, method, timeout, headers/body JSON) and **Script** (`script_path`, args/env JSON, payload timeout, optional inline script + `cron_allow_shell` hint); **job type** locked after create; **flow**-only advanced JSON payload block.
- **Cron queries** (`frontend/src/controllers/API/queries/cron/index.ts`) — Pause/resume mutations invalidate **`CRON_STATS`**.
- **i18n** (`frontend/src/i18n/locales/zh-CN|en-US/workflows.json`) — `cron.serviceUnavailable`, `cron.validation.*`, and extended **`cron.modal.*`** copy for task/webhook/script/flow.
- **Tests** — `frontend/src/pages/CronPage/cronJobPayload.test.ts`; `frontend/src/App.routing.test.tsx` stubs **`GET /api/v1/cron/health`**; `backend/tests/test_cron_api.py` exercises cron routes with a **fake `CronManager`** (`dependency_overrides`) plus **`GET /api/v1/cron/preview-next-runs`**.

### Added — Long-running Coding Agent runtime — 2026-05-11

- **Runtime profiles** (`leagent/agent/runtime_profile.py`, `leagent/config/settings.py`) — Added explicit `standard`, `coding_long`, and `coding_extended` budgets for agent turn limits, task deadlines, tool timeouts, stream drain windows, and code-execution ceilings.
- **Background Agent runs** (`leagent/api/v1/tasks.py`, `leagent/tasks/handlers/agent_handler.py`) — New `POST /api/v1/tasks/agent-runs` entrypoint starts coding agents as DB-backed tasks, returns a `task_id`, and streams JSONL progress through the existing task output endpoint.
- **Task lifecycle hardening** (`leagent/services/task_manager.py`) — Enforces task-level `timeout_seconds`, records `TIMEOUT`, separates cooperative cancel from forced kill, and reaps active code-execution subprocesses by task/session.
- **Code execution** (`leagent/tools/code/execution.py`) — Honors long runtime profiles for per-call `timeout_sec` validation while preserving finite hard limits.
- **Tasks UI** (`frontend/src/pages/TasksPage/index.tsx`, `frontend/src/hooks/useTasks.ts`) — Added a Long-running Coding Agent launcher with `coding_long` / `coding_extended` selection, task log polling, and existing cancel/kill controls.
- **Tests** — `backend/tests/test_task_manager_lifecycle.py`, `backend/tests/test_task_handlers.py`, and `backend/tests/test_code_execution.py` cover task timeouts, runtime-profile propagation, and long code-execution budgets.

### Added — Composer context usage ring & session transcript compression — 2026-05-13

- **Composer** (`frontend/src/components/chat/composer/ContextUsagePopover.tsx`, `ChatInput.tsx`) — **Circular progress ring** (reference **128k-token** budget) for context pressure; popover with **prompt-layer breakdown** (`usePromptPreview`), **last-turn prompt tokens**, **DeepSeek KV cache hit/miss** when present, and **Compress context** action. **Stable Zustand selector** (`EMPTY_MESSAGES`) avoids infinite re-renders from inline `[]` fallbacks.
- **Backend pipeline** (`leagent/context/session_compression.py`) — **`microcompact`** → **`ProgressiveCompressor`** → optional **`apply_forced_autocompact`** (tier2 summariser, `<compacted_history>`); **`POST /api/v1/chat/sessions/{session_id}/compact-context`** with optional `{ "force_llm": true }`.
- **Persistence** (`leagent/services/chat/service.py`) — **`replace_session_transcript`** replaces **`messages`** rows after compaction; **`merge_compressed_with_session_tail`** preserves trailing **`SessionMessage`** IDs when suffix matches.
- **Compaction core** (`leagent/memory/compact.py`) — **`apply_forced_autocompact`** for manual threshold bypass.
- **Usage / cache telemetry** (`leagent/llm/base.py`, `agent/deps.py`, `llm/providers/openai.py`, `llm/providers/deepseek.py`, `agent/controller.py`) — **`prompt_cache_hit_tokens`**, **`prompt_cache_miss_tokens`** (and OpenAI **`prompt_tokens_details.cached_tokens`** where applicable) flow through streaming **`context_usage`** and assistant **`token_usage`**.
- **Types & i18n** (`frontend/src/types/chat.ts`, `locales/*/chat.json`) — Extended **`MessageUsage`**; **`contextUsage*`** strings (zh/en parity).
- **Tests** — `backend/tests/test_session_compression.py`.
- **Documentation** — [`docs/context-compression-and-usage.md`](docs/context-compression-and-usage.md) (architecture, Mermaid diagrams, operational notes).

### Fixed — Chat session hard delete (SQLite foreign keys) — 2026-05-11

- **Backend** (`leagent/services/chat/service.py`) — Hard delete and expired-session cleanup remove **`agent_episodes`** and session-scoped **`files`** before **`chat_sessions`**, matching FK constraints (`agent_episodes.session_id`, `files.session_id`). Resolves `FOREIGN KEY constraint failed` on `DELETE FROM chat_sessions`.
- **Tests** — `backend/tests/test_chat_delete_session_hard.py` seeds `AgentEpisode` and `File` rows to guard regressions.

### Changed — GenUI inline: floating toolbar, full-area capture, print-quality PDF — 2026-05-09

- **Floating modal** (`GenUiInline.tsx`, `GenUiInlineToolbar.tsx`) — Toolbar mirrors inline (**PDF**, **screenshot**, **camera**); **Enlarge** and **expand/chevron** are hidden in the modal (`showExpandToggle={false}`) since the shell is already full-height. Modal body always **`flex-1 overflow-auto`** (no secondary collapsed height).
- **PNG capture** — **`genUiCaptureDom.ts`** (`expandScrollContainersForCapture`) temporarily clears scroll clipping so long tables and **ScrollArea** export fully; **`genUiExportDimensions.ts`** measures document trees at full **`scrollWidth` / `scrollHeight`**; **SlideDeck** PNG uses at least **1280×720** and grows with content.
- **PDF client defaults** (`useGenUiExportPdf.ts`) — **`mode: document`** → **A4 + portrait**; **`mode: deck`** → **Slide16x9 + landscape** when paper options are omitted.
- **Backend GenUI PDF** (`leagent/api/v1/canvas.py`) — **`emulate_media('print')`**; **A4/Letter**: margins, **footer** (page / total pages), **`outline`** and **`tagged`** PDFs; **Slide16x9**: dynamic **width/height** from layout (min 1280×720), viewport resize; **`wait_until="load"`**, fonts ready; Chromium **`--use-gl=swiftshader`** (no **`--disable-gpu`**).
- **Print HTML theme** (`leagent/services/gen_ui/print_renderer.py`) — Typography-driven stylesheet (variables, heading scale, tables with header bands / zebra, quotes, cards), **`lang="zh-CN"`** + **`<article class="print-root">`**, broader node coverage (**Icon**, **Badge**, **Stat**, **Card**, …). Slide deck slides use improved slide chrome vs bare print defaults.
- **Tests** — `backend/tests/test_genui_pdf_export.py`; `frontend/src/components/canvas/genUi/useGenUiExportPdf.test.ts`.

### Changed — Workflow template gallery & execution defaults — 2026-05-09

- **`config/workflows/templates/`** — Replaced the previous enterprise-style `F-*.yaml` set with **10 runnable demos** (`TPL-01` … `TPL-10`): script sandbox, `date_calculator`, `json_parser`, `text_splitter`, `rule_matcher`, `syntax_validator`, chained scripts/tools, `notification` (admin channel), and JSON→rules chaining. Each template uses only supported node types and registered tools, with **`workflow.inputs[].default`** where the UI sends empty `input_data`.
- **Built-in Python templates** (`leagent/workflow/templates/__init__.py`) — **`BUILTIN_TEMPLATES` is empty** so the gallery count stays **10** (YAML-only); `SCRIPT_EXAMPLE_WORKFLOW` remains in the module for direct imports.
- **`WorkflowExecutor.execute_async`** (`leagent/workflow/engine/executor.py`) — Merges **schema defaults** from `WorkflowDocument.inputs` with caller-supplied inputs (**user keys win**), so **`POST .../workflow/flows/{id}/run`** with `{}` still receives demo defaults.
- **Tests** — `backend/tests/workflow/test_templates_execute.py` runs every catalog template with **`inputs={}`** to `COMPLETED`; `backend/tests/test_cron_executor_task_target.py` adds **`CronExecutor._execute_workflow`** coverage with a mocked executor and registry.

### Fixed — Model providers (admin API & UI) — 2026-05-13

- **Backend** (`leagent/api/v1/models.py`) — `GET /models/providers` (and related provider payloads) include **`requires_api_key`** from provider presets. **`api_key_set`** is computed with **`_compute_api_key_set()`**: resolved YAML / `${ENV}` values first, then matching **global LLM settings** (e.g. DeepSeek, OpenAI, Anthropic, DashScope, **`tier1`** / **`tier2`** names). Avoids false “API key not configured” when the key exists only in environment.
- **Settings page** — Provider cards use **`api_key_set`** for the masked key line instead of inferring from **`is_healthy`**. Providers that do not use keys (preset) show **no API key required** and skip inline key editing.
- **Admin → Providers** — Detail panel shows three states for API keys (**not required** / **configured** / **not configured**); **Edit** and **Test connection** use **`Button` `leftIcon`** so icons and labels stay on one line.
- **Tests** — `backend/tests/test_models_api_key_set.py` exercises API key resolution.

### Added — Settings: backend Python environment management — 2026-05-13

- **Settings page** (`frontend/src/pages/SettingsPage/index.tsx`) — New **Python 包管理 / Python packages** tab: lists packages in the environment used by the running backend, install by PyPI requirement string, uninstall by distribution name; shows interpreter path and whether `uv` is available.
- **REST API** (`leagent/api/v1/python_env.py`, mounted at `/api/v1/python-env` from `router_deferred.py`) — `GET /info`, `GET /packages`, `POST /install` with body `{ "spec": "..." }`, `POST /uninstall` with body `{ "package": "..." }`. **`PythonEnvManager`** (`leagent/services/python_env/manager.py`) invokes `uv pip` when present, otherwise `python -m pip`, using the backend project root as working directory (aligned with official extension pack installs).

### Changed — Settings: extension packs copy & Python packages tab — 2026-05-13

- **Extension packs card** — `settings.pluginsCardDesc` (zh-CN and en-US) no longer states that install/remove requires administrator or `admin:panel` permission.
- **Python packages tab** — Refresh, Install, and per-row Uninstall buttons match the appearance theme control sizing (`min-h-[2.5rem]`, `sm:min-w-[7.5rem]`) so they align with the package spec input row.

### Changed — App shell & chat layout (frontend) — 2026-05-09

- **NavRail** (`frontend/src/components/layout/NavRail.tsx`, `navRailLayout.ts`) — Main navigation is a **floating** card (`fixed`, `rounded-2xl`, `border`, `shadow-soft`, ring) with **8px** side/bottom margins and **10px** top offset to align with the chat FAB row; **AppShell** reserves matching spacer width for main content; **Modal** main-area inset follows the same horizontal geometry.
- **NavRail chrome** — Removed the **top border** above the Pet dock / user menu block so the footer area no longer shows a divider line against the scrollable nav.
- **Chat right panel** (`RightPanel.tsx`, `ChatView/index.tsx`) — Workspace / artifact chrome uses **rounded pill tabs** (same primary tint pattern as the rail), outer panel wrapped in the same **floating surface** treatment; desktop `#chat-right` panel adds **padding** (`pt-[10px]`, horizontal/bottom `8px`) so the card floats inside the group; **narrow viewports** use the same outer offsets for the drawer.
- **Workspace panel** (`WorkspaceTabBar.tsx`, `ChatWorkspacePanel.tsx`) — Inner workspace segment tabs use the **rail-aligned active colors**; outer panel background is **transparent** so it reads as one card with `RightPanel`.
- **Chat resize separator** (`frontend/src/styles/chat.css`) — The `react-resizable-panels` **Separator** between chat center and right panel is **visually hidden** (no center line; **6px** transparent drag strip). While hovering or dragging, **`#right-panel-shell`** gets a **left border tint** so resize feels tied to the workspace edge without overriding card shadows.

### Added — Expanded tool system (80+ tools across 15 categories) — 2026-05-08

- **New `tools/chart/` category** — `ChartGeneratorTool`
  (`chart_generator.py`) wraps matplotlib/plotly for professional-grade
  charts with four built-in themes (`presentation`, `report`,
  `dashboard`, `minimal`). Runs chart generation inside the
  `code_execution` subprocess sandbox for isolation. Supports bar,
  line, scatter, pie, histogram, heatmap, and box plots.
- **New `tools/image/` category** — `ImageGenerateTool`
  (`image_generate.py`) for AI image synthesis via DALL-E 3 (extensible
  provider layer). Aliases: `generate_image`, `dall_e`,
  `text_to_image`, `create_image`.
- **New `tools/code/` category** — `CodeExecutionTool` (canonical
  location for the subprocess sandbox tool) and new
  `SyntaxValidatorTool` for fast JSON/Python syntax validation with
  line/column diagnostics.
- **New `tools/db/` category** — `DatabaseTool` for real RDBMS access
  (SQLite by default; PostgreSQL/MySQL gated behind
  `LEAGENT_DATABASE_TOOL_REMOTE=1`). Operations: `create_sqlite`,
  `query` (read-only), `execute` (DML/DDL with destructive confirm),
  `list_tables`, `describe_table`, `test_connection`. Accompanied by
  `sql_guard.py`, `inspector_ops.py`, `connection.py` helpers.
- **New `tools/canvas/` category** (5 tools) — `CanvasPublishTool`,
  `EmitUiTreeTool`, `EmitUiPatchTool`, `ListUiComponentsTool`,
  `GetHtmlCanvasGuideTool` for generative UI and hosted HTML canvas.
- **New `tools/project/` category** (8 tools) — full coding-agent
  toolbox: `project_read` (line-numbered), `project_write`,
  `project_edit` (uniqueness-checked string replace),
  `project_apply_patch` (unified diff), `project_grep` (rg-aware
  regex), `project_glob`, `project_tree` (gitignore-aware),
  `project_shell` (curated whitelist or free-form on local).
- **New `tools/coding_project/` category** (5 tools) — live-runtime
  tools wrapping `CodingProjectManager`: `scaffold`, `run` (dev
  server + signed preview URL), `stop`, `status`, `logs`.
- **New `tools/skills/` category** (5 tools) — `load_skill`,
  `read_skill_resource`, `run_skill_script`, `package_skill`,
  `install_skill` for the Agent Skills v1.0 progressive disclosure.
- **New `tools/workflow/` category** (8 tools) — `workflow_list`,
  `workflow_run`, `workflow_status`, `workflow_cancel`,
  `workflow_pause`, `workflow_resume`, `chat_workflow_emit`,
  `chat_workflow_embed_emit`.
- **`tools/gen/` enhancements**:
  - `PptxGeneratorTool` (`pptx_generator.py`) — creates `.pptx`
    presentations from scratch or templates with multiple slide
    layouts, text/image/table/chart/shape embedding, theme colors,
    and speaker notes. Aliases: `pptx_gen`, `powerpoint_gen`,
    `create_pptx`, `presentation_gen`.
  - `StyleRegistry` (`style_registry.py`) — reusable YAML style
    definitions for PDF, Word, and PPTX with built-in presets
    (`professional`, `minimal`, `modern`, `creative`). Thread-safe
    singleton via `get_style_registry()`.
  - `_image_resolver.py` — shared image resolution utility (file
    paths, base64, URLs) with optional resizing and 10 MB hard limit.
- **`tools/integration/` enhancements** — new `SpeechToTextTool`
  (`speech_to_text.py`) using OpenAI Whisper when `OPENAI_API_KEY` is
  set, with structured placeholder fallback for dev environments.
- **`tools/util/` enhancements** — new `AskUserTool` (`ask_user.py`)
  for LLM-initiated structured clarification with optional fixed
  choices, multi-select, and free-text.

### Added — Context system redesign (source-driven pipeline) — 2026-05-08

- **`ContextManager`** (`context/manager.py`) replaces the earlier
  flat prompt assembly with a recipe-driven source pipeline.
  `prepare_turn()` resolves an ordered list of `ContextSource`
  implementations, applies budget minimisation via `minimise()`,
  splits blocks into `SYSTEM` (system prompt text) and
  `ATTACHMENT_USER` (user-role messages), computes stable + full
  hashes for fingerprinting, and returns a `TurnContext`.
- **`ContextRecipe`** (`context/recipe.py`) + `RECIPE_REGISTRY`
  map each prompt variant (e.g. `default_agent`, `coding_agent`)
  to an ordered source ID list.
- **12 `ContextSource` implementations** under `context/sources/`:
  `IdentitySource`, `CapabilitiesSource`, `PoliciesSource`,
  `EnvironmentSource`, `ActiveProjectSource`, `ProjectMemorySource`,
  `UserInstructionsSource`, `RecallSource`,
  `SessionAttachmentsSource`, `WorkingSetSource`,
  `ToolHistorySource`, `RecentReadsSource`.
- **`FileState`** (`context/file_state.py`) — session-scoped read
  cache with LRU eviction, staleness detection (`has_changed`),
  pins, and token budget.
- **`minimise()`** (`context/budget.py`) — scores context blocks by
  freshness half-life and size; pinned blocks are kept
  unconditionally. Replaces the earlier per-layer budget policy.
- **Context audit ledger** (`context/ledger.py`) and per-source
  caching (`context/cache.py`) for observability and performance.

### Added — GenUI PPTX export and additional services — 2026-05-08

- **GenUI → PPTX renderer** (`services/gen_ui/pptx_renderer.py`) —
  `render_genui_to_pptx()` converts a gen UI tree (including
  `SlideDeck` components) into a `.pptx` file.
- **`POST /canvas/genui/export/pptx`** endpoint in
  `api/v1/canvas.py` (`GenUiExportPptxRequest`) — server-side PPTX
  export complementing the existing PDF export path.
- **Extensions system** (`leagent/extensions/`) — pluggable
  extension registry and manager for third-party integrations.
- **RTSP proxy** (`services/rtsp_proxy.py`) — RTSP→MJPEG proxy for
  live camera feeds in canvas `LiveCamera` components.

### Added — New prompt policy templates — 2026-05-08

- **`policies/code_generation.md`** — rules for standalone code
  generation and execution tasks (headless visualization, data
  processing diagnostics, timeout guidance, import tiers).
- **`policies/canvas_design.md`** — canvas routing policy (gen UI
  inline vs hosted HTML), `DesignSurface`, `AspectBox`, `Image`,
  `Icon`, `LiveCamera` components, and JSON argument safety rules.
- **`policies/coding_agent.md`** — hard rules for the project-scale
  coding sub-agent (path sandbox, read-before-write, shell discipline,
  git safety, secrets policy, code_execution vs project_* separation).
- **`policies/database_tool.md`** — safe-use policy for the real-
  database `database` tool vs in-memory `sql_query`, covering remote
  URL gating, read-only vs DML/DDL, destructive confirms, and bound
  params.
- **`coding_agent.md`** template — top-level persona template for
  the coding agent prompt variant.

### Added — Knowledge storage, session path grants, and local attachment paths — 2026-05-07

- **`FilesSettings.knowledge_storage_dir`** (env `LEAGENT_KNOWLEDGE_DIR` / `FILES_KNOWLEDGE_STORAGE_DIR`) with default **`LEAGENT_HOME/knowledge`**. Indexed knowledge documents are written under **`<that root>/documents/`** instead of `upload_dir/documents/`. The path sandbox always merges this knowledge root. **`leagent init`** creates `KNOWLEDGE_DIR`; migrate old blobs with a one-time copy from ``<FILES_UPLOAD_DIR>/documents/`` to ``<resolved knowledge root>/documents/`` if you had files there before upgrading.
- **Session authorized directories**: `GET/POST/DELETE /api/v1/chat/sessions/{session_id}/authorized-paths` stores grants in `chat_sessions.session_metadata` under `authorized_roots` and injects them as **`ToolContext.extra["authorized_roots"]`** for the agent (same directory semantics as `project_roots`).
- **Single-machine UI**: SSE attachment payloads may include **`local_path`** (resolved absolute storage path) when `LEAGENT_DESKTOP` or `LEAGENT_LOCAL` is enabled so the chat UI can show on-disk locations.
- **Coding scaffolds**: after template copy, **`git init`** runs when `git` is on `PATH` and `.git` is absent.

### Added — Folder code-project mode (Coding Agent integration) — 2026-05-07

- **`Folder` model gains three columns**: `is_project`, `project_path`,
  `project_path_checked_at`. Existing rows upgrade in place via
  Alembic migration `a3b4c5d6e7f8_folder_project_columns.py` with
  `is_project=False`. New `FolderProjectUpdate` schema and
  `is_project` / `project_path` are surfaced on `FolderRead`.
- **New `FILES_PROJECTS_ALLOWED_ROOTS` setting** (comma-separated
  absolute prefixes) on `FilesSettings`. Empty = unrestricted
  (single-user / dev default); multi-tenant deployments should
  pin it to a managed projects directory.
- **`leagent.services.coding_projects.paths`** — `validate_project_path`,
  `assert_folder_owner`, `resolve_owned_project_folder`. Pure helpers
  shared between the HTTP layer and the chat plumbing.
- **`leagent.services.coding_projects.git`** — async `git` subprocess
  wrapper (`run_git`, `git_log`, `git_show_file`, `git_diff_for_commit`,
  `git_diff_worktree`, `git_status_porcelain`, `git_init`,
  `is_git_repo`). `shell=False` argv, fixed timeouts, structured
  records.
- **Unified coding-project service package**: retired the older
  static-project service package and consolidated path safety,
  git helpers, binary allow-listing, scaffolding, runtime supervision,
  preview proxying, and template management under
  `leagent.services.coding_projects`. No DB tables, REST URLs,
  settings names, agent tool names, or frontend routes changed.
- **New folder project endpoints** under `/api/v1/folders/{id}/project/...`:
  - `PATCH /project` — toggle / re-target project mode.
  - `GET /tree?path=&depth=&include_ignored=` — gitignore-aware
    depth-N listing using `IgnoreMatcher`.
  - `GET /file?path=&offset=&limit=` — text read with binary
    detection and `MAX_TEXT_FILE_BYTES` truncation.
  - `GET /git/log`, `git/show`, `git/diff` (commit or `against_worktree`),
    `git/status`, `POST /git/init` (idempotent).
- **Chat plumbing**: `/chat/stream` accepts a new `project_folder_id`
  form field. The chat router resolves the folder, validates the
  path, persists `{project_folder_id, project_path}` on
  `ChatSession.session_metadata`, and threads
  `tool_extra["project_roots"]=[<path>]` through `AgentController`
  → `QueryEngine`. Sessions remember the binding across reloads.
- **`AgentController.run` / `run_stream` and `_run_via_query_engine`
  accept `project_roots: list[str]`**. When set, `QueryEngine.cwd`
  anchors to the project root so L4 `project_memory` walks discover
  the project's `AGENTS.md` / `.leagent/memory.md` files.
- **New L4 context source `active_project`** (registered in the
  `default_agent` and `coding_agent` recipes) renders an
  `<active_project>` block so the LLM sees the absolute root.
- **Frontend `FolderPage` Project tab** — new components under
  `pages/FolderPage/project/`: `ProjectModeBadge`, `ProjectFileTree`
  (lazy depth-1 expansion), `ProjectFileViewer` (uses existing
  `CodeBlock`), `ProjectGitHistory` (slide-over with custom +/- diff
  renderer), `ProjectGitStatusStrip`, plus `ProjectPanel` glue.
  No new dependencies.
- **`useProjectFolder.ts` hook** — `useProjectTree`, `useProjectFile`,
  `useProjectGitLog`, `useProjectGitShow`, `useProjectGitDiff`,
  `useProjectGitStatus`, `useUpdateFolderProject`, `useInitProjectGit`.
- **`chatDraft` store extended** with `projectFolderId` /
  `projectFolderName` / `projectFolderPath`. The composer renders an
  emerald project chip when set, and `runChatStream` forwards
  `project_folder_id` on submit. The binding survives across sends
  (cleared only by the chip's X button) so multi-turn coding-agent
  sessions stay anchored.
- Backend tests: `test_folder_project_api.py` (git wrapper happy +
  unhappy paths, safety helper); `test_chat_project_context.py`
  (controller injects `project_roots` into engine config and anchors
  `cwd`). `test_project_tools.py` extended with safety-helper cases.
- Docs: new "Folder code-project mode (Coding Agent integration)"
  section in `docs/architecture.md`.

### Changed — Script agent rename (`code_agent` → `script_agent`) — 2026-05-07

- **Script agent rename** — the subprocess compute delegation path formerly
  exposed as `code_agent` / `CodeAgentNode` is now `script_agent` /
  `ScriptAgentNode` (`leagent.agent.script_agent`, `register_script_agent_tool`,
  template `script_agent.md`). The `code_agent` tool name remains a registered
  alias for backward compatibility; workflow YAML may still use `type: code_agent`.

### Added — Layered prompt management package (`leagent/prompts/`) — 2026-04-24

- **`leagent.prompts` package** — a dedicated prompt management and
  generation module that centralises all system-prompt assembly into
  eight composable layers, replacing the scattered inline prompt logic
  that was previously duplicated across `AgentController`,
  `QueryEngine`, `code_agent`, `subagent`, `compact`, and
  `LLMJudgeEvaluator`.

  **Layered model:**

  | Layer | Name | Stability | Content |
  |-------|------|-----------|---------|
  | L0 | `persona` | stable | Template body (or caller override) with `{{var}}` substitution |
  | L1 | `capabilities` | stable | Tool listing + skill catalogue with resource/script hints |
  | L2 | `policies` | stable | Composable policy snippets (e.g. `file_access`) |
  | L3 | `environment` | stable | System facts (date, CWD, git, env) |
  | L4 | `project_memory` | stable | Project `.leagent/*.md` memory files |
  | L5 | `recall` | volatile | `RecallHandle` results (replaces the old `<recalled_memory>` injection) |
  | L6 | `session_state` | volatile | Attachment manifest, recent file reads, tool history |
  | L7 | `turn_extras` | volatile | Caller-supplied extras, workflow hints |

  **Key modules:**

  - `prompts/builder.py` — `PromptBuilder` orchestrates parallel layer
    collection, budget enforcement, fingerprinting, rendering, and
    session fingerprint persistence. Emits a structured `prompt_build`
    structlog event on every call.
  - `prompts/registry.py` — `PromptRegistry` loads `.md` templates with
    YAML front-matter from the file system, with mtime-based hot reload
    and fallback to built-in templates.
  - `prompts/layers.py` — eight async collector functions, one per layer.
  - `prompts/budget.py` — `BudgetPolicy` with per-layer + global char
    caps and a deterministic truncation priority order.
  - `prompts/fingerprint.py` — `stable_fingerprint` (L0–L4) for
    provider prompt caching; `full_fingerprint` (L0–L7) for change
    detection.
  - `prompts/render.py` — `PlainRenderer`, `OpenAIRenderer`, and
    `AnthropicRenderer` (with `cache_control: {"type": "ephemeral"}`
    markers on the stable prefix boundary).
  - `prompts/context.py` — `PromptContext` dataclass aggregating all
    runtime inputs for prompt layer collectors.
  - `prompts/types.py` — `PromptVariant`, `LayerResult`, `BuiltPrompt`,
    `RenderTarget`.
  - `prompts/templates/` — extracted prompt templates:
    `default_agent.md`, `code_agent.md`, `subagent.md`,
    `rule_judge.md`, `compact_summariser.md`, `policies/file_access.md`.

- **`PromptSettings`** added to `config/settings.py` (env prefix
  `LEAGENT_PROMPT_`) with `templates_dir`, `hot_reload`,
  `max_total_chars`, `per_layer_budget_chars`, and
  `enable_cache_boundaries`. Wired into `get_prompt_builder()` and
  `get_prompt_registry()` singletons.

- **New tests**: `tests/test_prompts_package.py` (17 tests covering
  registry parsing, budget enforcement, fingerprint stability,
  renderer output, builder end-to-end assembly, persona override,
  turn extras, and fingerprint persistence). Refactored
  `tests/test_query_engine_system_prompt.py` (4 async tests) and
  `tests/test_query_engine.py` (`TestPromptOwnership` now exercises
  the builder). Updated `tests/test_subagent.py` for the new
  `fork(prompt_variant=...)` signature. All 113 engine-adjacent tests
  pass.

### Changed — QueryEngine delegates system prompt to PromptBuilder — 2026-04-24

- `QueryEngine` no longer owns prompt assembly — `_build_system_prompt`
  and `_collect_skill_lines` / `_collect_skill_capability_hints` are
  deleted; replaced by a `_build_prompt` method that constructs a
  `PromptContext` and calls `PromptBuilder.build()`.
  `QueryEngineConfig` gains `prompt_variant`, `prompt_template_variant`,
  `prompt_builder`, `session_manager`, `working_scratchpad`, and
  `permission_context` fields.
- `AgentController._build_system_prompt` delegates to `PromptBuilder`
  instead of formatting the deleted `SYSTEM_PROMPT_TEMPLATE`.
  `_run_via_query_engine` no longer pre-builds the system prompt or
  injects the attachment manifest — the engine's prompt builder handles
  both (L6 Session State).
- `query._query_loop` no longer injects `<recalled_memory>` messages
  before the API call — recall is now rendered into the system prompt at
  L5 by the prompt builder. The `user_context` and `system_context`
  fields are removed from `QueryParams`.
- `code_agent.build_code_agent_engine` — `system_prompt` is now
  optional (defaults to the `code_agent` registry variant);
  `prompt_variant` parameter added.
- `subagent.fork_subagent` — `prompt_variant` parameter added (defaults
  to `"subagent"`); threaded to `QueryEngine.fork`.
- `memory/compact.py` — autocompact summariser prompt loaded from the
  `compact_summariser` template via `PromptRegistry`, with inline
  fallback for resilience.
- `rules/evaluator.py` — `LLMJudgeEvaluator` loads the judge system
  prompt from the `rule_judge` template via `PromptRegistry`, with
  inline fallback.
- `tasks/handlers/agent_handler.py` — `prompt_variant` parameter read
  from task params and forwarded to `QueryEngineConfig`.

### Removed — Inline system prompt template and recalled-memory message injection — 2026-04-24

- `SYSTEM_PROMPT_TEMPLATE` constant from `AgentController` — persona,
  tool listing, file-access policy, and context-info formatting are now
  owned by prompt layers L0–L4.
- `<recalled_memory>` injection logic from `query._query_loop` — owned
  by L5 in the prompt builder.
- `append_system_context` import from `query.py` — context folding is
  handled by the builder's L3 Environment layer.

### Added — Session management, cognitive memory redesign & file handling — 2026-04-24

- **`SessionManager` + `TieredSessionStore`** (`leagent/services/session/`)
  replace ad-hoc conversation persistence with a production-grade tiered
  store: LRU in-memory → Redis → PostgreSQL, with per-session
  `asyncio.Lock` for concurrency safety. `SessionState` carries
  messages, attachments, token usage, and system-prompt fingerprints.
  `AgentController._load_conversation` / `_save_conversation` now
  delegate entirely to the session manager.

- **Cognitive agent memory redesign** (`leagent/memory/`) — the legacy
  `MemoryManager`, `ShortTermMemory`, `BaseMemory`, and
  `MemorySystem` are deleted (no backward compatibility). Replaced by:
  - `AgentMemory` facade with a 4-method public API:
    `record_episode`, `upsert_fact`, `record_procedure`, `recall`.
  - Three cognitive stores: `EpisodicStore` (past-turn summaries),
    `SemanticStore` (extracted facts), `ProceduralStore` (tool
    outcomes with success rates).
  - `RetrievalPipeline` for hybrid search (semantic top-k + lexical
    fallback), recency-weighted reranking, `FileStateCache`-based
    deduplication, and duplicate collapsing.
  - `EmbeddingProvider` protocol with `LLMServiceEmbeddingProvider`
    and Redis-cached embeddings.
  - `MilvusCollection` wrapper for vector storage.
  - `WorkingScratchpad` (renamed from `WorkingMemory`) retaining only
    ephemeral `tool_history` and `scratchpad`, backed by Redis.
  - `RecallHandle` (renamed from `MemoryPrefetchHandle`) for
    async recall with cached results and failure resilience.
  - New ORM models: `AgentEpisode`, `AgentFact`, `AgentProcedure`
    in `services/database/models/agent_memory.py`.
  - Alembic migration drops `long_term_memories` +
    `task_history_memories` and creates the three new tables.

- **Session-aware file handling** — `File.session_id` is now a
  **non-nullable** FK. Upload endpoints (`/files/upload`,
  `/documents/upload`, chat file ingestion) require `session_id`.
  Upload directory consolidated to `settings.files.upload_dir` (reads
  from `leagent.config.constants.UPLOAD_DIR`); the sandbox
  `_DEFAULT_ROOTS` reads the same setting.

- **HMAC-signed attachment URLs** (`leagent/services/auth/signed_url.py`)
  — short-lived preview/download tokens so the frontend can embed
  `<img src="/api/v1/files/{id}/preview?token=...">` without
  shipping a JWT. New `GET /files/{id}/preview` and updated
  `GET /files/{id}/download` endpoints accept signed tokens.

- **Frontend `AttachmentCard`** component renders image thumbnails
  (via signed `previewUrl`) and generic file icons with download
  links. `ChatView` SSE handler processes new `attachments` event to
  hydrate user-message attachments with signed URLs in real time.
  `FilePreviewPanel` updated to use `URL_KEYS.FILE_DOWNLOAD`.

- **Local Redis provisioning** in `start.sh` — `start_redis()` shell
  function auto-launches a local Redis server with `--no-redis` /
  `--with-redis` CLI flags, persistent data directory, health checks,
  and graceful cleanup on exit. Integrated into backend, gateway,
  workflow, and micro launch paths.

- **New tests**: `test_session_manager.py` (6 tests),
  `test_agent_memory.py` (9 tests), `test_recall_pipeline.py` (6
  tests), `test_file_preview.py` (8 tests). Updated:
  `test_agent_hooks.py` (removed `MemoryCompactionHook`),
  `test_agent_planner.py` (aligned with `AgentMemory` recall API),
  `conftest.py` (`agent_memory` fixture). All 88 tests pass.

### Changed — SessionManager, AgentMemory, and chat attachment plumbing — 2026-04-24

- `AgentController` now accepts `session_manager` and `agent_memory`
  as constructor deps; `_build_system_prompt` prepends a session
  attachment manifest; `_store_to_memory` replaced by
  `_record_episode`.
- `QueryEngineConfig.memory` renamed to `agent_memory`;
  `MemoryPrefetchHandle` renamed to `RecallHandle` throughout.
- `TaskHistoryHook` calls `agent_memory.record_procedure` instead of
  the deleted `MemoryManager.record_task_completion`.
- `TaskPlanner._get_relevant_knowledge` uses `agent_memory.recall`.
- `ServiceManager.start_all` registers `SessionManager` and
  `AgentMemory`; the lazy `_get_memory_manager` helper in `chat.py`
  is deleted.
- `api/v1/chat.py` `_ingest_chat_files` replaced by
  `_attach_chat_files` (delegates to `SessionManager.attach_files`);
  SSE generator emits `attachments` event before the token stream.
- `settings.yaml` memory config section updated — `short_term_window`
  and `long_term_topk` replaced by `embedding_model` and cognitive
  store settings.

### Removed — Legacy memory stack and upload path constants — 2026-04-24

- Legacy memory modules: `memory/base.py`, `memory/short_term.py`,
  `memory/long_term.py`, `memory/manager.py`, `memory/working.py`
  (replaced by `working_scratchpad.py`), and the `MemorySystem` type
  alias.
- `MemoryCompactionHook` — functionality absorbed by
  `SessionManager` + `AgentMemory`.
- Hardcoded `/tmp/leagent/files` upload paths — replaced by
  `settings.files.upload_dir`.

### Fixed — SQLite `create_all` and test collection after memory hook removal — 2026-04-24

- Duplicate `ix_todos_due_at` index in `todo.py` (field had both
  `index=True` and an explicit `Index()` in `__table_args__`,
  crashing `create_all` on SQLite).
- Stale `MemoryCompactionHook` re-export in `agent/__init__.py`
  that broke test collection after the hook was removed.

### Added — Agent Skills v1.0 open specification — 2026-04-24

- **Full rewrite of the skills system** to conform to the
  [Agent Skills v1.0 specification](https://agentskills.my/specification).
  Skills are now `SKILL.md`-first directories with a strict
  frontmatter contract (`name` kebab-case matching the directory,
  `description` 1–1024 chars, optional `license`,
  `compatibility`, `metadata`, `allowed-tools`) plus three optional
  bundled subdirectories (`references/`, `assets/`, `scripts/`).
  Legacy `skill.yaml` / `skill.json` manifests are no longer
  loaded; run `leagent skills migrate --apply` to convert them
  in place (the original YAML is archived next to the generated
  `SKILL.md`).
- **Four-tier progressive disclosure** —
  1. `QueryEngine` advertises only `name: description` in the
     system prompt.
  2. New `load_skill` implementation lazy-reads the `SKILL.md`
     body with mtime-invalidated caching.
  3. New `read_skill_resource` tool returns bundled `references/`
     or `assets/` files (UTF-8 or base64, ≤1 MiB) after
     path-containment checks.
  4. New `run_skill_script` tool executes bundled `scripts/`
     entries via `asyncio.create_subprocess_exec` — argv-only, no
     shell, cwd = skill dir, bounded timeout. Opt-in behind
     `LEAGENT_SKILL_SCRIPTS_ENABLED` **and** a matching
     `allowed-tools` entry in the skill manifest.
- **Cross-agent discovery** (`leagent/skills/discovery.py`) —
  project roots (`.leagent/`, `.claude/`, `.cursor/`,
  `.codex/`, `.gemini/`, `.opencode/`, `.kiro/`, `.windsurf/`,
  `.github/`) and user roots (`$LEAGENT_HOME`, `~/.claude`,
  `~/.cursor`, `~/.codex`, `~/.gemini`, `~/.config/opencode`,
  `~/.kiro`, `~/.codeium/windsurf`, `~/.copilot`) are scanned
  alongside the bundled skill directory. A deterministic
  precedence order means a project-local skill shadows the
  user-scoped or bundled copy without any file shuffling.
- **Pluggable registry** (`leagent/skills/registry.py`) —
  `SkillRegistry` Protocol with two built-in implementations:
  `DisabledRegistry` (default; returns `501 Not configured`) and
  `HTTPSkillRegistry`. The HTTP registry supports `search`,
  `get`, `install` (downloads `.tar.gz`/`.zip`, verifies
  optional SHA-256, extracts safely with traversal checks,
  validates with the loader, performs an atomic filesystem swap
  with rollback) and `uninstall`. Configure via
  `LEAGENT_SKILLS_REGISTRY_URL` env var or the `skills.registry.url`
  key in `~/.leagent/config.yaml`.
- **New & updated tools in the curated bootstrap**
  (`leagent/bootstrap/tools.py`) — `SkillTool` refactored to
  remove the `skill.config["_prompt_content"]` back-channel;
  `SkillResourceTool` and `SkillScriptTool` registered alongside
  it so the LLM can discover them.
- **`QueryEngine` capability hints** — when any loaded skill
  declares resources or scripts, the system prompt now includes
  short pointers to `read_skill_resource` / `run_skill_script`
  so the model knows those tools are live.
- **HTTP API** (`/api/v1/skills`) —
  - `SkillDetail` response now surfaces `license`,
    `compatibility`, `metadata`, `allowed_tools`, `resources`,
    `scripts` (internal config keys are stripped).
  - New endpoints: `GET /{name}/body`, `GET /{name}/resources`,
    `GET /{name}/resources/{path}`, `GET /{name}/scripts`,
    `POST /{name}/scripts/{path}/run` (env-gated),
    `GET /hub/search`, `POST /hub/install/{name}`,
    `DELETE /{name}`.
- **CLI** (`leagent/cli/skills_cmd.py`) —
  - New subcommands: `leagent skills migrate [--apply]`,
    `leagent skills lint`, `leagent skills validate <path>`,
    `leagent skills init <name>`.
  - `install` accepts `--source <path-or-url>` for local / git
    installs; registry-based installs require a configured URL
    and fail loudly otherwise.
  - `list`, `show`, `enable`, `disable`, `uninstall`, `search`
    updated to the new models.
- **Bundled skills** (`leagent/skills/builtin/`) — the three
  shipped skills (`data-analyzer`, `document-processor`,
  `workflow-helper`) now use strict v1.0 frontmatter: `when_to_use`
  folded into `description`, `allowed-tools` space-delimited,
  `category` / `tags` / `version` / `author` moved under
  `metadata`.
- **Hot reload** — `SkillLoader.check_for_updates()` detects
  added, removed, and modified skills *and* reruns the bundled
  `references/`, `assets/`, `scripts/` scans on any file change
  inside those directories.
- **Safety model** — path traversal denied with
  `skill_resource_escape_attempt` / `skill_script_escape_attempt`
  structured warnings; extension allow-lists for resources
  (`.md .json .yaml .yml .csv .xml .txt`) and scripts
  (`.py .js .sh .ps1 .cs .csx`) are enforced at load time;
  install archives are member-by-member sandboxed before extraction.
- **Documentation** — new user guide at
  [`docs/guide/skills.md`](docs/guide/skills.md) covers authoring,
  discovery precedence, CLI, HTTP API, registry configuration,
  and the security model. Linked from the `mkdocs` nav under
  **User Guide → Skills**.
- **Tests** — `tests/test_skills.py` expanded from 23 → 53 cases:
  models (defaults, metadata round-trip, resources / scripts
  lookups, hub-entry parsing), loader validation (name regex,
  length, reserved words, directory match, description limit,
  no XML tags, compatibility length), resource/script
  discovery, lazy body read & cache invalidation, hot reload
  (new / modified / removed), manager precedence & any-skill-has
  helpers, progressive-disclosure tools (including path-escape
  rejection and env-flag gating), discovery root ordering,
  registry disabled behaviour + HTTP install rollback on bad
  checksum + mocked search, markdown parser kebab/snake
  normalization, CLI `migrate` dry-run / `--apply` and `validate`,
  and API `_detail_from_skill` config-stripping. All
  `tests/test_skills.py` and `tests/test_query_engine_system_prompt.py`
  cases pass offline (27 tests in the narrowed suite; 53 in
  total across `test_skills.py`).

### Removed — Legacy skill hub models and prompt back-channel — 2026-04-24

- Legacy skill models: `SkillTool`, `SkillPrompt`, `SkillMCPServer`
  (and their YAML/JSON parsing paths).
- The stubbed `DEFAULT_HUB_URL` pointing at
  `raw.githubusercontent.com/leagent/skills-registry` — replaced
  by the pluggable registry described above.
- `skill.config["_prompt_content"]` back-channel (skills now read
  their body lazily from disk via `Skill.read_body()`).

### Security — Tool filesystem sandbox & conversation persistence — 2026-04-24

- **Path sandbox for all file-touching tools** (`leagent/tools/_sandbox/paths.py`).
  Every tool that accepts a filesystem path now declares `path_params` /
  `output_path_params` class attributes on `BaseTool`. Before execution,
  `BaseTool.run()` validates each declared parameter through
  `PathSandbox.resolve_safe()`, which rejects any resolved path outside the
  configured allow-list. Default root: `/tmp/leagent/files` (the upload
  directory). Override via the `LEAGENT_TOOL_FILE_ROOTS` environment
  variable (comma-separated).
  - **Per-request attachment allow-list**: `ToolContext.extra["attachments"]`
    carries user-uploaded file paths, which are also permitted by the sandbox.
  - **Nested-path tools** (`archive_manager`, `data_merge`, `vector_search`,
    `template_filler`, `email_send`) override `_enforce_path_sandbox()` to
    validate paths embedded in array or object parameters.
  - Denial logging: every blocked path emits a structured WARN event
    (`path_sandbox_denied`) with `tool`, `request_id`, `attempted_path`,
    and `allowed_roots` — no file content is leaked.
  - Affected categories: **doc** (11 tools), **data** (7), **gen** (6),
    **util** (`file_manager`), **web** (`screenshot`, `browser_login`),
    **integration** (`email_send`).

- **Fixed `ShortTermMemory` missing `load_session` / `save_session`**
  (`leagent/memory/short_term.py`). `AgentController._load_conversation`
  and `_save_conversation` called these methods on every turn, but they
  did not exist on `ShortTermMemory`, causing silent `AttributeError`s
  logged as `conversation_load_failed` / `conversation_save_failed`. The
  agent lost context between turns and over-explored the filesystem.
  Both methods are now implemented with graceful no-Redis fallback (no-op
  instead of exception when Redis is unavailable).

- **Hardened agent system prompt** — `SYSTEM_PROMPT_TEMPLATE` in
  `leagent/agent/controller.py` now includes a "File access policy
  (strict)" block that instructs the LLM to only touch user-attached
  files and task outputs. `file_manager.description` and
  `text_processor.description` carry inline boundary reminders visible
  in the tool catalogue.

- **New tests**: `tests/test_path_sandbox.py` (21 tests covering
  `PathSandbox` unit tests, `FileManagerTool` sandbox enforcement, and
  `TextFileProcessorTool` sandbox enforcement), plus 4 new
  `ShortTermSessionPersistence` tests in   `tests/test_memory.py`.

### Added — QueryEngine, modular context/memory, DeepSeek integration — 2026-04-22
- **`QueryEngine` session orchestrator** (`leagent/agent/query_engine.py`)
  ported from the `QueryEngine.ts` reference design. Owns
  session-scoped state (`mutable_messages`, `FileStateCache`,
  `token_usage`, `cwd`, `session_id`) and exposes a streaming
  `submit_message()` async generator that yields typed `SDKMessage`s
  (`stream_delta` / `assistant` / `tool_use` / `tool_result` /
  `system` / `result`). Caller-owned `system_prompt` — no hardcoded
  prompts inside the engine or in `code_agent.py`.
- **Per-turn `query_loop()`** (`leagent/agent/query.py`) with an
  explicit pre-API pipeline (tool-result budgeting → microcompact →
  autocompact → memory prefetch drain), streaming, partitioned tool
  dispatch, and recovery/terminal transitions.
- **Structured transitions** (`leagent/agent/transitions.py`):
  `Terminal(reason=completed | max_turns | aborted | model_error |
  max_tool_calls)` and `Continue(reason=next_turn | recovered)`, plus
  `QueryState` / `AutoCompactTrackingState` in
  `leagent/agent/state.py`. Control flow is value-shaped, not
  exception-smuggled.
- **DI seam for LLM I/O** (`leagent/agent/deps.py`): `QueryDeps`
  Protocol abstracts `call_model` / `microcompact` / `autocompact`.
  `production_deps(llm_service, memory_manager)` wires the real
  services in; tests inject scripted stubs.
  `call_model` adapts `LLMService.chat_stream` into
  `ModelStreamEvent`s and coalesces OpenAI-compatible tool-call
  deltas per call id.
- **`ToolUseContext`** (`leagent/agent/tool_use_context.py`) — single
  handle carrying abort signal, registry/executor,
  `FileStateCache`, and `MemoryPrefetchHandle` through `query_loop` and
  into tools.
- **Modular context assembly** — `leagent/context/` split into
  single-purpose files: `system.py` (date / CWD / env / git),
  `user.py` (project `.leagent/*.md` memory files),
  `file_state_cache.py` (`FileStateCache` + `FileReadRecord`),
  `attachments.py` (`AttachmentMessage` + rendering/dedup), `api.py`
  (`append_system_context` / `prepend_user_context`). `system_context.py`
  is kept as a back-compat facade.
- **Memory prefetch + compaction** —
  `leagent/memory/prefetch.py::build_prefetch` starts a non-blocking
  long-term retrieval at turn start; `MemoryPrefetchHandle.results()`
  drains completed hits and dedups against `FileStateCache`.
  `leagent/memory/compact.py` exports
  `build_microcompact(memory_manager)` and
  `build_autocompact(llm_service, tier="tier2")`. New
  `MemoryManager.retrieve_attachments()` returns structured
  `AttachmentMessage`s instead of raw strings.
- **DeepSeek provider** (`leagent/llm/providers/deepseek.py`) —
  inherits `OpenAIProvider`, overrides `_parse_stream_chunk` to
  surface `reasoning_content` on `StreamChunk.raw_delta` without
  polluting the text channel. `llm/registry.py` auto-registers it
  whenever `DEEPSEEK_API_KEY` is set and aliases it as `tier1` /
  `tier2` if no tiered provider is configured. `LLMSettings` gains
  `deepseek_api_key` / `deepseek_model` / `deepseek_base_url` fields
  with `AliasChoices` for the `DEEPSEEK_*` env names;
  `deploy/.env.example` updated accordingly.
- **Excel-analysis demo + live integration test** —
  `backend/scripts/run_excel_demo.py` (hand-runnable CLI that
  streams tool_use / tool_result / assistant deltas with exit codes
  mapped to terminal reasons) and
  `backend/tests/integration/test_deepseek_excel.py` (gated behind
  `DEEPSEEK_API_KEY`, tagged `@pytest.mark.integration`, asserts
  `reason=="completed"` + ground-truth phrasing from the fixture
  manifest). Shared deterministic fixture at
  `backend/tests/fixtures/excel_analysis.py` idempotently generates
  `_cache/excel_sample.xlsx` (Sales / Products / Summary sheets).
  New guide: [`docs/guide/excel-analysis.md`](docs/guide/excel-analysis.md).
- **Offline test coverage**: `tests/test_query_engine.py` (13 tests —
  query loop, dispatch partitioning, prompt ownership),
  `tests/test_context_upgrade.py` (17 tests — `FileStateCache`,
  prompt assembly, attachments dedup, back-compat facade),
  `tests/test_memory_prefetch.py` (12 tests — prefetch handle +
  micro/autocompact with a fake memory manager),
  `tests/test_deepseek_provider.py` (10 tests — constructor
  defaults, stream parsing, registry wiring). All 52 tests run
  offline, <1s.

### Changed — AgentController compat shim over QueryEngine — 2026-04-22
- `leagent/agent/controller.py` is now a **compat shim** over
  `QueryEngine`. `AgentConfig.use_query_engine` (default `True`)
  routes `run` / `run_stream` through the engine and re-maps its
  `SDKMessage`s onto the legacy `StreamEvent` stream. Hooks, workflow
  matching, and abort semantics preserved.
- `leagent/api/v1/chat.py` — `/chat`, `/chat/stream`, and the
  WebSocket all drive a `QueryEngine` via
  `_build_agent_controller_with_memory()`, with a shared
  `MemoryManager` instance per app.
- `leagent/agent/code_agent.py` — removed hardcoded Excel-analysis
  prompt and default tool list. Now exposes
  `build_code_agent_engine(system_prompt=..., tools=..., ...)` as a
  prompt-agnostic builder that returns a preconfigured `QueryEngine`
  suitable for code-execution sub-agents and `CodeAgentNode`.

### Fixed — Streaming tool_calls round-trip and explicit tool registry wiring — 2026-04-22
- **`LLMService.chat_stream` dropped assistant `tool_calls`** during
  the `dict` → `ChatMessage` conversion, causing OpenAI-compatible
  providers (notably DeepSeek) to 400 on the follow-up
  `role=tool` message (`"Messages with role 'tool' must be a
  response to a preceding message with 'tool_calls'"`). The
  conversion now parses and preserves `tool_calls` the same way
  `chat()` already did.
- **`register_default_tools(registry=...)` silently fell back to the
  process-wide singleton** because `ToolRegistry.__len__` makes an
  empty registry falsy (`reg = registry or get_registry()`). Replaced
  the guard with an explicit
  `registry if registry is not None else get_registry()`. New
  registries now actually receive the discovered tools.

### Added — Accounts, RBAC, Workspaces, Notifications & Todos — 2026-04-22
- **Normalized RBAC** replaces the flat `User.role` enum with four new
  tables (`roles`, `permissions`, `role_permissions`, `user_roles`) and
  a canonical permission catalogue seeded by
  `scripts/seed_rbac.py`. Admins can create custom roles and edit the
  permission matrix from the new `/accounts/roles` UI; system roles
  (`admin`, `dept_head`, `staff`, `readonly`) are marked `is_system`
  and cannot be deleted.
- **`PermissionChecker` FastAPI dependency** in
  `leagent.services.auth.deps` enforces permissions consistently;
  superusers short-circuit. A CI audit script
  (`scripts/audit_router_auth.py`) fails the build if any `/api/v1/*`
  route forgets to declare an auth dep.
- **First-class Workspace entity** (`workspaces`,
  `workspace_members`, `users.default_workspace_id`). Every user gets a
  personal workspace on signup; legacy rows backfilled. JWTs carry
  `workspace_id` + `roles` + `permissions` claims; the gateway
  middleware binds `workspace_id` into `TenantContext` so
  `TenantScopedRepository` handles cross-workspace isolation for free.
- **Workspaces router** (`/api/v1/workspaces`) with list, switch,
  current, admin create + membership management.
- **Split admin API** — `/admin/users`, `/admin/roles`,
  `/admin/permissions` with DELETE / reset-password / status endpoints
  and role CRUD (guarded by `is_system`). Every RBAC mutation emits
  `rbac.changed` so the Redis principal cache invalidates.
- **`Accounts` sidebar section** (`frontend/src/pages/AccountsPage/`) —
  profile, workspaces, todos, users (admin), roles (admin), and
  assignments (admin) sub-panels. Route-level `PermissionRoute` +
  `usePermissions()` drive dynamic visibility.
- **Frontend workspace isolation** — Zustand `persist` keys are
  namespaced by `${userId}:${workspaceId}` via
  `lib/persistNamespace.ts`; React Query cache is cleared on
  `auth:logout` and workspace switch (manage workspaces under Accounts).
- **Notification center** — new `notifications` table,
  `NotificationService` with Redis Pub/Sub fan-out, REST router
  (list + unread count + read + read-all + delete) and WebSocket at
  `/api/v1/notifications/ws`. Frontend `NotificationBell` badge,
  `useNotifications` hook with auto-reconnect, `/notifications` history
  page, and new `notifications.json` bundle (both locales).
- **Todos** (`todos`, `todo_checklist_items`, `todo_comments`) distinct
  from the workflow `tasks` table. CRUD at `/api/v1/todos/*` with
  permission keys `todos:create / assign / update:own|any /
  delete:any`; admin bulk-assign + analytics at
  `/api/v1/admin/assignments/*`; hourly due-soon cron emitting
  notifications. Frontend kanban at `/accounts/todos`, admin view at
  `/accounts/assignments`, dashboard "due this week" widget.
- **Rollout flag** `AUTH_RBAC_V2_ENABLED` (default `True`). Legacy
  `User.role` column remains for one release as a deprecated read-path
  fallback; it will be removed once the flag is flipped in prod.

### Added — Scalable microservices platform — 2026-04-22
- **Shared core library `leagent_core/`** consumed by every runtime:
  `schema`, `proto`, `queue` (Redis Streams with consumer groups, DLQ,
  idempotency, exponential backoff), `events` (unified Pub/Sub + in-memory
  bus), `cache` (`RedisCache`, `CacheAside`, stampede lock),
  `ratelimit` (Lua token bucket), `circuit` (async circuit breaker),
  `telemetry` (OTel + structlog + `traceparent` helpers), `db`
  (async engine factory + `TenantScopedRepository`),
  `auth` (JWT, API key with Redis cache, `TenantContext`, `RoleChecker`),
  and `rpc` (gRPC server/client + auth/trace interceptors).
- **gRPC contracts** for every service under `backend/protos/*.proto`
  (`common`, `agent`, `workflow`, `llm`, `tool`) and a
  `python -m leagent_core.proto.build` generator.
- **Per-service entrypoints** under `leagent/apps/`:
  - `gateway/` — FastAPI app factory (`app.py`, `main.py`) with DDD
    layering (`domain/`, `application/ports.py`, `infrastructure/`,
    `interfaces/`), `RequestContextMiddleware` (request id, tenant,
    `traceparent`), Redis-backed rate-limit middleware, distributed
    WebSocket fan-out (`ws_fanout.py`), distributed task registry
    (`task_registry.py`).
  - `agent_runtime/` — `AgentRuntimeService` gRPC servicer (`Run`,
    `Stream`, `Cancel`) + standalone entrypoint.
  - `workflow_dispatcher/` and `workflow_worker/` — split from the
    monolith, Redis-Streams backed, no per-process state.
  - `llm_gateway/` — `LLMGatewayService` with prompt-hash cache,
    `QuotaEnforcer`, per-provider circuit breaker, streaming bridge.
  - `tool_worker/` — stateless tool/MCP gRPC pool.
- **Multi-tenancy**: optional `workspace_id` column on flows,
  flow_versions, files, folders, tasks, cron_jobs, cron_executions,
  workflow_executions, chat_sessions, messages, propagated via JWT
  claim + `TenantContext` contextvar and enforced by
  `TenantScopedRepository`. Alembic migration
  `b7c8d9e0f1a2_add_workspace_id_tenancy.py` adds the nullable,
  indexed columns.
- **Observability stack** at `backend/deploy/observability/`:
  OTel Collector, Prometheus, Tempo, Loki, Grafana provisioning
  (datasources + dashboards), with trace propagation across HTTP →
  gRPC → Redis Streams and structured JSON logs carrying `trace_id`,
  `request_id`, `user_id`, `tenant_id`, `service.name`.
- **Deployment artefacts**:
  - Single multi-stage `backend/deploy/services/Dockerfile` + dispatcher
    `entrypoint.sh` keyed on `LEAGENT_SERVICE`.
  - `backend/deploy/docker-compose.microservices.yml` for dev/staging
    with gateway×1, agent×1, wf-dispatcher×1, wf-worker×2,
    llm-gateway×1, tool-worker×2 and the full observability stack.
  - Helm chart under `backend/deploy/k8s/charts/leagent/` with
    per-service HPAs (CPU for gateway/agent/LLM/tool, Redis queue depth
    for workflow-worker), PodDisruptionBudgets, readiness/liveness/
    startup probes, and a pre-install Alembic Job.
  - `leagent/scripts/run_migrations.py` runs Alembic once, guarded by
    a Postgres advisory lock, so any replica can safely invoke it on
    startup.
- **Load-test harness** at `backend/tests/load/`:
  Locust profile (`locustfile.py`) for chat/flow/tool/upload mix,
  k6 scenarios (`k6_agent.js`, `k6_llm.js`), a CI gate script
  (`ci-perf.sh`) enforcing p95 ≤ 750 ms and error rate ≤ 1 % at
  50 RPS for 2 min, plus a monolith baseline at
  `baselines/monolith.json`.
- **Updated docs**: `backend/README.md` now documents the service
  topology, entrypoint table, and 6-step phased migration runbook;
  `leagent/AGENTS.md` repo map expanded to cover `apps/`,
  `leagent_core/`, and `deploy/` subtrees plus the topology invariants.

### Changed — Concurrency & performance — 2026-04-22
- **Redis-first defaults**: `queue_backend` switched from `memory` to
  `redis`; workflow `_prompt_to_execution` moved from an in-process dict
  to a Redis-backed `PromptExecutionMap` with TTL
  (`leagent/workflow/prompt_map.py`).
- **Unified event bus**: the previous parallel `ExecutionEventBus` and
  `get_event_bus` singletons now resolve through a single shared bus
  populated by `ServiceManager`.
- **Distributed state**: chat WebSocket registry uses Redis Pub/Sub for
  cross-replica fan-out; `TaskManager._running_tasks` backed by a
  `DistributedTaskRegistry` (Redis HASH + Pub/Sub) so any Gateway
  replica can push to any client or cancel any task.
- **Auth path hardening**: `services/auth/deps.py` now routes API-key
  auth through `leagent_core.auth.ApiKeyVerifier` (Redis cache +
  `api_keys.rate_limit` enforcement) and `RoleChecker` through a
  DB-backed, cache-fronted `RoleCheckerFactory`.
- **Rate limiting**: `RateLimitMiddleware` with Lua token-bucket
  applied per-IP, per-user, and per-API-key on the Gateway.

### Fixed — ToolRegistry default accessor cleanup — 2026-04-22
- `ToolRegistry.get_default` call site in `services/service_manager.py`
  is no longer referenced; `_get_tool_registry()` is used consistently.

### Added — Unified tool bootstrap & code execution — 2026-04-22
- **Unified tool bootstrap** (`leagent.bootstrap.tools`): single
  async entrypoint that handles tool discovery, curated-util registration,
  builtin workflow nodes, and the per-tool `Tool.<name>` factory. Used
  by the HTTP server, CLI, and workflow worker so every process gets the
  same palette.
- **Dual-tier code execution**:
  - `ScriptNode` — lightweight in-process RestrictedPython sandbox for
    small Python snippets inside workflows (no external dependencies
    beyond pure-Python `RestrictedPython`).
  - `code_execution` tool — professional out-of-process sandbox
    (`leagent.services.code_execution`) with per-session workspace,
    rlimit/SIGALRM resource caps, and JSON-envelope runner protocol.
  - `CodeExecutionAgent` + `CodeAgentTool` + `CodeAgentNode` — a
    restricted ReAct agent dedicated to compute-heavy turns, exposed
    both as a sub-tool to parent agents and as a workflow node.
- **Native workflow support for every tool** via
  `workflow/io/schema_bridge.py` (JSON Schema → typed IO inputs) and
  `workflow/nodes/tool_factory.py` (auto-generated `Tool.<name>` node
  subclass per registered tool).
- **Data processing primitives** in `leagent/tools/_data/`
  (`ArtifactRef`, `TabularSchema`, `emit_records`, `load_records`,
  spill-to-disk) with `sql_query`, `vector_search`, `data_clean`,
  `data_transform`, `data_merge`, `data_aggregate`, and `data_validate`
  refactored to use them uniformly.

### Changed — ToolExecutor consolidation and workflow agent shim — 2026-04-22
- Consolidated the two previous tool executors into a single
  `leagent.tools.executor.ToolExecutor` that natively accepts both
  `AgentContext` and `ToolContext` and carries the `ServiceManager`;
  removed the `AgentToolAdapter` shim.
- `WorkflowExecutor` now exposes the parent `AgentController` to nodes
  through `_ContextShim.agent_controller`, enabling `CodeAgentNode` to
  delegate turns back to a fresh code-execution agent.

### Deprecated — Legacy per-process utility tool registration — 2026-04-22
- `main._register_utility_tools` and the legacy copy in
  `cli/bootstrap.py` — replaced by `leagent.bootstrap.register_default_tools`.

## [1.0.0] - 2026-03-07

### Added

#### Core Platform
- Hybrid ReAct + Plan-and-Execute agent architecture
- Multi-provider LLM support (OpenAI, Anthropic, DashScope, Ollama, vLLM)
- Intelligent model routing with tier-based selection
- Three-tier memory system (short-term, working, long-term)

#### Tool System (46+ tools)
- **Document Tools**: PDF reader, Word reader, Excel reader, Image OCR (PaddleOCR), Invoice OCR, Table extractor, Document classifier
- **Web Tools**: Web scraper, Form filler, Click automation, Screenshot, Login handler (Playwright)
- **Data Tools**: Data cleaner, Data merger, Data validator, Data transformer, Data aggregator, Vector search, SQL query
- **Generation Tools**: Word generator, Excel generator, PDF generator, Report generator, Checklist generator, Template filler
- **Integration Tools**: OA API, OA import/export, Email sender, Notification sender, External API caller
- **Utility Tools**: File manager, Date calculator, Rule matcher, JSON parser, Text splitter, Cache manager

#### Workflow Engine
- Visual workflow builder with ReactFlow
- YAML workflow definitions
- Node types: start, end, tool_call, llm_call, condition, parallel, loop, human_review, sub_workflow, error_handler
- 18 pre-built workflow templates
- Workflow versioning and history

#### Rule Engine
- YAML-based declarative rules
- 8 rule types: compare, date_range, threshold, contains_all, date_diff, regex_match, cross_validate, llm_judge
- Hot-reload capability
- Rule evaluation API

#### Multi-Channel Communication
- Web interface (ChatGPT-like)
- DingTalk integration
- Feishu/Lark integration
- WeChat Work integration
- REST API channel
- Console channel

#### Frontend
- React 19 with TypeScript
- Vite 7 build system
- Tailwind CSS + shadcn/ui components
- ReactFlow for visual workflow builder
- Zustand state management
- TanStack React Query for API calls
- i18n support (Chinese + English)
- Dark/Light theme

#### Backend
- FastAPI with Python 3.12
- SQLModel + Alembic for database
- Redis for caching and queuing
- Milvus for vector storage
- MinIO for file storage
- JWT + API key authentication
- RBAC authorization

#### CLI
- `leagent app` - Run server
- `leagent init` - Initialize configuration
- `leagent models` - Manage LLM providers
- `leagent channels` - Configure channels
- `leagent skills` - Manage skills
- `leagent cron` - Manage scheduled jobs

#### Deployment
- Multi-stage Dockerfile
- Docker Compose for full stack
- GPU overlay for vLLM
- Nginx reverse proxy
- Supervisor process management

#### Observability
- Prometheus metrics
- Grafana dashboards
- Structured JSON logging
- Health check endpoints

### Security
- JWT with refresh tokens
- API key authentication
- Role-based access control (Admin, Dept Head, Staff, Readonly)
- AES-256 encryption for secrets
- Audit logging

## [0.9.0] - 2026-02-15 (Beta)

### Added
- Beta release for internal testing
- Core agent functionality
- Basic tool set (20 tools)
- Web chat interface
- Docker deployment

### Fixed
- Memory leak in long conversations
- Tool timeout handling
- WebSocket reconnection

## [0.8.0] - 2026-01-20 (Alpha)

### Added
- Alpha release for early adopters
- Agent core with ReAct loop
- Document processing tools
- Basic web interface

### Known Issues
- Limited LLM provider support
- No workflow builder
- Basic authentication only

---

## Migration Guides

### Upgrading from 1.0.x to 1.1.0

1. **Database migration** — `cd backend && alembic upgrade head` (new tables/columns for sessions, memory, workspaces, tasks, etc., depending on your starting revision).
2. **Frontend** — `cd frontend && npm ci && npm run build` (or your CI image rebuild); clear the browser app cache if you see stale bundles.
3. **Configuration** — review [`AGENTS.md`](AGENTS.md) for new env vars (Playwright install skips/mirrors, `WEB_FETCH_*`, `LEAGENT_CJK_FONT`, mail/SMTP, skills registry, knowledge directory). Extension packs may run `playwright install` on install.

### Upgrading from 0.9.x to 1.0.0

1. **Database Migration**
   ```bash
   cd backend
   alembic upgrade head
   ```

2. **Configuration Update**
   - Move `config.json` to `config/settings.yaml`
   - Update channel configurations to new format

3. **API Changes**
   - `/api/chat` → `/api/v1/chat`
   - Authentication now uses HttpOnly cookies

4. **Frontend**
   - Rebuild with `npm run build`
   - Clear browser cache

---

## Versioning

- **Major (X.0.0)**: Breaking API changes, major features
- **Minor (0.X.0)**: New features, backward compatible
- **Patch (0.0.X)**: Bug fixes, security patches

[Unreleased]: https://github.com/vixues/LeAgent/compare/v1.1.1...HEAD
[1.1.1]: https://github.com/vixues/LeAgent/releases/tag/v1.1.1
[1.1.0]: https://github.com/vixues/LeAgent/releases/tag/v1.1.0
[1.0.0]: https://github.com/your-org/leagent/releases/tag/v1.0.0
[0.9.0]: https://github.com/your-org/leagent/releases/tag/v0.9.0
[0.8.0]: https://github.com/your-org/leagent/releases/tag/v0.8.0
