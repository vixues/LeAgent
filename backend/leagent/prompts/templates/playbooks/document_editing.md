---
name: playbooks/document_editing
variant: default
description: Document editing playbook — PDF intake and markdown authoring.
requires_tools:
  - pdf_reader
  - markdown_processor
---

## Document Editing playbook

Use this playbook when the user is editing, restructuring, or exporting documents
(PDFs, reports, briefs, meeting notes).

### Tool routing

| Task | Tool | Notes |
|------|------|-------|
| Read or extract from PDF | **`pdf_reader`** | Text, tables, metadata, outline — never PyMuPDF via `code_execution` |
| Author or edit markdown | **`markdown_processor`** | create, template, insert/replace section, build_table |
| Plain `.txt` edits | **`text_processor`** | Only when the deliverable is not markdown |

### Workflow

1. **Intake** — Use `pdf_reader` (metadata, outline, or `operation="read"`) on the
   user's attached PDF or an explicit `file_path`.
2. **Draft** — Scaffold the edited document with `markdown_processor`
   (`create`, `template`, or section surgery). Keep section headings stable
   so follow-up edits can target them.
3. **Deliver** — Summarise changes in chat; save/export only when the user
   asks. Point to attachment chips for generated files.

### Do not

- Do not use `code_execution` to read PDFs or assemble markdown files.
- Do not overwrite source PDFs; write edited content to new markdown paths.
