"""Pure PyMuPDF helpers powering the PDF Research Mode.

These functions are framework-agnostic (no FastAPI / LLM coupling) so they can be
reused by both the ``/api/v1/pdf`` endpoints and the agent-facing BaseTools.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_SECTION_KEYWORDS = (
    "abstract",
    "introduction",
    "background",
    "related work",
    "preliminaries",
    "methodology",
    "methods",
    "approach",
    "model",
    "experiments",
    "experimental setup",
    "evaluation",
    "results",
    "analysis",
    "discussion",
    "ablation",
    "limitations",
    "conclusion",
    "conclusions",
    "future work",
    "acknowledgments",
    "acknowledgements",
    "references",
    "bibliography",
    "appendix",
)

# Numbered headings like "3", "3.1", "3.1.2" followed by a title.
_NUMBERED_HEADING_RE = re.compile(r"^(\d+(?:\.\d+){0,2})\.?\s+([A-Z][^\n]{2,80})$")
_FIGURE_RE = re.compile(r"\b(Fig(?:ure)?|Table)\s*\.?\s*([0-9]+|[IVX]+)\b", re.IGNORECASE)
_DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
_URL_RE = re.compile(r"https?://[^\s)]+", re.IGNORECASE)


def _import_fitz():
    try:
        import fitz

        return fitz
    except ImportError as exc:  # pragma: no cover - exercised only without dep
        raise RuntimeError(
            "PyMuPDF is not installed. Install with: pip install pymupdf"
        ) from exc


def _open(file_path: str):
    fitz = _import_fitz()
    fp = Path(file_path)
    if not fp.exists():
        raise FileNotFoundError(f"PDF file not found: {fp}")
    return fitz.open(str(fp))


def _heading_level(title: str, numbering: str | None) -> int:
    if numbering:
        return min(3, numbering.count(".") + 1)
    return 1


def extract_structure(file_path: str) -> dict[str, Any]:
    """Return page count, title, outline, heuristic sections, and figures/tables."""
    doc = _open(file_path)
    try:
        page_count = len(doc)
        meta_title = (doc.metadata or {}).get("title") or None

        outline: list[dict[str, Any]] = []
        toc = doc.get_toc(simple=True) or []
        for entry in toc:
            level, title, page = entry[0], entry[1], entry[2]
            title = (title or "").strip()
            if not title:
                continue
            outline.append(
                {"title": title, "page": page if page and page > 0 else None, "level": level}
            )

        sections = _derive_sections(doc, outline, page_count)
        figures = _derive_figures(doc, page_count)

        return {
            "page_count": page_count,
            "title": meta_title,
            "outline": outline,
            "sections": sections,
            "figures": figures,
        }
    finally:
        doc.close()


def _derive_sections(doc, outline: list[dict[str, Any]], page_count: int) -> list[dict[str, Any]]:
    """Use the PDF outline when available, else scan for heading-like lines."""
    sections: list[dict[str, Any]] = []
    if outline:
        for i, node in enumerate(outline):
            if node["level"] <= 2 and node["page"]:
                sections.append(
                    {
                        "id": f"sec-{i}",
                        "title": node["title"],
                        "page": node["page"],
                        "level": node["level"],
                    }
                )
        if sections:
            return sections[:80]

    # Heuristic scan (text-only papers without embedded bookmarks).
    seen: set[str] = set()
    idx = 0
    scan_pages = min(page_count, 40)
    for p in range(scan_pages):
        page = doc[p]
        for raw in page.get_text("text").splitlines():
            line = raw.strip()
            if not line or len(line) > 90:
                continue
            match = _NUMBERED_HEADING_RE.match(line)
            numbering = None
            title = None
            if match:
                numbering, title = match.group(1), match.group(2).strip()
            elif line.lower() in _SECTION_KEYWORDS or (
                line.isupper() and 3 <= len(line) <= 40 and line.lower() in _SECTION_KEYWORDS
            ):
                title = line.title() if line.isupper() else line
            elif line.lower().rstrip(":") in _SECTION_KEYWORDS:
                title = line.rstrip(":")
            if not title:
                continue
            key = title.lower()
            if key in seen:
                continue
            seen.add(key)
            sections.append(
                {
                    "id": f"sec-{idx}",
                    "title": (f"{numbering} {title}" if numbering else title).strip(),
                    "page": p + 1,
                    "level": _heading_level(title, numbering),
                }
            )
            idx += 1
    return sections[:80]


def _derive_figures(doc, page_count: int) -> list[dict[str, Any]]:
    """Detect figure/table references and the first page each appears on.

    Each figure also carries a ``bbox`` ([x0, y0, x1, y1] in PDF points, top-left
    origin) locating its caption — and, for figures, the nearest image above the
    caption — so the reader can highlight the region on the page.
    """
    figures: list[dict[str, Any]] = []
    seen: set[str] = set()
    for p in range(page_count):
        page = doc[p]
        text = page.get_text("text")
        for match in _FIGURE_RE.finditer(text):
            kind_raw = match.group(1).lower()
            number = match.group(2)
            kind = "table" if kind_raw.startswith("table") else "figure"
            label = f"{'Table' if kind == 'table' else 'Figure'} {number}"
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            entry: dict[str, Any] = {
                "id": f"fig-{len(figures)}",
                "label": label,
                "page": p + 1,
                "kind": kind,
            }
            bbox = _figure_bbox(page, number, kind)
            if bbox:
                entry["bbox"] = bbox
            figures.append(entry)
    # Stable order: figures then tables, by page.
    figures.sort(key=lambda f: (f["kind"] != "figure", f["page"]))
    return figures[:120]


def _figure_bbox(page, number: str, kind: str) -> list[float] | None:
    """Best-effort bounding box for a figure/table caption (PDF points)."""
    try:
        words = page.get_text("words")  # (x0, y0, x1, y1, word, block, line, word)
    except Exception:  # noqa: BLE001 - defensive against odd PDFs
        return None

    caption: list[float] | None = None
    for i, w in enumerate(words):
        token = str(w[4]).lower().strip(".:")
        if token not in {"figure", "fig", "table"}:
            continue
        line_words = [ww for ww in words if ww[5] == w[5] and ww[6] == w[6]]
        line_text = " ".join(str(ww[4]) for ww in line_words)
        if not re.search(rf"\b{re.escape(number)}\b", line_text):
            continue
        x0 = min(ww[0] for ww in line_words)
        y0 = min(ww[1] for ww in line_words)
        x1 = max(ww[2] for ww in line_words)
        y1 = max(ww[3] for ww in line_words)
        caption = [float(x0), float(y0), float(x1), float(y1)]
        break

    if caption is None:
        return None

    # For figures, extend the box to include the closest image sitting above the
    # caption (captions usually sit below the figure they describe).
    if kind == "figure":
        try:
            images = page.get_image_info() or []
        except Exception:  # noqa: BLE001
            images = []
        best: tuple[float, list[float]] | None = None
        for info in images:
            ib = info.get("bbox") if isinstance(info, dict) else None
            if not ib or len(ib) != 4:
                continue
            # image bottom must be above the caption top, with horizontal overlap
            if ib[3] > caption[1] + 4:
                continue
            if ib[2] < caption[0] or ib[0] > caption[2]:
                continue
            gap = caption[1] - ib[3]
            if gap < 0:
                continue
            if best is None or gap < best[0]:
                best = (gap, [float(ib[0]), float(ib[1]), float(ib[2]), float(ib[3])])
        if best is not None:
            img = best[1]
            caption = [
                min(caption[0], img[0]),
                min(caption[1], img[1]),
                max(caption[2], img[2]),
                max(caption[3], img[3]),
            ]

    return caption


_MATH_SYMBOLS = (
    "=≈≤≥≠∑∫∏√∞±×÷·∂∇∈∉⊂⊆⊃∪∩∀∃∝⇒⇔→←↦∼≜ℓ"
    "αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ"
)
_MATH_HINT_RE = re.compile(
    r"[" + re.escape(_MATH_SYMBOLS) + r"]|\\(?:frac|sum|int|prod|sqrt|partial|nabla)"
    r"|\^\{?\w|_\{?\w",
)
_MATH_NOISE_RE = re.compile(r"https?://|www\.|doi[:.]|©|\bfig(?:ure)?\b|\btable\b", re.IGNORECASE)
_EQ_LABEL_RE = re.compile(r"\(\s*(\d{1,3}[a-z]?)\s*\)\s*$")


def extract_formula_candidates(file_path: str, max_items: int = 60) -> list[dict[str, Any]]:
    """Heuristic, LLM-free fallback: scan for equation-like lines.

    Returns the same shape as the LLM extractor (``id``/``latex``/``page``/
    ``label``/``description``) but flags each entry ``approx=True`` because the
    captured text is raw (not guaranteed-valid LaTeX).
    """
    doc = _open(file_path)
    try:
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for p in range(len(doc)):
            for raw in doc[p].get_text("text").splitlines():
                line = raw.strip()
                if len(line) < 3 or len(line) > 180:
                    continue
                if _MATH_NOISE_RE.search(line):
                    continue
                hits = _MATH_HINT_RE.findall(line)
                if not hits:
                    continue
                # Skip prose: a line with many words but only one weak symbol.
                words = [w for w in re.split(r"\s+", line) if w]
                if len(words) > 14 and len(hits) < 2:
                    continue
                key = re.sub(r"\s+", "", line)
                if key in seen:
                    continue
                seen.add(key)
                label_match = _EQ_LABEL_RE.search(line)
                label = f"({label_match.group(1)})" if label_match else ""
                latex = line
                if label:
                    latex = _EQ_LABEL_RE.sub("", latex).strip()
                out.append(
                    {
                        "id": f"eq-{len(out)}",
                        "latex": latex,
                        "page": p + 1,
                        "label": label,
                        "description": "",
                        "approx": True,
                    }
                )
                if len(out) >= max_items:
                    return out
        return out
    finally:
        doc.close()


def extract_pages_text_tagged(
    file_path: str, *, max_pages: int = 40, char_budget: int = 24_000
) -> str:
    """Return page text annotated with ``[[PAGE n]]`` markers for LLM extraction."""
    doc = _open(file_path)
    try:
        total = min(len(doc), max_pages)
        parts: list[str] = []
        used = 0
        for p in range(total):
            body = doc[p].get_text("text").strip()
            if not body:
                continue
            chunk = f"[[PAGE {p + 1}]]\n{body}"
            if used + len(chunk) > char_budget:
                parts.append(chunk[: max(0, char_budget - used)])
                break
            parts.append(chunk)
            used += len(chunk)
        return "\n\n".join(parts)
    finally:
        doc.close()


def extract_page_text(file_path: str, start_page: int | None, end_page: int | None) -> str:
    """Extract plain text for an inclusive 1-based page range (whole doc if None)."""
    doc = _open(file_path)
    try:
        total = len(doc)
        start = max(1, start_page or 1)
        end = min(total, end_page or total)
        parts: list[str] = []
        for p in range(start - 1, end):
            parts.append(doc[p].get_text("text").strip())
        return "\n\n".join(part for part in parts if part)
    finally:
        doc.close()


def extract_region_text(
    file_path: str, page: int, bbox: tuple[float, float, float, float]
) -> str:
    """Extract text within a bbox (PDF points, origin top-left) on a 1-based page."""
    fitz = _import_fitz()
    doc = _open(file_path)
    try:
        if page < 1 or page > len(doc):
            return ""
        clip = fitz.Rect(*bbox)
        return doc[page - 1].get_text("text", clip=clip).strip()
    finally:
        doc.close()


def extract_citations(file_path: str, max_items: int = 200) -> list[dict[str, Any]]:
    """Extract reference list entries from the References/Bibliography section."""
    doc = _open(file_path)
    try:
        page_count = len(doc)
        # Find the references section start (scan from the back half).
        ref_text_parts: list[str] = []
        started = False
        for p in range(page_count):
            text = doc[p].get_text("text")
            if not started:
                head = "\n".join(text.splitlines()[:6]).lower()
                if re.search(r"\b(references|bibliography)\b", head) or re.search(
                    r"^\s*(references|bibliography)\s*$",
                    text,
                    re.IGNORECASE | re.MULTILINE,
                ):
                    started = True
                    # Keep text after the heading on this page.
                    split = re.split(
                        r"\b(references|bibliography)\b", text, maxsplit=1, flags=re.IGNORECASE
                    )
                    ref_text_parts.append(split[-1] if len(split) > 1 else text)
                    continue
            if started:
                ref_text_parts.append(text)
        if not started:
            return []

        blob = "\n".join(ref_text_parts)
        entries = _split_reference_entries(blob)
        citations: list[dict[str, Any]] = []
        for i, entry in enumerate(entries[:max_items]):
            marker_match = re.match(r"^\s*[\[(]?(\d{1,3})[\]).]", entry)
            marker = f"[{marker_match.group(1)}]" if marker_match else ""
            doi_match = _DOI_RE.search(entry)
            url_match = _URL_RE.search(entry)
            citations.append(
                {
                    "id": f"cit-{i}",
                    "marker": marker,
                    "text": re.sub(r"\s+", " ", entry).strip()[:600],
                    "doi": doi_match.group(0) if doi_match else None,
                    "url": url_match.group(0) if url_match else None,
                }
            )
        return citations
    finally:
        doc.close()


def _split_reference_entries(blob: str) -> list[str]:
    """Split a reference blob into individual entries via numbered markers."""
    blob = blob.strip()
    if not blob:
        return []
    # Prefer numbered markers: "[1]" / "1." at line starts.
    numbered = re.split(r"\n\s*(?=\[\d{1,3}\]|\(\d{1,3}\)|\d{1,3}\.\s)", "\n" + blob)
    numbered = [e.strip() for e in numbered if e.strip()]
    if len(numbered) >= 3:
        return numbered
    # Fallback: blank-line separated blocks.
    blocks = re.split(r"\n\s*\n", blob)
    blocks = [b.strip() for b in blocks if len(b.strip()) > 20]
    if len(blocks) >= 3:
        return blocks
    # Last resort: single-line entries.
    return [l.strip() for l in blob.splitlines() if len(l.strip()) > 20]
