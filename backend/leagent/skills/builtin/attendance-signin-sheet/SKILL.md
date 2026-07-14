---
name: attendance-signin-sheet
description: >
  Generate printable attendance / 签到表 spreadsheets from name lists. Use when
  the user asks for 签到表, attendance sheet, meeting sign-in table, or similar
  printable roster tables (not full payroll attendance scoring unless asked).
license: Apache-2.0
allowed-tools: ask_user excel_generator excel_reader code_execution csv_processor
metadata:
  version: 1.0.0
  category: office
  tags: [attendance, signin, spreadsheet, 签到表, 考勤]
---

# Attendance / sign-in sheet

## Scope

- **In scope:** printable sign-in / 签到 sheet with people rows and signature columns.
- **Out of scope:** full attendance anomaly scoring, leave math, or payroll — decline
  or hand off unless the user explicitly expands scope.

## Before generating

If layout/business params are missing, call **`ask_user` alone** for 3–5 blockers:

1. Meeting / title text (and whether rows 1–3 are print title rows)
2. Name source (which attachment / column)
3. Sort order (e.g. by department, roster order)
4. Row height / grid / print centering (defaults: row height 22, show gridlines,
   landscape or portrait per user)
5. Extra columns (employee id, department, signature, date)

## Generate

- Prefer `excel_generator` with real data rows (never header-only).
- If scripting is required, use `code_execution`, then cite the **managed**
  `file_id` / `download_url` from the tool result (never a sandbox path).
- If `quality_passed` is false, fill data and regenerate until the download has
  content rows.

## After user corrections

Fold corrected rules (row height, title rows, sort map) back into this skill /
procedure memory for the next run — do not only fix the one-off file.
