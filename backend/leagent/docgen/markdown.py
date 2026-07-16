"""Markdown → document IR parser (markdown-it-py based).

Supported syntax beyond CommonMark:

- GFM tables, strikethrough, and autolinked bare URLs (linkify)
- Task lists (``- [ ]`` / ``- [x]``)
- Math (LaTeX): ``$inline$``, ``$$display$$``, AMS environments
  (``\\begin{align}…``), and fenced ```` ```math ```` blocks — rendered by
  :mod:`leagent.docgen.mathtext` in every output format.
- Footnotes: ``[^1]`` references + ``[^1]: definition`` (collected into a
  trailing :class:`~leagent.docgen.model.FootnotesBlock`).
- Definition lists (``Term`` / ``: definition``).
- YAML front matter (``---`` fenced) — extracted by
  :func:`parse_markdown_document` as document metadata.
- Callout containers::

      ::: warning Optional Title
      Body text.
      :::

  Variants: info, note, tip, success, warning, danger.
- ``chart`` / ``metrics`` / ``checklist`` fenced code blocks whose body is
  JSON (or YAML) matching :class:`~leagent.docgen.model.ChartBlock` /
  :class:`~leagent.docgen.model.MetricsBlock` /
  :class:`~leagent.docgen.model.ChecklistBlock` payloads.
- Page breaks: a paragraph containing only ``\\newpage`` or ``\\pagebreak``,
  or an HTML comment ``<!-- pagebreak -->``.
- ``[TOC]`` on its own line places the table of contents.

Inline markdown (bold/italic/code/links/strikethrough/math/footnote refs) is
preserved in block text fields and parsed by renderers via
:func:`parse_inline`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import structlog

from leagent.docgen.model import (
    Block,
    CalloutBlock,
    ChartBlock,
    ChecklistBlock,
    CodeBlock,
    DefinitionItem,
    DefinitionListBlock,
    DividerBlock,
    FootnoteItem,
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
    TableBlock,
    TocBlock,
)

logger = structlog.get_logger(__name__)

_CALLOUT_VARIANTS = ("info", "note", "tip", "success", "warning", "danger")
_TASK_RE = re.compile(r"^\[( |x|X)\]\s+")
_PAGEBREAK_RE = re.compile(r"^\\(newpage|pagebreak)\s*$")
_PAGEBREAK_HTML_RE = re.compile(r"<!--\s*pagebreak\s*-->", re.IGNORECASE)
_TOC_RE = re.compile(r"^\[TOC\]$", re.IGNORECASE)
_MATH_FENCE_LANGS = ("math", "latex", "tex", "katex")
_FOOTNOTE_REF_RE = re.compile(r"\[\^([^\]\s]+)\]")


@lru_cache(maxsize=1)
def _parser() -> Any:
    from markdown_it import MarkdownIt
    from mdit_py_plugins.amsmath import amsmath_plugin
    from mdit_py_plugins.container import container_plugin
    from mdit_py_plugins.deflist import deflist_plugin
    from mdit_py_plugins.dollarmath import dollarmath_plugin
    from mdit_py_plugins.footnote import footnote_plugin
    from mdit_py_plugins.front_matter import front_matter_plugin

    md = MarkdownIt("commonmark").enable("table").enable("strikethrough")
    try:  # bare-URL autolinks need the optional linkify-it-py package
        import linkify_it  # noqa: F401

        md.options["linkify"] = True
        md.enable("linkify")
    except ImportError:
        pass
    # allow_space/digits=False keeps currency text ("$5 and $10") out of math.
    md.use(dollarmath_plugin, allow_space=False, double_inline=False)
    md.use(amsmath_plugin)
    md.use(footnote_plugin)
    md.use(deflist_plugin)
    md.use(front_matter_plugin)
    for name in _CALLOUT_VARIANTS:
        md.use(container_plugin, name)
    return md


# ---------------------------------------------------------------------------
# Inline spans
# ---------------------------------------------------------------------------


@dataclass
class InlineSpan:
    """One styled run of text produced by :func:`parse_inline`.

    ``math=True`` marks the span text as a LaTeX expression (from
    ``$…$``); ``sup``/``sub`` request super/subscript placement (footnote
    references are emitted as superscript markers).
    """

    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    strike: bool = False
    link: str | None = None
    math: bool = False
    sup: bool = False
    sub: bool = False


def parse_inline(text: str) -> list[InlineSpan]:
    """Parse markdown inline syntax into styled spans.

    Plain text (no markdown markers) round-trips as a single span.
    """
    if not text:
        return []
    if not any(ch in text for ch in "*_`[~\\$:"):
        return [InlineSpan(text=text)]
    try:
        tokens = _parser().parseInline(text)
    except Exception:  # noqa: BLE001 - never fail rendering over inline syntax
        return [InlineSpan(text=text)]
    spans: list[InlineSpan] = []
    for tok in tokens:
        _walk_inline(tok.children or [], spans, _InlineState())
    return spans or [InlineSpan(text=text)]


@dataclass
class _InlineState:
    bold: bool = False
    italic: bool = False
    strike: bool = False
    link: str | None = None
    link_depth: int = 0
    stack: list[str] = field(default_factory=list)


def _walk_inline(children: list[Any], spans: list[InlineSpan], st: _InlineState) -> None:
    for tok in children:
        t = tok.type
        if t == "text":
            if tok.content:
                # Footnote references survive as literal ``[^label]`` when the
                # definition environment is absent (block text is re-parsed at
                # render time) — convert them to superscript markers here.
                pos = 0
                for m in _FOOTNOTE_REF_RE.finditer(tok.content):
                    if m.start() > pos:
                        spans.append(
                            InlineSpan(
                                text=tok.content[pos : m.start()],
                                bold=st.bold,
                                italic=st.italic,
                                strike=st.strike,
                                link=st.link,
                            )
                        )
                    spans.append(InlineSpan(text=m.group(1), sup=True))
                    pos = m.end()
                if pos < len(tok.content):
                    spans.append(
                        InlineSpan(
                            text=tok.content[pos:],
                            bold=st.bold,
                            italic=st.italic,
                            strike=st.strike,
                            link=st.link,
                        )
                    )
        elif t == "code_inline":
            spans.append(
                InlineSpan(text=tok.content, code=True, bold=st.bold, italic=st.italic)
            )
        elif t == "strong_open":
            st.bold = True
        elif t == "strong_close":
            st.bold = False
        elif t == "em_open":
            st.italic = True
        elif t == "em_close":
            st.italic = False
        elif t == "s_open":
            st.strike = True
        elif t == "s_close":
            st.strike = False
        elif t == "link_open":
            st.link = tok.attrGet("href") or None
        elif t == "link_close":
            st.link = None
        elif t == "math_inline":
            spans.append(
                InlineSpan(text=tok.content, math=True, bold=st.bold, italic=st.italic)
            )
        elif t == "footnote_ref":
            meta = tok.meta or {}
            marker = str(meta.get("label") or meta.get("id", 0) + 1)
            spans.append(InlineSpan(text=marker, sup=True))
        elif t in ("softbreak", "hardbreak"):
            spans.append(InlineSpan(text="\n" if t == "hardbreak" else " "))
        elif t == "image":
            alt = tok.content or tok.attrGet("alt") or ""
            if alt:
                spans.append(InlineSpan(text=alt, italic=True))
        elif tok.children:
            _walk_inline(tok.children, spans, st)


def inline_to_plain(text: str) -> str:
    """Strip markdown inline markers, returning plain text."""
    return "".join(s.text for s in parse_inline(text))


# ---------------------------------------------------------------------------
# Block parsing
# ---------------------------------------------------------------------------


def parse_markdown_blocks(markdown_text: str) -> list[Block]:
    """Parse a markdown document into IR blocks."""
    if not markdown_text or not markdown_text.strip():
        return []
    tokens = _parser().parse(markdown_text)
    walker = _TokenWalker(tokens)
    return walker.parse_blocks(until=None)


def parse_markdown_document(markdown_text: str) -> tuple[dict[str, Any], list[Block]]:
    """Parse markdown into ``(front_matter_metadata, blocks)``.

    YAML front matter (``---`` fenced at the top) is returned as a metadata
    dict — callers map recognised keys (title, subtitle, author, date,
    theme, toc, …) onto the :class:`~leagent.docgen.model.DocumentSpec`.
    """
    if not markdown_text or not markdown_text.strip():
        return {}, []
    tokens = _parser().parse(markdown_text)
    meta: dict[str, Any] = {}
    for tok in tokens:
        if tok.type == "front_matter":
            try:
                import yaml

                loaded = yaml.safe_load(tok.content or "")
                if isinstance(loaded, dict):
                    meta = loaded
            except Exception as exc:  # noqa: BLE001 - bad YAML must not fail parsing
                logger.warning("docgen_front_matter_invalid", error=str(exc))
            break
    walker = _TokenWalker(tokens)
    return meta, walker.parse_blocks(until=None)


class _TokenWalker:
    def __init__(self, tokens: list[Any]) -> None:
        self.tokens = tokens
        self.i = 0

    # -- primitives ---------------------------------------------------

    def peek(self) -> Any | None:
        return self.tokens[self.i] if self.i < len(self.tokens) else None

    def next(self) -> Any:
        tok = self.tokens[self.i]
        self.i += 1
        return tok

    def skip_until_close(self, close_type: str) -> None:
        depth = 1
        while self.i < len(self.tokens):
            tok = self.next()
            if tok.type == close_type:
                depth -= 1
                if depth == 0:
                    return

    # -- block parsing --------------------------------------------------

    def parse_blocks(self, until: str | None) -> list[Block]:
        blocks: list[Block] = []
        while self.i < len(self.tokens):
            tok = self.peek()
            if tok is None:
                break
            if until is not None and tok.type == until:
                self.next()
                return blocks
            block = self._parse_one()
            if block is None:
                continue
            if isinstance(block, list):
                blocks.extend(block)
            else:
                blocks.append(block)
        return blocks

    def _parse_one(self) -> Block | list[Block] | None:
        tok = self.next()
        t = tok.type

        if t == "heading_open":
            level = int(tok.tag[1]) if len(tok.tag) == 2 else 1
            inline = self.next()
            self.next()  # heading_close
            return HeadingBlock(text=inline.content or "", level=level)

        if t == "paragraph_open":
            inline = self.next()
            self.next()  # paragraph_close
            return self._paragraph_from_inline(inline)

        if t in ("bullet_list_open", "ordered_list_open"):
            ordered = t == "ordered_list_open"
            items = self._parse_list_items(
                "bullet_list_close" if not ordered else "ordered_list_close"
            )
            return ListBlock(ordered=ordered, items=items)

        if t == "table_open":
            return self._parse_table()

        if t == "fence":
            return self._parse_fence(tok)

        if t == "code_block":
            return CodeBlock(code=tok.content.rstrip("\n"))

        if t == "blockquote_open":
            return self._parse_blockquote()

        if t == "hr":
            return DividerBlock()

        if t in ("math_block", "math_block_label"):
            latex = (tok.content or "").strip()
            return MathBlock(latex=latex) if latex else None

        if t == "amsmath":
            latex = (tok.content or "").strip()
            return MathBlock(latex=latex) if latex else None

        if t == "dl_open":
            return self._parse_definition_list()

        if t == "footnote_block_open":
            return self._parse_footnotes()

        if t == "front_matter":
            return None  # metadata; handled by parse_markdown_document

        if t == "html_block":
            if _PAGEBREAK_HTML_RE.search(tok.content or ""):
                return PageBreakBlock()
            return None

        # Callout containers: container_<name>_open
        if t.startswith("container_") and t.endswith("_open"):
            variant = t[len("container_") : -len("_open")]
            title = (tok.info or "").strip()
            title = title[len(variant):].strip() or None if title.lower().startswith(variant) else title or None
            inner = self.parse_blocks(until=f"container_{variant}_close")
            text = "\n\n".join(
                b.text for b in inner if isinstance(b, ParagraphBlock)
            )
            return CalloutBlock(variant=variant, title=title, text=text)  # type: ignore[arg-type]

        if t.endswith("_open"):
            # Unknown wrapper — skip its subtree to stay well-formed.
            self.skip_until_close(t[: -len("_open")] + "_close")
            return None
        return None

    def _paragraph_from_inline(self, inline: Any) -> Block | None:
        content = (inline.content or "").strip()
        if _TOC_RE.match(content):
            return TocBlock()
        if _PAGEBREAK_RE.match(content) or _PAGEBREAK_HTML_RE.search(content):
            return PageBreakBlock()
        children = inline.children or []
        non_ws = [
            c
            for c in children
            if not (c.type in ("text", "softbreak") and not (c.content or "").strip())
        ]
        if len(non_ws) == 1 and non_ws[0].type == "image":
            img = non_ws[0]
            src = img.attrGet("src") or ""
            alt = img.content or ""
            from leagent.docgen.images import extract_file_id

            fid = extract_file_id(src)
            if fid:
                return ImageBlock(file_id=fid, caption=alt or None)
            if src.startswith(("http://", "https://")):
                return ImageBlock(url=src, caption=alt or None)
            if src.startswith("data:"):
                return ImageBlock(base64_data=src, caption=alt or None)
            return ImageBlock(path=src, caption=alt or None)
        if not content:
            return None
        return ParagraphBlock(text=inline.content or "")

    def _parse_list_items(self, close_type: str) -> list[ListItem]:
        items: list[ListItem] = []
        while self.i < len(self.tokens):
            tok = self.next()
            if tok.type == close_type:
                break
            if tok.type != "list_item_open":
                continue
            item = ListItem(text="")
            texts: list[str] = []
            while self.i < len(self.tokens):
                inner = self.peek()
                if inner is None:
                    break
                if inner.type == "list_item_close":
                    self.next()
                    break
                if inner.type == "paragraph_open":
                    self.next()
                    inline = self.next()
                    self.next()
                    texts.append(inline.content or "")
                elif inner.type in ("bullet_list_open", "ordered_list_open"):
                    self.next()
                    close = (
                        "bullet_list_close"
                        if inner.type == "bullet_list_open"
                        else "ordered_list_close"
                    )
                    item.children.extend(self._parse_list_items(close))
                elif inner.type == "inline":
                    self.next()
                    texts.append(inner.content or "")
                else:
                    self.next()
            raw = "\n".join(x for x in texts if x)
            m = _TASK_RE.match(raw)
            if m:
                item.checked = m.group(1).lower() == "x"
                raw = raw[m.end() :]
            item.text = raw
            items.append(item)
        return items

    def _parse_table(self) -> TableBlock:
        header: list[str] = []
        aligns: list[str] = []
        rows: list[list[str]] = []
        current: list[str] | None = None
        in_header = False
        while self.i < len(self.tokens):
            tok = self.next()
            t = tok.type
            if t == "table_close":
                break
            if t == "thead_open":
                in_header = True
            elif t == "thead_close":
                in_header = False
            elif t == "tr_open":
                current = []
            elif t == "tr_close":
                if current is not None and not in_header:
                    rows.append(current)
                current = None
            elif t in ("th_open", "td_open"):
                style = tok.attrGet("style") or ""
                if in_header:
                    if "center" in style:
                        aligns.append("center")
                    elif "right" in style:
                        aligns.append("right")
                    else:
                        aligns.append("left")
                inline = self.peek()
                cell = ""
                if inline is not None and inline.type == "inline":
                    self.next()
                    cell = inline.content or ""
                if in_header:
                    header.append(cell)
                elif current is not None:
                    current.append(cell)
        return TableBlock(
            columns=header or None,
            rows=rows,
            align=aligns or None,  # type: ignore[arg-type]
        )

    def _parse_definition_list(self) -> DefinitionListBlock:
        items: list[DefinitionItem] = []
        current: DefinitionItem | None = None
        depth = 1
        while self.i < len(self.tokens):
            tok = self.next()
            t = tok.type
            if t == "dl_open":
                depth += 1
            elif t == "dl_close":
                depth -= 1
                if depth == 0:
                    break
            elif t == "dt_open":
                inline = self.peek()
                term = ""
                if inline is not None and inline.type == "inline":
                    self.next()
                    term = inline.content or ""
                current = DefinitionItem(term=term)
                items.append(current)
            elif t == "inline" and current is not None:
                text = (tok.content or "").strip()
                if text:
                    current.definitions.append(text)
        return DefinitionListBlock(items=items)

    def _parse_footnotes(self) -> FootnotesBlock:
        items: list[FootnoteItem] = []
        label = ""
        texts: list[str] = []
        while self.i < len(self.tokens):
            tok = self.next()
            t = tok.type
            if t == "footnote_block_close":
                break
            if t == "footnote_open":
                meta = tok.meta or {}
                label = str(meta.get("label") or meta.get("id", len(items)) + 1)
                texts = []
            elif t == "footnote_close":
                items.append(FootnoteItem(label=label, text="\n".join(texts)))
            elif t == "inline":
                text = (tok.content or "").strip()
                if text:
                    texts.append(text)
        return FootnotesBlock(items=items)

    def _parse_fence(self, tok: Any) -> Block:
        lang = (tok.info or "").strip().split()[0].lower() if (tok.info or "").strip() else ""
        body = tok.content or ""
        if lang in _MATH_FENCE_LANGS:
            latex = body.strip()
            if latex:
                return MathBlock(latex=latex)
            return CodeBlock(code=body.rstrip("\n"), language=lang)
        if lang == "chart":
            payload = _parse_structured_payload(body)
            if payload is not None:
                try:
                    return ChartBlock.model_validate(payload)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("docgen_chart_fence_invalid", error=str(exc))
            return CodeBlock(code=body.rstrip("\n"), language="json")
        if lang == "metrics":
            payload = _parse_structured_payload(body)
            if payload is not None:
                if isinstance(payload, list):
                    payload = {"items": payload}
                try:
                    return MetricsBlock.model_validate(payload)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("docgen_metrics_fence_invalid", error=str(exc))
            return CodeBlock(code=body.rstrip("\n"), language="json")
        if lang == "checklist":
            payload = _parse_structured_payload(body)
            if payload is not None:
                if isinstance(payload, list):
                    payload = {"items": payload}
                try:
                    return ChecklistBlock.model_validate(payload)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("docgen_checklist_fence_invalid", error=str(exc))
            return CodeBlock(code=body.rstrip("\n"), language="json")
        return CodeBlock(code=body.rstrip("\n"), language=lang or None)

    def _parse_blockquote(self) -> QuoteBlock:
        inner = self.parse_blocks(until="blockquote_close")
        parts: list[str] = []
        for b in inner:
            if isinstance(b, (ParagraphBlock, HeadingBlock)):
                parts.append(b.text)
        return QuoteBlock(text="\n\n".join(parts))


def _parse_structured_payload(body: str) -> Any | None:
    """Parse a chart/metrics fence body as JSON, falling back to YAML."""
    body = body.strip()
    if not body:
        return None
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        pass
    try:
        import yaml

        return yaml.safe_load(body)
    except Exception:  # noqa: BLE001
        return None
