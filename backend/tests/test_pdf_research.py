"""Tests for PDF Research Mode core helpers and agent-facing tools."""

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
def paper_pdf(tmp_path: Path) -> Path:
    """A small paper-like PDF: title, sections, a figure caption, references."""
    import fitz

    path = tmp_path / "paper.pdf"
    doc = fitz.open()

    page1 = doc.new_page()
    page1.insert_text(
        (72, 72),
        "A Study of Widgets\n\n"
        "Abstract\n"
        "We study widgets and report strong results on the widget benchmark.\n\n"
        "1 Introduction\n"
        "Widgets are important. See Figure 1 for an overview.\n\n"
        "2 Methods\n"
        "We use a transformer over widget tokens.",
    )

    page2 = doc.new_page()
    page2.insert_text(
        (72, 72),
        "3 Results\n"
        "Our method beats the baseline. Table 1 lists the numbers.\n\n"
        "4 Conclusion\n"
        "Widgets work.\n\n"
        "References\n"
        "[1] A. Author. Widget theory. Journal of Widgets, 2020. "
        "https://doi.org/10.1234/widget.2020\n"
        "[2] B. Builder. More widgets. Widget Press, 2021.\n"
        "[3] C. Creator. Even more widgets. arXiv, 2022.",
    )

    doc.set_metadata({"title": "A Study of Widgets", "author": "Tester"})
    doc.save(str(path))
    doc.close()
    return path


# --------------------------------------------------------------------------- #
# Core helpers
# --------------------------------------------------------------------------- #


def test_extract_structure(paper_pdf: Path) -> None:
    from leagent.tools.doc.pdf_research_core import extract_structure

    data = extract_structure(str(paper_pdf))
    assert data["page_count"] == 2
    titles = {s["title"].lower() for s in data["sections"]}
    # Heuristic section scan should find these headings.
    assert any("introduction" in t for t in titles)
    assert any("methods" in t for t in titles)
    fig_labels = {f["label"].lower() for f in data["figures"]}
    assert "figure 1" in fig_labels
    assert "table 1" in fig_labels


def test_extract_page_text_range(paper_pdf: Path) -> None:
    from leagent.tools.doc.pdf_research_core import extract_page_text

    p1 = extract_page_text(str(paper_pdf), 1, 1)
    assert "Abstract" in p1
    assert "References" not in p1
    full = extract_page_text(str(paper_pdf), None, None)
    assert "References" in full


def test_extract_citations(paper_pdf: Path) -> None:
    from leagent.tools.doc.pdf_research_core import extract_citations

    citations = extract_citations(str(paper_pdf))
    assert len(citations) >= 3
    markers = {c["marker"] for c in citations}
    assert "[1]" in markers
    doi_hit = [c for c in citations if c["doi"]]
    assert doi_hit and doi_hit[0]["doi"].startswith("10.1234/")


def test_extract_region_text(paper_pdf: Path) -> None:
    from leagent.tools.doc.pdf_research_core import extract_region_text

    # Region covering the top-left text block on page 1.
    text = extract_region_text(str(paper_pdf), 1, (60, 60, 400, 120))
    assert "Widgets" in text or "Study" in text


def test_figures_carry_bbox(paper_pdf: Path) -> None:
    from leagent.tools.doc.pdf_research_core import extract_structure

    figures = extract_structure(str(paper_pdf))["figures"]
    by_label = {f["label"].lower(): f for f in figures}
    fig1 = by_label["figure 1"]
    assert "bbox" in fig1
    assert len(fig1["bbox"]) == 4
    x0, y0, x1, y1 = fig1["bbox"]
    assert x1 > x0 and y1 > y0


def test_extract_pages_text_tagged(paper_pdf: Path) -> None:
    from leagent.tools.doc.pdf_research_core import extract_pages_text_tagged

    tagged = extract_pages_text_tagged(str(paper_pdf))
    assert "[[PAGE 1]]" in tagged
    assert "[[PAGE 2]]" in tagged
    assert tagged.index("[[PAGE 1]]") < tagged.index("[[PAGE 2]]")


def test_parse_formula_json_variants() -> None:
    from leagent.tools.doc.pdf_research import parse_formula_json

    fenced = (
        "```json\n"
        '[{"latex": "E = mc^2", "page": 2, "label": "(1)", "description": "energy"},\n'
        ' {"latex": "", "page": 3},\n'
        ' {"latex": "a^2 + b^2 = c^2", "page": 0, "label": "", "description": ""}]\n'
        "```"
    )
    out = parse_formula_json(fenced)
    assert len(out) == 2  # empty-latex item dropped
    assert out[0]["latex"] == "E = mc^2"
    assert out[0]["page"] == 2
    assert out[1]["page"] is None  # page 0 normalised to None
    assert parse_formula_json("not json at all") == []


