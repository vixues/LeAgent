"""HTML representation of a validated GenUi tree for Chromium PDF export.

Uses layout/CSS tuned for **screen-quality typography** under ``print`` media,
not bare browser defaults — paired with ``page.emulate_media('print')`` and
structured margins / outlines in the API layer.
"""

from __future__ import annotations

import html
from typing import Any


_DESIGN_SURFACE_PRESETS = frozenset(
    {"poster", "slide", "card", "editorial", "minimal", "brutalist", "geek"}
)


def _esc(x: object) -> str:
    return html.escape(str(x), quote=True)


def _normalize_design_surface_preset(value: object, *, fallback: str = "slide") -> str:
    raw = str(value or "").strip().lower()
    return raw if raw in _DESIGN_SURFACE_PRESETS else fallback


def _props_primary_text(props: dict[str, Any]) -> str:
    for key in ("value", "label", "title", "message", "description", "subtitle", "name", "quote", "content"):
        v = props.get(key)
        if v is not None and str(v).strip():
            return str(v)
    return ""


def _node_inner(node: dict[str, Any]) -> str:
    """Render node inner HTML (no outer wrapper by kind)."""
    kind = str(node.get("kind") or "")
    props: dict[str, Any] = dict(node.get("props") or {})
    children = [c for c in (node.get("children") or []) if isinstance(c, dict)]

    if kind == "Text":
        return f'<p class="p">{_esc(props.get("value", ""))}</p>'
    if kind == "Heading":
        level = min(4, max(1, int(props.get("level") or 2)))
        tag = f"h{level}"
        return f"<{tag} class='h'>{_esc(props.get('value', ''))}</{tag}>"
    if kind == "Markdown":
        return f"<pre class='md'>{_esc(props.get('content', ''))}</pre>"
    if kind == "Image":
        src = _esc(props.get("src", ""))
        alt = _esc(props.get("alt", ""))
        return f'<div class="imgwrap"><img src="{src}" alt="{alt}" /></div>'
    if kind in {"Stack", "Row", "Grid", "ScrollArea"}:
        inner = "".join(f"<div class='ch'>{_node_inner(ch)}</div>" for ch in children)
        return f"<div class='{kind.lower()}'>{inner}</div>"
    if kind == "DesignSurface":
        preset = _normalize_design_surface_preset(props.get("preset"))
        inner = "".join(_node_inner(ch) for ch in children)
        return f"<div class='designsurface designsurface-{preset}'>{inner}</div>"
    if kind == "Slide":
        eyebrow = _esc(props.get("eyebrow", ""))
        title = _esc(props.get("title", ""))
        subtitle = _esc(props.get("subtitle", ""))
        head = ""
        if eyebrow:
            head += f"<p class='eyebrow'>{eyebrow}</p>"
        if title:
            head += f"<h1 class='slidetitle'>{title}</h1>"
        if subtitle:
            head += f"<p class='slidesub'>{subtitle}</p>"
        inner = "".join(_node_inner(ch) for ch in children)
        return f"<div class='slideinner'>{head}{inner}</div>"
    if kind == "Table":
        headers = props.get("headers") or []
        head_html = ""
        if isinstance(headers, list) and headers:
            cells = "".join(f"<th>{_esc(h)}</th>" for h in headers if isinstance(h, str))
            head_html = f"<thead><tr>{cells}</tr></thead>"
        body_html = "".join(f"<tr>{_node_inner(ch)}</tr>" for ch in children)
        return f"<table class='tbl'>{head_html}<tbody>{body_html}</tbody></table>"
    if kind == "TableRow":
        return "".join(_node_inner(ch) for ch in children)
    if kind == "TableCell":
        return f"<td>{_esc(props.get('value', ''))}</td>"
    if kind == "SectionHeader":
        eyebrow = _esc(props.get("eyebrow", ""))
        title = _esc(props.get("title", ""))
        description = _esc(props.get("description", ""))
        bits = []
        if eyebrow:
            bits.append(f"<p class='eyebrow'>{eyebrow}</p>")
        if title:
            bits.append(f"<h2 class='h'>{title}</h2>")
        if description:
            bits.append(f"<p class='p'>{description}</p>")
        return "".join(bits) if bits else ""
    if kind == "SlideDeck":
        inner = "".join(_node_inner(ch) for ch in children)
        return f"<div class='blk slidedeck'>{inner}</div>"
    if kind == "FeatureGrid":
        raw_items = props.get("items")
        items = raw_items if isinstance(raw_items, list) else []
        parts: list[str] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            t = _esc(it.get("title", ""))
            d = _esc(it.get("description", ""))
            parts.append(f"<div class='featitem'><p class='p'><strong>{t}</strong></p><p class='p'>{d}</p></div>")
        return f"<div class='featgrid'>{''.join(parts)}</div>"
    if kind == "KeyValueList":
        raw_items = props.get("items")
        items = raw_items if isinstance(raw_items, list) else []
        rows = []
        for it in items:
            if not isinstance(it, dict):
                continue
            rows.append(
                "<tr><td class='kv-label'>{}</td><td>{}</td></tr>".format(
                    _esc(it.get("label", "")),
                    _esc(it.get("value", "")),
                )
            )
        return f"<table class='tbl kv'><tbody>{''.join(rows)}</tbody></table>"
    if kind == "QuoteCard":
        q = _esc(props.get("quote", ""))
        author = _esc(props.get("author", ""))
        role = _esc(props.get("role", ""))
        cap = f"<p class='p'><em>{author}</em>" + (f" — {role}" if role else "") + "</p>" if author or role else ""
        return f"<blockquote class='quote'><p>{q}</p>{cap}</blockquote>"
    if kind == "Stepper":
        raw_steps = props.get("steps")
        steps = raw_steps if isinstance(raw_steps, list) else []
        lis = []
        for st in steps:
            if not isinstance(st, dict):
                continue
            lis.append(f"<li>{_esc(st.get('title', ''))}: {_esc(st.get('description', ''))}</li>")
        return f"<ol class='stepper'>{''.join(lis)}</ol>"
    if kind == "ImageGallery":
        raw_items = props.get("items")
        items = raw_items if isinstance(raw_items, list) else []
        imgs = []
        for it in items:
            if not isinstance(it, dict):
                continue
            src = _esc(it.get("src", ""))
            alt = _esc(it.get("alt", ""))
            imgs.append(f'<div class="imgwrap"><img src="{src}" alt="{alt}" /></div>')
        return f"<div class='gallery'>{''.join(imgs)}</div>"

    if kind == "Chart":
        title = _esc(props.get("title", "") or "")
        chart_t = _esc(str(props.get("chart", "line")))
        raw_cats = props.get("categories")
        categories = [str(x) for x in raw_cats] if isinstance(raw_cats, list) else []
        raw_series = props.get("series")
        series_rows: list[tuple[str, list[str]]] = []
        if isinstance(raw_series, list):
            for s in raw_series:
                if not isinstance(s, dict):
                    continue
                nm = str(s.get("name", "Series"))
                vals_raw = s.get("values")
                vals: list[str] = []
                if isinstance(vals_raw, list):
                    for v in vals_raw:
                        vals.append("" if v is None else str(v))
                series_rows.append((nm, vals))
        cap = f"<p class='muted'>{chart_t} chart (table)</p>"
        head_html = ""
        if title:
            head_html += f"<h3 class='h'>{title}</h3>"
        head_html += cap
        if not series_rows:
            return f"<div class='chart-fallback'>{head_html}<p class='p'>(no series data)</p></div>"
        col_headers = "".join(f"<th>{_esc(nm)}</th>" for nm, _ in series_rows)
        n_series_max = max(len(v) for _, v in series_rows)
        n_rows = max(len(categories), n_series_max)
        body_rows: list[str] = []
        for i in range(n_rows):
            cat = categories[i] if i < len(categories) else str(i + 1)
            tds = "".join(
                f"<td>{_esc(vals[i]) if i < len(vals) else ''}</td>"
                for _, vals in series_rows
            )
            body_rows.append(f"<tr><td>{_esc(cat)}</td>{tds}</tr>")
        tbl = (
            f"<table class='tbl'><thead><tr><th></th>{col_headers}</tr></thead>"
            f"<tbody>{''.join(body_rows)}</tbody></table>"
        )
        return f"<div class='chart-fallback'>{head_html}{tbl}</div>"

    if kind == "Icon":
        name = _esc(props.get("name", ""))
        return f'<span class="icon-glyph">[{name}]</span>'
    if kind == "Badge":
        return f'<span class="badge">{_esc(props.get("value", ""))}</span>'
    if kind == "Chip":
        return f'<span class="badge">{_esc(props.get("label") or props.get("value", ""))}</span>'
    if kind == "Tag":
        return f'<span class="badge">{_esc(props.get("label", ""))}</span>'
    if kind == "Stat":
        label = _esc(props.get("label", ""))
        value = _esc(props.get("value", ""))
        delta = _esc(props.get("delta", ""))
        tail = f" ({delta})" if delta else ""
        return f'<div class="stat"><p class="muted">{label}</p><p class="statval">{value}{tail}</p></div>'
    if kind == "Progress":
        lab = _esc(props.get("label", ""))
        val = props.get("value")
        try:
            pct = max(0.0, min(100.0, float(val))) if val is not None else 0.0
        except (TypeError, ValueError):
            pct = 0.0
        return f'<div class="progress"><p class="muted">{lab}</p><p>{pct:.0f}%</p></div>'
    if kind == "Avatar":
        name = str(props.get("name", "") or "")
        initials = "".join(w[0] for w in name.split() if w)[:2].upper() or "?"
        src = props.get("src") or props.get("avatarUrl")
        if isinstance(src, str) and src.strip():
            return f'<div class="avatar"><img src="{_esc(src)}" alt="{_esc(name)}"/></div>'
        return f'<div class="avatar circ">{_esc(initials)}</div>'
    if kind == "Divider":
        return "<hr class='hrule'/>"
    if kind == "CodeBlock":
        body = props.get("code") or props.get("content") or ""
        return f"<pre class='md'>{_esc(body)}</pre>"
    if kind == "List":
        inner = "".join(_node_inner(ch) for ch in children)
        return f"<ul class='list'>{inner}</ul>"
    if kind == "ListItem":
        icon_txt = _esc(props.get("icon", ""))
        prefix = f"[{icon_txt}] " if props.get("icon") else ""
        text = _esc(props.get("value", ""))
        nested = "".join(_node_inner(ch) for ch in children)
        return f"<li>{prefix}{text}{nested}</li>"
    if kind == "Card":
        bits: list[str] = []
        if props.get("eyebrow"):
            bits.append(f"<p class='eyebrow'>{_esc(props.get('eyebrow'))}</p>")
        if props.get("title"):
            bits.append(f"<p class='p'><strong>{_esc(props.get('title'))}</strong></p>")
        if props.get("subtitle"):
            bits.append(f"<p class='muted'>{_esc(props.get('subtitle'))}</p>")
        inner = "".join(_node_inner(ch) for ch in children)
        return f"<div class='cardblk'>{''.join(bits)}{inner}</div>"
    if kind == "DataCard":
        title = _esc(props.get("title", ""))
        value = _esc(props.get("value", ""))
        desc = _esc(props.get("description", ""))
        icon = props.get("icon")
        head = f"<p class='muted'>{title}</p><p class='statval'>{value}</p>"
        if desc:
            head += f"<p class='muted'>{desc}</p>"
        ic = f'<p class="muted">[{_esc(icon)}]</p>' if icon else ""
        inner = "".join(_node_inner(ch) for ch in children)
        return f"<div class='cardblk'>{ic}{head}{inner}</div>"
    if kind == "MetricCard":
        title = _esc(props.get("title", ""))
        value = _esc(props.get("value", ""))
        delta = _esc(props.get("delta", ""))
        period = _esc(props.get("period", ""))
        bits = f"<p class='muted'>{title}</p><p class='statval'>{value}</p>"
        if delta:
            bits += f"<p class='muted'>{delta}</p>"
        if period:
            bits += f"<p class='muted'>{period}</p>"
        return f"<div class='cardblk'>{bits}</div>"
    if kind in {"Alert", "AlertCard", "Callout"}:
        msg = _esc(props.get("message") or props.get("title") or props.get("description") or "")
        return f"<div class='callout'><p class='p'>{msg}</p></div>"

    inner = "".join(_node_inner(ch) for ch in children)
    if inner:
        return f"<div class='blk {kind}'>{inner}</div>"
    primary = _props_primary_text(props)
    if primary:
        return f"<div class='blk {kind}'><p class='p'>{_esc(primary)}</p></div>"
    return ""


