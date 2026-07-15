---
name: policies/blob_staging
variant: default
description: When and how to use tool_argument_blob for large payloads — JSON safety and chunked staging as a fallback.
requires_tools:
  - tool_argument_blob
---

## Large argument staging (`tool_argument_blob`)

### Default for compact content: inline

For small payloads (scripts, diffs, compact HTML ≲ ~20KB tool-call JSON — a soft
inline budget under default output tokens, **not** the canvas store cap) **inline**
the content in the tool call (`html`, `content`, `source`, `diff`). The runtime
auto-recovers malformed JSON when double quotes or newlines break the outer
envelope. Canvas HTML can be much larger on disk/blob (up to max_html_bytes).

### Large HTML / multi-file pages (preferred ladder)

When the page (or `html_files` map) would exceed ~20KB **in one tool-call JSON**
**do not** inline bodies into `canvas_publish`:

1. **No Active Project:** `tool_argument_blob(create_and_finalize)` →
   `html_blob_id` / `html_files_blob_id` (`tool_argument_blob` is a registered tool).
2. **Active Project:** `project_write` → `canvas_publish(html_paths=[…])`
   (`html_bundle_entry` optional when `index.html` or a sole `*.html` exists).
3. **Last resort:** inline `html` / `html_files` only if TOTAL tool-call JSON ≲ ~20KB.

### Staging flow

**Prefer one blob tool call** when the full body fits in a single append (under
~1 MB UTF-8 characters):

1. `tool_argument_blob(action=create_and_finalize, chunk=…)` — plain `chunk`
   is preferred; use `chunk_base64` only when quotes would break JSON.
2. Pass the returned `blob_id` via the matching `*_blob_id` parameter, then call
   the consumer tool.

**Multi-step staging** (`create` → `append` → `finalize`) is only when a prior
output was **truncated mid-payload** or the body exceeds one append limit. Use
the largest practical append per turn (up to ~1 MB decoded chars), not many tiny
chunks. Avoid `chunk_base64` unless plain `chunk` breaks JSON.

`*_blob_id` targets: `content_blob_id` (project_write), `source_blob_id`
(code_execution), `html_blob_id` / `html_files_blob_id` (canvas_publish),
`diff_blob_id` (project_apply_patch), `old_string_blob_id` / `new_string_blob_id`
(project_edit).

### JSON argument safety

- Escape double quotes as `\"` and line breaks as `\n` inside string values.
- If a tool returns `Malformed tool arguments JSON`, the runtime usually
  auto-recovers. Only switch to blob staging if a second attempt also fails.
