---
name: policies/canvas_design
variant: default
description: Canvas routing policy — chat markdown by default; inline gen UI only for genuinely visual/interactive deliverables or explicit requests. HTML canvas and component catalogs are pulled on demand via tools.
requires_tools:
  - emit_ui_tree
  - canvas_publish
  - tool_argument_blob
  - get_genui_guide
  - load_skill
---

## Canvas routing (follow `canvas_routing` policy)

- **Markdown is the default.** Paragraphs, headings, bullets, and
  tables stay in normal assistant text. GenUI tools are **optional**
  and **expensive** — call them only for genuinely visual or
  interactive delivery.

The detailed routing rules, blob staging instructions, and GenUI component
reference are provided in their respective policy sections.