def render_pages_html(normalized_tree: dict[str, Any], *, mode: str) -> str:
    """Return HTML body inner markup (no html/head) for one or more pages."""
    root = normalized_tree.get("root")
    if not isinstance(root, dict):
        return "<section class='page'><p>(empty)</p></section>"

    root_kind = str(root.get("kind") or "")
    if mode == "deck" and root_kind == "SlideDeck":
        slides = [
            c
            for c in (root.get("children") or [])
            if isinstance(c, dict) and str(c.get("kind")) == "Slide"
        ]
        if not slides:
            slides = [c for c in (root.get("children") or []) if isinstance(c, dict)]
        parts: list[str] = []
        for sl in slides:
            inner = _node_inner(sl)
            parts.append(f"<section class='page slidepage'>{inner}</section>")
        return "".join(parts) if parts else f"<section class='page'>{_node_inner(root)}</section>"

    return f"<section class='page docpage'>{_node_inner(root)}</section>"


# ---------------------------------------------------------------------------
# Print themes — tuned for Chromium PDF (pair with emulate_media('print') +
# page.pdf margins / outline in canvas.py). External fonts intentionally omitted
# so exports work offline; stack covers Latin + common CJK UI fonts.
# ---------------------------------------------------------------------------

_PRINT_FONT_STACK = (
    'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, '
    '"Helvetica Neue", Arial, "Noto Sans", "PingFang SC", "Microsoft YaHei", '
    '"Source Han Sans SC", sans-serif'
)

