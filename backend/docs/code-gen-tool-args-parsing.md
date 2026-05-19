# Tool-call argument parsing and large-payload tools

This note maps where LLM tool arguments are parsed, why JSON errors appear unrelated to generated code, and which tools embed large strings in the OpenAI-style `function.arguments` JSON string.

**Blob semantics:** in this codebase, `tool_argument_blob` is a **side channel to keep large UTF-8 out of prompt-adjacent JSON** (tool-call `function.arguments` and fragile string escaping)—not a generic binary object store.

## Parse entrypoints (authoritative order)

1. **Streaming assembly** — [`leagent/agent/deps.py`](../leagent/agent/deps.py) `_make_llm_call_model`: concatenates `chunk.tool_calls_delta[*].function.arguments` into one string per tool-call index. No parse until the stream completes.

2. **Final parse (QueryEngine path)** — Same module, end of `_call`: `parse_tool_arguments_str(args_str)`; on failure, arguments become `{"__raw__": args_str}` and `tool_call_parse_error` is logged (with `tool_name` when known).

3. **Legacy controller path** — [`leagent/agent/controller.py`](../leagent/agent/controller.py) `_extract_tool_calls`: same `parse_tool_arguments_str` / `__raw__` split.

4. **Executor recovery** — [`leagent/tools/executor.py`](../leagent/tools/executor.py) `normalize_tool_parameters`: if parameters contain `__raw__`, calls `_try_parse_raw_tool_args` (fences, trailing commas, control-char repair, tool-specific recovery). `ToolExecutor.execute` logs `tool_args_parse_failed` with `tool=` and optional JSON position metadata.

5. **Subprocess runner (code execution)** — [`leagent/services/code_execution/runner.py`](../leagent/services/code_execution/runner.py): after tool args are parsed, the execution engine may send a **framed stdin** payload (see `LEAGENT_RUNNER_V2` in runner) so Python `source` is not embedded as a giant JSON string value on that hop.

## Tools that commonly carry large string fields (high JSON-fragility)

| Tool | Large field(s) | Mitigation in codebase |
|------|----------------|-------------------------|
| `code_execution` | `source` | Executor `_recover_code_execution_args`; optional `source_blob_id` via [`tool_argument_blob`](../leagent/tools/util/tool_argument_blob.py) |
| `project_write` | `content` | Executor `_recover_project_write_args`; optional `content_blob_id` |
| `project_apply_patch` | `diff` | Executor `_recover_project_apply_patch_args`; optional `diff_blob_id` |
| `project_edit` | `old_string`, `new_string` | Prefer small hunks; optional `old_string_blob_id` / `new_string_blob_id` via [`tool_argument_blob`](../leagent/tools/util/tool_argument_blob.py); no malformed-string JSON recovery (high false-positive risk) |
| `emit_ui_tree` / `emit_ui_patch` | `tree`, patches | `_recover_emit_ui_tree_args`, truncation closer |
| `canvas_publish` | `html` (mode=html) | Executor `_recover_canvas_publish_args`; prefer **`html_files`** + `html_bundle_entry` for multi-asset pages, or `html_blob_id` / `html_files_blob_id` + `tool_argument_blob` for large single payloads |
| `tool_argument_blob` | `chunk` on `append` | HTML/JSX: use **`chunk_base64`** (base64 of UTF-8) so JSON never embeds raw `"` from markup; plain `chunk` still must be valid JSON |

## Side channel for large bodies

Session-scoped staging: [`leagent/tools/util/tool_argument_blob.py`](../leagent/tools/util/tool_argument_blob.py) — `tool_argument_blob` (`create` / `append` / `finalize` / `discard`). On **`append`**, pass payload as **`chunk_base64`** when the text is HTML, SVG, or JSX so the tool-call JSON stays a thin envelope (no quote-escaping of markup). Then pass **`source_blob_id`**, **`content_blob_id`**, **`diff_blob_id`**, **`old_string_blob_id`** / **`new_string_blob_id`**, **`html_blob_id`**, or **`html_files_blob_id`** into `code_execution`, `project_write`, `project_apply_patch`, `project_edit`, or `canvas_publish` so bulk UTF-8 is not inlined in tool-call JSON.

