"""Professional PDF renderer (ReportLab platypus).

Highlights over the legacy ``pdf_generator``:

- Fonts are guaranteed via :class:`~leagent.docgen.fonts.FontManager`
  (auto-download) — Chinese never silently degrades to Helvetica without a
  structured warning in the result.
- Real multi-pass table of contents with page numbers and dotted leaders
  (``TableOfContents`` + ``afterFlowable`` notification), plus PDF outline
  bookmarks for every heading.
- Consulting-grade cover page (brand band, logo, left-aligned title block),
  running header/footer with ``{page}/{pages}/{title}/{author}/{date}/
  {section}`` placeholders resolved on a deferred canvas pass, watermark,
  styled tables (zebra striping, repeated header rows), code blocks,
  callouts, metrics rows, and matplotlib charts.
- Precision formatting: optional heading numbering (1 / 1.1 / 1.1.1),
  justified body text with widow/orphan control, per-section page breaks,
  automatic 图/表 (Figure/Table) caption numbering, and true multi-column
  layouts (``ColumnsBlock``). Merge of existing PDFs and encryption via
  pypdf.
- Native vector math: display equations are drawn as real PDF vector paths
  (glyph outlines + fraction/radical bars from :mod:`leagent.docgen.mathtext`)
  — crisp and scalable, never rasterised. Inline math (which must live inside
  a wrapping paragraph, where ReportLab offers no vector fragment) uses a
  high-DPI transparent image.
"""

from __future__ import annotations

import base64
import contextlib
import io
import re
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import structlog

from leagent.docgen.charts import render_chart_png
from leagent.docgen.checklist import (
    checklist_stats,
    priority_meta,
    status_meta,
)
from leagent.docgen.fonts import get_font_manager
from leagent.docgen.images import resolve_image
from leagent.docgen.markdown import InlineSpan, parse_inline
from leagent.docgen.mathtext import (
    MathVector,
    latex_lines,
    latex_to_unicode,
    math_vector_path,
    render_math_png,
)
from leagent.docgen.model import (
    CalloutBlock,
    ChartBlock,
    ChecklistBlock,
    ChecklistItem,
    CodeBlock,
    ColumnsBlock,
    DefinitionListBlock,
    DividerBlock,
    DocumentSpec,
    FootnotesBlock,
    HeadingBlock,
    ImageBlock,
    ListBlock,
    ListItem,
    MathBlock,
    MetricsBlock,
    PageBreakBlock,
    ParagraphBlock,
    QuoteBlock,
    SpacerBlock,
    TableBlock,
    TocBlock,
)
from leagent.docgen.tables import process_table, resolve_table_style
from leagent.docgen.themes import CALLOUT_COLORS, get_theme

logger = structlog.get_logger(__name__)

_SOFT_BREAK_RE = re.compile(r"[A-Za-z0-9_./:@#%+\-]{24,}")
_PLACEHOLDER_RE = re.compile(r"\{(page|pages|title|author|date|section)\}")


def _inject_soft_breaks(text: str, max_len: int = 24) -> str:
    """Insert zero-width breakpoints inside long unspaced tokens."""

    def _chunk(m: re.Match[str]) -> str:
        token = m.group(0)
        return "\u200b".join(token[i : i + max_len] for i in range(0, len(token), max_len))

    return _SOFT_BREAK_RE.sub(_chunk, text)


def _hex_color(colors_mod: Any, value: str, fallback: str = "#000000") -> Any:
    raw = (value or fallback).lstrip("#")
    try:
        r = int(raw[0:2], 16) / 255
        g = int(raw[2:4], 16) / 255
        b = int(raw[4:6], 16) / 255
        return colors_mod.Color(r, g, b)
    except (ValueError, IndexError):
        return colors_mod.black


def spans_to_markup(
    spans: list[InlineSpan],
    *,
    mono_font: str,
    soft_breaks: bool = True,
    math_img: Any = None,
) -> str:
    """Convert inline spans to ReportLab paragraph XML markup.

    ``math_img(latex) -> str | None`` supplies an ``<img …/>`` tag for
    inline math; when absent (or when rendering fails) math falls back to
    italic Unicode text.
    """
    parts: list[str] = []
    for span in spans:
        if span.math:
            rendered = math_img(span.text) if math_img is not None else None
            if rendered:
                parts.append(rendered)
            else:
                parts.append(f"<i>{escape(latex_to_unicode(span.text))}</i>")
            continue
        text = escape(span.text)
        if soft_breaks:
            text = _inject_soft_breaks(text)
        text = text.replace("\n", "<br/>")
        if span.code:
            text = f'<font face="{mono_font}">{text}</font>'
        if span.bold:
            text = f"<b>{text}</b>"
        if span.italic:
            text = f"<i>{text}</i>"
        if span.strike:
            text = f"<strike>{text}</strike>"
        if span.sup:
            text = f"<super>{text}</super>"
        elif span.sub:
            text = f"<sub>{text}</sub>"
        if span.link:
            href = escape(span.link, {'"': "&quot;"})
            text = f'<link href="{href}" color="#2E75B6"><u>{text}</u></link>'
        parts.append(text)
    return "".join(parts)


def _markup(text: str, *, mono_font: str) -> str:
    return spans_to_markup(parse_inline(text), mono_font=mono_font)