_PRINT_SERIF_STACK = (
    'ui-serif, Georgia, "Noto Serif", "Source Han Serif SC", "Songti SC", serif'
)

PRINT_CSS = f"""
@page {{
  margin: 0;
  size: auto;
}}
:root {{
  --ink: #0f172a;
  --ink-muted: #475569;
  --border: #e2e8f0;
  --surface: #f8fafc;
  --accent: #0369a1;
  --radius: 8px;
}}
* {{ box-sizing: border-box; }}
html {{
  -webkit-print-color-adjust: exact;
  print-color-adjust: exact;
}}
body {{
  margin: 0;
  padding: 0;
  font-family: {_PRINT_FONT_STACK};
  font-size: 10.5pt;
  line-height: 1.55;
  color: var(--ink);
  background: #fff;
  hyphens: auto;
  -webkit-hyphens: auto;
  text-rendering: optimizeLegibility;
}}
.print-root {{
  max-width: 100%;
}}
.print-root--doc .docpage {{
  padding: 0;
}}
.page {{
  page-break-after: always;
}}
.page:last-child {{ page-break-after: auto; }}

/* Heading scale — report-style rhythm */
.docpage h1.h {{ font-size: 1.65rem; font-weight: 700; letter-spacing: -0.02em; margin: 0 0 0.75rem; line-height: 1.25; color: var(--ink); }}
.docpage h2.h {{ font-size: 1.35rem; font-weight: 600; margin: 1.35rem 0 0.55rem; line-height: 1.3; color: var(--ink); }}
.docpage h3.h {{ font-size: 1.12rem; font-weight: 600; margin: 1.1rem 0 0.45rem; }}
.docpage h4.h {{ font-size: 1rem; font-weight: 600; margin: 1rem 0 0.35rem; }}

.p {{
  margin: 0 0 0.65em;
  orphans: 3;
  widows: 3;
}}
.p:last-child {{ margin-bottom: 0; }}

.eyebrow {{
  font-size: 0.65rem;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: var(--accent);
  font-weight: 700;
  margin: 0 0 0.35rem;
}}

/* Deck / slides — presentation layout */
.slidepage {{
  min-height: 168mm;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14mm 16mm;
  background: linear-gradient(180deg, #ffffff 0%, #fafbfc 100%);
  box-decoration-break: clone;
}}
.slidetitle {{
  font-size: 26px;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.15;
  margin: 0 0 0.35rem;
  color: var(--ink);
}}
.slidesub {{
  font-size: 13px;
  color: var(--ink-muted);
  margin: 0 0 1rem;
  line-height: 1.45;
}}
.slideinner {{
  display: flow-root;
}}

/* Tables — publication-style */
.tbl {{
  width: 100%;
  border-collapse: collapse;
  margin: 1rem 0;
  font-size: 9.5pt;
  page-break-inside: auto;
  border: 1px solid var(--border);
  border-radius: 6px;
  overflow: hidden;
}}
.tbl thead {{
  display: table-header-group;
  background: var(--surface);
}}
.tbl thead th {{
  border-bottom: 2px solid #cbd5e1;
  font-weight: 600;
  font-size: 8.5pt;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--ink-muted);
}}
.tbl tbody tr:nth-child(even) td {{
  background: #fafbfc;
}}
.tbl tbody tr {{
  page-break-inside: avoid;
}}
.tbl th, .tbl td {{
  border: 1px solid var(--border);
  padding: 0.45rem 0.55rem;
  text-align: left;
  vertical-align: top;
}}
.tbl.kv td.kv-label {{
  font-weight: 600;
  color: var(--ink-muted);
  width: 32%;
}}

/* Blocks */
.md {{
  white-space: pre-wrap;
  font-family: ui-monospace, "Cascadia Code", "SF Mono", Menlo, monospace;
  font-size: 8.75pt;
  line-height: 1.45;
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 0.65rem 0.75rem;
  border-radius: 6px;
  margin: 0.75rem 0;
}}
.quote {{
  margin: 1rem 0;
  padding: 0.65rem 0 0.65rem 1rem;
  border-left: 4px solid var(--accent);
  background: var(--surface);
  border-radius: 0 6px 6px 0;
  font-family: {_PRINT_SERIF_STACK};
}}
.quote p {{ margin: 0.35em 0; }}

.designsurface {{
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.9rem;
  margin: 0.65rem 0;
  background: #fff;
}}
.designsurface-geek {{
  --ink: #d1fae5;
  --ink-muted: #67e8f9;
  --border: rgba(45, 212, 191, 0.45);
  --surface: rgba(15, 23, 42, 0.82);
  --accent: #34d399;
  color: var(--ink);
  background:
    radial-gradient(circle at top left, rgba(34, 211, 238, 0.28), transparent 30%),
    linear-gradient(135deg, #020617 0%, #0f172a 56%, #064e3b 100%);
  border-color: var(--border);
  font-family: ui-monospace, "Cascadia Code", "SF Mono", Menlo, monospace;
  box-shadow: 0 0 26px rgba(16, 185, 129, 0.18);
}}
.designsurface-geek .cardblk,
.designsurface-geek .callout,
.designsurface-geek .featitem,
.designsurface-geek .tbl,
.designsurface-geek .md {{
  background: rgba(15, 23, 42, 0.72);
  border-color: rgba(45, 212, 191, 0.38);
  color: var(--ink);
}}
.designsurface-geek .tbl thead,
.designsurface-geek .tbl tbody tr:nth-child(even) td,
.designsurface-geek .badge {{
  background: rgba(6, 78, 59, 0.55);
  color: var(--ink);
  border-color: rgba(45, 212, 191, 0.38);
}}

.stepper {{
  margin: 0.75rem 0;
  padding-left: 1.15rem;
}}
.stepper li {{ margin: 0.35em 0; }}

.featgrid {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 0.65rem;
  margin: 0.75rem 0;
}}
.featitem {{
  padding: 0.55rem 0.65rem;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: #fff;
}}

.muted {{ color: var(--ink-muted); font-size: 9.5pt; }}
.statval {{ font-size: 17px; font-weight: 700; margin: 0.15em 0; letter-spacing: -0.02em; }}
.stat {{ margin: 0.65rem 0; }}
.badge {{
  display: inline-block;
  padding: 0.15rem 0.45rem;
  border-radius: 999px;
  background: var(--surface);
  border: 1px solid var(--border);
  font-size: 8.5pt;
  font-weight: 500;
}}
.icon-glyph {{ font-size: 9px; color: var(--ink-muted); }}

.cardblk {{
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 0.75rem 0.85rem;
  margin: 0.65rem 0;
  background: #fff;
  box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
}}
.callout {{
  border-left: 4px solid var(--accent);
  padding: 0.55rem 0.85rem;
  background: var(--surface);
  margin: 0.65rem 0;
  border-radius: 0 6px 6px 0;
}}

.avatar img {{ width: 48px; height: 48px; border-radius: 999px; object-fit: cover; }}
.avatar.circ {{
  width: 48px; height: 48px; border-radius: 999px;
  background: var(--border);
  display: inline-flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 14px;
}}

.list {{ margin: 0.55rem 0; padding-left: 1.2rem; }}
.hrule {{ border: none; border-top: 1px solid var(--border); margin: 1rem 0; }}

.imgwrap img {{ max-width: 100%; height: auto; display: block; }}
.gallery {{ display: grid; gap: 0.5rem; margin: 0.65rem 0; }}

.scrollarea {{ max-height: none !important; overflow: visible !important; }}
.stack, .row, .grid {{ overflow: visible !important; min-height: 0; }}

.ch {{ margin: 0.35rem 0; }}
"""

