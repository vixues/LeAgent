"""Tests for all document-processing tools.

Each tool is instantiated directly (no registry, no HTTP) and exercised
with the programmatic sample files from tests/fixtures/conftest.py.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from leagent.tools.base import ToolContext, ToolResult


def _have(*modules: str) -> bool:
    """Return True iff every module in ``modules`` is importable."""
    return all(importlib.util.find_spec(m) is not None for m in modules)


# Optional stacks split off into ``[office]`` (and friends) extras in the
# uv migration (M01). When the extras are not installed we skip the
# corresponding tool tests rather than failing.
_HAVE_PYMUPDF = _have("fitz")
_HAVE_DOCX = _have("docx")
_HAVE_EXCEL = _have("openpyxl") and _have("pandas")

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def make_ctx() -> ToolContext:
    return ToolContext(user_id="u1", session_id="s1")


async def run(tool_name: str, params: dict[str, Any]) -> ToolResult:
    """Import and run a tool by name."""
    # All doc tools are SyncTool subclasses — call .run() (async wrapper)
    import importlib

    # map tool_name to module path
    _module_map = {
        "pdf_reader": "leagent.tools.doc.pdf_reader.PDFReaderTool",
        "word_reader": "leagent.tools.doc.word_reader.WordReaderTool",
        "excel_reader": "leagent.tools.doc.excel_reader.ExcelReaderTool",
        "csv_processor": "leagent.tools.doc.csv_processor.CSVProcessorTool",
        "html_processor": "leagent.tools.doc.html_processor.HTMLProcessorTool",
        "markdown_processor": "leagent.tools.doc.markdown_processor.MarkdownProcessorTool",
        "text_processor": "leagent.tools.doc.text_processor.TextFileProcessorTool",
        "config_file": "leagent.tools.doc.config_file_tool.ConfigFileTool",
        "archive_manager": "leagent.tools.doc.archive_manager.ArchiveManagerTool",
    }
    cls_path = _module_map[tool_name]
    module_path, cls_name = cls_path.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    cls = getattr(mod, cls_name)
    tool = cls()
    return await tool.run(params, make_ctx())


# ===========================================================================
# PDFReaderTool
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(not _HAVE_PYMUPDF, reason="PyMuPDF not installed (extras-only [office])")
class TestPDFReaderTool:
    async def test_read_all_pages(self, sample_pdf: Path) -> None:
        result = await run("pdf_reader", {"file_path": str(sample_pdf)})
        assert result.success
        assert isinstance(result.data, dict)

    async def test_page_range(self, sample_pdf: Path) -> None:
        result = await run("pdf_reader", {
            "file_path": str(sample_pdf),
            "start_page": 1,
            "end_page": 1,
        })
        assert result.success

    async def test_metadata_flag(self, sample_pdf: Path) -> None:
        result = await run("pdf_reader", {
            "file_path": str(sample_pdf),
            "extract_metadata": True,
        })
        assert result.success
        assert "metadata" in result.data or "pages" in result.data

    async def test_legacy_full_mode(self, sample_pdf: Path) -> None:
        result = await run("pdf_reader", {
            "file_path": str(sample_pdf),
            "mode": "full",
        })
        assert result.success
        assert isinstance(result.data, dict)
        assert "text" in result.data

    async def test_extract_text_operation_alias(self, sample_pdf: Path) -> None:
        result = await run("pdf_reader", {
            "file_path": str(sample_pdf),
            "operation": "extract_text",
        })
        assert result.success
        assert isinstance(result.data, dict)
        assert "text" in result.data

    async def test_missing_file(self) -> None:
        result = await run("pdf_reader", {"file_path": "/nonexistent/path/to.pdf"})
        assert not result.success
        assert result.error

    async def test_non_pdf_file(self, sample_txt: Path) -> None:
        result = await run("pdf_reader", {"file_path": str(sample_txt)})
        assert not result.success


# ===========================================================================
# WordReaderTool
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(not _HAVE_DOCX, reason="python-docx not installed (extras-only [office])")
class TestWordReaderTool:
    async def test_read_paragraphs(self, sample_docx: Path) -> None:
        result = await run("word_reader", {"file_path": str(sample_docx)})
        assert result.success
        assert isinstance(result.data, dict)

    async def test_include_tables(self, sample_docx: Path) -> None:
        result = await run("word_reader", {
            "file_path": str(sample_docx),
            "extract_tables": True,
        })
        assert result.success

    async def test_missing_file(self) -> None:
        result = await run("word_reader", {"file_path": "/nonexistent/doc.docx"})
        assert not result.success

    async def test_read_legacy_doc_mock_pyantiword(self, tmp_path: Path) -> None:
        """Legacy .doc path returns text shaped like docx output (pyantiword mocked)."""
        p = tmp_path / "legacy.doc"
        p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 200)
        with patch(
            "pyantiword.antiword_wrapper.extract_text_with_antiword",
            return_value="Line one.\n\nLine two.",
        ):
            result = await run("word_reader", {"file_path": str(p)})
        assert result.success
        data = result.data
        assert isinstance(data, dict)
        assert "Line one" in data.get("text", "")
        assert data.get("metadata", {}).get("legacy_format") == "doc"
        assert data.get("metadata", {}).get("extraction_source") == "pyantiword"


# ===========================================================================
# ExcelReaderTool
# ===========================================================================


@pytest.mark.asyncio
@pytest.mark.skipif(not _HAVE_EXCEL, reason="openpyxl/pandas not installed (extras-only [office])")
class TestExcelReaderTool:
    async def test_read_records(self, sample_xlsx: Path) -> None:
        result = await run("excel_reader", {
            "file_path": str(sample_xlsx),
            "output_format": "records",
        })
        assert result.success

    async def test_read_by_sheet_name(self, sample_xlsx: Path) -> None:
        result = await run("excel_reader", {
            "file_path": str(sample_xlsx),
            "sheet_name": "Employees",
        })
        assert result.success

    async def test_read_by_sheet_index(self, sample_xlsx: Path) -> None:
        result = await run("excel_reader", {
            "file_path": str(sample_xlsx),
            "sheet_index": 0,
        })
        assert result.success

    async def test_missing_file(self) -> None:
        result = await run("excel_reader", {"file_path": "/nonexistent/data.xlsx"})
        assert not result.success


# ===========================================================================
# CSVProcessorTool
# ===========================================================================


@pytest.mark.asyncio
class TestCSVProcessorTool:
    async def test_read_operation(self, sample_csv: Path) -> None:
        result = await run("csv_processor", {
            "operation": "read",
            "file_path": str(sample_csv),
        })
        assert result.success
        assert isinstance(result.data, dict)

    async def test_stats_operation(self, sample_csv: Path) -> None:
        result = await run("csv_processor", {
            "operation": "stats",
            "file_path": str(sample_csv),
        })
        assert result.success

    async def test_query_operation(self, sample_csv: Path) -> None:
        result = await run("csv_processor", {
            "operation": "query",
            "file_path": str(sample_csv),
            "filter_column": "name",
            "filter_value": "alpha",
        })
        assert result.success

    async def test_tsv_file(self, sample_tsv: Path) -> None:
        result = await run("csv_processor", {
            "operation": "read",
            "file_path": str(sample_tsv),
        })
        assert result.success

    async def test_convert_to_json(self, sample_csv: Path, tmp_path: Path) -> None:
        out = tmp_path / "out.json"
        result = await run("csv_processor", {
            "operation": "convert",
            "file_path": str(sample_csv),
            "output_path": str(out),
            "output_format": "json",
        })
        assert result.success

    async def test_write_creates_new_file(self, tmp_path: Path) -> None:
        """write must resolve a destination path that does not exist yet (sandbox allow_create)."""
        out = tmp_path / "brand_new_output.csv"
        assert not out.exists()
        result = await run("csv_processor", {
            "operation": "write",
            "file_path": str(out),
            "data": [{"a": "1", "b": "2"}],
        })
        assert result.success
        assert out.is_file()
        raw = out.read_text(encoding="utf-8")
        assert "a" in raw and "b" in raw

    async def test_missing_file(self) -> None:
        result = await run("csv_processor", {
            "operation": "read",
            "file_path": "/nonexistent/data.csv",
        })
        assert not result.success

    async def test_read_basename_via_knowledge_style_attachment(
        self,
        tmp_path: Path,
    ) -> None:
        """Bare filename resolves when path is merged like chat ``file_ids`` / knowledge."""
        from leagent.tools._sandbox.paths import reset_roots
        from leagent.tools.doc.csv_processor import CSVProcessorTool
        from leagent.tools.session_attachment_context import build_attachment_lookup

        prev_roots = os.environ.get("LEAGENT_TOOL_FILE_ROOTS")
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = str(tmp_path)
        reset_roots()
        try:
            kid = uuid.uuid4()
            kb = tmp_path / "knowledge"
            kb.mkdir()
            stored = (kb / f"{kid}_report.csv").resolve()
            stored.write_text("a,b\n1,2\n", encoding="utf-8")

            lookup = build_attachment_lookup(
                session_attachments=[],
                normalized_attachments=[str(stored)],
            )
            ctx = ToolContext(user_id="u1", session_id=str(uuid.uuid4()))
            ctx.extra["attachments"] = [str(stored)]
            ctx.extra["attachment_lookup"] = {
                "by_id": lookup.get("by_id") or {},
                "by_name": lookup.get("by_name") or {},
            }
            tool = CSVProcessorTool()
            result = await tool.run(
                {"operation": "read", "file_path": "report.csv", "max_rows": 10},
                ctx,
            )
            assert result.success
            assert isinstance(result.data, dict)
        finally:
            if prev_roots is None:
                os.environ.pop("LEAGENT_TOOL_FILE_ROOTS", None)
            else:
                os.environ["LEAGENT_TOOL_FILE_ROOTS"] = prev_roots
            reset_roots()


# ===========================================================================
# HTMLProcessorTool
# ===========================================================================


@pytest.mark.asyncio
class TestHTMLProcessorTool:
    async def test_read_operation(self, sample_html: Path) -> None:
        result = await run("html_processor", {
            "operation": "read",
            "file_path": str(sample_html),
        })
        assert result.success

    async def test_extract_links(self, sample_html: Path) -> None:
        result = await run("html_processor", {
            "operation": "extract_links",
            "file_path": str(sample_html),
        })
        assert result.success
        links = result.data.get("links", result.data)
        assert len(links) >= 2

    async def test_extract_tables(self, sample_html: Path) -> None:
        result = await run("html_processor", {
            "operation": "extract_tables",
            "file_path": str(sample_html),
        })
        assert result.success

    async def test_extract_metadata(self, sample_html: Path) -> None:
        result = await run("html_processor", {
            "operation": "extract_metadata",
            "file_path": str(sample_html),
        })
        assert result.success

    async def test_convert_to_text(self, sample_html: Path) -> None:
        result = await run("html_processor", {
            "operation": "convert",
            "file_path": str(sample_html),
            "output_format": "plain_text",
        })
        assert result.success


# ===========================================================================
# MarkdownProcessorTool
# ===========================================================================


@pytest.mark.asyncio
class TestMarkdownProcessorTool:
    async def test_read_operation(self, sample_md: Path) -> None:
        result = await run("markdown_processor", {
            "operation": "read",
            "file_path": str(sample_md),
        })
        assert result.success

    async def test_extract_toc(self, sample_md: Path) -> None:
        result = await run("markdown_processor", {
            "operation": "extract_toc",
            "file_path": str(sample_md),
        })
        assert result.success

    async def test_extract_code_blocks(self, sample_md: Path) -> None:
        result = await run("markdown_processor", {
            "operation": "extract_code_blocks",
            "file_path": str(sample_md),
        })
        assert result.success
        blocks = result.data.get("code_blocks", result.data)
        assert len(blocks) >= 1

    async def test_convert_to_html(self, sample_md: Path) -> None:
        result = await run("markdown_processor", {
            "operation": "convert",
            "file_path": str(sample_md),
            "output_format": "html",
        })
        assert result.success


# ===========================================================================
# TextFileProcessorTool
# ===========================================================================


@pytest.mark.asyncio
class TestTextFileProcessorTool:
    async def test_read_operation(self, sample_txt: Path) -> None:
        result = await run("text_processor", {
            "operation": "read",
            "file_path": str(sample_txt),
        })
        assert result.success

    async def test_head_operation(self, sample_txt: Path) -> None:
        result = await run("text_processor", {
            "operation": "head",
            "file_path": str(sample_txt),
            "lines": 5,
        })
        assert result.success
        content = result.data.get("content", result.data.get("lines", ""))
        assert content  # 5 lines of content

    async def test_tail_operation(self, sample_txt: Path) -> None:
        result = await run("text_processor", {
            "operation": "tail",
            "file_path": str(sample_txt),
            "lines": 3,
        })
        assert result.success

    async def test_search_operation(self, sample_txt: Path) -> None:
        result = await run("text_processor", {
            "operation": "search",
            "file_path": str(sample_txt),
            "pattern": "quick brown fox",
        })
        assert result.success

    async def test_stats_operation(self, sample_txt: Path) -> None:
        result = await run("text_processor", {
            "operation": "stats",
            "file_path": str(sample_txt),
        })
        assert result.success

    async def test_missing_file(self) -> None:
        result = await run("text_processor", {
            "operation": "read",
            "file_path": "/no/such/file.txt",
        })
        assert not result.success

    async def test_detect_encoding_utf8_bom(self, tmp_path: Path) -> None:
        p = tmp_path / "bom.txt"
        p.write_bytes(b"\xef\xbb\xbf" + "hello".encode("utf-8"))
        result = await run("text_processor", {
            "operation": "detect_encoding",
            "file_path": str(p),
        })
        assert result.success
        assert result.data["bom_encoding"] == "utf-8-sig"
        assert result.data["encoding"] == "utf-8-sig"

    async def test_try_decodings_gb18030(self, tmp_path: Path) -> None:
        p = tmp_path / "gb.txt"
        p.write_bytes("中文测试".encode("gb18030"))
        result = await run("text_processor", {
            "operation": "try_decodings",
            "file_path": str(p),
            "encodings": ["utf-8", "gb18030"],
        })
        assert result.success
        rows = result.data["results"]
        gb = next(r for r in rows if r["encoding"] == "gb18030")
        assert gb["strict_ok"] is True
        utf = next(r for r in rows if r["encoding"] == "utf-8")
        assert utf["strict_ok"] is False

    async def test_read_line_endings_and_errors_replace(self, tmp_path: Path) -> None:
        p = tmp_path / "crlf.txt"
        p.write_bytes(b"a\r\nb\nc")
        result = await run("text_processor", {
            "operation": "read",
            "file_path": str(p),
            "encoding": "utf-8",
            "errors": "replace",
        })
        assert result.success
        assert result.data["line_endings"]["crlf"] >= 1
        assert "decode" in result.data


# ===========================================================================
# ConfigFileTool
# ===========================================================================


@pytest.mark.asyncio
class TestConfigFileTool:
    async def test_read_json(self, sample_json: Path) -> None:
        result = await run("config_file", {
            "operation": "read",
            "file_path": str(sample_json),
        })
        assert result.success
        assert isinstance(result.data, dict)

    async def test_read_yaml(self, sample_yaml: Path) -> None:
        result = await run("config_file", {
            "operation": "read",
            "file_path": str(sample_yaml),
        })
        assert result.success

    async def test_read_toml(self, sample_toml: Path) -> None:
        result = await run("config_file", {
            "operation": "read",
            "file_path": str(sample_toml),
        })
        assert result.success

    async def test_read_tilde_openclaw_json(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from leagent.tools._sandbox.paths import reset_roots
        from leagent.tools.doc.config_file_tool import ConfigFileTool

        allowed_root = tmp_path / "allowed"
        upload_root = tmp_path / "uploads"
        home = tmp_path / "home"
        config = home / ".openclaw" / "openclaw.json"
        allowed_root.mkdir()
        config.parent.mkdir(parents=True)
        config.write_text('{"app":{"name":"openclaw"}}', encoding="utf-8")
        monkeypatch.setenv("HOME", str(home))
        monkeypatch.delenv("OPENCLAW_HOME", raising=False)
        monkeypatch.setenv("LEAGENT_TOOL_FILE_ROOTS", str(allowed_root))
        monkeypatch.setenv("LEAGENT_FILES_UPLOAD_DIR", str(upload_root))
        reset_roots()
        try:
            result = await ConfigFileTool().run(
                {
                    "operation": "read",
                    "file_path": "~/.openclaw/openclaw.json",
                },
                ToolContext(user_id="u1", session_id="s-openclaw"),
            )
        finally:
            reset_roots()

        assert result.success
        assert result.data["data"]["app"]["name"] == "openclaw"

    async def test_query_operation(self, sample_json: Path) -> None:
        result = await run("config_file", {
            "operation": "query",
            "file_path": str(sample_json),
            "path": "app.name",
        })
        assert result.success

    async def test_write_operation(self, tmp_path: Path) -> None:
        out = tmp_path / "out.json"
        result = await run("config_file", {
            "operation": "write",
            "file_path": str(out),
            "data": {"key": "value", "nested": {"x": 1}},
        })
        assert result.success
        assert out.exists()

    async def test_convert_json_to_yaml(self, sample_json: Path, tmp_path: Path) -> None:
        out = tmp_path / "output.yaml"
        result = await run("config_file", {
            "operation": "convert",
            "file_path": str(sample_json),
            "output_path": str(out),
            "output_format": "yaml",
        })
        assert result.success


# ===========================================================================
# ArchiveManagerTool
# ===========================================================================


@pytest.mark.asyncio
class TestArchiveManagerTool:
    async def test_list_zip(self, sample_zip: Path) -> None:
        result = await run("archive_manager", {
            "operation": "list",
            "archive_path": str(sample_zip),
        })
        assert result.success
        files = result.data.get("files", result.data.get("entries", []))
        assert len(files) >= 2

    async def test_list_tar(self, sample_tar: Path) -> None:
        result = await run("archive_manager", {
            "operation": "list",
            "archive_path": str(sample_tar),
        })
        assert result.success

    async def test_extract_zip(self, sample_zip: Path, tmp_path: Path) -> None:
        out = tmp_path / "extracted"
        out.mkdir()
        result = await run("archive_manager", {
            "operation": "extract",
            "archive_path": str(sample_zip),
            "output_dir": str(out),
        })
        assert result.success

    async def test_info_zip(self, sample_zip: Path) -> None:
        result = await run("archive_manager", {
            "operation": "info",
            "archive_path": str(sample_zip),
        })
        assert result.success

    async def test_create_zip(self, sample_txt: Path, tmp_path: Path) -> None:
        out = tmp_path / "created.zip"
        result = await run("archive_manager", {
            "operation": "create",
            "archive_path": str(out),
            "files": [str(sample_txt)],
            "format": "zip",
        })
        assert result.success
        assert out.exists()


# ===========================================================================
# DocClassifierTool — dispatch only (no real LLM call)
# ===========================================================================


@pytest.mark.asyncio
class TestDocClassifierTool:
    async def test_classify_pdf(self, sample_pdf: Path) -> None:
        from leagent.tools.doc.doc_classifier import DocClassifierTool

        tool = DocClassifierTool()
        result = await tool.run(
            {"file_path": str(sample_pdf)},
            make_ctx(),
        )
        # Classification may fail without LLM — just verify it doesn't crash
        assert isinstance(result, ToolResult)

    async def test_classify_csv(self, sample_csv: Path) -> None:
        from leagent.tools.doc.doc_classifier import DocClassifierTool

        tool = DocClassifierTool()
        result = await tool.run(
            {"file_path": str(sample_csv)},
            make_ctx(),
        )
        assert isinstance(result, ToolResult)


# ===========================================================================
# ImageOCRTool — mock-based (PaddleOCR is optional)
# ===========================================================================


@pytest.mark.asyncio
class TestImageOCRTool:
    async def test_missing_image_returns_error(self) -> None:
        from leagent.tools.doc.image_ocr import ImageOCRTool

        tool = ImageOCRTool()
        result = await tool.run(
            {"file_path": "/nonexistent/image.png"},
            make_ctx(),
        )
        assert not result.success

    async def test_instantiation(self) -> None:
        from leagent.tools.doc.image_ocr import ImageOCRTool

        tool = ImageOCRTool()
        assert tool.name
        assert tool.category is not None
