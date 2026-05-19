---
name: document-processor
description: Guidance for processing documents, extracting content, and transforming structured information. Use when the user asks to process, parse, extract, or transform document content such as PDFs, Word files, or spreadsheets.
license: Apache-2.0
allowed-tools: document_parser pdf_extractor docx_extractor excel_extractor table_extractor
metadata:
  version: 1.0.0
  category: document
  tags: [document, processing, parsing, extraction, conversion]
---

# Document Processing

You are assisting with document processing tasks. Follow these guidelines.

## Document Analysis Workflow

1. **Identify** the document type: PDF, DOCX, XLSX, TXT, Markdown, HTML.
2. **Assess** document structure: headers, sections, tables, images, metadata.
3. **Extract** relevant content based on the user's request.
4. **Transform** extracted content to the requested format.
5. **Validate** accuracy, structure, and completeness.

## Common Operations

### Text Extraction

- Preserve document structure (headers, paragraphs, lists).
- Keep formatting where semantically meaningful (bold terms, emphasis).
- Extract metadata (author, creation date, document properties) when relevant.

### Table Extraction

- Identify table boundaries and column headers.
- Preserve row/column relationships when exporting to CSV or JSON.
- Handle merged cells, nested tables, and multi-page tables carefully.

### Information Extraction

- Extract specific fields (names, dates, amounts, addresses) with high precision.
- Use structured output (JSON, YAML) when returning multiple fields.
- Report confidence when extraction is ambiguous.

### Format Conversion

- PDF ↔ Text/Markdown
- DOCX ↔ Markdown/HTML
- XLSX ↔ CSV/JSON
- HTML ↔ Markdown

## Quality Guidelines

- Verify that extracted content matches the source.
- Preserve line breaks and paragraph structure unless asked to flatten.
- Flag OCR artifacts or illegible sections explicitly.
- For multi-page documents, maintain page references where useful.

## Error Handling

- Document any parts that could not be processed (e.g., encrypted pages, images).
- Provide clear error messages for unsupported formats.
- Suggest alternative approaches when the primary method fails.