# Slide PDFs: full-bleed canvas; typography inherits from PRINT_CSS.
PRINT_CSS_SLIDE = """
@page { margin: 0; size: 1280px 720px; }
.slidepage {
  width: 1280px;
  height: 720px;
  overflow: hidden;
  box-sizing: border-box;
}
""" + PRINT_CSS.replace(
    "@page {\n  margin: 0;\n  size: auto;\n}\n",
    "",
    1,
)


def render_print_document_html(
    normalized_tree: dict[str, Any],
    *,
    mode: str,
    page_size: str | None = None,
) -> str:
    """Full HTML document for Chromium PDF (use ``print`` media + margins in caller)."""
    inner = render_pages_html(normalized_tree, mode=mode)
    is_slide_pdf = page_size == "Slide16x9"
    css = PRINT_CSS_SLIDE if is_slide_pdf else PRINT_CSS
    root_class = "print-root print-root--slides" if is_slide_pdf else "print-root print-root--doc"
    return (
        "<!DOCTYPE html><html lang=\"zh-CN\"><head>"
        "<meta charset=\"utf-8\"/>"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"/>"
        "<title>Export</title>"
        f"<style>{css}</style>"
        "</head><body>"
        f"<article class=\"{root_class}\" dir=\"auto\">{inner}</article>"
        "</body></html>"
    )
