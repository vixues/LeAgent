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
- **Frontend / webpage files are not Python string literals.** Project files
  go through `project_write`; hosted pages through `canvas_publish` / blob
  staging. `code_execution` is for computation and data — not markup assembly.
- **Markdown documents → `markdown_processor` (ALWAYS).** When the
  deliverable is a `.md` file (story, report, notes, article, meeting
  minutes, README, changelog, or any saved markdown), use
  **`markdown_processor`** directly — *never* `code_execution`.
  Key operations:
  - `write` — requires `file_path` + `content`.
  - `create` — requires `file_path`; optional `title`, `sections`, `metadata`.
  - `template` — requires `file_path`, `template_name` (`story`, `report`, `notes`,
    `article`, `meeting`, `readme`, `changelog`).
  - `append` / `prepend` — add content to an existing file.
  - `insert_section` / `replace_section` / `delete_section` — surgical
    editing by heading name.
  - `build_table` — construct markdown tables from headers + rows.
  - `build_list` — construct nested ordered/unordered lists.
  - `merge` — combine multiple markdown files.
  - `format` — prettify/normalize markdown.
  - `generate_toc` — produce a linked table of contents.
- **Plain-text documents → `text_processor` (ALWAYS).** When the
  deliverable is a `.txt` or any plain-text file, use
  **`text_processor`** directly — *never* `code_execution`.
  Key operations:
  - `write` — save text content directly.
  - `append` / `prepend` — add content to existing files.
  - `replace` — regex find-and-replace (single or all occurrences,
    supports backreferences).
  - `insert` — insert text at a specific line number.
  - `transform` — uppercase, lowercase, title_case, wrap, indent,
    dedent, sort_lines, unique_lines, number_lines, remove_blank_lines,
    tabs_to_spaces, etc.
  - `extract` — pull content by line range, regex pattern, or markers.
  - `split` — break a file into parts by delimiter or line count.
  - `join` — concatenate multiple files.
- **PDF operations → `pdf_reader` (ALWAYS).** For any PDF task, use
  **`pdf_reader`** directly — *never* `code_execution` with PyMuPDF.
  Key operations:
  - `read` — extract text (full or by page range/specific pages).
  - `extract_tables` — detect and pull tabular data.
  - `extract_images` — save embedded images to disk.
  - `extract_links` — get all hyperlinks and annotations.
  - `search` — find text across pages with context.
  - `outline` — extract bookmarks/table of contents.
  - `convert_to_images` — render pages as PNG/JPEG.
  - `split` / `merge` / `extract_pages` — PDF manipulation.
  - `metadata` / `page_info` — document properties and dimensions.
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
  text may include CJK glyphs. After `code_execution` returns
  `managed_artifacts` / `images`, show plots via
  `![caption](/api/v1/files/{id}/preview)` in markdown or an
  `emit_ui_tree` **`Image`** node — do **not** print or paste base64
  image data in stdout or the final answer.
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
