---
name: travel-expense-audit
description: >
  Audit travel / 差旅报销 claims against uploaded policy handbooks and rate
  tables (lodging caps, transport, per diem). Use for 差旅费审核, travel expense
  review, or lodging over-limit checks.
license: Apache-2.0
allowed-tools: ask_user pdf_reader excel_reader document_parser code_execution excel_generator
metadata:
  version: 1.0.0
  category: office
  tags: [travel, audit, 差旅, 报销, expense]
---

# Travel expense audit

## Required inputs

1. Claim packet (forms, invoices, itinerary)
2. Policy / finance handbook (PDF/DOCX) — ask the user to upload if missing
3. Rate tables when lodging/transport caps are not in the handbook

## Before auditing

Use **`ask_user` alone** if any of these are unclear:

- Which handbook version applies
- Whether lodging / meal / transport caps must all be checked
- Output format (marked PDF notes vs Excel findings table)

## Workflow

1. Extract rule clauses that apply (especially **住宿费超标**).
2. Normalize claim line items (date, city, amount, category).
3. Check each line against caps; list pass/fail with cited rule text.
4. Emit a structured findings table; cite managed download URLs.

## Learning

When the user points out a missed rule, add it to the skill notes / procedure
so the next audit of the same org includes that check by default.
