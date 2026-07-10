"""Per-format render smoke tests, including the PDF anti-tofu regression test."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from leagent.docgen.markdown import parse_markdown_blocks
from leagent.docgen.model import DeckSpec, DocumentSpec

CJK_SAMPLE = "季度业绩持续增长，中文渲染正常。"

_MARKDOWN = f"""
# 季度报告

{CJK_SAMPLE} English text mixed in.

## 数据

| 指标 | 数值 |
| --- | --- |
| 收入 | 1200 |
| 成本 | 800 |

- [x] 完成年度预算
- [ ] 审核合同

> 引用：稳中求进。
"""


def _doc_spec(**overrides) -> DocumentSpec:
    payload = {
        "title": "季度报告",
        "author": "测试",
        "blocks": parse_markdown_blocks(_MARKDOWN),
        **overrides,
    }
    return DocumentSpec.model_validate(payload)


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------


def test_render_pdf_anti_tofu(tmp_path: Path) -> None:
    """Chinese glyphs must survive a render → extract round trip."""
    fitz = pytest.importorskip("fitz")
    from leagent.docgen.renderers.pdf import render_pdf

    out = tmp_path / "report.pdf"
    result = render_pdf(_doc_spec(toc=True, cover=True), out)

    assert result["success"] is True
    assert out.is_file() and out.stat().st_size > 0
    assert result["page_count"] >= 2  # cover + toc + body

    if not result["font_embedded"]:
        pytest.skip(f"no CJK font available in this environment: {result['warnings']}")

    doc = fitz.open(str(out))
    text = "".join(page.get_text() for page in doc)
    doc.close()
    assert CJK_SAMPLE in text
    assert "季度报告" in text
    # No tofu / replacement characters in the extracted text.
    assert "\ufffd" not in text


def test_render_pdf_reports_font_warning_when_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from leagent.docgen import fonts as fonts_mod
    from leagent.docgen.fonts import FontManager
    from leagent.docgen.renderers import pdf as pdf_mod

    monkeypatch.delenv("LEAGENT_CJK_FONT", raising=False)
    monkeypatch.setenv("LEAGENT_FONT_AUTO_DOWNLOAD", "0")
    monkeypatch.setattr(fonts_mod, "discover_cjk_font_file", lambda *, is_bold: None)
    empty_mgr = FontManager(fonts_dir=tmp_path / "no-fonts")
    monkeypatch.setattr(pdf_mod, "get_font_manager", lambda: empty_mgr)

    out = tmp_path / "latin.pdf"
    result = pdf_mod.render_pdf(
        DocumentSpec.model_validate(
            {"title": "Latin only", "blocks": [{"type": "paragraph", "text": "hello"}]}
        ),
        out,
    )
    assert result["success"] is True
    assert result["font_embedded"] is False
    assert result["warnings"]


# ---------------------------------------------------------------------------
# DOCX
# ---------------------------------------------------------------------------


def test_render_docx_sets_east_asia_fonts(tmp_path: Path) -> None:
    docx = pytest.importorskip("docx")
    from leagent.docgen.renderers.docx import render_docx

    out = tmp_path / "report.docx"
    result = render_docx(_doc_spec(toc=True), out)
    assert result["success"] is True
    assert out.is_file()
    assert result["east_asia_font"]

    document = docx.Document(str(out))
    all_text = "\n".join(p.text for p in document.paragraphs)
    assert CJK_SAMPLE in all_text

    # Every run carrying CJK text must declare an eastAsia typeface.
    ea_attr = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}eastAsia"
    for para in document.paragraphs:
        for run in para.runs:
            if any("\u4e00" <= ch <= "\u9fff" for ch in run.text):
                rfonts = run.font.element.rPr.rFonts if run.font.element.rPr is not None else None
                assert rfonts is not None
                assert rfonts.get(ea_attr)


# ---------------------------------------------------------------------------
# PPTX
# ---------------------------------------------------------------------------


def test_render_pptx_deck(tmp_path: Path) -> None:
    pptx = pytest.importorskip("pptx")
    from leagent.docgen.renderers.pptx import render_pptx

    spec = DeckSpec.model_validate(
        {
            "title": "年度汇报",
            "subtitle": "2026 计划",
            "slides": [
                {"layout": "title", "title": "年度汇报", "subtitle": "战略回顾"},
                {
                    "layout": "content",
                    "title": "重点工作",
                    "body": "- 拓展市场\n- 降本增效\n- **技术升级**",
                    "notes": "强调技术投入",
                },
                {
                    "layout": "table",
                    "title": "数据一览",
                    "table": {"columns": ["项目", "值"], "rows": [["收入", "1200"]]},
                },
                {"layout": "quote", "quote": "行稳致远", "attribution": "管理层"},
            ],
        }
    )
    out = tmp_path / "deck.pptx"
    result = render_pptx(spec, out)
    assert result["success"] is True
    assert out.is_file()
    assert result["slide_count"] == 4

    prs = pptx.Presentation(str(out))
    assert len(prs.slides) == 4
    texts = []
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_text_frame:
                texts.append(shape.text_frame.text)
    joined = "\n".join(texts)
    assert "年度汇报" in joined
    assert "拓展市场" in joined

    # Speaker notes survive.
    notes = prs.slides[1].notes_slide.notes_text_frame.text
    assert "强调技术投入" in notes

    # Every DrawingML run declares an east-asian typeface.
    ea_qname = "{http://schemas.openxmlformats.org/drawingml/2006/main}ea"
    ea_count = 0
    for slide in prs.slides:
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    if run.text.strip():
                        assert run.font._rPr is not None
                        assert run.font._rPr.find(ea_qname) is not None
                        ea_count += 1
    assert ea_count > 0


# ---------------------------------------------------------------------------
# HTML / Markdown
# ---------------------------------------------------------------------------


def test_render_html_escapes_and_contains_content(tmp_path: Path) -> None:
    from leagent.docgen.renderers.html import render_html

    spec = DocumentSpec.model_validate(
        {
            "title": "报告 <script>alert(1)</script>",
            "blocks": [
                {"type": "heading", "text": "总览", "level": 1},
                {"type": "paragraph", "text": CJK_SAMPLE},
                {"type": "paragraph", "text": "<img src=x onerror=alert(1)>"},
            ],
        }
    )
    out = tmp_path / "report.html"
    result = render_html(spec, out)
    assert result["success"] is True

    html_text = out.read_text(encoding="utf-8")
    assert CJK_SAMPLE in html_text
    assert "<script>alert(1)</script>" not in html_text
    assert "<img src=x onerror" not in html_text


def test_render_markdown_output(tmp_path: Path) -> None:
    from leagent.docgen.renderers.html import render_markdown

    out = tmp_path / "report.md"
    result = render_markdown(_doc_spec(), out)
    assert result["success"] is True
    md_text = out.read_text(encoding="utf-8")
    assert "# " in md_text
    assert CJK_SAMPLE in md_text
    assert "| 指标 |" in md_text
