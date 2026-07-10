"""Precision-formatting tests for the PDF renderer (and format fallbacks).

Covers header/footer placeholders, running section headers, automatic
figure/table numbering, per-section page breaks, multi-column layouts, and
the consulting-style cover (brand band + logo).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from leagent.docgen.model import DocumentSpec


def _pdf_text_pages(path: Path) -> list[str]:
    fitz = pytest.importorskip("fitz")
    with fitz.open(str(path)) as doc:
        return [page.get_text() for page in doc]


def _spec(**overrides: Any) -> DocumentSpec:
    payload = {
        "title": "Annual Strategy Review",
        "author": "Advisory Team",
        "date": "2026-07-09",
        **overrides,
    }
    return DocumentSpec.model_validate(payload)


# ---------------------------------------------------------------------------
# Header / footer placeholders
# ---------------------------------------------------------------------------


def test_footer_placeholders_resolve(tmp_path: Path) -> None:
    from leagent.docgen.renderers.pdf import render_pdf

    spec = _spec(
        footer={"text": "{title} — {page}/{pages}", "alignment": "center"},
        blocks=[
            {"type": "paragraph", "text": "First page."},
            {"type": "page_break"},
            {"type": "paragraph", "text": "Second page."},
        ],
    )
    out = tmp_path / "footer.pdf"
    result = render_pdf(spec, out)
    assert result["success"] is True
    assert result["page_count"] == 2

    pages = _pdf_text_pages(out)
    assert "Annual Strategy Review — 1/2" in pages[0]
    assert "Annual Strategy Review — 2/2" in pages[1]


def test_running_section_header(tmp_path: Path) -> None:
    from leagent.docgen.renderers.pdf import render_pdf

    spec = _spec(
        section_pages=True,
        header={"text": "{section}", "alignment": "left"},
        blocks=[
            {"type": "heading", "text": "Market Overview", "level": 1},
            {"type": "paragraph", "text": "Alpha."},
            {"type": "heading", "text": "Financial Analysis", "level": 1},
            {"type": "paragraph", "text": "Beta."},
        ],
    )
    out = tmp_path / "sections.pdf"
    result = render_pdf(spec, out)
    assert result["success"] is True
    # section_pages: each H1 opens its own page.
    assert result["page_count"] == 2

    pages = _pdf_text_pages(out)
    assert "Market Overview" in pages[0]
    assert "Financial Analysis" not in pages[0]
    assert "Financial Analysis" in pages[1]


def test_show_page_number_without_placeholders_still_works(tmp_path: Path) -> None:
    from leagent.docgen.renderers.pdf import render_pdf

    spec = _spec(
        footer={"text": "Confidential", "show_page_number": True},
        blocks=[{"type": "paragraph", "text": "Body."}],
    )
    out = tmp_path / "plain-footer.pdf"
    assert render_pdf(spec, out)["success"] is True
    assert "Confidential  ·  1" in _pdf_text_pages(out)[0]


# ---------------------------------------------------------------------------
# Figure / table numbering
# ---------------------------------------------------------------------------


def test_numbered_figures_and_tables(tmp_path: Path) -> None:
    from leagent.docgen.renderers.pdf import render_pdf

    spec = _spec(
        numbered_figures=True,
        blocks=[
            {
                "type": "table",
                "columns": ["Region", "Revenue"],
                "rows": [["East", "1200"]],
                "caption": "Revenue by region",
            },
            {
                "type": "chart",
                "chart_type": "bar",
                "categories": ["Q1", "Q2"],
                "series": [{"name": "Revenue", "values": [1, 2]}],
                "caption": "Quarterly trend",
            },
            {
                "type": "table",
                "columns": ["A", "B"],
                "rows": [["1", "2"]],
                "caption": "Second table",
            },
        ],
    )
    out = tmp_path / "numbered.pdf"
    assert render_pdf(spec, out)["success"] is True
    text = "".join(_pdf_text_pages(out))
    assert "Table 1" in text
    assert "Table 2" in text
    assert "Figure 1" in text


def test_numbered_figures_chinese_labels(tmp_path: Path) -> None:
    from leagent.docgen.renderers.pdf import render_pdf

    spec = _spec(
        title="年度战略评估",
        numbered_figures=True,
        blocks=[
            {"type": "paragraph", "text": "中文内容。"},
            {
                "type": "table",
                "columns": ["区域", "收入"],
                "rows": [["华东", "1200"]],
                "caption": "区域收入",
            },
        ],
    )
    out = tmp_path / "numbered-zh.pdf"
    result = render_pdf(spec, out)
    assert result["success"] is True
    if not result["font_embedded"]:
        pytest.skip("no CJK font available in this environment")
    text = "".join(_pdf_text_pages(out))
    assert "表 1" in text


# ---------------------------------------------------------------------------
# Columns
# ---------------------------------------------------------------------------


def test_columns_block_renders_side_by_side(tmp_path: Path) -> None:
    from leagent.docgen.renderers.pdf import render_pdf

    spec = _spec(
        justify=True,
        blocks=[
            {
                "type": "columns",
                "columns": [
                    [
                        {"type": "heading", "text": "Strengths", "level": 3},
                        {"type": "paragraph", "text": "Broad channel coverage."},
                    ],
                    [
                        {"type": "heading", "text": "Risks", "level": 3},
                        {
                            "type": "callout",
                            "variant": "warning",
                            "text": "Supply concentration.",
                        },
                    ],
                ],
                "widths": [1, 1],
            }
        ],
    )
    out = tmp_path / "columns.pdf"
    result = render_pdf(spec, out)
    assert result["success"] is True
    text = "".join(_pdf_text_pages(out))
    assert "Strengths" in text
    assert "Supply concentration." in text


def test_columns_fallbacks_html_docx_markdown(tmp_path: Path) -> None:
    docx = pytest.importorskip("docx")
    from leagent.docgen.renderers.docx import render_docx
    from leagent.docgen.renderers.html import render_html, render_markdown

    spec = _spec(
        numbered_figures=True,
        blocks=[
            {
                "type": "columns",
                "columns": [
                    [{"type": "paragraph", "text": "Left column text."}],
                    [{"type": "paragraph", "text": "Right column text."}],
                ],
            },
            {
                "type": "table",
                "columns": ["A"],
                "rows": [["1"]],
                "caption": "Only table",
            },
        ],
    )

    html_out = tmp_path / "cols.html"
    assert render_html(spec, html_out)["success"] is True
    html_text = html_out.read_text(encoding="utf-8")
    assert 'class="cols"' in html_text
    assert "Left column text." in html_text
    assert "Table 1" in html_text

    docx_out = tmp_path / "cols.docx"
    assert render_docx(spec, docx_out)["success"] is True
    document = docx.Document(str(docx_out))
    all_text = "\n".join(p.text for p in document.paragraphs)
    assert "Left column text." in all_text
    assert "Right column text." in all_text
    assert "Table 1" in all_text

    md_out = tmp_path / "cols.md"
    assert render_markdown(spec, md_out)["success"] is True
    md_text = md_out.read_text(encoding="utf-8")
    assert "Left column text." in md_text
    assert "Right column text." in md_text


# ---------------------------------------------------------------------------
# Cover
# ---------------------------------------------------------------------------


def test_cover_band_with_logo(tmp_path: Path) -> None:
    pil = pytest.importorskip("PIL.Image")
    from leagent.docgen.renderers.pdf import render_pdf

    logo = tmp_path / "logo.png"
    pil.new("RGBA", (120, 48), (255, 255, 255, 255)).save(logo)

    spec = _spec(
        subtitle="Deep-dive 2026",
        cover={"organization": "LeAgent Consulting", "logo_path": str(logo)},
        blocks=[{"type": "paragraph", "text": "Body content."}],
    )
    out = tmp_path / "cover.pdf"
    result = render_pdf(spec, out)
    assert result["success"] is True
    assert result["warnings"] == []
    assert result["page_count"] == 2

    pages = _pdf_text_pages(out)
    assert "Annual Strategy Review" in pages[0]
    assert "LeAgent Consulting" in pages[0]
    assert "Deep-dive 2026" in pages[0]
    assert "Advisory Team" in pages[0]
    # No footer/header decoration on the cover page.
    assert "Body content." not in pages[0]


def test_cover_missing_logo_warns(tmp_path: Path) -> None:
    from leagent.docgen.renderers.pdf import render_pdf

    spec = _spec(
        cover={"logo_path": str(tmp_path / "missing.png")},
        blocks=[{"type": "paragraph", "text": "Body."}],
    )
    out = tmp_path / "cover-warn.pdf"
    result = render_pdf(spec, out)
    assert result["success"] is True
    assert any("logo" in w.lower() for w in result["warnings"])