Optional durability: when **`FILES_TOOL_ARGUMENT_BLOB_PERSIST=true`**, finalized blobs are also written under `<FILES_UPLOAD_DIR>/tool-argument-blobs/<session>/` until consumed (see `FilesSettings.tool_argument_blob_persist`).

## Observability

- **Parse failures** — [`ToolExecutor.execute`](../leagent/tools/executor.py) logs `tool_args_parse_failed` with `args_len`, optional JSON line/column, `blob_id_hint_present` when the raw arguments string mentions blob fields (suggests switching fully to the side channel).
- **Verification gap** — [`_run_engine` result shaping](../leagent/agent/subagent.py) logs `coding_agent_verification_gap` when the coding sub-agent changed files but did not run `project_shell`.
- **Blob consumption** — successful blob reads log `tool_argument_blob_consumed` (see `resolve_blob_text`).

## Inbound tool results: artifact refs (design)

**Problem.** Outbound large payloads use `tool_argument_blob` + `*_blob_id` so the model never has to emit megabyte JSON strings. Inbound is different: `role=tool` messages still carry full strings (capped per tool via `max_result_size_chars`, paginated reads, then [`microcompact` / progressive transcript compress / `autocompact`](../leagent/agent/query.py) before the next model call). That is effective but **not symmetric** with the outbound side channel; very large reads or shell output can still dominate the transcript until compression runs.

**Goal.** Optional second channel: when a tool result exceeds a threshold, persist the payload server-side (session-scoped, TTL/prune similar to [`ToolArgumentBlobStore`](../leagent/tools/util/tool_argument_blob.py)), and put a **short JSON envelope** in the tool message the model sees, e.g. `{"_artifact": true, "artifact_id": "...", "tool": "project_read", "path": "...", "bytes": N, "preview": "first 2k chars...", "truncated": true}`.

**Consumption.** Either:

1. **Implicit expansion:** the LLM adapter or a thin wrapper before `call_model` resolves `artifact_id` back to full text for providers that need the full body (keeps protocol stable for the API client but still saves tokens if the resolver strips older artifacts), or  
2. **Explicit tool:** add something like `tool_result_read(artifact_id, offset?, limit?)` so the model **pulls** ranges on demand (closest to Cursor/Devin-style file buffers; requires prompt updates so the model knows to call it).

**Integration points.**

- **Write path:** after `ToolExecutor.execute` (or per-tool), if serialized `ToolResult` content length > threshold and tool is in an allow-list (`project_read`, `project_shell`, …), store UTF-8 (or structured JSON string) in a new `ToolResultArtifactStore` keyed by `(session_id, artifact_id)`, replace `content` with the envelope.  
- **Read path:** (2) above implements fetch in the executor; (1) above implements transparent hydration in [`deps._make_llm_call_model`](../leagent/agent/deps.py) or the message builder used by `query_loop`.  
- **Scratchpad / tool_history:** [`ToolHistorySource`](../leagent/context/sources/tool_history.py) logs `arguments` only; artifact refs mainly affect **tool message bodies**. Ensure compaction does not drop `artifact_id` without either hydrating or leaving a pointer.  
- **Subagents:** same store keyed by session; parent summarization ([`compress_tool_result`](../leagent/context/compression.py)) stays as-is unless the parent should receive `artifact_id` for drill-down (future).

**Operational parity with blobs.** Reuse patterns from `tool_argument_blob`: session key from `ToolContext`, max bytes per artifact, max artifacts per session, LRU prune, single-consumer `take` vs multi-read `peek` depending on whether compaction needs to re-read.

**Phased rollout.** Phase 1: envelope + `tool_result_read` + coding-agent prompt one-liner. Phase 2: tune thresholds per tool. Phase 3: optional transparent hydration for non-coding agents. Risks: models ignoring `tool_result_read`; double storage if both artifact and full message persisted in DB session logs—persist **either** full body or `artifact_id` in durable session store, not both, or GC artifacts when session rows are written.