def render_pdf(spec: DocumentSpec, output_path: Path) -> dict[str, Any]:
    """Render a document spec to a PDF file."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A3, A4, A5, LEGAL, LETTER, landscape
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas
    from reportlab.platypus import (
        BaseDocTemplate,
        Frame,
        ListFlowable,
        NextPageTemplate,
        PageBreak,
        PageTemplate,
        Paragraph,
        Preformatted,
        Spacer,
        Table,
        TableStyle,
    )
    from reportlab.platypus import (
        Image as RLImage,
    )
    from reportlab.platypus import (
        ListItem as RLListItem,
    )
    from reportlab.platypus.flowables import Flowable, HRFlowable
    from reportlab.platypus.tableofcontents import TableOfContents

    class _VectorMathFlowable(Flowable):
        """Display equation drawn as native PDF vector paths (no raster).

        Fills the glyph outlines + fraction/radical bars produced by
        :func:`~leagent.docgen.mathtext.math_vector_path` directly on the
        canvas, so the equation is crisp and scalable at any zoom / print size.
        """

        def __init__(
            self,
            mv: MathVector,
            fill: Any,
            avail_width: float,
            *,
            top_pad: float = 4.0,
            bottom_pad: float = 4.0,
        ) -> None:
            Flowable.__init__(self)
            self._mv = mv
            self._fill = fill
            self._scale = (
                min(1.0, (avail_width * 0.9) / mv.width) if mv.width else 1.0
            )
            self._top_pad = top_pad
            self._bottom_pad = bottom_pad
            self.width = mv.width * self._scale
            self.height = mv.height * self._scale + top_pad + bottom_pad
            self.hAlign = "CENTER"

        def wrap(self, avail_width: float, avail_height: float) -> tuple[float, float]:
            return self.width, self.height

        def draw(self) -> None:
            canv = self.canv
            canv.saveState()
            canv.translate(0, self._bottom_pad + self._mv.depth * self._scale)
            canv.scale(self._scale, self._scale)
            canv.setFillColor(self._fill)
            path = canv.beginPath()
            for contour in self._mv.contours:
                for op, pts in contour:
                    if op == "m":
                        path.moveTo(pts[0], pts[1])
                    elif op == "l":
                        path.lineTo(pts[0], pts[1])
                    elif op == "c":
                        path.curveTo(pts[0], pts[1], pts[2], pts[3], pts[4], pts[5])
                    elif op == "z":
                        path.close()
            canv.drawPath(path, stroke=0, fill=1)
            canv.restoreState()

    theme = get_theme(spec.theme, kind="document")
    fonts = get_font_manager().register_pdf_fonts()
    font_regular: str = fonts["regular"]
    font_bold: str = fonts["bold"]
    font_mono: str = fonts["mono"]
    warnings: list[str] = list(fonts["warnings"])

    page_sizes = {"A4": A4, "LETTER": LETTER, "LEGAL": LEGAL, "A3": A3, "A5": A5}
    page_size = page_sizes.get(spec.page.size, A4)
    if spec.page.orientation == "landscape":
        page_size = landscape(page_size)
    margins = spec.page.margins

    alignment_map = {
        "left": TA_LEFT,
        "center": TA_CENTER,
        "right": TA_RIGHT,
        "justify": TA_JUSTIFY,
    }

    c = theme.colors
    primary = _hex_color(colors, c.primary)
    accent = _hex_color(colors, c.accent)
    text_color = _hex_color(colors, c.text)
    text_light = _hex_color(colors, c.text_light)
    surface = _hex_color(colors, c.surface)
    border = _hex_color(colors, c.border)

    body_size = theme.sizes.body
    leading = body_size * theme.spacing.line_spacing

    styles: dict[str, ParagraphStyle] = {}
    styles["body"] = ParagraphStyle(
        "DocBody",
        fontName=font_regular,
        fontSize=body_size,
        leading=leading,
        spaceAfter=theme.spacing.paragraph_spacing,
        textColor=text_color,
        wordWrap="CJK",
        alignment=TA_JUSTIFY if spec.justify else TA_LEFT,
        # Widow/orphan control: never leave a single line stranded.
        allowWidows=0,
        allowOrphans=0,
    )
    for level in range(1, 7):
        size = theme.sizes.heading(level)
        styles[f"h{level}"] = ParagraphStyle(
            f"DocH{level}",
            fontName=font_bold,
            fontSize=size,
            leading=size * 1.3,
            spaceBefore=max(10.0, size * 0.9) if level <= 2 else 8.0,
            spaceAfter=max(5.0, size * 0.35),
            textColor=primary if level <= 2 else text_color,
            wordWrap="CJK",
            keepWithNext=1,
        )
    styles["title"] = ParagraphStyle(
        "DocTitle",
        fontName=font_bold,
        fontSize=theme.sizes.title,
        leading=theme.sizes.title * 1.25,
        alignment=TA_CENTER,
        textColor=primary,
        wordWrap="CJK",
    )
    styles["caption"] = ParagraphStyle(
        "DocCaption",
        fontName=font_regular,
        fontSize=theme.sizes.small,
        leading=theme.sizes.small * 1.4,
        alignment=TA_CENTER,
        textColor=text_light,
        spaceBefore=4,
        spaceAfter=10,
        wordWrap="CJK",
    )
    styles["quote"] = ParagraphStyle(
        "DocQuote",
        parent=styles["body"],
        leftIndent=18,
        rightIndent=12,
        fontName=font_regular,
        textColor=text_light,
        borderPadding=(4, 8, 4, 8),
    )
    styles["code"] = ParagraphStyle(
        "DocCode",
        fontName=font_mono,
        fontSize=theme.sizes.code,
        leading=theme.sizes.code * 1.45,
        textColor=text_color,
    )

    stats = {
        "headings": 0,
        "paragraphs": 0,
        "tables": 0,
        "images": 0,
        "charts": 0,
        "lists": 0,
        "code_blocks": 0,
        "callouts": 0,
        "equations": 0,
    }

    # -- inline math ------------------------------------------------------
    # Display math is drawn as native vector paths (see _VectorMathFlowable).
    # Inline math must sit *inside* a wrapping Paragraph, and ReportLab has no
    # inline-vector fragment, so inline fragments are embedded as high-DPI
    # (440) transparent images — crisp at print sizes and only a few px tall.

    def _inline_math(latex: str) -> str | None:
        rendered = render_math_png(latex, font_size=body_size, color=c.text, dpi=440)
        if rendered is None:
            return None
        png, w_pt, h_pt, d_pt = rendered
        b64 = base64.b64encode(png).decode("ascii")
        return (
            f'<img src="data:image/png;base64,{b64}" width="{w_pt:.2f}" '
            f'height="{h_pt:.2f}" valign="{-d_pt:.2f}"/>'
        )

    def _markup(text: str, *, mono_font: str) -> str:  # shadows module fn
        return spans_to_markup(
            parse_inline(text), mono_font=mono_font, math_img=_inline_math
        )

    # ------------------------------------------------------------------
    # Heading numbering + TOC plumbing
    # ------------------------------------------------------------------

    counters = [0] * 6

    def heading_prefix(level: int) -> str:
        if not spec.numbered_headings:
            return ""
        counters[level - 1] += 1
        for i in range(level, 6):
            counters[i] = 0
        return ".".join(str(counters[i]) for i in range(level)) + " "

    class _DocTemplate(BaseDocTemplate):
        def afterFlowable(self, flowable: Any) -> None:  # noqa: N802
            if isinstance(flowable, Paragraph):
                outline_meta = getattr(flowable, "_docgen_heading", None)
                if outline_meta is None:
                    return
                level, plain = outline_meta
                if level == 1:
                    # Running-section state for the {section} placeholder.
                    self.canv._docgen_section = plain
                key = f"h-{self.page}-{abs(hash(plain)) % 10_000_000}"
                self.canv.bookmarkPage(key)
                # Outline nesting can reject level jumps.
                with contextlib.suppress(Exception):
                    self.canv.addOutlineEntry(
                        plain, key, level=min(level - 1, 3), closed=level > 2
                    )
                if level <= 3:
                    self.notify("TOCEntry", (level - 1, plain, self.page, key))

    # ------------------------------------------------------------------
    # Page decoration (header / footer / watermark)
    # ------------------------------------------------------------------

    cover = spec.cover_spec()
    width, height = page_size

    def _draw_watermark(canv: Any) -> None:
        if not spec.watermark:
            return
        wm = spec.watermark
        canv.saveState()
        canv.setFillColor(_hex_color(colors, wm.color), alpha=wm.opacity)
        canv.setFont(font_bold, wm.font_size)
        canv.translate(width / 2, height / 2)
        canv.rotate(wm.angle)
        canv.drawCentredString(0, 0, wm.text)
        canv.restoreState()

    def _expand_placeholders(text: str, page_num: int, total: int, section: str) -> str:
        mapping = {
            "page": str(page_num),
            "pages": str(total),
            "title": spec.title or "",
            "author": spec.author or "",
            "date": spec.date or "",
            "section": section,
        }
        return _PLACEHOLDER_RE.sub(lambda m: mapping[m.group(1)], text)

    def _decorate_page(canv: Any, page_num: int, total: int, section: str) -> None:
        """Header/footer drawing — deferred so {pages}/{section} resolve."""
        if cover is not None and page_num == 1:
            return
        for cfg, is_header in ((spec.header, True), (spec.footer, False)):
            if cfg is None:
                continue
            raw = cfg.text or ""
            text = _expand_placeholders(raw, page_num, total, section)
            if cfg.show_page_number and "{page" not in raw:
                text = f"{text}  ·  {page_num}" if text else str(page_num)
            if not text:
                continue
            canv.saveState()
            canv.setFont(font_regular, theme.sizes.small)
            canv.setFillColor(text_light)
            y = height - margins.top * 0.55 if is_header else margins.bottom * 0.45
            if cfg.alignment == "left":
                canv.drawString(margins.left, y, text)
            elif cfg.alignment == "right":
                canv.drawRightString(width - margins.right, y, text)
            else:
                canv.drawCentredString(width / 2, y, text)
            if is_header:
                canv.setStrokeColor(border)
                canv.setLineWidth(0.5)
                canv.line(
                    margins.left,
                    y - 6,
                    width - margins.right,
                    y - 6,
                )
            canv.restoreState()

    class _DecoratedCanvas(rl_canvas.Canvas):
        """Two-pass canvas: page content is buffered at ``showPage`` and the
        header/footer is drawn at ``save`` time, when the total page count and
        each page's running section are known."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            self._docgen_states: list[dict[str, Any]] = []
            self._docgen_section = ""

        def showPage(self) -> None:  # noqa: N802
            self._docgen_states.append(dict(self.__dict__))
            self._startPage()

        def save(self) -> None:
            total = len(self._docgen_states)
            for state in self._docgen_states:
                self.__dict__.update(state)
                _decorate_page(self, self._pageNumber, total, self._docgen_section)
                rl_canvas.Canvas.showPage(self)
            rl_canvas.Canvas.save(self)

    def _draw_cover(canv: Any) -> None:
        """Consulting-style cover: full-bleed brand band with an accent
        baseline, org + logo header, left-aligned title block, meta footer."""
        cv = cover
        if cv is None:
            return
        band_h = height * 0.42
        band_y = height - band_h
        x = margins.left
        text_w = width - margins.left - margins.right

        canv.saveState()
        canv.setFillColor(primary)
        canv.rect(0, band_y, width, band_h, stroke=0, fill=1)
        canv.setFillColor(accent)
        canv.rect(0, band_y - 5, width, 5, stroke=0, fill=1)

        on_band = colors.Color(1, 1, 1)
        on_band_soft = colors.Color(1, 1, 1, alpha=0.82)

        if cv.organization:
            canv.setFillColor(on_band_soft)
            canv.setFont(font_bold, theme.sizes.body + 1)
            canv.drawString(x, height - 58, cv.organization)

        if cv.logo_path:
            resolved = resolve_image(path=cv.logo_path)
            if resolved is None:
                # multiBuild redraws the cover; warn once.
                msg = f"Cover logo could not be resolved: {cv.logo_path}"
                if msg not in warnings:
                    warnings.append(msg)
            else:
                with contextlib.suppress(Exception):
                    reader = ImageReader(io.BytesIO(resolved.data))
                    iw, ih = reader.getSize()
                    logo_h = 42.0
                    logo_w = iw * (logo_h / ih) if ih else logo_h
                    canv.drawImage(
                        reader,
                        width - margins.right - logo_w,
                        height - 58 - logo_h + theme.sizes.body,
                        width=logo_w,
                        height=logo_h,
                        mask="auto",
                        preserveAspectRatio=True,
                    )

        title_style = ParagraphStyle(
            "CoverBandTitle",
            fontName=font_bold,
            fontSize=theme.sizes.title + 8,
            leading=(theme.sizes.title + 8) * 1.18,
            textColor=on_band,
            wordWrap="CJK",
        )
        title_p = Paragraph(escape(cv.title or "Untitled"), title_style)
        title_p.wrapOn(canv, text_w, band_h - 90)
        title_p.drawOn(canv, x, band_y + 30)

        if cv.subtitle:
            sub_style = ParagraphStyle(
                "CoverBandSubtitle",
                fontName=font_regular,
                fontSize=theme.sizes.h2,
                leading=theme.sizes.h2 * 1.45,
                textColor=text_light,
                wordWrap="CJK",
            )
            sub_p = Paragraph(escape(cv.subtitle), sub_style)
            _, sh = sub_p.wrapOn(canv, text_w, 200)
            sub_p.drawOn(canv, x, band_y - 40 - sh)

        rule_y = margins.bottom + 42
        canv.setStrokeColor(border)
        canv.setLineWidth(0.75)
        canv.line(x, rule_y, width - margins.right, rule_y)
        meta_bits = [b for b in (cv.author, cv.date) if b]
        if meta_bits:
            canv.setFillColor(text_light)
            canv.setFont(font_regular, theme.sizes.body)
            canv.drawString(x, rule_y - 18, "   ·   ".join(meta_bits))
        canv.restoreState()

    def _on_page_main(canv: Any, doc_: Any) -> None:
        _draw_watermark(canv)

    def _on_page_cover(canv: Any, doc_: Any) -> None:
        _draw_watermark(canv)
        _draw_cover(canv)

    doc = _DocTemplate(
        str(output_path),
        pagesize=page_size,
        leftMargin=margins.left,
        rightMargin=margins.right,
        topMargin=margins.top,
        bottomMargin=margins.bottom,
        title=spec.title or "",
        author=spec.author or "",
        subject=spec.subject or "",
        keywords=", ".join(spec.keywords) if spec.keywords else "",
    )
    frame = Frame(
        margins.left,
        margins.bottom,
        width - margins.left - margins.right,
        height - margins.top - margins.bottom,
        id="main",
    )
    # The first template in the list is used for page 1.
    templates = [PageTemplate(id="main", frames=[frame], onPage=_on_page_main)]
    if spec.cover_spec() is not None:
        templates.insert(0, PageTemplate(id="cover", frames=[frame], onPage=_on_page_cover))
    doc.addPageTemplates(templates)

    content_width = width - margins.left - margins.right

    # ------------------------------------------------------------------
    # Block builders
    # ------------------------------------------------------------------

    zh = _looks_chinese(spec)
    nums = {"figure": 0, "table": 0, "equation": 0}
    _caption_words = {
        "table": ("表", "Table"),
        "figure": ("图", "Figure"),
        "equation": ("式", "Equation"),
    }

    def _caption_markup(kind: str, caption: str) -> str:
        """Caption markup with automatic 图/表/式 (Figure/Table/Eq.) numbers."""
        if not spec.numbered_figures:
            return _markup(caption, mono_font=font_mono)
        nums[kind] += 1
        word = _caption_words[kind][0 if zh else 1]
        label = f"{word} {nums[kind]}"
        return f"<b>{escape(label)}</b> &nbsp; " + _markup(caption, mono_font=font_mono)

    def _table_flowables(block: TableBlock, avail: float | None = None) -> list[Any]:
        frame_w = avail if avail is not None else content_width
        pt = process_table(block, theme=theme)
        if not pt.header and not pt.body:
            return []
        ts = resolve_table_style(theme, pt.style)

        cell_size = max(theme.sizes.small, body_size - 1)
        cell_style = ParagraphStyle(
            "DocTableCell",
            parent=styles["body"],
            fontSize=cell_size,
            leading=cell_size * 1.35,
            spaceAfter=0,
        )
        head_style = ParagraphStyle(
            "DocTableHead",
            parent=cell_style,
            fontName=font_bold,
            textColor=_hex_color(colors, ts.header_text)
            if ts.header_fill
            else primary,
        )
        style_cache: dict[str, ParagraphStyle] = {}

        def _cell(cell: Any, base: ParagraphStyle) -> Any:
            key = f"{base.name}|{cell.align}|{cell.bold}"
            st = style_cache.get(key)
            if st is None:
                st = ParagraphStyle(
                    key,
                    parent=base,
                    alignment=alignment_map[cell.align],
                    fontName=font_bold if cell.bold else base.fontName,
                )
                style_cache[key] = st
            markup = _markup(cell.text, mono_font=font_mono)
            if cell.polarity:
                hue = ts.positive if cell.polarity == "positive" else ts.negative
                markup = f'<font color="{hue}">{markup}</font>'
            return Paragraph(markup, st)

        data: list[list[Any]] = []
        if pt.header:
            data.append([_cell(cl, head_style) for cl in pt.header])
        for row in pt.body:
            data.append([_cell(cl, cell_style) for cl in row])

        widths = [max(52.0, f * frame_w) for f in pt.width_fractions()]
        overflow = sum(widths) - frame_w
        if overflow > 0:
            scale = frame_w / sum(widths)
            widths = [w * scale for w in widths]
        table = Table(data, colWidths=widths, repeatRows=1 if pt.header else 0)

        cmds: list[tuple[Any, ...]] = [
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), ts.pad_v),
            ("BOTTOMPADDING", (0, 0), (-1, -1), ts.pad_v),
            ("LEFTPADDING", (0, 0), (-1, -1), ts.pad_h),
            ("RIGHTPADDING", (0, 0), (-1, -1), ts.pad_h),
        ]
        body_start = 1 if pt.header else 0
        n_rows = len(data)

        if ts.grid:
            cmds.append(("GRID", (0, 0), (-1, -1), 0.5, border))
        else:
            if ts.row_rule and n_rows > body_start:
                cmds.append(
                    (
                        "LINEBELOW",
                        (0, body_start),
                        (-1, -2 if pt.total_row_index is not None else -1),
                        ts.row_rule_width,
                        _hex_color(colors, ts.row_rule),
                    )
                )
            if ts.outer_rule:
                hue = _hex_color(colors, ts.outer_rule)
                cmds.append(("LINEABOVE", (0, 0), (-1, 0), ts.outer_rule_width, hue))
                cmds.append(("LINEBELOW", (0, -1), (-1, -1), ts.outer_rule_width, hue))

        if pt.header:
            if ts.header_fill:
                cmds.append(("BACKGROUND", (0, 0), (-1, 0), _hex_color(colors, ts.header_fill)))
            cmds.append(
                (
                    "LINEBELOW",
                    (0, 0),
                    (-1, 0),
                    ts.header_rule_width,
                    _hex_color(colors, ts.header_rule),
                )
            )

        if pt.zebra and ts.zebra_fill:
            zebra_fill = _hex_color(colors, ts.zebra_fill)
            for i in range(body_start, n_rows):
                body_idx = i - body_start
                if body_idx == pt.total_row_index:
                    continue
                if body_idx % 2 == 1:
                    cmds.append(("BACKGROUND", (0, i), (-1, i), zebra_fill))

        if pt.total_row_index is not None:
            r = body_start + pt.total_row_index
            if ts.total_fill:
                cmds.append(("BACKGROUND", (0, r), (-1, r), _hex_color(colors, ts.total_fill)))
            cmds.append(
                (
                    "LINEABOVE",
                    (0, r),
                    (-1, r),
                    ts.total_rule_width,
                    _hex_color(colors, ts.total_rule),
                )
            )

        table.setStyle(TableStyle(cmds))

        out: list[Any] = [table]
        if pt.caption:
            out.append(Paragraph(_caption_markup("table", pt.caption), styles["caption"]))
        else:
            out.append(Spacer(1, 8))
        stats["tables"] += 1
        return out

    def _image_flowables(block: ImageBlock, avail: float | None = None) -> list[Any]:
        frame_w = avail if avail is not None else content_width
        resolved = resolve_image(
            path=block.path, base64_data=block.base64_data, url=block.url
        )
        if resolved is None:
            warnings.append(
                f"Image could not be resolved: {block.path or block.url or 'base64'}"
            )
            return []
        max_w = frame_w * ((block.width_pct or 88.0) / 100.0)
        img = RLImage(io.BytesIO(resolved.data))
        iw, ih = float(img.imageWidth), float(img.imageHeight)
        scale = min(1.0, max_w / iw) if iw else 1.0
        img.drawWidth = iw * scale
        img.drawHeight = ih * scale
        img.hAlign = {"left": "LEFT", "right": "RIGHT"}.get(block.alignment or "center", "CENTER")
        out: list[Any] = [img]
        if block.caption:
            out.append(Paragraph(_caption_markup("figure", block.caption), styles["caption"]))
        else:
            out.append(Spacer(1, 8))
        stats["images"] += 1
        return out

    def _chart_flowables(block: ChartBlock, avail: float | None = None) -> list[Any]:
        frame_w = avail if avail is not None else content_width
        png = render_chart_png(block, theme)
        if png is None:
            warnings.append(f"Chart could not be rendered: {block.title or block.chart_type}")
            return []
        max_w = frame_w * ((block.width_pct or 88.0) / 100.0)
        img = RLImage(io.BytesIO(png))
        iw, ih = float(img.imageWidth), float(img.imageHeight)
        scale = min(1.0, max_w / iw) if iw else 1.0
        img.drawWidth = iw * scale
        img.drawHeight = ih * scale
        img.hAlign = "CENTER"
        out: list[Any] = [img]
        if block.caption:
            out.append(Paragraph(_caption_markup("figure", block.caption), styles["caption"]))
        else:
            out.append(Spacer(1, 8))
        stats["charts"] += 1
        return out

    def _code_flowables(block: CodeBlock, avail: float | None = None) -> list[Any]:
        frame_w = avail if avail is not None else content_width
        # Preformatted does not wrap; hard-wrap long lines to the frame width.
        max_chars = max(20, int((frame_w - 20) / (theme.sizes.code * 0.62)))
        wrapped_lines: list[str] = []
        for line in block.code.splitlines() or [""]:
            while len(line) > max_chars:
                wrapped_lines.append(line[:max_chars])
                line = line[max_chars:]
            wrapped_lines.append(line)
        pre = Preformatted("\n".join(wrapped_lines), styles["code"])
        box = Table([[pre]], colWidths=[frame_w])
        box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), surface),
                    ("BOX", (0, 0), (-1, -1), 0.5, border),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        out: list[Any] = [box]
        if block.caption:
            out.append(Paragraph(_markup(block.caption, mono_font=font_mono), styles["caption"]))
        else:
            out.append(Spacer(1, 8))
        stats["code_blocks"] += 1
        return out

    def _callout_flowables(block: CalloutBlock, avail: float | None = None) -> list[Any]:
        frame_w = avail if avail is not None else content_width
        fill_hex, bar_hex = CALLOUT_COLORS.get(block.variant, CALLOUT_COLORS["info"])
        fill = _hex_color(colors, fill_hex)
        bar = _hex_color(colors, bar_hex)
        inner: list[Any] = []
        if block.title:
            inner.append(
                Paragraph(
                    f"<b>{_markup(block.title, mono_font=font_mono)}</b>",
                    ParagraphStyle(
                        "DocCalloutTitle",
                        parent=styles["body"],
                        textColor=bar,
                        spaceAfter=3,
                    ),
                )
            )
        if block.text:
            inner.append(
                Paragraph(
                    _markup(block.text, mono_font=font_mono),
                    ParagraphStyle(
                        "DocCalloutBody", parent=styles["body"], spaceAfter=0
                    ),
                )
            )
        box = Table([["", inner]], colWidths=[4, frame_w - 4])
        box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), bar),
                    ("BACKGROUND", (1, 0), (1, -1), fill),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (1, 0), (1, -1), 8),
                    ("BOTTOMPADDING", (1, 0), (1, -1), 8),
                    ("LEFTPADDING", (1, 0), (1, -1), 10),
                    ("RIGHTPADDING", (1, 0), (1, -1), 10),
                    ("TOPPADDING", (0, 0), (0, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (0, -1), 0),
                    ("LEFTPADDING", (0, 0), (0, -1), 0),
                    ("RIGHTPADDING", (0, 0), (0, -1), 0),
                ]
            )
        )
        stats["callouts"] += 1
        return [box, Spacer(1, 8)]

    def _metrics_flowables(block: MetricsBlock, avail: float | None = None) -> list[Any]:
        frame_w = avail if avail is not None else content_width
        if not block.items:
            return []
        items = block.items[:5]
        n = len(items)
        cells: list[Any] = []
        for item in items:
            parts: list[Any] = [
                Paragraph(
                    f"<b>{escape(item.value)}</b>",
                    ParagraphStyle(
                        "DocMetricValue",
                        fontName=font_bold,
                        fontSize=theme.sizes.h2,
                        leading=theme.sizes.h2 * 1.2,
                        alignment=TA_CENTER,
                        textColor=primary,
                        wordWrap="CJK",
                    ),
                ),
                Paragraph(
                    escape(item.label),
                    ParagraphStyle(
                        "DocMetricLabel",
                        parent=styles["caption"],
                        spaceBefore=2,
                        spaceAfter=0,
                    ),
                ),
            ]
            if item.delta:
                delta_color = "#2F9E5B" if not item.delta.strip().startswith("-") else "#C0392B"
                parts.append(
                    Paragraph(
                        f'<font color="{delta_color}">{escape(item.delta)}</font>',
                        ParagraphStyle(
                            "DocMetricDelta",
                            parent=styles["caption"],
                            spaceBefore=1,
                            spaceAfter=0,
                        ),
                    )
                )
            cells.append(parts)
        table = Table([cells], colWidths=[frame_w / n] * n)
        table.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("BACKGROUND", (0, 0), (-1, -1), surface),
                    ("BOX", (0, 0), (-1, -1), 0.5, border),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, border),
                    ("TOPPADDING", (0, 0), (-1, -1), 12),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
                ]
            )
        )
        return [table, Spacer(1, 10)]

    def _checklist_flowables(
        block: ChecklistBlock, avail: float | None = None
    ) -> list[Any]:
        frame_w = avail if avail is not None else content_width
        groups = block.normalized_groups()
        if not groups:
            return []
        out: list[Any] = []
        if block.title:
            out.append(
                Paragraph(
                    _markup(block.title, mono_font=font_mono),
                    ParagraphStyle(
                        "DocChecklistTitle",
                        parent=styles["body"],
                        fontName=font_bold,
                        fontSize=theme.sizes.h3,
                        textColor=primary,
                        spaceAfter=3,
                    ),
                )
            )
        if block.description:
            out.append(
                Paragraph(
                    _markup(block.description, mono_font=font_mono),
                    ParagraphStyle(
                        "DocChecklistDesc",
                        parent=styles["body"],
                        textColor=text_light,
                        spaceAfter=6,
                    ),
                )
            )

        stats = checklist_stats(block)
        if block.show_progress and stats["total_items"]:
            pct = stats["progress_percentage"]
            label = (
                f"{'完成度' if zh else 'Progress'}: {pct}% "
                f"({stats['completed']}/{stats['total_items']})"
            )
            out.append(
                Paragraph(
                    f"<b>{escape(label)}</b>",
                    ParagraphStyle(
                        "DocChecklistProg",
                        parent=styles["body"],
                        fontSize=theme.sizes.small,
                        textColor=text_color,
                        spaceAfter=3,
                    ),
                )
            )
            done_w = max(0.0, min(frame_w, frame_w * pct / 100.0))
            green = _hex_color(colors, "#2F9E5B")
            if 0 < done_w < frame_w:
                bar = Table(
                    [[" ", " "]], colWidths=[done_w, frame_w - done_w], rowHeights=[7]
                )
                bar.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (0, 0), green),
                            ("BACKGROUND", (1, 0), (1, 0), surface),
                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ]
                    )
                )
            else:
                bar = Table([[" "]], colWidths=[frame_w], rowHeights=[7])
                bar.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, -1), green if pct >= 100 else surface),
                            ("TOPPADDING", (0, 0), (-1, -1), 0),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                        ]
                    )
                )
            out.append(bar)
            out.append(Spacer(1, 8))

        item_style = ParagraphStyle(
            "DocChecklistItem", parent=styles["body"], spaceAfter=0, leading=theme.sizes.body * 1.3
        )
        meta_style = ParagraphStyle(
            "DocChecklistMeta",
            parent=styles["body"],
            fontSize=theme.sizes.small,
            textColor=text_light,
            spaceBefore=1,
            spaceAfter=0,
        )
        status_col = theme.sizes.body * 1.6

        def _item_rows(items: list[ChecklistItem], depth: int) -> list[Any]:
            rows: list[list[Any]] = []
            for item in items:
                glyph, color_hex, _ = status_meta(item.status)
                indent = "&nbsp;" * (depth * 4)
                glyph_cell = Paragraph(
                    f'<font color="{color_hex}">{glyph}</font>',
                    ParagraphStyle(
                        "DocChecklistGlyph",
                        parent=item_style,
                        fontName=font_bold,
                        alignment=TA_CENTER,
                    ),
                )
                text_markup = indent + _markup(item.text, mono_font=font_mono)
                if item.status in ("completed", "skipped"):
                    text_markup = f'<font color="#8A8F98">{text_markup}</font>'
                prio = priority_meta(item.priority)
                if prio:
                    p_color, p_label = prio
                    text_markup += (
                        f' &nbsp;<font size="{theme.sizes.small - 1:.0f}" '
                        f'color="{p_color}"><b>[{escape(p_label.upper())}]</b></font>'
                    )
                content: list[Any] = [Paragraph(text_markup, item_style)]
                meta_bits: list[str] = []
                if item.assignee:
                    meta_bits.append(f"@{escape(item.assignee)}")
                if item.due_date:
                    due_word = "截止" if zh else "Due"
                    meta_bits.append(f"{due_word}: {escape(item.due_date)}")
                if meta_bits:
                    content.append(Paragraph(" · ".join(meta_bits), meta_style))
                if item.notes:
                    content.append(
                        Paragraph(
                            "<i>" + _markup(item.notes, mono_font=font_mono) + "</i>",
                            meta_style,
                        )
                    )
                rows.append([glyph_cell, content])
                if item.sub_items:
                    rows.extend(_item_rows(item.sub_items, depth + 1))
            return rows

        for group in groups:
            if group.name:
                out.append(
                    Paragraph(
                        _markup(group.name, mono_font=font_mono),
                        ParagraphStyle(
                            "DocChecklistGroup",
                            parent=styles["body"],
                            fontName=font_bold,
                            fontSize=theme.sizes.body + 1,
                            textColor=text_color,
                            spaceBefore=6,
                            spaceAfter=3,
                            keepWithNext=1,
                        ),
                    )
                )
            if group.description:
                out.append(Paragraph(_markup(group.description, mono_font=font_mono), meta_style))
            rows = _item_rows(group.items, 0)
            if not rows:
                continue
            table = Table(rows, colWidths=[status_col, frame_w - status_col])
            table.setStyle(
                TableStyle(
                    [
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ("LEFTPADDING", (0, 0), (0, -1), 0),
                        ("LINEBELOW", (0, 0), (-1, -2), 0.4, border),
                    ]
                )
            )
            out.append(table)

        if block.show_legend:
            swatches = []
            for status in ("completed", "in_progress", "blocked", "pending"):
                glyph, color_hex, lbl = status_meta(status)
                swatches.append(
                    f'<font color="{color_hex}"><b>{glyph}</b></font> {escape(lbl)}'
                )
            legend_word = "图例" if zh else "Legend"
            out.append(Spacer(1, 4))
            out.append(
                Paragraph(
                    f"<b>{legend_word}:</b> &nbsp; " + " &nbsp;&nbsp; ".join(swatches),
                    meta_style,
                )
            )
        out.append(Spacer(1, 10))
        return out

    def _list_flowables(block: ListBlock) -> list[Any]:
        def _items(items: list[ListItem], depth: int) -> list[Any]:
            out: list[Any] = []
            for item in items:
                # U+2713 / U+25A1 are covered by Noto Sans SC; the ballot-box
                # glyphs (U+2610/U+2611) are not and would render as tofu.
                prefix = ""
                if item.checked is True:
                    prefix = '<font color="#2F9E5B">\u2713</font> '
                elif item.checked is False:
                    prefix = "\u25a1 "
                para = Paragraph(
                    prefix + _markup(item.text, mono_font=font_mono),
                    ParagraphStyle(
                        f"DocListItem{depth}",
                        parent=styles["body"],
                        spaceAfter=2.5,
                    ),
                )
                children: list[Any] = [para]
                if item.children:
                    children.append(
                        ListFlowable(
                            _items(item.children, depth + 1),
                            bulletType="bullet",
                            bulletFontName=font_regular,
                            bulletFontSize=body_size - 1,
                            leftIndent=14,
                        )
                    )
                out.append(RLListItem(children))
            return out

        flow = ListFlowable(
            _items(block.items, 0),
            bulletType="1" if block.ordered else "bullet",
            bulletFontName=font_regular,
            bulletFontSize=body_size,
            leftIndent=16,
        )
        stats["lists"] += 1
        return [flow, Spacer(1, theme.spacing.paragraph_spacing)]

    def _math_flowables(block: MathBlock, avail: float | None = None) -> list[Any]:
        frame_w = avail if avail is not None else content_width
        display_size = body_size * 1.18
        rows: list[Any] = []
        for row in latex_lines(block.latex):
            mv = math_vector_path(row, font_size=display_size)
            if mv is None:
                rows = []
                break
            rows.append(_VectorMathFlowable(mv, text_color, frame_w))
        if not rows:
            # Unrenderable LaTeX degrades to a code box, never a hard failure.
            warnings.append(f"Math could not be rendered: {block.latex[:80]}")
            return _code_flowables(
                CodeBlock(code=block.latex, language="latex"), frame_w
            )
        out: list[Any] = [Spacer(1, 4)]
        for idx, row_flowable in enumerate(rows):
            if idx > 0:
                out.append(Spacer(1, 3))
            out.append(row_flowable)
        if block.caption:
            out.append(
                Paragraph(_caption_markup("equation", block.caption), styles["caption"])
            )
        else:
            out.append(Spacer(1, 8))
        stats["equations"] += 1
        return out

    def _definition_list_flowables(
        block: DefinitionListBlock, avail: float | None = None
    ) -> list[Any]:
        out: list[Any] = []
        term_style = ParagraphStyle(
            "DocDefTerm",
            parent=styles["body"],
            fontName=font_bold,
            spaceAfter=1.5,
            keepWithNext=1,
        )
        def_style = ParagraphStyle(
            "DocDefBody",
            parent=styles["body"],
            leftIndent=16,
            spaceAfter=3,
        )
        for item in block.items:
            out.append(Paragraph(_markup(item.term, mono_font=font_mono), term_style))
            for definition in item.definitions:
                out.append(Paragraph(_markup(definition, mono_font=font_mono), def_style))
        if out:
            out.append(Spacer(1, theme.spacing.paragraph_spacing * 0.6))
        return out

    def _footnotes_flowables(
        block: FootnotesBlock, avail: float | None = None
    ) -> list[Any]:
        if not block.items:
            return []
        note_style = ParagraphStyle(
            "DocFootnote",
            parent=styles["body"],
            fontSize=theme.sizes.small,
            leading=theme.sizes.small * 1.5,
            textColor=text_light,
            spaceAfter=2,
        )
        out: list[Any] = [
            HRFlowable(
                width="30%",
                thickness=0.6,
                color=border,
                spaceBefore=14,
                spaceAfter=6,
                hAlign="LEFT",
            )
        ]
        for item in block.items:
            out.append(
                Paragraph(
                    f"<super>{escape(item.label)}</super> "
                    + _markup(item.text, mono_font=font_mono),
                    note_style,
                )
            )
        return out

    # ------------------------------------------------------------------
    # Story assembly
    # ------------------------------------------------------------------

    story: list[Any] = []
    has_cover = cover is not None

    if has_cover:
        # The cover is drawn on the canvas (onPage) for precise placement;
        # the frame only holds a stub flowable before switching templates.
        story.append(Spacer(1, 1))
        story.append(NextPageTemplate("main"))
        story.append(PageBreak())

    toc_requested = spec.toc or any(isinstance(b, TocBlock) for b in spec.blocks)
    toc_placed = False

    def _toc_flowables(title: str | None) -> list[Any]:
        toc = TableOfContents()
        toc.levelStyles = [
            ParagraphStyle(
                "TOC1",
                fontName=font_bold,
                fontSize=body_size + 1,
                leading=(body_size + 1) * 1.6,
                leftIndent=0,
                textColor=text_color,
            ),
            ParagraphStyle(
                "TOC2",
                fontName=font_regular,
                fontSize=body_size,
                leading=body_size * 1.6,
                leftIndent=14,
                textColor=text_color,
            ),
            ParagraphStyle(
                "TOC3",
                fontName=font_regular,
                fontSize=body_size - 0.5,
                leading=(body_size - 0.5) * 1.6,
                leftIndent=28,
                textColor=text_light,
            ),
        ]
        toc.dotsMinLevel = 0
        heading = Paragraph(
            escape(title or ("目录" if _looks_chinese(spec) else "Contents")),
            styles["h1"],
        )
        return [heading, Spacer(1, 6), toc, PageBreak()]

    if not has_cover and spec.title and not any(
        isinstance(b, HeadingBlock) and b.level == 1 for b in spec.blocks[:1]
    ):
        story.append(Paragraph(escape(spec.title), styles["title"]))
        if spec.subtitle:
            story.append(
                Paragraph(
                    escape(spec.subtitle),
                    ParagraphStyle(
                        "DocSubtitle",
                        parent=styles["caption"],
                        fontSize=theme.sizes.h3,
                        leading=theme.sizes.h3 * 1.4,
                    ),
                )
            )
        story.append(Spacer(1, 10))

    if toc_requested and spec.toc and not any(isinstance(b, TocBlock) for b in spec.blocks):
        story.extend(_toc_flowables(None))
        toc_placed = True

    # ``content_started`` tracks whether any body content precedes the
    # current block, so section_pages does not open with a blank page.
    content_started = False

    def _columns_flowables(block: ColumnsBlock, avail: float) -> list[Any]:
        cols = [col for col in block.columns[:3] if col]
        n = len(cols)
        if n == 0:
            return []
        if n == 1:
            out: list[Any] = []
            for b in cols[0]:
                out.extend(_flowables_for(b, avail, top_level=False))
            return out
        weights = (
            [max(0.05, float(x)) for x in block.widths[:n]]
            if block.widths and len(block.widths) >= n
            else [1.0] * n
        )
        gap = max(0.0, block.gap_pt)
        usable = max(60.0 * n, avail - gap * (n - 1))
        total_weight = sum(weights)
        cells: list[Any] = []
        col_widths: list[float] = []
        for idx, col_blocks in enumerate(cols):
            w = usable * weights[idx] / total_weight
            flows: list[Any] = []
            for b in col_blocks:
                if isinstance(b, (PageBreakBlock, TocBlock)):
                    continue  # page-level blocks are meaningless inside a column
                flows.extend(_flowables_for(b, w, top_level=False))
            if idx > 0:
                cells.append("")
                col_widths.append(gap)
            cells.append(flows or "")
            col_widths.append(w)
        grid = Table([cells], colWidths=col_widths)
        grid.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )
        return [grid, Spacer(1, theme.spacing.paragraph_spacing)]

    def _flowables_for(
        block: Any, avail: float | None = None, *, top_level: bool = True
    ) -> list[Any]:
        nonlocal content_started, toc_placed
        w = avail if avail is not None else content_width
        out: list[Any] = []
        if isinstance(block, HeadingBlock):
            if (
                top_level
                and spec.section_pages
                and block.level == 1
                and content_started
            ):
                out.append(PageBreak())
            plain = "".join(s.text for s in parse_inline(block.text))
            prefix = heading_prefix(block.level) if top_level else ""
            para = Paragraph(
                escape(prefix) + _markup(block.text, mono_font=font_mono),
                styles[f"h{block.level}"],
            )
            if top_level:
                para._docgen_heading = (block.level, prefix + plain)  # type: ignore[attr-defined]
            out.append(para)
            if block.level == 1:
                # Short accent rule anchoring top-level sections.
                out.append(
                    HRFlowable(
                        width=46,
                        thickness=2.25,
                        color=accent,
                        spaceBefore=0,
                        spaceAfter=8,
                        hAlign="LEFT",
                    )
                )
            stats["headings"] += 1
        elif isinstance(block, ParagraphBlock):
            st = styles["body"]
            if block.alignment:
                st = ParagraphStyle(
                    f"DocBody_{block.alignment}",
                    parent=styles["body"],
                    alignment=alignment_map.get(block.alignment, TA_LEFT),
                )
            out.append(Paragraph(_markup(block.text, mono_font=font_mono), st))
            stats["paragraphs"] += 1
        elif isinstance(block, ListBlock):
            out.extend(_list_flowables(block))
        elif isinstance(block, TableBlock):
            out.extend(_table_flowables(block, w))
        elif isinstance(block, ImageBlock):
            out.extend(_image_flowables(block, w))
        elif isinstance(block, ChartBlock):
            out.extend(_chart_flowables(block, w))
        elif isinstance(block, CodeBlock):
            out.extend(_code_flowables(block, w))
        elif isinstance(block, QuoteBlock):
            quote_table = Table(
                [[Paragraph(_markup(block.text, mono_font=font_mono), styles["quote"])]],
                colWidths=[w],
            )
            quote_table.setStyle(
                TableStyle(
                    [
                        ("LINEBEFORE", (0, 0), (0, -1), 2.5, primary),
                        ("LEFTPADDING", (0, 0), (-1, -1), 12),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            out.append(quote_table)
            if block.attribution:
                out.append(
                    Paragraph(
                        f"— {_markup(block.attribution, mono_font=font_mono)}",
                        ParagraphStyle(
                            "DocQuoteAttr",
                            parent=styles["caption"],
                            alignment=TA_RIGHT,
                        ),
                    )
                )
            out.append(Spacer(1, 8))
        elif isinstance(block, CalloutBlock):
            out.extend(_callout_flowables(block, w))
        elif isinstance(block, MetricsBlock):
            out.extend(_metrics_flowables(block, w))
        elif isinstance(block, ChecklistBlock):
            out.extend(_checklist_flowables(block, w))
        elif isinstance(block, MathBlock):
            out.extend(_math_flowables(block, w))
        elif isinstance(block, DefinitionListBlock):
            out.extend(_definition_list_flowables(block, w))
        elif isinstance(block, FootnotesBlock):
            out.extend(_footnotes_flowables(block, w))
        elif isinstance(block, ColumnsBlock):
            out.extend(_columns_flowables(block, w))
        elif isinstance(block, DividerBlock):
            out.append(
                HRFlowable(
                    width="100%",
                    thickness=0.75,
                    color=border,
                    spaceBefore=8,
                    spaceAfter=8,
                )
            )
        elif isinstance(block, PageBreakBlock):
            content_started = False
            return [PageBreak()]
        elif isinstance(block, SpacerBlock):
            out.append(Spacer(1, block.height_pt))
        elif isinstance(block, TocBlock):
            if top_level and not toc_placed:
                toc_placed = True
                content_started = False
                return _toc_flowables(block.title)
            return []
        if out and top_level:
            content_started = True
        return out

    for block in spec.blocks:
        story.extend(_flowables_for(block))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if toc_placed:
        doc.multiBuild(story, canvasmaker=_DecoratedCanvas)
    else:
        doc.build(story, canvasmaker=_DecoratedCanvas)

    if spec.merge_sources or spec.encryption:
        _postprocess_pdf(output_path, spec, warnings)

    page_count = _count_pages(output_path)
    result = {
        "success": True,
        "output_path": str(output_path),
        "format": "pdf",
        "file_size_bytes": output_path.stat().st_size,
        "page_count": page_count,
        "content_stats": stats,
        "font_embedded": bool(fonts["embedded"]),
        "font_source": fonts["source"],
        "theme": theme.name,
        "encrypted": spec.encryption is not None,
        "merged_sources": len(spec.merge_sources),
        "warnings": warnings,
    }
    logger.info(
        "docgen_pdf_rendered",
        output_path=str(output_path),
        page_count=page_count,
        font_embedded=fonts["embedded"],
        **stats,
    )
    return result


def _looks_chinese(spec: DocumentSpec) -> bool:
    sample = spec.title + "".join(
        getattr(b, "text", "") for b in spec.blocks[:8] if hasattr(b, "text")
    )
    return any("\u4e00" <= ch <= "\u9fff" for ch in sample)


def _postprocess_pdf(
    output_path: Path, spec: DocumentSpec, warnings: list[str]
) -> None:
    """Merge additional PDFs and/or encrypt the output using pypdf."""
    try:
        from pypdf import PdfReader, PdfWriter
    except ImportError:
        warnings.append(
            "pypdf is not installed; merge/encryption skipped "
            "(install the [office] extra)."
        )
        logger.warning("docgen_pypdf_missing_postprocess_skipped")
        return

    writer = PdfWriter()
    reader = PdfReader(str(output_path))
    for page in reader.pages:
        writer.add_page(page)

    for src in spec.merge_sources:
        src_path = Path(src)
        if not src_path.is_file():
            warnings.append(f"Merge source not found: {src}")
            continue
        src_reader = PdfReader(str(src_path))
        for page in src_reader.pages:
            writer.add_page(page)

    if spec.encryption:
        user_pw = spec.encryption.user_password
        writer.encrypt(
            user_password=user_pw,
            owner_password=spec.encryption.owner_password or user_pw,
        )

    with open(str(output_path), "wb") as f:
        writer.write(f)


def _count_pages(pdf_path: Path) -> int:
    try:
        from pypdf import PdfReader

        return len(PdfReader(str(pdf_path)).pages)
    except Exception:  # noqa: BLE001 - optional dep; try PyMuPDF next
        pass
    try:
        import fitz

        with fitz.open(str(pdf_path)) as doc:
            return doc.page_count
    except Exception:  # noqa: BLE001
        return 0