def test_build_formula_extraction_prompt() -> None:
    from leagent.tools.doc.pdf_research import build_formula_extraction_prompt

    prompt = build_formula_extraction_prompt("[[PAGE 1]]\nx = y + 1")
    assert "JSON array" in prompt
    assert "latex" in prompt
    assert "[[PAGE 1]]" in prompt


def test_extract_formula_candidates(tmp_path: Path) -> None:
    """The LLM-free fallback should capture equation-like lines and skip prose."""
    import fitz

    from leagent.tools.doc.pdf_research_core import extract_formula_candidates

    path = tmp_path / "eqs.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text(
        (72, 72),
        "Introduction\n"
        "We define the loss as L = sum_i (y_i - x_i)^2 (3)\n"
        "This is an ordinary prose sentence without any mathematics here.\n"
        "E = mc^2",
    )
    doc.save(str(path))
    doc.close()

    out = extract_formula_candidates(str(path))
    latexes = [o["latex"] for o in out]
    assert any("mc^2" in s for s in latexes)
    assert all(o["approx"] is True for o in out)
    # The numbered equation keeps its label and strips it from the body.
    labeled = [o for o in out if o["label"] == "(3)"]
    assert labeled and "(3)" not in labeled[0]["latex"]
    # Pure prose is ignored.
    assert not any("ordinary prose sentence" in s for s in latexes)


# --------------------------------------------------------------------------- #
# Agent-facing tools
# --------------------------------------------------------------------------- #


def _ctx(llm=None) -> ToolContext:
    return ToolContext(user_id="u1", session_id="s1", llm=llm)


@pytest.mark.asyncio
async def test_pdf_structure_tool(paper_pdf: Path) -> None:
    from leagent.tools.doc.pdf_research import PDFStructureTool

    result = await PDFStructureTool().execute({"file_path": str(paper_pdf)}, _ctx())
    assert result.success
    assert result.data["page_count"] == 2


@pytest.mark.asyncio
async def test_citation_extractor_tool(paper_pdf: Path) -> None:
    from leagent.tools.doc.pdf_research import CitationExtractorTool

    result = await CitationExtractorTool().execute({"file_path": str(paper_pdf)}, _ctx())
    assert result.success
    assert result.data["count"] >= 3


@pytest.mark.asyncio
async def test_section_summarizer_tool_uses_llm(paper_pdf: Path) -> None:
    from leagent.tools.doc.pdf_research import SectionSummarizerTool

    class _StubLLM:
        last_prompt = ""

        async def complete(self, prompt, max_tokens=0):  # noqa: ANN001
            _StubLLM.last_prompt = prompt
            return "SUMMARY: widgets are great."

    stub = _StubLLM()
    result = await SectionSummarizerTool().execute(
        {"file_path": str(paper_pdf), "start_page": 1, "end_page": 1}, _ctx(stub)
    )
    assert result.success
    assert "widgets are great" in result.data["summary"].lower()
    assert "Abstract" in stub.last_prompt


@pytest.mark.asyncio
async def test_section_summarizer_requires_llm(paper_pdf: Path) -> None:
    from leagent.tools.doc.pdf_research import SectionSummarizerTool

    result = await SectionSummarizerTool().execute(
        {"file_path": str(paper_pdf)}, _ctx(None)
    )
    assert not result.success


@pytest.mark.asyncio
async def test_pdf_translate_tool_text(paper_pdf: Path) -> None:
    from leagent.tools.doc.pdf_research import PDFTranslateTool

    class _StubLLM:
        async def complete(self, prompt, max_tokens=0):  # noqa: ANN001
            return "[translated] hello"

    result = await PDFTranslateTool().execute(
        {"text": "hello", "target_lang": "zh-CN"}, _ctx(_StubLLM())
    )
    assert result.success
    assert result.data["translated_text"] == "[translated] hello"
    assert result.data["target_lang"] == "zh-CN"


@pytest.mark.asyncio
async def test_pdf_translate_region(paper_pdf: Path) -> None:
    from leagent.tools.doc.pdf_research import PDFTranslateTool

    class _StubLLM:
        seen = ""

        async def complete(self, prompt, max_tokens=0):  # noqa: ANN001
            _StubLLM.seen = prompt
            return "translated-region"

    result = await PDFTranslateTool().execute(
        {
            "file_path": str(paper_pdf),
            "page": 1,
            "bbox": [60, 60, 400, 120],
            "target_lang": "en",
        },
        _ctx(_StubLLM()),
    )
    assert result.success
    assert result.data["translated_text"] == "translated-region"
    assert result.data["source_text"]
