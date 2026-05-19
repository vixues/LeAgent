"""Tests for FileProcessingService: routing, handler resolution, text extraction."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from leagent.services.file_processing.service import (
    EXTENSION_HANDLER_MAP,
    FileProcessingService,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service() -> FileProcessingService:
    return FileProcessingService()


# ---------------------------------------------------------------------------
# _resolve_handler
# ---------------------------------------------------------------------------


class TestResolveHandler:
    def test_pdf_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.pdf"
        f.touch()
        svc = _make_service()
        assert svc._resolve_handler(f, None, None) == "pdf_reader"

    def test_docx_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.docx"
        f.touch()
        svc = _make_service()
        assert svc._resolve_handler(f, None, None) == "word_reader"

    def test_doc_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "legacy.doc"
        f.touch()
        svc = _make_service()
        assert svc._resolve_handler(f, None, None) == "word_reader"

    def test_xlsx_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "data.xlsx"
        f.touch()
        svc = _make_service()
        assert svc._resolve_handler(f, None, None) == "excel_reader"

    def test_csv_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "data.csv"
        f.touch()
        svc = _make_service()
        assert svc._resolve_handler(f, None, None) == "csv_processor"

    def test_md_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "README.md"
        f.touch()
        svc = _make_service()
        assert svc._resolve_handler(f, None, None) == "markdown_processor"

    def test_html_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "page.html"
        f.touch()
        svc = _make_service()
        assert svc._resolve_handler(f, None, None) == "html_processor"

    def test_txt_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.touch()
        svc = _make_service()
        assert svc._resolve_handler(f, None, None) == "text_processor"

    def test_zip_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "archive.zip"
        f.touch()
        svc = _make_service()
        assert svc._resolve_handler(f, None, None) == "archive_manager"

    def test_fallback_to_mime_pdf(self, tmp_path: Path) -> None:
        f = tmp_path / "noextension"
        f.touch()
        svc = _make_service()
        handler = svc._resolve_handler(f, "application/pdf", None)
        assert handler == "pdf_reader"

    def test_fallback_to_mime_html(self, tmp_path: Path) -> None:
        f = tmp_path / "noextension"
        f.touch()
        svc = _make_service()
        assert svc._resolve_handler(f, "text/html", None) == "html_processor"

    def test_fallback_to_original_name(self, tmp_path: Path) -> None:
        f = tmp_path / "upload_abc123"
        f.touch()
        svc = _make_service()
        handler = svc._resolve_handler(f, None, "report.pdf")
        assert handler == "pdf_reader"

    def test_unknown_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "file.xyz_unknown"
        f.touch()
        svc = _make_service()
        assert svc._resolve_handler(f, None, None) is None


# ---------------------------------------------------------------------------
# _extract_text_from_result
# ---------------------------------------------------------------------------


class TestExtractTextFromResult:
    def _svc(self) -> FileProcessingService:
        return FileProcessingService()

    def test_extracts_text_key(self) -> None:
        svc = self._svc()
        result = {"text": "hello world"}
        assert svc._extract_text_from_result("pdf_reader", result) == "hello world"

    def test_extracts_content_key(self) -> None:
        svc = self._svc()
        result = {"content": "some content"}
        assert svc._extract_text_from_result("text_processor", result) == "some content"

    def test_extracts_raw_text_key(self) -> None:
        svc = self._svc()
        result = {"raw_text": "raw content here"}
        assert svc._extract_text_from_result("html_processor", result) == "raw content here"

    def test_extracts_extracted_text_key(self) -> None:
        svc = self._svc()
        result = {"extracted_text": "extracted!"}
        assert svc._extract_text_from_result("pdf_reader", result) == "extracted!"

    def test_nested_data_dict(self) -> None:
        svc = self._svc()
        result = {"data": {"text": "nested text"}}
        assert svc._extract_text_from_result("pdf_reader", result) == "nested text"

    def test_non_dict_result_returns_none(self) -> None:
        svc = self._svc()
        assert svc._extract_text_from_result("pdf_reader", None) is None  # type: ignore[arg-type]

    def test_no_text_key_returns_none(self) -> None:
        svc = self._svc()
        assert svc._extract_text_from_result("pdf_reader", {"pages": [1, 2]}) is None

    def test_truncates_long_text(self) -> None:
        svc = self._svc()
        long_text = "a" * 600_000
        result = {"text": long_text}
        extracted = svc._extract_text_from_result("pdf_reader", result)
        assert extracted is not None
        assert len(extracted) <= 500_000


# ---------------------------------------------------------------------------
# process_file — integration tests with real files via mock registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestProcessFile:
    async def test_missing_file_returns_error(self, tmp_path: Path) -> None:
        svc = _make_service()
        result = await svc.process_file("/nonexistent/path/to/file.txt")
        assert "error" in result
        assert result.get("extracted_text") is None

    async def test_unknown_extension_no_handler(self, tmp_path: Path) -> None:
        f = tmp_path / "file.xyz_unknown"
        f.write_text("content", encoding="utf-8")
        svc = _make_service()
        result = await svc.process_file(str(f))
        assert result.get("handler") is None

    async def test_process_txt_file(self, sample_txt: Path) -> None:
        svc = _make_service()
        with patch.object(svc, "_run_handler", new=AsyncMock(return_value={"text": "hello"})):
            result = await svc.process_file(str(sample_txt))
        assert result["handler"] == "text_processor"
        assert result["extracted_text"] == "hello"

    async def test_process_csv_file(self, sample_csv: Path) -> None:
        svc = _make_service()
        mock_data = {"rows": [[1, "a"], [2, "b"]], "text": "tabular data"}
        with patch.object(svc, "_run_handler", new=AsyncMock(return_value=mock_data)):
            result = await svc.process_file(str(sample_csv))
        assert result["handler"] == "csv_processor"

    async def test_process_with_mime_type_override(self, tmp_path: Path) -> None:
        f = tmp_path / "upload"
        f.write_text("some html content", encoding="utf-8")
        svc = _make_service()
        mock_data = {"content": "html content extracted"}
        with patch.object(svc, "_run_handler", new=AsyncMock(return_value=mock_data)):
            result = await svc.process_file(str(f), mime_type="text/html")
        assert result["handler"] == "html_processor"
        assert result["extracted_text"] == "html content extracted"

    async def test_handler_exception_returns_error(self, sample_txt: Path) -> None:
        svc = _make_service()
        with patch.object(svc, "_run_handler", side_effect=RuntimeError("tool failed")):
            result = await svc.process_file(str(sample_txt))
        assert "error" in result
        assert result.get("extracted_text") is None


# ---------------------------------------------------------------------------
# Extension map completeness
# ---------------------------------------------------------------------------


class TestExtensionMap:
    def test_common_extensions_present(self) -> None:
        required = [".pdf", ".docx", ".xlsx", ".csv", ".txt", ".html", ".md", ".zip"]
        for ext in required:
            assert ext in EXTENSION_HANDLER_MAP, f"{ext} missing from EXTENSION_HANDLER_MAP"

    def test_all_handlers_valid_names(self) -> None:
        valid = {
            "pdf_reader", "word_reader", "excel_reader", "csv_processor",
            "html_processor", "markdown_processor", "text_processor",
            "config_file", "archive_manager", "image_ocr",
        }
        for ext, handler in EXTENSION_HANDLER_MAP.items():
            assert handler in valid, f"Unknown handler {handler!r} for extension {ext}"
