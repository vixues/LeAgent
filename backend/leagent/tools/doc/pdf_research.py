"""Agent-facing PDF research tools (structure, citations, summary, translation).

These wrap :mod:`leagent.tools.doc.pdf_research_core` so the agent can reason
about a paper the same way the Research Paper Mode UI does. The factory
auto-generates ``Tool.<name>`` workflow nodes for each.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext, ToolResult
from leagent.tools.doc.pdf_research_core import (
    extract_citations,
    extract_page_text,
    extract_region_text,
    extract_structure,
)

logger = structlog.get_logger(__name__)

_SUMMARY_CHAR_BUDGET = 16_000


class PDFStructureTool(BaseTool):
    """Extract a paper's outline, sections, and figure/table list."""

    name = "pdf_structure"
    description = (
        "Analyze a PDF's structure: page count, title, outline/bookmarks, "
        "heuristic section headings, and detected figures/tables with page numbers. "
        "Use before summarizing or navigating an academic paper."
    )
    category = ToolCategory.DOC
    is_read_only = True
    is_concurrency_safe = True
    path_params = ("file_path",)
    search_hint = "pdf outline sections figures structure paper"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the PDF file.",
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        del context
        try:
            data = extract_structure(params["file_path"])
            return ToolResult(success=True, data=data)
        except Exception as exc:  # noqa: BLE001 - surface as tool error
            logger.warning("pdf_structure_failed", error=str(exc))
            return ToolResult(success=False, error=str(exc))


class CitationExtractorTool(BaseTool):
    """Extract the reference/bibliography list from a PDF."""

    name = "citation_extractor"
    description = (
        "Extract the reference list from an academic PDF. Returns each entry with "
        "its marker (e.g. [1]), full text, and any DOI/URL detected."
    )
    category = ToolCategory.DOC
    is_read_only = True
    is_concurrency_safe = True
    path_params = ("file_path",)
    search_hint = "pdf references citations bibliography doi extract"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the PDF file.",
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        del context
        try:
            citations = extract_citations(params["file_path"])
            return ToolResult(
                success=True,
                data={"citations": citations, "count": len(citations)},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("citation_extractor_failed", error=str(exc))
            return ToolResult(success=False, error=str(exc))


class SectionSummarizerTool(BaseTool):
    """Summarize a page range / section of a PDF with the LLM."""

    name = "section_summarizer"
    description = (
        "Summarize a PDF page range (or whole paper) into a concise, structured "
        "summary. Provide start_page/end_page to target a specific section."
    )
    category = ToolCategory.DOC
    is_read_only = True
    path_params = ("file_path",)
    search_hint = "summarize pdf paper section abstract tldr"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Path to the PDF file."},
                "start_page": {
                    "type": "integer",
                    "description": "1-based first page (inclusive). Omit for whole document.",
                },
                "end_page": {
                    "type": "integer",
                    "description": "1-based last page (inclusive). Omit for whole document.",
                },
                "section_title": {
                    "type": "string",
                    "description": "Optional section label for context.",
                },
                "target_lang": {
                    "type": "string",
                    "description": "Optional output language code (e.g. en, zh-CN).",
                },
            },
            "required": ["file_path"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.llm is None:
            return ToolResult(success=False, error="LLM client not available.")
        try:
            text = extract_page_text(
                params["file_path"],
                params.get("start_page"),
                params.get("end_page"),
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=str(exc))
        if not text.strip():
            return ToolResult(
                success=False,
                error="No extractable text (the PDF may be scanned; try OCR).",
            )
        summary = await summarize_text(
            context.llm,
            text[:_SUMMARY_CHAR_BUDGET],
            section_title=params.get("section_title"),
            target_lang=params.get("target_lang"),
        )
        return ToolResult(
            success=True,
            data={"summary": summary, "section_title": params.get("section_title")},
        )


class PDFTranslateTool(BaseTool):
    """Translate free text or a PDF page region."""

    name = "pdf_translate"
    description = (
        "Translate text into a target language. Either pass `text`, or pass "
        "`file_path` + `page` + `bbox` to translate a region of a PDF page."
    )
    category = ToolCategory.DOC
    is_read_only = True
    path_params = ("file_path",)
    search_hint = "translate pdf region text language"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to translate."},
                "file_path": {
                    "type": "string",
                    "description": "PDF path (for region translation).",
                },
                "page": {"type": "integer", "description": "1-based page number."},
                "bbox": {
                    "type": "array",
                    "items": {"type": "number"},
                    "description": "Region [x0, y0, x1, y1] in PDF points (top-left origin).",
                },
                "target_lang": {
                    "type": "string",
                    "description": "Target language code (e.g. en, zh-CN). Defaults to en.",
                },
            },
            "required": [],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        if context.llm is None:
            return ToolResult(success=False, error="LLM client not available.")
        target_lang = params.get("target_lang") or "en"
        source = params.get("text") or ""
        if not source and params.get("file_path") and params.get("page") and params.get("bbox"):
            bbox = params["bbox"]
            if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
                return ToolResult(success=False, error="bbox must be [x0, y0, x1, y1].")
            try:
                source = extract_region_text(
                    params["file_path"], int(params["page"]), tuple(float(v) for v in bbox)
                )
            except Exception as exc:  # noqa: BLE001
                return ToolResult(success=False, error=str(exc))
        if not source.strip():
            return ToolResult(success=False, error="No text to translate.")
        translated = await translate_text(context.llm, source, target_lang)
        return ToolResult(
            success=True,
            data={
                "source_text": source,
                "translated_text": translated,
                "target_lang": target_lang,
            },
        )


