---
name: policies/blob_staging
variant: default
description: When and how to use tool_argument_blob for large payloads — JSON safety and chunked staging as a fallback.
requires_tools:
  - tool_argument_blob
---

## Large argument staging (`tool_argument_blob`)

### Default: inline content directly

For most content — especially HTML pages, Python scripts, diffs, code files — **inline
the content directly** in the tool call (`html`, `content`, `source`, `diff`).
The runtime auto-recovers malformed JSON when double quotes or newlines break
the outer JSON envelope. This is faster than blob staging because it takes
**one tool call** instead of three or more.

For webpages, the default is always:

`canvas_publish(mode=html, html="<!DOCTYPE html>...")`

Do not generate HTML through Python or stage it with `tool_argument_blob` as the first attempt.

### When to fall back to blob staging

Use `tool_argument_blob` only when:

- A **prior direct call failed** and the runtime could not recover it.
- The content exceeds **~64K characters** (output token limit risk).
- You need to stage **binary data** (base64-encoded files).

### Staging flow (fallback only)

**Prefer one blob tool call** when the full body fits in a single append (under
~64K UTF-8 characters):

1. `tool_argument_blob(action=create_and_finalize, chunk=…)` — or
   `chunk_base64` only when plain `chunk` would break JSON (many unescaped `"`).
2. Pass the returned `blob_id` via the matching `*_blob_id` parameter, then call
   the consumer tool (e.g. `canvas_publish(html_blob_id=…)`).

**Multi-step staging** (`create` → `append` → `finalize`) is only when a prior
output was **truncated mid-payload** or the body exceeds one append limit. Use
the largest practical append per turn (up to ~64K decoded chars), not many tiny
chunks. Use `chunk_base64` for HTML / SVG / JSX only when needed for JSON safety.

`*_blob_id` targets: `content_blob_id` (project_write), `source_blob_id`
(code_execution), `html_blob_id` (canvas_publish), `diff_blob_id`
(project_apply_patch), `old_string_blob_id` / `new_string_blob_id` (project_edit).

### JSON argument safety

- Escape double quotes as `\"` and line breaks as `\n` inside string values.
- If a tool returns `Malformed tool arguments JSON`, the runtime usually
  auto-recovers. Only switch to blob staging if a second attempt also fails.
