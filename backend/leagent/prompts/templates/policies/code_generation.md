---
name: policies/code_generation
variant: default
description: Rules for code generation in the sandbox (and the project/sandbox boundary).
requires_tools:
  - code_execution
---

Code generation policy:

- **Project work uses `project_*`.** Files under the adopted project
  root are the source of truth: read with `project_read` before
  editing, then prefer minimal edits (`project_edit`, then
  `project_apply_patch`) over wholesale regeneration so prior work
  can be reused across turns. Reach for `project_write` only when
  creating a new file or doing an intentional whole-file rewrite.
- **Frontend files are not Python string literals.** Never generate
  HTML, CSS, or JavaScript by writing them as Python strings inside
  `code_execution` (e.g. `html = "<html>..." ; open("index.html","w").write(html)`).
  Frontend content must be written directly with `project_write`
  using the appropriate technology. The `code_execution` sandbox is
  for computation, data processing, and visualisation — not for
  producing markup via Python string concatenation.
- **Large tool arguments go through `tool_argument_blob`.** Never
  inline multi-kilobyte strings in tool-call JSON. Stage with
  `create` → multiple `append` calls → `finalize` and pass the
  matching `*_blob_id` to `project_write` (`content_blob_id`),
  `project_apply_patch` (`diff_blob_id`), `project_edit`
  (`old_string_blob_id` / `new_string_blob_id`), `code_execution`
  (`source_blob_id`), or `canvas_publish`
  (`html_blob_id` / `html_files_blob_id`). On `append`, use
  **`chunk_base64`** for HTML / SVG / JSX so the JSON never has to
  escape quotes inside the payload. Use `create_and_finalize` **only**
  for payloads under ~2 000 characters — anything larger will exceed
  the output token limit and be truncated.
- **Standalone scripts** (not project edits) put the complete source
  in one `code_execution` call — or stage with `source_blob_id` when
  the program is long.
- **Imports.** Standard library and any installed third-party packages
  are available. Handle missing optional libraries with an
  `ImportError` fallback when appropriate; call `uv_pip_install` when
  the dependency must actually be installed.
- **Visualisation.** Use a headless backend, save figures to files
  (`dpi=150` minimum, `bbox_inches="tight"`), and follow
  **`document_fonts`** for pan-Unicode font registration whenever
  text may include CJK glyphs.
- **Data processing.** Print summary statistics, row counts, column
  names, shapes, and warnings before heavy transforms so errors can
  be diagnosed from stdout. Save large outputs as files
  (`.csv`, `.json`, `.parquet`, `.xlsx`) — do not stream them through
  stdout.
- **Timeouts.** `timeout_sec=30` for simple scripts, `60`–`120` for
  data processing or visualisation, `120`–`300` only for explicitly
  requested long-running computation.
- **Mixed-script documents** (PDF / DOCX / PPTX / Excel via standalone
  scripts) must follow **`document_fonts`** — register a pan-Unicode
  font (Noto Sans SC/CJK, Source Han Sans, WenQuanYi Micro Hei,
  Microsoft YaHei) rather than relying on Latin-stripped fallback
  fonts.
