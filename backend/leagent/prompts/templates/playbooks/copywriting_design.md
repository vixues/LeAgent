---
name: playbooks/copywriting_design
variant: default
description: Copywriting and design playbook — marketing copy and text polish.
requires_tools:
  - markdown_processor
  - text_processor
---

## Copywriting & Design playbook

Use this playbook when drafting marketing copy, landing-page text, campaign
briefs, or polishing prose before export.

### Tool routing

| Deliverable | Tool | Notes |
|-------------|------|-------|
| Structured copy (headlines, sections) | **`markdown_processor`** | create, template (article, report), build_list |
| Plain-text polish (.txt, logs) | **`text_processor`** | transform, replace, stats, write |
| Visual layout / posters | **`emit_ui_tree`** / **`canvas_publish`** | Follow `canvas_design` — only when genuinely visual |

### Workflow

1. **Draft** — Use `markdown_processor` with `operation="create"` or
   `operation="template", template_name="article", file_path="…"` plus
   clear headline, body, and CTA sections.
2. **Refine** — Use `text_processor` for regex replace, case transforms, or
   `stats` to check length; re-read after writes before further edits.
3. **Design** — Keep copy in markdown by default. Reach for GenUI/canvas only
   when the user asks for a poster, slide frame, or visual mockup.

### Voice and style

- Match the user's language (zh-CN / en-US) and requested tone (formal,
  playful, technical).
- Lead with the headline or hook; keep body scannable (short paragraphs,
  bullets where appropriate).

### Do not

- Do not use `code_execution` to write marketing markdown or plain text.
- Do not call `emit_ui_tree` for copy that fits comfortably in chat markdown.
