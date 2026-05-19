"""PDF Reader Tool - Extract text and metadata from PDF files.

Uses PyMuPDF (fitz) for efficient PDF processing with page-by-page extraction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext, ValidationResult

logger = structlog.get_logger(__name__)


class PDFReaderTool(SyncTool):
    """Extract text and metadata from PDF documents.

    Features:
    - Page-by-page text extraction
    - Document metadata extraction (title, author, creation date, etc.)
    - Page range selection for partial extraction
    - OCR fallback detection for image-based PDFs
    """

    name = "pdf_reader"
    description = (
        "Extract text content and metadata from PDF files. "
        "Supports page-by-page extraction with optional page range selection."
    )
    category = ToolCategory.DOC
    version = "1.0.0"
    timeout_sec = 120
    aliases = ["pdf", "read_pdf", "pdf_extract"]
    search_hint = "PDF read extract text metadata pages document"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    path_params = ("file_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the PDF file to read.",
                },
                "start_page": {
                    "type": "integer",
                    "description": "Starting page number (1-indexed). Defaults to 1.",
                    "minimum": 1,
                },
                "end_page": {
                    "type": "integer",
                    "description": "Ending page number (1-indexed, inclusive). Defaults to last page.",
                    "minimum": 1,
                },
                "extract_metadata": {
                    "type": "boolean",
                    "description": "Whether to extract document metadata. Defaults to True.",
                    "default": True,
                },
                "include_page_numbers": {
                    "type": "boolean",
                    "description": "Whether to include page numbers in output. Defaults to True.",
                    "default": True,
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
        }

    async def validate_input(self, params: dict[str, Any], context: ToolContext) -> ValidationResult:
        from pathlib import Path
        fp = params.get("file_path", "")
        if fp and not Path(fp).exists():
            return ValidationResult(valid=False, message=f"PDF file not found: {fp}")
        if fp and not fp.lower().endswith(".pdf"):
            return ValidationResult(valid=False, message=f"Not a PDF file: {fp}")
        return ValidationResult(valid=True)

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Reading PDF document"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Extract text and metadata from a PDF file.

        Args:
            params: Tool parameters including file_path and optional page range.
            context: Execution context.

        Returns:
            Dictionary containing extracted text, metadata, and page information.

        Raises:
            FileNotFoundError: If the PDF file doesn't exist.
            ValueError: If the file is not a valid PDF.
            RuntimeError: If PyMuPDF encounters an error.
        """
        try:
            import fitz  # PyMuPDF
        except ImportError as e:
            raise RuntimeError(
                "PyMuPDF is not installed. Install with: pip install pymupdf"
            ) from e

        file_path = Path(params["file_path"])
        start_page = params.get("start_page", 1)
        end_page = params.get("end_page")
        extract_metadata = params.get("extract_metadata", True)
        include_page_numbers = params.get("include_page_numbers", True)

        if not file_path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        if not file_path.suffix.lower() == ".pdf":
            raise ValueError(f"File is not a PDF: {file_path}")

        logger.info("Opening PDF file", file_path=str(file_path))

        try:
            doc = fitz.open(str(file_path))
        except Exception as e:
            raise RuntimeError(f"Failed to open PDF: {e}") from e

        try:
            total_pages = len(doc)
            if end_page is None:
                end_page = total_pages

            if start_page > total_pages:
                raise ValueError(
                    f"Start page {start_page} exceeds total pages {total_pages}"
                )
            if end_page > total_pages:
                end_page = total_pages
            if start_page > end_page:
                raise ValueError(
                    f"Start page {start_page} cannot be greater than end page {end_page}"
                )

            pages_content: list[dict[str, Any]] = []
            full_text_parts: list[str] = []
            total_chars = 0
            empty_pages = 0

            for page_num in range(start_page - 1, end_page):
                page = doc[page_num]
                text = page.get_text("text").strip()

                if not text:
                    empty_pages += 1

                page_data: dict[str, Any] = {
                    "text": text,
                    "char_count": len(text),
                }

                if include_page_numbers:
                    page_data["page_number"] = page_num + 1

                pages_content.append(page_data)
                full_text_parts.append(text)
                total_chars += len(text)

            full_text = "\n\n".join(full_text_parts)

            result: dict[str, Any] = {
                "text": full_text,
                "pages": pages_content,
                "total_pages": total_pages,
                "extracted_pages": end_page - start_page + 1,
                "total_characters": total_chars,
            }

            if empty_pages > 0:
                result["warning"] = (
                    f"{empty_pages} page(s) contain no extractable text. "
                    "The PDF may contain scanned images requiring OCR."
                )

            if extract_metadata:
                metadata = doc.metadata
                result["metadata"] = {
                    "title": metadata.get("title", ""),
                    "author": metadata.get("author", ""),
                    "subject": metadata.get("subject", ""),
                    "keywords": metadata.get("keywords", ""),
                    "creator": metadata.get("creator", ""),
                    "producer": metadata.get("producer", ""),
                    "creation_date": metadata.get("creationDate", ""),
                    "modification_date": metadata.get("modDate", ""),
                    "encrypted": doc.is_encrypted,
                }

            logger.info(
                "PDF extraction complete",
                file_path=str(file_path),
                pages_extracted=result["extracted_pages"],
                total_chars=total_chars,
            )

            return result

        finally:
            doc.close()
