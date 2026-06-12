"""PDF Processor Tool — professional PDF reading, extraction, search, and manipulation.

Full-featured PDF toolkit:
- Read: extract full text with page-by-page granularity
- Extract tables: detect and extract tabular data from pages
- Extract images: save embedded images to files
- Extract links: hyperlinks and annotations
- Search: find text across pages with context
- Page info: dimensions, rotation, content type detection
- Outline: extract bookmarks/table of contents
- Convert: render pages to images (PNG/JPEG)
- Split: break PDF into individual page files or ranges
- Merge: combine multiple PDFs into one
- Extract pages: pull specific pages into a new PDF
- Metadata: read/display document properties
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext, ValidationResult

logger = structlog.get_logger(__name__)


def _import_fitz():
    try:
        import fitz
        return fitz
    except ImportError as e:
        raise RuntimeError(
            "PyMuPDF is not installed. Install with: pip install pymupdf"
        ) from e


class PDFReaderTool(SyncTool):
    """Professional PDF processor with comprehensive extraction and manipulation.

    Features:
    - Page-by-page text extraction with page range selection
    - Table detection and extraction
    - Image extraction and export
    - Text search across pages with context
    - Bookmark/outline extraction
    - Page-to-image conversion (PNG/JPEG)
    - PDF split, merge, and page extraction
    - Document metadata and page info
    - OCR fallback detection for image-based PDFs
    """

    name = "pdf_reader"
    description = (
        "Professional PDF processor: extract text (full or by page range), "
        "detect and extract tables, save embedded images, search text across pages, "
        "extract bookmarks/outline, convert pages to images, split/merge/extract pages, "
        "get page dimensions and metadata. Handles scanned PDFs with OCR detection."
    )
    category = ToolCategory.DOC
    version = "2.0.0"
    timeout_sec = 180
    aliases = ["pdf", "read_pdf", "pdf_extract", "pdf_processor"]
    search_hint = (
        "PDF read extract text metadata pages document table image search "
        "split merge convert outline bookmarks annotations links"
    )
    is_concurrency_safe = True
    is_read_only = False
    is_destructive = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    path_params = ("file_path", "merge_files")
    output_path_params = ("output_path", "output_dir")

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "read",
                        "extract_text",
                        "full_text",
                        "text",
                        "extract_tables",
                        "extract_images",
                        "extract_links",
                        "search",
                        "page_info",
                        "outline",
                        "convert_to_images",
                        "split",
                        "merge",
                        "extract_pages",
                        "metadata",
                    ],
                    "default": "read",
                    "description": (
                        "Operation (default: read): read/extract_text/full_text/text|"
                        "extract_tables|extract_images|extract_links|search|page_info|outline|"
                        "convert_to_images|split|merge|extract_pages|metadata"
                    ),
                },
                "mode": {
                    "type": "string",
                    "enum": [
                        "full",
                        "text",
                        "metadata",
                        "pages",
                        "page_info",
                        "outline",
                        "tables",
                        "images",
                        "links",
                    ],
                    "description": (
                        "Legacy/shortcut mode. full/text/pages map to read; "
                        "tables/images/links map to extraction operations."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the PDF file.",
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
                "pages": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Specific page numbers to process (1-indexed). Alternative to start/end_page.",
                },
                "query": {
                    "type": "string",
                    "description": "Search query text for search operation.",
                },
                "case_sensitive": {
                    "type": "boolean",
                    "description": "Whether search is case-sensitive. Default: false.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Output file path for merge/extract_pages operations.",
                },
                "output_dir": {
                    "type": "string",
                    "description": "Output directory for split/convert_to_images/extract_images.",
                },
                "image_format": {
                    "type": "string",
                    "enum": ["png", "jpeg"],
                    "description": "Image format for convert_to_images. Default: png.",
                },
                "dpi": {
                    "type": "integer",
                    "description": "Resolution for convert_to_images (72-600). Default: 150.",
                    "minimum": 72,
                    "maximum": 600,
                },
                "merge_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of PDF file paths to merge (in order).",
                },
                "extract_metadata": {
                    "type": "boolean",
                    "description": "Include document metadata in read results. Default: true.",
                },
                "include_page_numbers": {
                    "type": "boolean",
                    "description": "Include page numbers in output. Default: true.",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Maximum characters to return for read. Default: 200000.",
                    "minimum": 1000,
                    "maximum": 500_000,
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
        }

    async def validate_input(self, params: dict[str, Any], context: ToolContext) -> ValidationResult:
        fp = params.get("file_path", "")
        operation = self._normalize_operation(params)

        if operation == "merge":
            merge_files = params.get("merge_files", [])
            if not merge_files:
                return ValidationResult(valid=False, message="merge_files is required for merge operation")
            for mf in merge_files:
                if not Path(mf).exists():
                    return ValidationResult(valid=False, message=f"Merge source not found: {mf}")
            return ValidationResult(valid=True)

        if not fp or not str(fp).strip():
            attachments = context.extra.get("attachments") or []
            if isinstance(attachments, list) and attachments:
                return ValidationResult(
                    valid=False,
                    message=(
                        "file_path is required. Upload a PDF to this chat session and run the step again, "
                        "or pass the filename in optional input."
                    ),
                )
            return ValidationResult(
                valid=False,
                message="file_path is required. Upload a PDF to this chat session first.",
            )

        if fp and not Path(fp).exists():
            return ValidationResult(valid=False, message=f"PDF file not found: {fp}")
        if fp and not fp.lower().endswith(".pdf"):
            return ValidationResult(valid=False, message=f"Not a PDF file: {fp}")
        return ValidationResult(valid=True)

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = self._normalize_operation(params or {})
        return f"PDF: {op}"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        operation = self._normalize_operation(params)
        logger.info("pdf_processor", operation=operation, file_path=params.get("file_path"))

        dispatch = {
            "read": self._read,
            "extract_tables": self._extract_tables,
            "extract_images": self._extract_images,
            "extract_links": self._extract_links,
            "search": self._search,
            "page_info": self._page_info,
            "outline": self._outline,
            "convert_to_images": self._convert_to_images,
            "split": self._split,
            "merge": self._merge,
            "extract_pages": self._extract_pages,
            "metadata": self._metadata,
        }
        if operation not in dispatch:
            raise ValueError(f"Unknown operation: {operation}")
        return dispatch[operation](params)

    def _normalize_operation(self, params: dict[str, Any]) -> str:
        """Normalize legacy modes and intuitive aliases to canonical operations."""
        operation = (params.get("operation") or "").strip().lower()
        mode = (params.get("mode") or "").strip().lower()

        aliases = {
            "extract_text": "read",
            "full_text": "read",
            "text": "read",
            "full": "read",
            "pages": "read",
            "table": "extract_tables",
            "tables": "extract_tables",
            "image": "extract_images",
            "images": "extract_images",
            "link": "extract_links",
            "links": "extract_links",
            "bookmarks": "outline",
            "toc": "outline",
        }

        if operation:
            return aliases.get(operation, operation)
        if mode:
            return aliases.get(mode, mode)
        return "read"

    def _open_doc(self, file_path: str):
        fitz = _import_fitz()
        fp = Path(file_path)
        if not fp.exists():
            raise FileNotFoundError(f"PDF file not found: {fp}")
        if not fp.suffix.lower() == ".pdf":
            raise ValueError(f"File is not a PDF: {fp}")
        return fitz.open(str(fp))

    def _resolve_pages(self, params: dict[str, Any], total_pages: int) -> list[int]:
        """Resolve page selection to 0-indexed page numbers."""
        pages = params.get("pages")
        if pages:
            return [p - 1 for p in pages if 1 <= p <= total_pages]

        start = params.get("start_page", 1)
        end = params.get("end_page", total_pages)
        start = max(1, min(start, total_pages))
        end = max(start, min(end, total_pages))
        return list(range(start - 1, end))

    def _read(self, params: dict[str, Any]) -> dict[str, Any]:
        doc = self._open_doc(params["file_path"])
        try:
            total_pages = len(doc)
            page_indices = self._resolve_pages(params, total_pages)
            extract_metadata = params.get("extract_metadata", True)
            include_page_numbers = params.get("include_page_numbers", True)
            max_chars = params.get("max_chars", 200_000)

            pages_content: list[dict[str, Any]] = []
            full_text_parts: list[str] = []
            total_chars = 0
            empty_pages = 0

            for page_num in page_indices:
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

                if total_chars >= max_chars:
                    break

            full_text = "\n\n".join(full_text_parts)
            if len(full_text) > max_chars:
                full_text = full_text[:max_chars]

            result: dict[str, Any] = {
                "text": full_text,
                "pages": pages_content,
                "total_pages": total_pages,
                "extracted_pages": len(pages_content),
                "total_characters": min(total_chars, max_chars),
                "truncated": total_chars > max_chars,
            }

            if empty_pages > 0:
                result["warning"] = (
                    f"{empty_pages} page(s) contain no extractable text. "
                    "The PDF may contain scanned images requiring OCR."
                )

            if extract_metadata:
                result["metadata"] = self._get_metadata(doc)

            return result
        finally:
            doc.close()

    def _extract_tables(self, params: dict[str, Any]) -> dict[str, Any]:
        fitz = _import_fitz()
        doc = self._open_doc(params["file_path"])
        try:
            total_pages = len(doc)
            page_indices = self._resolve_pages(params, total_pages)

            all_tables: list[dict[str, Any]] = []
            for page_num in page_indices:
                page = doc[page_num]
                try:
                    tabs = page.find_tables()
                    for i, tab in enumerate(tabs):
                        table_data = tab.extract()
                        if table_data:
                            headers = table_data[0] if table_data else []
                            rows = table_data[1:] if len(table_data) > 1 else []
                            all_tables.append({
                                "page": page_num + 1,
                                "table_index": i,
                                "headers": headers,
                                "rows": rows,
                                "row_count": len(rows),
                                "col_count": len(headers) if headers else 0,
                            })
                except AttributeError:
                    text = page.get_text("text")
                    lines = text.splitlines()
                    table_lines = [
                        l for l in lines
                        if l.count("\t") >= 2 or l.count("  ") >= 3
                    ]
                    if table_lines:
                        rows = []
                        for line in table_lines:
                            cells = re.split(r"\t+|\s{2,}", line.strip())
                            if cells:
                                rows.append(cells)
                        if rows:
                            all_tables.append({
                                "page": page_num + 1,
                                "table_index": 0,
                                "headers": rows[0] if rows else [],
                                "rows": rows[1:] if len(rows) > 1 else [],
                                "row_count": len(rows) - 1,
                                "col_count": len(rows[0]) if rows else 0,
                                "detection": "heuristic",
                            })

            return {
                "file": params["file_path"],
                "tables": all_tables,
                "table_count": len(all_tables),
                "pages_scanned": len(page_indices),
            }
        finally:
            doc.close()

    def _extract_images(self, params: dict[str, Any]) -> dict[str, Any]:
        fitz = _import_fitz()
        doc = self._open_doc(params["file_path"])
        try:
            total_pages = len(doc)
            page_indices = self._resolve_pages(params, total_pages)

            output_dir = params.get("output_dir")
            if not output_dir:
                output_dir = str(Path(params["file_path"]).parent / f"{Path(params['file_path']).stem}_images")

            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)

            saved_images: list[dict[str, Any]] = []
            img_count = 0

            for page_num in page_indices:
                page = doc[page_num]
                image_list = page.get_images(full=True)

                for img_idx, img_info in enumerate(image_list):
                    xref = img_info[0]
                    try:
                        pix = fitz.Pixmap(doc, xref)

                        if pix.n - pix.alpha > 3:
                            pix = fitz.Pixmap(fitz.csRGB, pix)

                        img_count += 1
                        ext = "png"
                        img_path = out_path / f"page{page_num+1}_img{img_idx+1}.{ext}"
                        pix.save(str(img_path))

                        saved_images.append({
                            "page": page_num + 1,
                            "image_index": img_idx + 1,
                            "path": str(img_path),
                            "width": pix.width,
                            "height": pix.height,
                            "colorspace": pix.colorspace.name if pix.colorspace else "unknown",
                        })
                        pix = None
                    except Exception as e:
                        logger.debug("pdf_image_extract_skip", xref=xref, error=str(e))

            return {
                "file": params["file_path"],
                "output_dir": str(out_path),
                "images": saved_images,
                "image_count": len(saved_images),
                "pages_scanned": len(page_indices),
            }
        finally:
            doc.close()

    def _extract_links(self, params: dict[str, Any]) -> dict[str, Any]:
        doc = self._open_doc(params["file_path"])
        try:
            total_pages = len(doc)
            page_indices = self._resolve_pages(params, total_pages)

            all_links: list[dict[str, Any]] = []
            for page_num in page_indices:
                page = doc[page_num]
                links = page.get_links()
                for link in links:
                    link_info: dict[str, Any] = {
                        "page": page_num + 1,
                        "kind": link.get("kind", 0),
                    }
                    if link.get("uri"):
                        link_info["uri"] = link["uri"]
                        link_info["type"] = "external"
                    elif link.get("page") is not None:
                        link_info["target_page"] = link["page"] + 1
                        link_info["type"] = "internal"
                    else:
                        link_info["type"] = "other"

                    all_links.append(link_info)

            return {
                "file": params["file_path"],
                "links": all_links,
                "link_count": len(all_links),
                "external_links": sum(1 for l in all_links if l.get("type") == "external"),
                "internal_links": sum(1 for l in all_links if l.get("type") == "internal"),
                "pages_scanned": len(page_indices),
            }
        finally:
            doc.close()

    def _search(self, params: dict[str, Any]) -> dict[str, Any]:
        query = params.get("query")
        if not query:
            raise ValueError("'query' is required for search operation")

        doc = self._open_doc(params["file_path"])
        try:
            total_pages = len(doc)
            page_indices = self._resolve_pages(params, total_pages)
            case_sensitive = params.get("case_sensitive", False)

            results: list[dict[str, Any]] = []
            flags = 0 if case_sensitive else re.IGNORECASE

            for page_num in page_indices:
                page = doc[page_num]
                text = page.get_text("text")
                lines = text.splitlines()

                for line_idx, line in enumerate(lines):
                    if re.search(re.escape(query), line, flags):
                        context_start = max(0, line_idx - 1)
                        context_end = min(len(lines), line_idx + 2)
                        results.append({
                            "page": page_num + 1,
                            "line_number": line_idx + 1,
                            "line": line.strip(),
                            "context": [l.strip() for l in lines[context_start:context_end]],
                        })

                        if len(results) >= 100:
                            break
                if len(results) >= 100:
                    break

            return {
                "file": params["file_path"],
                "query": query,
                "case_sensitive": case_sensitive,
                "results": results,
                "match_count": len(results),
                "pages_scanned": len(page_indices),
                "truncated": len(results) >= 100,
            }
        finally:
            doc.close()

    def _page_info(self, params: dict[str, Any]) -> dict[str, Any]:
        doc = self._open_doc(params["file_path"])
        try:
            total_pages = len(doc)
            page_indices = self._resolve_pages(params, total_pages)

            pages_info: list[dict[str, Any]] = []
            for page_num in page_indices:
                page = doc[page_num]
                rect = page.rect
                text = page.get_text("text").strip()
                images = page.get_images(full=True)

                content_type = "text"
                if not text and images:
                    content_type = "image_only"
                elif text and images:
                    content_type = "mixed"
                elif not text and not images:
                    content_type = "empty"

                pages_info.append({
                    "page_number": page_num + 1,
                    "width": round(rect.width, 1),
                    "height": round(rect.height, 1),
                    "width_inches": round(rect.width / 72, 2),
                    "height_inches": round(rect.height / 72, 2),
                    "rotation": page.rotation,
                    "content_type": content_type,
                    "char_count": len(text),
                    "image_count": len(images),
                })

            return {
                "file": params["file_path"],
                "total_pages": total_pages,
                "pages": pages_info,
            }
        finally:
            doc.close()

    def _outline(self, params: dict[str, Any]) -> dict[str, Any]:
        doc = self._open_doc(params["file_path"])
        try:
            toc = doc.get_toc(simple=False)

            bookmarks: list[dict[str, Any]] = []
            for entry in toc:
                level = entry[0]
                title = entry[1]
                page = entry[2]
                bookmarks.append({
                    "level": level,
                    "title": title,
                    "page": page,
                })

            return {
                "file": params["file_path"],
                "bookmarks": bookmarks,
                "bookmark_count": len(bookmarks),
                "has_outline": len(bookmarks) > 0,
                "total_pages": len(doc),
            }
        finally:
            doc.close()

    def _convert_to_images(self, params: dict[str, Any]) -> dict[str, Any]:
        fitz = _import_fitz()
        doc = self._open_doc(params["file_path"])
        try:
            total_pages = len(doc)
            page_indices = self._resolve_pages(params, total_pages)

            output_dir = params.get("output_dir")
            if not output_dir:
                output_dir = str(Path(params["file_path"]).parent / f"{Path(params['file_path']).stem}_pages")

            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)

            img_format = params.get("image_format", "png")
            dpi = params.get("dpi", 150)
            zoom = dpi / 72.0
            mat = fitz.Matrix(zoom, zoom)

            saved_files: list[dict[str, Any]] = []
            for page_num in page_indices:
                page = doc[page_num]
                pix = page.get_pixmap(matrix=mat)

                filename = f"page_{page_num+1:03d}.{img_format}"
                img_path = out_path / filename

                if img_format == "jpeg":
                    pix.save(str(img_path), output="jpeg")
                else:
                    pix.save(str(img_path))

                saved_files.append({
                    "page": page_num + 1,
                    "path": str(img_path),
                    "width": pix.width,
                    "height": pix.height,
                })
                pix = None

            return {
                "file": params["file_path"],
                "output_dir": str(out_path),
                "format": img_format,
                "dpi": dpi,
                "files": saved_files,
                "page_count": len(saved_files),
            }
        finally:
            doc.close()

    def _split(self, params: dict[str, Any]) -> dict[str, Any]:
        fitz = _import_fitz()
        doc = self._open_doc(params["file_path"])
        try:
            total_pages = len(doc)
            page_indices = self._resolve_pages(params, total_pages)

            output_dir = params.get("output_dir")
            if not output_dir:
                output_dir = str(Path(params["file_path"]).parent / f"{Path(params['file_path']).stem}_split")

            out_path = Path(output_dir)
            out_path.mkdir(parents=True, exist_ok=True)

            saved_files: list[str] = []
            for page_num in page_indices:
                new_doc = fitz.open()
                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)
                filename = f"page_{page_num+1:03d}.pdf"
                pdf_path = out_path / filename
                new_doc.save(str(pdf_path))
                new_doc.close()
                saved_files.append(str(pdf_path))

            return {
                "file": params["file_path"],
                "output_dir": str(out_path),
                "files": saved_files,
                "page_count": len(saved_files),
            }
        finally:
            doc.close()

    def _merge(self, params: dict[str, Any]) -> dict[str, Any]:
        fitz = _import_fitz()
        merge_files = params.get("merge_files")
        if not merge_files:
            raise ValueError("'merge_files' is required for merge operation")

        output_path = params.get("output_path")
        if not output_path:
            output_path = str(Path(params["file_path"]).parent / "merged.pdf")

        out_path = Path(output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)

        merged_doc = fitz.open()
        total_pages = 0
        try:
            for fp in merge_files:
                p = Path(fp)
                if not p.exists():
                    raise FileNotFoundError(f"Merge source not found: {fp}")
                src_doc = fitz.open(str(p))
                merged_doc.insert_pdf(src_doc)
                total_pages += len(src_doc)
                src_doc.close()

            merged_doc.save(str(out_path))
            return {
                "success": True,
                "output_path": str(out_path),
                "files_merged": len(merge_files),
                "total_pages": total_pages,
                "size_bytes": out_path.stat().st_size,
            }
        finally:
            merged_doc.close()

    def _extract_pages(self, params: dict[str, Any]) -> dict[str, Any]:
        fitz = _import_fitz()
        doc = self._open_doc(params["file_path"])
        try:
            total_pages = len(doc)
            page_indices = self._resolve_pages(params, total_pages)

            output_path = params.get("output_path")
            if not output_path:
                stem = Path(params["file_path"]).stem
                output_path = str(Path(params["file_path"]).parent / f"{stem}_extracted.pdf")

            out_path = Path(output_path)
            out_path.parent.mkdir(parents=True, exist_ok=True)

            new_doc = fitz.open()
            for page_num in page_indices:
                new_doc.insert_pdf(doc, from_page=page_num, to_page=page_num)

            new_doc.save(str(out_path))
            new_doc.close()

            return {
                "success": True,
                "output_path": str(out_path),
                "pages_extracted": len(page_indices),
                "source_total_pages": total_pages,
                "size_bytes": out_path.stat().st_size,
            }
        finally:
            doc.close()

    def _metadata(self, params: dict[str, Any]) -> dict[str, Any]:
        doc = self._open_doc(params["file_path"])
        try:
            file_path = Path(params["file_path"])
            meta = self._get_metadata(doc)
            meta["file_path"] = str(file_path)
            meta["file_size_bytes"] = file_path.stat().st_size
            meta["total_pages"] = len(doc)

            total_chars = 0
            for page in doc:
                total_chars += len(page.get_text("text"))
            meta["total_characters"] = total_chars

            return meta
        finally:
            doc.close()

    def _get_metadata(self, doc) -> dict[str, Any]:
        metadata = doc.metadata
        return {
            "title": metadata.get("title", ""),
            "author": metadata.get("author", ""),
            "subject": metadata.get("subject", ""),
            "keywords": metadata.get("keywords", ""),
            "creator": metadata.get("creator", ""),
            "producer": metadata.get("producer", ""),
            "creation_date": metadata.get("creationDate", ""),
            "modification_date": metadata.get("modDate", ""),
            "encrypted": doc.is_encrypted,
            "pdf_version": f"{doc.metadata.get('format', '')}",
        }
