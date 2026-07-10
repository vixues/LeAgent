"""Themed standalone HTML + Markdown output renderers.

All user content is HTML-escaped (the legacy ``report_generator`` HTML path
interpolated raw strings). Charts render to base64-inlined PNGs so the file
is fully self-contained; the CSS font stack prefers the same pan-Unicode CJK
families used elsewhere.
"""

from __future__ import annotations

import base64
import html
from typing import TYPE_CHECKING, Any

import structlog

from leagent.docgen.charts import render_chart_png
from leagent.docgen.checklist import checklist_stats, priority_meta, status_meta
from leagent.docgen.images import resolve_image
from leagent.docgen.markdown import parse_inline
from leagent.docgen.mathtext import latex_lines, latex_to_unicode, render_math_png
from leagent.docgen.model import (
    Block,
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

if TYPE_CHECKING:
    from pathlib import Path

logger = structlog.get_logger(__name__)

_FONT_STACK = (
    '-apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, '
    '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", "Source Han Sans SC", sans-serif'
)
_MONO_STACK = (
    'ui-monospace, "SF Mono", Menlo, Consolas, "Noto Sans Mono CJK SC", monospace'
)


def _math_img_html(latex: str, *, font_size: float = 12.0, display: bool = False) -> str:
    """One LaTeX expression → self-contained ``<img>`` (base64 PNG)."""
    rendered = render_math_png(latex, font_size=font_size, color="#333333", dpi=300)
    if rendered is None:
        return f"<em>{html.escape(latex_to_unicode(latex))}</em>"
    png, w_pt, h_pt, d_pt = rendered
    b64 = base64.b64encode(png).decode("ascii")
    alt = html.escape(latex, quote=True)
    if display:
        return (
            f'<img class="math-display" src="data:image/png;base64,{b64}" '
            f'style="height:{h_pt:.2f}pt" alt="{alt}"/>'
        )
    return (
        f'<img class="math-inline" src="data:image/png;base64,{b64}" '
        f'style="height:{h_pt:.2f}pt;vertical-align:{-d_pt:.2f}pt" alt="{alt}"/>'
    )


def _inline_html(text: str) -> str:
    """Markdown inline spans → escaped HTML."""
    parts: list[str] = []
    for span in parse_inline(text):
        if span.math:
            parts.append(_math_img_html(span.text))
            continue
        piece = html.escape(span.text).replace("\n", "<br/>")
        if span.code:
            piece = f"<code>{piece}</code>"
        if span.bold:
            piece = f"<strong>{piece}</strong>"
        if span.italic:
            piece = f"<em>{piece}</em>"
        if span.strike:
            piece = f"<del>{piece}</del>"
        if span.sup:
            piece = f"<sup>{piece}</sup>"
        elif span.sub:
            piece = f"<sub>{piece}</sub>"
        if span.link:
            href = html.escape(span.link, quote=True)
            piece = f'<a href="{href}">{piece}</a>'
        parts.append(piece)
    return "".join(parts)


_GFM_STATUS = {"completed": "x", "in_progress": "~", "blocked": "!", "skipped": "-"}


def _checklist_markdown(block: ChecklistBlock) -> list[str]:
    """Emit a checklist as GFM task lists (round-trippable)."""
    lines: list[str] = []
    if block.title:
        lines += [f"**{block.title}**", ""]
    if block.description:
        lines += [block.description, ""]

    def _emit(item: ChecklistItem, depth: int) -> None:
        mark = _GFM_STATUS.get(item.status, " ")
        pad = "  " * depth
        extra = []
        if item.priority:
            extra.append(f"[{item.priority.upper()}]")
        if item.assignee:
            extra.append(f"@{item.assignee}")
        if item.due_date:
            extra.append(f"({item.due_date})")
        suffix = (" " + " ".join(extra)) if extra else ""
        lines.append(f"{pad}- [{mark}] {item.text}{suffix}")
        if item.notes:
            lines.append(f"{pad}  - _{item.notes}_")
        for sub in item.sub_items:
            _emit(sub, depth + 1)

    for group in block.normalized_groups():
        if group.name:
            lines += [f"**{group.name}**", ""]
        for item in group.items:
            _emit(item, 0)
        lines.append("")
    return lines


def _checklist_html(block: ChecklistBlock, *, zh: bool) -> str:
    """Render a checklist with progress bar, status badges, and legend."""
    groups = block.normalized_groups()
    if not groups:
        return ""
    parts: list[str] = ['<div class="checklist">']
    if block.title:
        parts.append(f'<div class="cl-title">{_inline_html(block.title)}</div>')
    if block.description:
        parts.append(f'<div class="cl-desc">{_inline_html(block.description)}</div>')

    stats = checklist_stats(block)
    if block.show_progress and stats["total_items"]:
        pct = stats["progress_percentage"]
        word = "完成度" if zh else "Progress"
        parts.append(
            f'<div class="cl-progress-label">{word}: {pct}% '
            f'({stats["completed"]}/{stats["total_items"]})</div>'
            f'<div class="cl-progress"><div class="cl-progress-bar" '
            f'style="width:{pct}%">{pct if pct > 8 else ""}'
            f'{"%" if pct > 8 else ""}</div></div>'
        )

    def _item_html(item: ChecklistItem) -> str:
        glyph, color_hex, _ = status_meta(item.status)
        dim = " cl-done" if item.status in ("completed", "skipped") else ""
        prio = priority_meta(item.priority)
        prio_html = ""
        if prio:
            p_color, p_label = prio
            prio_html = (
                f'<span class="cl-prio" style="background:{p_color}">'
                f"{html.escape(p_label.upper())}</span>"
            )
        meta_bits = []
        if item.assignee:
            meta_bits.append(f"@{html.escape(item.assignee)}")
        if item.due_date:
            meta_bits.append(f"{'截止' if zh else 'Due'}: {html.escape(item.due_date)}")
        meta_html = (
            f'<div class="cl-meta">{" · ".join(meta_bits)}</div>' if meta_bits else ""
        )
        notes_html = (
            f'<div class="cl-notes">{_inline_html(item.notes)}</div>'
            if item.notes
            else ""
        )
        subs = ""
        if item.sub_items:
            subs = (
                '<div class="cl-subs">'
                + "".join(_item_html(s) for s in item.sub_items)
                + "</div>"
            )
        return (
            f'<div class="cl-item{dim}">'
            f'<span class="cl-glyph" style="color:{color_hex}">{glyph}</span>'
            f'<div class="cl-body"><div class="cl-text">{_inline_html(item.text)}'
            f"{prio_html}</div>{meta_html}{notes_html}{subs}</div></div>"
        )

    for group in groups:
        parts.append('<div class="cl-group">')
        if group.name:
            parts.append(f'<div class="cl-group-name">{_inline_html(group.name)}</div>')
        if group.description:
            parts.append(f'<div class="cl-desc">{_inline_html(group.description)}</div>')
        parts.extend(_item_html(item) for item in group.items)
        parts.append("</div>")

    if block.show_legend:
        swatches = []
        for status in ("completed", "in_progress", "blocked", "pending"):
            glyph, color_hex, lbl = status_meta(status)
            swatches.append(
                f'<span class="cl-legend-item"><span style="color:{color_hex}">'
                f"{glyph}</span> {html.escape(lbl)}</span>"
            )
        legend_word = "图例" if zh else "Legend"
        parts.append(
            f'<div class="cl-legend"><strong>{legend_word}:</strong> '
            + " ".join(swatches)
            + "</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def render_html(spec: DocumentSpec, output_path: Path) -> dict[str, Any]:
    """Render a document spec to a standalone themed HTML file."""
    theme = get_theme(spec.theme, kind="document")
    warnings: list[str] = []
    stats = {
        "headings": 0,
        "paragraphs": 0,
        "tables": 0,
        "images": 0,
        "charts": 0,
        "equations": 0,
    }

    body_parts: list[str] = []
    toc_entries: list[tuple[int, str, str]] = []
    heading_idx = 0
    zh = _looks_chinese(spec)
    nums = {"figure": 0, "table": 0, "equation": 0}
    _caption_words = {
        "table": ("表", "Table"),
        "figure": ("图", "Figure"),
        "equation": ("式", "Equation"),
    }

    def _caption_html(kind: str, caption: str) -> str:
        if not spec.numbered_figures:
            return _inline_html(caption)
        nums[kind] += 1
        word = _caption_words[kind][0 if zh else 1]
        label = f"{word} {nums[kind]}"
        return f"<strong>{html.escape(label)}</strong>&ensp;{_inline_html(caption)}"

    cover = spec.cover_spec()
    if cover is not None:
        meta_bits = "  ·  ".join(
            html.escape(b) for b in (cover.organization, cover.author, cover.date) if b
        )
        body_parts.append(
            '<header class="cover">'
            f"<h1>{html.escape(cover.title or 'Untitled')}</h1>"
            + (f"<p class='subtitle'>{html.escape(cover.subtitle)}</p>" if cover.subtitle else "")
            + (f"<p class='meta'>{meta_bits}</p>" if meta_bits else "")
            + "</header>"
        )
    elif spec.title:
        body_parts.append(
            '<header class="cover-inline">'
            f"<h1>{html.escape(spec.title)}</h1>"
            + (f"<p class='subtitle'>{html.escape(spec.subtitle)}</p>" if spec.subtitle else "")
            + "</header>"
        )

    toc_marker = "<!--DOCGEN_TOC-->"
    toc_requested = spec.toc or any(isinstance(b, TocBlock) for b in spec.blocks)
    if spec.toc and not any(isinstance(b, TocBlock) for b in spec.blocks):
        body_parts.append(toc_marker)

    def _block_html(block: Block) -> str:  # noqa: PLR0911, PLR0912
        nonlocal heading_idx
        if isinstance(block, HeadingBlock):
            heading_idx += 1
            anchor = f"h-{heading_idx}"
            if block.level <= 3:
                toc_entries.append((block.level, block.text, anchor))
            stats["headings"] += 1
            return f'<h{block.level} id="{anchor}">{_inline_html(block.text)}</h{block.level}>'
        if isinstance(block, ParagraphBlock):
            stats["paragraphs"] += 1
            style = f' style="text-align:{block.alignment}"' if block.alignment else ""
            return f"<p{style}>{_inline_html(block.text)}</p>"
        if isinstance(block, ListBlock):
            return _list_html(block)
        if isinstance(block, TableBlock):
            stats["tables"] += 1
            return _table_html(block, theme, caption_html=_caption_html)
        if isinstance(block, ImageBlock):
            resolved = resolve_image(
                path=block.path, base64_data=block.base64_data, url=block.url
            )
            if resolved is None:
                warnings.append(
                    f"Image could not be resolved: {block.path or block.url or 'base64'}"
                )
                return ""
            stats["images"] += 1
            b64 = base64.b64encode(resolved.data).decode("ascii")
            width = f' style="width:{block.width_pct}%"' if block.width_pct else ""
            caption = (
                f"<figcaption>{_caption_html('figure', block.caption)}</figcaption>"
                if block.caption
                else ""
            )
            return (
                f'<figure class="align-{block.alignment or "center"}">'
                f'<img src="data:{resolved.mime};base64,{b64}"{width} alt=""/>{caption}</figure>'
            )
        if isinstance(block, ChartBlock):
            png = render_chart_png(block, theme)
            if png is None:
                warnings.append(
                    f"Chart could not be rendered: {block.title or block.chart_type}"
                )
                return ""
            stats["charts"] += 1
            b64 = base64.b64encode(png).decode("ascii")
            caption = (
                f"<figcaption>{_caption_html('figure', block.caption)}</figcaption>"
                if block.caption
                else ""
            )
            return (
                '<figure class="align-center">'
                f'<img src="data:image/png;base64,{b64}" alt=""/>{caption}</figure>'
            )
        if isinstance(block, CodeBlock):
            lang = f' data-lang="{html.escape(block.language, quote=True)}"' if block.language else ""
            return f"<pre{lang}><code>{html.escape(block.code)}</code></pre>"
        if isinstance(block, QuoteBlock):
            attribution = (
                f"<footer>— {_inline_html(block.attribution)}</footer>"
                if block.attribution
                else ""
            )
            return f"<blockquote><p>{_inline_html(block.text)}</p>{attribution}</blockquote>"
        if isinstance(block, CalloutBlock):
            fill, bar = CALLOUT_COLORS.get(block.variant, CALLOUT_COLORS["info"])
            title = (
                f'<p class="callout-title" style="color:{bar}">{_inline_html(block.title)}</p>'
                if block.title
                else ""
            )
            return (
                f'<div class="callout" style="background:{fill};border-left-color:{bar}">'
                f"{title}<p>{_inline_html(block.text)}</p></div>"
            )
        if isinstance(block, MetricsBlock):
            cells = []
            for item in block.items[:5]:
                delta = ""
                if item.delta:
                    color = "#2F9E5B" if not item.delta.strip().startswith("-") else "#C0392B"
                    delta = f'<div class="delta" style="color:{color}">{html.escape(item.delta)}</div>'
                cells.append(
                    '<div class="metric">'
                    f'<div class="value">{html.escape(item.value)}</div>'
                    f'<div class="label">{html.escape(item.label)}</div>{delta}</div>'
                )
            return f'<div class="metrics">{"".join(cells)}</div>'
        if isinstance(block, ChecklistBlock):
            return _checklist_html(block, zh=zh)
        if isinstance(block, MathBlock):
            stats["equations"] += 1
            rows = "".join(
                f"<div>{_math_img_html(row, font_size=13.0, display=True)}</div>"
                for row in latex_lines(block.latex)
            )
            caption = (
                f"<figcaption>{_caption_html('equation', block.caption)}</figcaption>"
                if block.caption
                else ""
            )
            return f'<figure class="math">{rows}{caption}</figure>'
        if isinstance(block, DefinitionListBlock):
            items = []
            for item in block.items:
                items.append(f"<dt>{_inline_html(item.term)}</dt>")
                items.extend(f"<dd>{_inline_html(d)}</dd>" for d in item.definitions)
            return f"<dl>{''.join(items)}</dl>"
        if isinstance(block, FootnotesBlock):
            notes = "".join(
                f'<li id="fn-{html.escape(item.label, quote=True)}">'
                f"{_inline_html(item.text)}</li>"
                for item in block.items
            )
            return f'<section class="footnotes"><hr/><ol>{notes}</ol></section>'
        if isinstance(block, ColumnsBlock):
            cols = [col for col in block.columns[:3] if col]
            if not cols:
                return ""
            weights = (
                [max(0.05, float(x)) for x in block.widths[: len(cols)]]
                if block.widths and len(block.widths) >= len(cols)
                else [1.0] * len(cols)
            )
            parts = []
            for col_blocks, weight in zip(cols, weights, strict=False):
                inner = "".join(
                    _block_html(b)
                    for b in col_blocks
                    if not isinstance(b, (PageBreakBlock, TocBlock))
                )
                parts.append(f'<div class="col" style="flex:{weight}">{inner}</div>')
            return f'<div class="cols" style="gap:{block.gap_pt}pt">{"".join(parts)}</div>'
        if isinstance(block, DividerBlock):
            return "<hr/>"
        if isinstance(block, PageBreakBlock):
            return '<div class="page-break"></div>'
        if isinstance(block, SpacerBlock):
            return f'<div style="height:{block.height_pt}pt"></div>'
        if isinstance(block, TocBlock):
            return toc_marker
        return ""

    for block in spec.blocks:
        rendered = _block_html(block)
        if rendered:
            body_parts.append(rendered)

    body = "\n".join(body_parts)
    if toc_requested and toc_marker in body:
        items = "".join(
            f'<li class="toc-l{level}"><a href="#{anchor}">{_inline_html(text)}</a></li>'
            for level, text, anchor in toc_entries
        )
        toc_title = "目录" if _looks_chinese(spec) else "Contents"
        toc_html = f'<nav class="toc"><h2>{toc_title}</h2><ul>{items}</ul></nav>'
        body = body.replace(toc_marker, toc_html, 1)
        body = body.replace(toc_marker, "")

    doc_html = _page_shell(spec, theme, body)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(doc_html, encoding="utf-8")

    result = {
        "success": True,
        "output_path": str(output_path),
        "format": "html",
        "file_size_bytes": output_path.stat().st_size,
        "content_stats": stats,
        "theme": theme.name,
        "warnings": warnings,
    }
    logger.info("docgen_html_rendered", output_path=str(output_path), **stats)
    return result


def _list_html(block: ListBlock) -> str:
    def _items(items: list[ListItem]) -> str:
        out = []
        for item in items:
            prefix = ""
            if item.checked is True:
                prefix = '<span class="task done">✓</span> '
            elif item.checked is False:
                prefix = '<span class="task">□</span> '
            children = (
                f"<ul>{_items(item.children)}</ul>" if item.children else ""
            )
            out.append(f"<li>{prefix}{_inline_html(item.text)}{children}</li>")
        return "".join(out)

    tag = "ol" if block.ordered else "ul"
    return f"<{tag}>{_items(block.items)}</{tag}>"


def _table_html(block: TableBlock, theme: Any, *, caption_html: Any = None) -> str:
    pt = process_table(block, theme=theme)
    if not pt.header and not pt.body:
        return ""
    ts = resolve_table_style(theme, pt.style)

    grid_border = f"border:1px solid {theme.colors.border};" if ts.grid else ""
    colgroup = "".join(
        f'<col style="width:{f * 100:.1f}%"/>' for f in pt.width_fractions()
    )

    def _cell_html(tag: str, pcell: Any, extra: str = "") -> str:
        styles = [f"text-align:{pcell.align}", "padding:8px 10px"]
        if grid_border:
            styles.append(grid_border.rstrip(";"))
        if pcell.bold and tag == "td":
            styles.append("font-weight:700")
        if pcell.polarity:
            hue = ts.positive if pcell.polarity == "positive" else ts.negative
            styles.append(f"color:{hue}")
        if extra:
            styles.append(extra.rstrip(";"))
        return f'<{tag} style="{";".join(styles)}">{_inline_html(pcell.text)}</{tag}>'

    thead = ""
    if pt.header:
        if ts.header_fill:
            th_extra = (
                f"background:{ts.header_fill};color:{ts.header_text};"
                f"border-bottom:{ts.header_rule_width}pt solid {ts.header_rule}"
            )
        else:
            th_extra = (
                f"color:{ts.header_text};"
                f"border-top:{ts.outer_rule_width}pt solid {ts.outer_rule};"
                f"border-bottom:{ts.header_rule_width}pt solid {ts.header_rule}"
            )
        cells = "".join(_cell_html("th", cl, th_extra) for cl in pt.header)
        thead = f"<thead><tr>{cells}</tr></thead>"

    rows: list[str] = []
    n_body = len(pt.body)
    for r_idx, row in enumerate(pt.body):
        is_total = r_idx == pt.total_row_index
        is_last = r_idx == n_body - 1
        row_bits: list[str] = []
        if is_total:
            row_bits.append(f"border-top:{ts.total_rule_width}pt solid {ts.total_rule}")
            if ts.total_fill:
                row_bits.append(f"background:{ts.total_fill}")
        elif pt.zebra and ts.zebra_fill and r_idx % 2 == 1:
            row_bits.append(f"background:{ts.zebra_fill}")
        td_extra = ""
        if not ts.grid:
            if is_last and ts.outer_rule:
                td_extra = f"border-bottom:{ts.outer_rule_width}pt solid {ts.outer_rule}"
            elif not is_last and ts.row_rule and not (
                pt.total_row_index is not None and r_idx == pt.total_row_index - 1
            ):
                td_extra = f"border-bottom:{ts.row_rule_width}pt solid {ts.row_rule}"
        tr_style = f' style="{";".join(row_bits)}"' if row_bits else ""
        row_bits_html = "".join(_cell_html("td", cl, td_extra) for cl in row)
        rows.append(f"<tr{tr_style}>{row_bits_html}</tr>")

    if pt.caption:
        rendered = (
            caption_html("table", pt.caption) if caption_html else _inline_html(pt.caption)
        )
        caption = f"<caption>{rendered}</caption>"
    else:
        caption = ""
    return (
        f'<table class="dg-table">{caption}{colgroup}{thead}'
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _looks_chinese(spec: DocumentSpec) -> bool:
    sample = spec.title + "".join(
        getattr(b, "text", "") for b in spec.blocks[:8] if hasattr(b, "text")
    )
    return any("\u4e00" <= ch <= "\u9fff" for ch in sample)


def _page_shell(spec: DocumentSpec, theme: Any, body: str) -> str:
    c = theme.colors
    s = theme.sizes
    return f"""<!DOCTYPE html>
<html lang="{'zh-CN' if _looks_chinese(spec) else 'en'}">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>{html.escape(spec.title or 'Document')}</title>
<style>
:root {{ color-scheme: light; }}
* {{ box-sizing: border-box; }}
body {{
  font-family: {_FONT_STACK};
  font-size: {s.body + 2}pt;
  line-height: {theme.spacing.line_spacing + 0.15};
  color: {c.text};
  background: {c.background};
  max-width: 860px;
  margin: 0 auto;
  padding: 48px 32px 96px;
}}
h1, h2, h3, h4, h5, h6 {{ color: {c.primary}; line-height: 1.3; margin: 1.4em 0 0.5em; }}
h1 {{ font-size: {s.h1 + 4}pt; }} h2 {{ font-size: {s.h2 + 2}pt; }} h3 {{ font-size: {s.h3 + 1}pt; }}
h3, h4, h5, h6 {{ color: {c.text}; }}
p {{ margin: 0 0 0.8em;{' text-align: justify;' if spec.justify else ''} }}
.cols {{ display: flex; align-items: flex-start; margin: 1em 0; }}
.cols .col {{ min-width: 0; }}
a {{ color: {c.secondary}; }}
header.cover {{ text-align: center; padding: 120px 0 80px; page-break-after: always; }}
header.cover h1 {{ font-size: {s.title + 4}pt; margin-bottom: 0.3em; }}
header.cover .subtitle {{ font-size: {s.h2}pt; color: {c.text_light}; }}
header.cover .meta {{ margin-top: 64px; color: {c.text_light}; }}
header.cover-inline {{ text-align: center; margin-bottom: 2em; }}
header.cover-inline .subtitle {{ color: {c.text_light}; }}
nav.toc {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 8px; padding: 16px 24px; margin: 1.5em 0; }}
nav.toc ul {{ list-style: none; margin: 0; padding: 0; }}
nav.toc li {{ margin: 0.3em 0; }}
nav.toc li.toc-l2 {{ padding-left: 1.2em; }}
nav.toc li.toc-l3 {{ padding-left: 2.4em; font-size: 0.92em; color: {c.text_light}; }}
nav.toc a {{ text-decoration: none; }}
table {{ border-collapse: collapse; width: 100%; margin: 1em 0; font-size: 0.95em; }}
caption {{ caption-side: bottom; color: {c.text_light}; font-size: 0.88em; padding-top: 6px; }}
pre {{ background: {c.surface}; border: 1px solid {c.border}; border-radius: 6px; padding: 14px 16px; overflow-x: auto; }}
code {{ font-family: {_MONO_STACK}; font-size: 0.9em; }}
p code, li code {{ background: {c.surface}; border-radius: 3px; padding: 1px 5px; }}
blockquote {{ border-left: 3px solid {c.primary}; margin: 1em 0; padding: 4px 0 4px 16px; color: {c.text_light}; }}
blockquote footer {{ text-align: right; font-size: 0.9em; }}
.callout {{ border-left: 4px solid; border-radius: 4px; padding: 12px 16px; margin: 1em 0; }}
.callout p {{ margin: 0; }}
.callout .callout-title {{ font-weight: 700; margin-bottom: 4px; }}
.metrics {{ display: flex; gap: 12px; margin: 1.2em 0; flex-wrap: wrap; }}
.metric {{ flex: 1 1 120px; background: {c.surface}; border: 1px solid {c.border}; border-radius: 8px; padding: 16px 12px; text-align: center; }}
.metric .value {{ font-size: {s.h2 + 2}pt; font-weight: 700; color: {c.primary}; }}
.metric .label {{ color: {c.text_light}; font-size: 0.85em; margin-top: 4px; }}
.metric .delta {{ font-size: 0.85em; margin-top: 2px; }}
figure {{ margin: 1.2em 0; text-align: center; }}
figure img {{ max-width: 100%; height: auto; }}
figure.math {{ margin: 1em 0; }}
figure.math img.math-display {{ width: auto; max-width: 100%; }}
img.math-inline {{ width: auto; }}
dl {{ margin: 1em 0; }}
dt {{ font-weight: 700; margin-top: 0.6em; }}
dd {{ margin: 0.2em 0 0.2em 1.4em; }}
section.footnotes {{ margin-top: 2em; font-size: 0.88em; color: {c.text_light}; }}
section.footnotes hr {{ width: 30%; margin: 0 0 0.8em; }}
section.footnotes ol {{ padding-left: 1.4em; }}
.checklist {{ margin: 1.2em 0; }}
.cl-title {{ font-size: 1.15em; font-weight: 700; color: {c.primary}; margin-bottom: 0.2em; }}
.cl-desc {{ color: {c.text_light}; margin-bottom: 0.6em; }}
.cl-progress-label {{ font-size: 0.85em; font-weight: 700; margin: 0.4em 0 0.2em; }}
.cl-progress {{ background: {c.surface}; border-radius: 6px; overflow: hidden; height: 14px; margin-bottom: 1em; }}
.cl-progress-bar {{ background: #2F9E5B; height: 14px; color: #fff; font-size: 10px; font-weight: 700; text-align: center; line-height: 14px; min-width: 0; transition: width .3s; }}
.cl-group {{ margin-bottom: 0.8em; }}
.cl-group-name {{ font-weight: 700; margin: 0.6em 0 0.3em; }}
.cl-item {{ display: flex; align-items: flex-start; gap: 8px; padding: 4px 0; border-bottom: 1px solid {c.border}; }}
.cl-glyph {{ font-weight: 700; flex-shrink: 0; width: 1.2em; text-align: center; }}
.cl-body {{ flex: 1; }}
.cl-text {{ font-size: 0.95em; }}
.cl-done .cl-text {{ color: {c.text_light}; }}
.cl-prio {{ display: inline-block; margin-left: 8px; padding: 1px 6px; border-radius: 4px; font-size: 0.68em; font-weight: 700; color: #fff; vertical-align: middle; }}
.cl-meta {{ font-size: 0.78em; color: {c.text_light}; margin-top: 2px; }}
.cl-notes {{ font-size: 0.8em; color: {c.text_light}; font-style: italic; margin-top: 2px; }}
.cl-subs {{ margin-left: 1em; margin-top: 2px; }}
.cl-subs .cl-item {{ border-bottom: none; }}
.cl-legend {{ margin-top: 0.8em; padding: 8px 12px; background: {c.surface}; border-radius: 6px; font-size: 0.8em; }}
.cl-legend-item {{ margin-right: 16px; }}
figure.align-left {{ text-align: left; }}
figure.align-right {{ text-align: right; }}
figcaption {{ color: {c.text_light}; font-size: 0.88em; margin-top: 6px; }}
.task {{ color: {c.text_light}; }}
.task.done {{ color: #2F9E5B; }}
hr {{ border: none; border-top: 1px solid {c.border}; margin: 2em 0; }}
.page-break {{ page-break-after: always; }}
@media print {{
  body {{ max-width: none; padding: 0; }}
  nav.toc a {{ color: {c.text}; }}
}}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def _iter_flat_blocks(blocks: list[Block]) -> Any:
    """Yield blocks with column layouts flattened to sequential content."""
    for block in blocks:
        if isinstance(block, ColumnsBlock):
            for col in block.columns:
                yield from _iter_flat_blocks(col)
        else:
            yield block


def render_markdown(spec: DocumentSpec, output_path: Path) -> dict[str, Any]:
    """Render a document spec back to a clean markdown file."""
    lines: list[str] = []
    stats = {"headings": 0, "paragraphs": 0, "tables": 0}

    if spec.title:
        lines += [f"# {spec.title}", ""]
        if spec.subtitle:
            lines += [f"*{spec.subtitle}*", ""]
        meta_bits = "  ·  ".join(b for b in (spec.author, spec.date) if b)
        if meta_bits:
            lines += [meta_bits, ""]

    for block in _iter_flat_blocks(spec.blocks):
        if isinstance(block, HeadingBlock):
            stats["headings"] += 1
            lines += [f"{'#' * min(block.level + 1, 6)} {block.text}", ""]
        elif isinstance(block, ParagraphBlock):
            stats["paragraphs"] += 1
            lines += [block.text, ""]
        elif isinstance(block, ListBlock):
            lines += _markdown_list_lines(block) + [""]
        elif isinstance(block, TableBlock):
            stats["tables"] += 1
            pt = process_table(block)
            markers = {"left": " --- ", "center": " :---: ", "right": " ---: "}
            if pt.header:
                lines.append("| " + " | ".join(cl.text for cl in pt.header) + " |")
                lines.append(
                    "|" + "|".join(markers[col.align] for col in pt.columns) + "|"
                )
            for row in pt.body:
                lines.append("| " + " | ".join(cl.text for cl in row) + " |")
            lines.append("")
        elif isinstance(block, CodeBlock):
            lines += [f"```{block.language or ''}", block.code, "```", ""]
        elif isinstance(block, QuoteBlock):
            lines += [f"> {block.text}", ""]
        elif isinstance(block, CalloutBlock):
            title = f" {block.title}" if block.title else ""
            lines += [f"::: {block.variant}{title}", block.text, ":::", ""]
        elif isinstance(block, ChartBlock):
            payload = block.model_dump_json(exclude_none=True, exclude_defaults=True)
            lines += ["```chart", payload, "```", ""]
        elif isinstance(block, MetricsBlock):
            payload = block.model_dump_json(exclude_none=True)
            lines += ["```metrics", payload, "```", ""]
        elif isinstance(block, ImageBlock):
            src = block.path or block.url or ""
            lines += [f"![{block.caption or ''}]({src})", ""]
        elif isinstance(block, ChecklistBlock):
            lines += _checklist_markdown(block)
        elif isinstance(block, MathBlock):
            lines += ["$$", block.latex, "$$", ""]
        elif isinstance(block, DefinitionListBlock):
            for item in block.items:
                lines.append(item.term)
                lines.extend(f": {d}" for d in item.definitions)
                lines.append("")
        elif isinstance(block, FootnotesBlock):
            lines += [f"[^{item.label}]: {item.text}" for item in block.items] + [""]
        elif isinstance(block, DividerBlock):
            lines += ["---", ""]
        elif isinstance(block, PageBreakBlock):
            lines += ["\\newpage", ""]
        elif isinstance(block, TocBlock):
            lines += ["[TOC]", ""]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return {
        "success": True,
        "output_path": str(output_path),
        "format": "markdown",
        "file_size_bytes": output_path.stat().st_size,
        "content_stats": stats,
        "warnings": [],
    }


def _markdown_list_lines(block: ListBlock) -> list[str]:
    lines: list[str] = []

    def _walk(items: list[ListItem], depth: int) -> None:
        for idx, item in enumerate(items):
            indent = "  " * depth
            marker = f"{idx + 1}." if block.ordered and depth == 0 else "-"
            check = ""
            if item.checked is True:
                check = "[x] "
            elif item.checked is False:
                check = "[ ] "
            lines.append(f"{indent}{marker} {check}{item.text}")
            if item.children:
                _walk(item.children, depth + 1)

    _walk(block.items, 0)
    return lines
