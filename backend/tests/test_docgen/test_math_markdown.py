"""Advanced markdown parsing + cross-format math rendering tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from leagent.docgen.markdown import parse_inline, parse_markdown_blocks, parse_markdown_document
from leagent.docgen.mathtext import (
    latex_lines,
    latex_to_unicode,
    math_vector_path,
    render_math_png,
)
from leagent.docgen.model import (
    DeckSpec,
    DefinitionListBlock,
    DocumentSpec,
    FootnotesBlock,
    MathBlock,
    ParagraphBlock,
)
from leagent.docgen.omml import latex_to_omml_xml

# ---------------------------------------------------------------------------
# mathtext core
# ---------------------------------------------------------------------------


def test_render_math_png_geometry() -> None:
    result = render_math_png(r"\frac{-b \pm \sqrt{b^2 - 4ac}}{2a}", font_size=12)
    assert result is not None
    png, w_pt, h_pt, d_pt = result
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    assert w_pt > 0 and h_pt > 0
    assert d_pt >= 0  # fraction bar extends below the baseline


def test_render_math_png_invalid_latex_returns_none() -> None:
    assert render_math_png(r"\frac{1}{") is None
    assert render_math_png("") is None


def test_latex_lines_strips_ams_environment() -> None:
    rows = latex_lines(r"\begin{aligned} a &= b + c \\ d &= e \end{aligned}")
    assert len(rows) == 2
    assert "begin" not in rows[0] and "&" not in rows[0]


def test_latex_to_unicode_fallback() -> None:
    text = latex_to_unicode(r"E = mc^2 \quad \alpha \le \beta_1")
    assert "mc²" in text
    assert "α" in text and "≤" in text and "β₁" in text


def test_math_vector_path_geometry() -> None:
    mv = math_vector_path(r"\frac{-b \pm \sqrt{b^2-4ac}}{2a}", font_size=12)
    assert mv is not None
    assert mv.width > 0 and mv.height > 0 and mv.depth >= 0
    assert mv.contours  # glyph outlines + fraction/radical bars
    ops = {op for contour in mv.contours for op, _ in contour}
    assert "m" in ops and "c" in ops  # move + Bézier curves


def test_math_vector_path_invalid_returns_none() -> None:
    assert math_vector_path(r"\frac{1}{") is None
    assert math_vector_path("") is None


# ---------------------------------------------------------------------------
# LaTeX → OMML (native Office equations)
# ---------------------------------------------------------------------------


def test_omml_fraction_and_radical() -> None:
    xml = latex_to_omml_xml(r"\frac{a}{\sqrt{b}}")
    assert xml is not None
    assert "<m:f>" in xml  # fraction
    assert "<m:rad>" in xml  # radical
    assert "<m:num>" in xml and "<m:den>" in xml


def test_omml_nary_operator() -> None:
    from leagent.docgen.omml import M_NS, latex_to_omml_element

    xml = latex_to_omml_xml(r"\sum_{i=1}^{n} x_i")
    assert xml is not None
    assert "<m:nary>" in xml
    # The operator char is captured on m:chr (serialised as an XML entity).
    el = latex_to_omml_element(r"\sum_{i=1}^{n} x_i")
    chr_el = el.find(f".//{{{M_NS}}}chr")
    assert chr_el is not None
    assert chr_el.get(f"{{{M_NS}}}val") == "∑"


def test_omml_scripts() -> None:
    assert "<m:sSup>" in (latex_to_omml_xml(r"x^2") or "")
    assert "<m:sSub>" in (latex_to_omml_xml(r"x_i") or "")
    assert "<m:sSubSup>" in (latex_to_omml_xml(r"x_i^2") or "")


def test_omml_display_wraps_para() -> None:
    xml = latex_to_omml_xml(r"E = mc^2", display=True)
    assert xml is not None
    assert xml.lstrip().startswith("<m:oMathPara")


def test_omml_invalid_returns_none() -> None:
    assert latex_to_omml_xml(r"\frac{1}{") is None
    assert latex_to_omml_xml("") is None


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_dollar_math_block() -> None:
    (block,) = parse_markdown_blocks("$$\nE = mc^2\n$$\n")
    assert isinstance(block, MathBlock)
    assert block.latex == "E = mc^2"


def test_amsmath_environment_block() -> None:
    md = "\\begin{align}\na &= b \\\\\nc &= d\n\\end{align}\n"
    (block,) = parse_markdown_blocks(md)
    assert isinstance(block, MathBlock)
    assert "align" in block.latex


def test_math_fence_block() -> None:
    (block,) = parse_markdown_blocks("```math\n\\sqrt{x}\n```\n")
    assert isinstance(block, MathBlock)
    assert block.latex == "\\sqrt{x}"


def test_inline_math_span() -> None:
    spans = parse_inline("before $x^2$ after")
    math = next(s for s in spans if s.math)
    assert math.text == "x^2"
    assert [s.text for s in spans if not s.math] == ["before ", " after"]


def test_currency_is_not_math() -> None:
    blocks = parse_markdown_blocks("Price is $5 and $10 total.\n")
    (block,) = blocks
    assert isinstance(block, ParagraphBlock)
    spans = parse_inline(block.text)
    assert not any(s.math for s in spans)


def test_footnotes_collected_and_referenced() -> None:
    md = "Body text[^1] here.\n\n[^1]: The source.\n"
    blocks = parse_markdown_blocks(md)
    notes = next(b for b in blocks if isinstance(b, FootnotesBlock))
    assert notes.items[0].label == "1"
    assert notes.items[0].text == "The source."
    para = next(b for b in blocks if isinstance(b, ParagraphBlock))
    spans = parse_inline(para.text)
    assert any(s.sup and s.text == "1" for s in spans)


def test_definition_list() -> None:
    md = "Term A\n: First def.\n: Second def.\n\nTerm B\n: Other.\n"
    (block,) = parse_markdown_blocks(md)
    assert isinstance(block, DefinitionListBlock)
    assert [it.term for it in block.items] == ["Term A", "Term B"]
    assert block.items[0].definitions == ["First def.", "Second def."]


def test_front_matter_metadata() -> None:
    md = "---\ntitle: 测试\nauthor: Team\ntoc: true\n---\n\n# Heading\n"
    meta, blocks = parse_markdown_document(md)
    assert meta == {"title": "测试", "author": "Team", "toc": True}
    assert blocks and blocks[0].type == "heading"


def test_front_matter_date_coerced_to_string() -> None:
    import datetime as dt

    from leagent.docgen.model import DocumentSpec

    md = "---\ntitle: Resume\ndate: 2026-07-10\n---\n\n# Section\n"
    meta, blocks = parse_markdown_document(md)
    assert meta["date"] == dt.date(2026, 7, 10)
    spec = DocumentSpec.model_validate(
        {
            "title": meta["title"],
            "date": meta["date"],
            "blocks": blocks,
        }
    )
    assert spec.date == "2026-07-10"


def test_front_matter_absent() -> None:
    meta, blocks = parse_markdown_document("# Just content\n")
    assert meta == {}
    assert len(blocks) == 1


def test_linkify_bare_url() -> None:
    pytest.importorskip("linkify_it")
    spans = parse_inline("see https://example.com now")
    link = next(s for s in spans if s.link)
    assert link.link.startswith("https://example.com")


# ---------------------------------------------------------------------------
# Cross-format rendering
# ---------------------------------------------------------------------------

_MATH_MD = (
    "# Math\n\n"
    "Inline $x^2 + \\alpha$ with a footnote[^1].\n\n"
    "$$\n\\int_0^1 x\\,dx = \\frac{1}{2}\n$$\n\n"
    "Term\n: A definition.\n\n"
    "[^1]: Note text.\n"
)


def _spec(**kwargs) -> DocumentSpec:
    payload = {"title": "Math Test", "blocks": parse_markdown_blocks(_MATH_MD)}
    payload.update(kwargs)
    return DocumentSpec.model_validate(payload)


def test_render_pdf_math_native_vector(tmp_path: Path) -> None:
    from leagent.docgen.renderers.pdf import render_pdf

    result = render_pdf(_spec(), tmp_path / "math.pdf")
    assert result["success"] is True
    assert result["content_stats"]["equations"] == 1

    fitz = pytest.importorskip("fitz")
    doc = fitz.open(str(tmp_path / "math.pdf"))
    try:
        page = doc[0]
        # Display math is drawn as native vector paths (not raster).
        assert len(page.get_drawings()) > 0
        # Only the inline fragment is a raster image (ReportLab inline limit).
        assert len(page.get_images(full=True)) <= 1
        text = page.get_text()
        assert "Term" in text and "Note text" in text
    finally:
        doc.close()


def test_render_pdf_numbered_equation_caption(tmp_path: Path) -> None:
    from leagent.docgen.renderers.pdf import render_pdf

    spec = DocumentSpec.model_validate(
        {
            "title": "Eq",
            "numbered_figures": True,
            "blocks": [{"type": "math", "latex": "a + b", "caption": "Sum rule"}],
        }
    )
    result = render_pdf(spec, tmp_path / "eq.pdf")
    assert result["success"] is True
    fitz = pytest.importorskip("fitz")
    doc = fitz.open(str(tmp_path / "eq.pdf"))
    try:
        assert "Equation 1" in doc[0].get_text()
    finally:
        doc.close()


def test_render_pdf_invalid_math_degrades_to_code(tmp_path: Path) -> None:
    from leagent.docgen.renderers.pdf import render_pdf

    spec = DocumentSpec.model_validate(
        {"title": "Bad", "blocks": [{"type": "math", "latex": "\\frac{1}{"}]}
    )
    result = render_pdf(spec, tmp_path / "bad.pdf")
    assert result["success"] is True
    assert any("Math could not be rendered" in w for w in result["warnings"])


def test_render_docx_math_native_omml(tmp_path: Path) -> None:
    import zipfile

    import docx as docx_lib

    from leagent.docgen.renderers.docx import render_docx

    result = render_docx(_spec(), tmp_path / "math.docx")
    assert result["success"] is True
    assert result["content_stats"]["equations"] == 1

    with zipfile.ZipFile(tmp_path / "math.docx") as z:
        doc_xml = z.read("word/document.xml").decode("utf-8")
    # Native, editable OMML equations — no rasterised math pictures.
    assert doc_xml.count("<m:oMath") >= 2  # 1 inline + 1 display
    assert "<m:oMathPara" in doc_xml
    assert "<w:drawing" not in doc_xml
    # Round-trips through python-docx.
    d = docx_lib.Document(str(tmp_path / "math.docx"))
    all_text = "\n".join(p.text for p in d.paragraphs)
    assert "Note text" in all_text


def test_render_html_math(tmp_path: Path) -> None:
    from leagent.docgen.renderers.html import render_html

    result = render_html(_spec(), tmp_path / "math.html")
    assert result["success"] is True
    text = (tmp_path / "math.html").read_text(encoding="utf-8")
    assert "math-inline" in text
    assert "math-display" in text
    assert "<dl>" in text and "<dt>" in text
    assert 'class="footnotes"' in text


def test_render_markdown_roundtrip(tmp_path: Path) -> None:
    from leagent.docgen.renderers.html import render_markdown

    result = render_markdown(_spec(), tmp_path / "math.md")
    assert result["success"] is True
    text = (tmp_path / "math.md").read_text(encoding="utf-8")
    assert "$$" in text
    assert "[^1]: Note text." in text
    assert ": A definition." in text
    # Round-trips: the emitted markdown parses back to the same block types.
    reparsed = parse_markdown_blocks(text)
    assert any(isinstance(b, MathBlock) for b in reparsed)
    assert any(isinstance(b, FootnotesBlock) for b in reparsed)
    assert any(isinstance(b, DefinitionListBlock) for b in reparsed)


def test_render_pptx_math_native_omml(tmp_path: Path) -> None:
    import zipfile

    from pptx import Presentation

    from leagent.docgen.renderers.pptx import render_pptx

    deck = DeckSpec.model_validate(
        {
            "title": "Deck",
            "slides": [
                {
                    "layout": "content",
                    "title": "Formulas",
                    "body": "- Energy $E = mc^2$\n- Bound $\\alpha \\le \\beta_1$",
                }
            ],
        }
    )
    result = render_pptx(deck, tmp_path / "math.pptx")
    assert result["success"] is True

    with zipfile.ZipFile(tmp_path / "math.pptx") as z:
        slide_xml = z.read("ppt/slides/slide2.xml").decode("utf-8")
    # Native OMML behind an mc:AlternateContent choice ...
    assert "AlternateContent" in slide_xml
    assert "oMath" in slide_xml
    assert "office/drawing/2010/main" in slide_xml  # a14 namespace
    # ... with a Unicode fallback so non-supporting viewers still show math.
    assert "mc²" in slide_xml and "≤" in slide_xml
    # Round-trips through python-pptx.
    prs = Presentation(str(tmp_path / "math.pptx"))
    assert len(prs.slides._sldIdLst) == 2  # noqa: SLF001
