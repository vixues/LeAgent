from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from leagent.tools.base import ToolContext


def _have(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


_HAVE_PYMUPDF = _have("fitz")

pytestmark = pytest.mark.skipif(
    not _HAVE_PYMUPDF, reason="PyMuPDF not installed (extras-only [office])"
)


@pytest.fixture()
def small_pdf(tmp_path: Path) -> Path:
    import fitz

    path = tmp_path / "tiny.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello PDF\nPage one content.")
    doc.save(str(path))
    doc.close()
    return path


@pytest.mark.asyncio
async def test_pdf_reader_accepts_common_alias_params(small_pdf: Path) -> None:
    """LLMs often emit page_start/page_end + extract_text; accept them."""
    from leagent.tools.doc.pdf_reader import PDFReaderTool

    ctx = ToolContext(user_id="u1", session_id="s1")
    result = await PDFReaderTool().run(
        {
            "file_path": str(small_pdf),
            "operation": "extract_text",
            "page_start": 1,
            "page_end": 1,
        },
        ctx,
    )
    assert result.success
    assert isinstance(result.data, dict)
    assert "text" in result.data