# ---------------------------------------------------------------------------
# Shared LLM prompt helpers (used by tools and the /api/v1/pdf endpoints).
# ---------------------------------------------------------------------------


def build_summary_prompt(
    text: str, *, section_title: str | None, target_lang: str | None
) -> str:
    scope = f'the section "{section_title}"' if section_title else "this academic content"
    lang = f"\nWrite the summary in {target_lang}." if target_lang else ""
    return (
        f"Summarize {scope} for a researcher. Produce a concise, structured summary "
        f"with the key idea, method/approach, and main findings or takeaways. "
        f"Use short paragraphs or bullet points; do not invent content.{lang}\n\n"
        f"---\n{text}\n---"
    )


def build_translate_prompt(text: str, target_lang: str) -> str:
    return (
        f"Translate the following text into {target_lang}. Preserve technical terms, "
        f"math notation, and formatting. Return only the translation without notes.\n\n"
        f"---\n{text}\n---"
    )


def build_formula_extraction_prompt(tagged_text: str) -> str:
    """Prompt the LLM to extract every distinct equation as renderable LaTeX.

    ``tagged_text`` is page text annotated with ``[[PAGE n]]`` markers so the
    model can attribute each formula to a page.
    """
    return (
        "You are a meticulous scientific document parser. From the paper text "
        "below, extract EVERY distinct, non-trivial mathematical equation or "
        "formula (display equations, key inline equations, loss/objective "
        "functions, definitions). Ignore plain numbers, citation markers, and "
        "section numbers.\n\n"
        "For each formula return an object with:\n"
        '- "latex": valid LaTeX for the formula WITHOUT surrounding $ or \\[ \\] '
        "delimiters. Reconstruct broken/garbled math faithfully.\n"
        '- "page": the integer page number (from the nearest preceding '
        "[[PAGE n]] marker).\n"
        '- "label": the equation number if present (e.g. "(3)"), else "".\n'
        '- "description": one concise plain-language sentence on what it computes '
        "or means.\n\n"
        "Return ONLY a JSON array (no prose, no code fences). If there are no "
        "formulas, return []. Deduplicate identical formulas.\n\n"
        f"---\n{tagged_text}\n---"
    )


def parse_formula_json(raw: str) -> list[dict[str, Any]]:
    """Parse the LLM's formula JSON robustly (tolerates fences / surrounding prose)."""
    import json

    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        # Drop an optional leading ``json`` language tag.
        if text[:4].lower() == "json":
            text = text[4:]
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        data = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        latex = str(item.get("latex") or "").strip()
        if not latex:
            continue
        try:
            page = int(item.get("page") or 0)
        except (ValueError, TypeError):
            page = 0
        out.append(
            {
                "id": f"eq-{i}",
                "latex": latex,
                "page": page if page > 0 else None,
                "label": str(item.get("label") or "").strip(),
                "description": str(item.get("description") or "").strip()[:400],
            }
        )
    return out


async def summarize_text(
    llm: Any, text: str, *, section_title: str | None = None, target_lang: str | None = None
) -> str:
    """Summarize via the tool LLM client (returns plain text)."""
    prompt = build_summary_prompt(text, section_title=section_title, target_lang=target_lang)
    response = await llm.complete(prompt, max_tokens=800)
    return (response or "").strip()


async def translate_text(llm: Any, text: str, target_lang: str) -> str:
    """Translate via the tool LLM client (returns plain text)."""
    prompt = build_translate_prompt(text, target_lang)
    response = await llm.complete(prompt, max_tokens=1200)
    return (response or "").strip()
