---
name: procurement-audit
description: >
  Review procurement contracts and purchase packages against uploaded compliance
  rules (招标/采购制度). Use for 采购审核, contract compliance checklists, or
  procurement statistics rollups.
license: Apache-2.0
allowed-tools: ask_user pdf_reader excel_reader document_parser code_execution excel_generator
metadata:
  version: 1.0.0
  category: office
  tags: [procurement, audit, 采购, 合同, compliance]
---

# Procurement audit

## Scope

Map each claim/contract clause to an explicit rule in the uploaded policy pack.
Do not invent institutional thresholds.

## Before starting

Call **`ask_user` alone** when needed for:

- Which rule documents apply
- Audit depth (full checklist vs spot-check)
- Whether to produce a summary stats sheet plus a findings sheet

## Multi-file join

When ≥2 attachments are present (catalog, contract, bid sheet):

1. List each file’s role and key columns
2. Align join keys before filling any template
3. Flag unmatched rows explicitly

## Output

- Findings table with rule citation + evidence snippet
- Optional stats rollup Excel
- Always return managed `file_id` / `download_url`

When the user adds a missed rule (e.g. lodging-equivalent procurement caps),
update this skill / procedure for subsequent runs.
