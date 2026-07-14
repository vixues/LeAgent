# Structured output elicitation

When the user asks you to **generate or fill structured artifacts** (spreadsheet,
签到表/attendance form, audit report, Word/PDF report, multi-file join into a
template) and the request is underspecified, **do not invent silent defaults for
blocking layout or business rules**.

## When this applies

Trigger on requests like: generate 签到表 / Excel / 报表, audit 差旅 / 采购 /
报销, fill a template from attachments, or produce a printable table.

Skip elicitation when the user already supplied a complete parameter set, a
skill/procedure with rules, or an explicit “just do it / 按常见标准”.

## Blocking parameters (ask 3–5, not more)

Call **`ask_user` alone** (no other tools in the same turn) with a short
questionnaire covering the unknowns, for example:

| Domain | Blocking params |
|--------|-----------------|
| Spreadsheet / 签到表 | title rows, sort/order, which columns, row height / print settings, data source among attachments |
| Audit report | which rule handbook applies, fee caps / special exceptions, output format |
| Multi-file fill | join keys per file, how to treat missing fields, which sheet is the master |

Follow the `human_gate` policy: one `ask_user` call, `"ui_variant": "questionnaire"`
or clear prompts with choices when useful.

## After clarification

1. Align schemas across ≥2 attachments (list columns/keys per file) **before**
   writing outputs.
2. Prefer dedicated tools (`excel_generator`, readers) when they fit; use
   `code_execution` only when logic needs a script.
3. Always cite **managed `file_id` / `download_url`** from tool results — never
   sandbox paths. If `quality_passed` is false, regenerate until content is real
   (not header-only).
4. When the user corrects a rule, update the relevant Skill / procedure rather
   than only patching once.
