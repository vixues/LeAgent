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
- **Frontend files and webpages are not Python string literals.** Never generate
  HTML, CSS, or JavaScript by writing them as Python strings inside
  `code_execution` (e.g. `html = "<html>..." ; open("index.html","w").write(html)`).
  Project frontend files must be written directly with `project_write`;
  standalone webpages must be published directly with
  `canvas_publish(mode=html, html="...")`. The `code_execution` sandbox is
  for computation, data processing, and visualisation — not for producing
  markup via Python string concatenation.
- **Markdown and plain-text documents are not scratch scripts.** When the
  deliverable is a saved `.md` / `.txt` document or generated report, prefer
  the document tools (`report_generator`, `template_filler`,
  `checklist_generator`, `text_processor`, `markdown_processor`) or
  `project_write` for a project file. Do not use `code_execution` just to
  assemble a Markdown/text string and write it with `open(...).write(...)`.
- **Inline content is preferred.** Pass `content` / `source` /
  `old_string` / `new_string` directly in the tool call — the runtime
  resolves content transparently (inline text or `*_blob_id`). Use
  **`tool_argument_blob`** (`create` → `append` → `finalize` →
  `*_blob_id`) only as a **fallback** when a direct call fails and
  runtime recovery cannot salvage it, or for payloads beyond the model
  output window. On `append`, use **`chunk_base64`** for markup so
  JSON never carries raw quotes from the payload.
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
