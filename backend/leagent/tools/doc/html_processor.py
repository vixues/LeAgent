"""HTML Processor Tool — extract text, links, tables, metadata, and convert to Markdown/plain text."""

from __future__ import annotations

from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


def _read_file(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="replace")


def _normalize_ws(s: str) -> str:
    return " ".join(s.split())


def _is_external_href(href: str) -> bool:
    h = href.strip()
    if not h or h.lower().startswith(("javascript:", "data:", "#")):
        return False
    if h.startswith("//"):
        return True
    p = urlparse(h)
    if p.scheme in ("http", "https", "mailto", "tel", "ftp"):
        return True
    return False


class _SkipScriptStyleMixin:
    _skip_depth: int

    def _ss_start(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip_depth += 1

    def _ss_end(self, tag: str) -> None:
        if tag in ("script", "style", "noscript"):
            self._skip_depth = max(0, self._skip_depth - 1)


class _ReadParser(HTMLParser, _SkipScriptStyleMixin):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._in_title = False
        self.title = ""
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        self._ss_start(t)
        if self._skip_depth:
            return
        if t == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        self._ss_end(t)
        if t == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title += data
        else:
            self.chunks.append(data)


class _LinksParser(HTMLParser, _SkipScriptStyleMixin):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.links: list[dict[str, Any]] = []
        self._in_a = False
        self._href = ""
        self._text_parts: list[str] = []
        self._a_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        self._ss_start(t)
        if self._skip_depth and t != "a":
            return
        if t == "a":
            self._a_depth += 1
            ad = {k.lower(): (v or "") for k, v in attrs}
            href = ad.get("href", "")
            if self._a_depth == 1 and href:
                self._in_a = True
                self._href = href
                self._text_parts = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "a" and self._in_a and self._a_depth == 1:
            text = _normalize_ws(unescape("".join(self._text_parts)))
            self.links.append(
                {
                    "text": text,
                    "href": self._href,
                    "is_external": _is_external_href(self._href),
                }
            )
            self._in_a = False
        if t == "a":
            self._a_depth = max(0, self._a_depth - 1)
        self._ss_end(t)

    def handle_data(self, data: str) -> None:
        if self._in_a and not self._skip_depth:
            self._text_parts.append(data)


class _TableState:
    __slots__ = ("rows", "cur_row", "in_thead", "cell_parts", "in_cell", "cell_tag")

    def __init__(self) -> None:
        self.rows: list[list[tuple[str, str]]] = []
        self.cur_row: list[tuple[str, str]] | None = None
        self.in_thead = False
        self.cell_parts: list[str] = []
        self.in_cell = False
        self.cell_tag = "td"


class _TablesParser(HTMLParser, _SkipScriptStyleMixin):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.tables: list[dict[str, Any]] = []
        self._stack: list[_TableState] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        self._ss_start(t)
        if self._skip_depth:
            return
        if t == "table":
            self._stack.append(_TableState())
            return
        if not self._stack:
            return
        st = self._stack[-1]
        if t == "thead":
            st.in_thead = True
        elif t == "tbody" or t == "tfoot":
            st.in_thead = False
        elif t == "tr":
            st.cur_row = []
        elif t in ("td", "th"):
            st.in_cell = True
            st.cell_tag = t
            st.cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        self._ss_end(t)
        if self._skip_depth:
            return
        if not self._stack:
            return
        st = self._stack[-1]
        if t in ("td", "th") and st.in_cell:
            txt = _normalize_ws(unescape("".join(st.cell_parts)))
            if st.cur_row is not None:
                st.cur_row.append((st.cell_tag, txt))
            st.in_cell = False
        elif t == "tr" and st.cur_row is not None:
            st.rows.append(st.cur_row)
            st.cur_row = None
        elif t == "table":
            finished = self._stack.pop()
            built = _table_dict_from_rows(finished.rows)
            if self._stack:
                parent = self._stack[-1]
                nested_txt = _format_table_plain(built)
                if parent.in_cell:
                    parent.cell_parts.append(nested_txt)
                elif parent.cur_row is not None:
                    parent.cur_row.append(("td", nested_txt))
            else:
                self.tables.append(built)

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._stack and self._stack[-1].in_cell:
            self._stack[-1].cell_parts.append(data)


def _table_dict_from_rows(rows: list[list[tuple[str, str]]]) -> dict[str, Any]:
    if not rows:
        return {"headers": [], "rows": []}
    header_idx = None
    for i, row in enumerate(rows):
        if row and all(c[0] == "th" for c in row):
            header_idx = i
            break
    if header_idx is None and rows[0] and all(c[0] == "th" for c in rows[0]):
        header_idx = 0
    if header_idx is not None:
        headers = [c[1] for c in rows[header_idx]]
        body = rows[header_idx + 1 :]
    else:
        max_cols = max((len(r) for r in rows), default=0)
        headers = [f"Column{i + 1}" for i in range(max_cols)]
        body = rows
    out_rows: list[dict[str, str]] = []
    for row in body:
        cells = [c[1] for c in row]
        d: dict[str, str] = {}
        for j, h in enumerate(headers):
            d[h] = cells[j] if j < len(cells) else ""
        out_rows.append(d)
    return {"headers": headers, "rows": out_rows}


def _format_table_plain(t: dict[str, Any]) -> str:
    lines = []
    if t["headers"]:
        lines.append(" | ".join(t["headers"]))
    for r in t["rows"]:
        lines.append(" | ".join(str(r.get(h, "")) for h in t["headers"]))
    return "\n".join(lines)


class _MetaParser(HTMLParser, _SkipScriptStyleMixin):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._in_title = False
        self.title = ""
        self.description = ""
        self.keywords = ""
        self.charset = ""
        self.og_tags: dict[str, str] = {}
        self.other_meta: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        self._ss_start(t)
        if self._skip_depth:
            return
        ad = {k.lower(): (v or "") for k, v in attrs}
        if t == "title":
            self._in_title = True
        elif t == "meta":
            name = ad.get("name", "").lower()
            prop = ad.get("property", "").lower()
            content = ad.get("content", "")
            http_equiv = ad.get("http-equiv", "").lower()
            if ad.get("charset"):
                self.charset = ad["charset"].strip()
            elif http_equiv == "content-type" and "charset=" in content.lower():
                part = content.lower().split("charset=")
                if len(part) > 1:
                    self.charset = part[1].split(";")[0].strip().strip('"')
            if name == "description":
                self.description = content
            elif name == "keywords":
                self.keywords = content
            elif prop.startswith("og:"):
                self.og_tags[prop] = content
            elif name or prop:
                self.other_meta.append(
                    {
                        "name": name or "",
                        "property": prop or "",
                        "content": content,
                    }
                )

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "title":
            self._in_title = False
        self._ss_end(t)

    def handle_data(self, data: str) -> None:
        if self._in_title and not self._skip_depth:
            self.title += data


class _MdTableAwareParser(HTMLParser, _SkipScriptStyleMixin):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._out: list[str] = []
        self._pre_depth = 0
        self._list_stack: list[tuple[str, int]] = []
        self._tbl_depth = 0
        self._nested_stack: list[list[str]] = []
        self._table_rows: list[list[str]] = []
        self._cur_cells: list[str] = []
        self._cell_buf: list[str] = []
        self._in_cell = False
        self._fmt: list[str] = []
        self._a_depth = 0
        self._a_href = ""
        self._a_buf: list[str] = []

    def _flush_cell(self) -> None:
        if self._in_cell:
            raw = "".join(self._cell_buf)
            self._cur_cells.append(_inline_md_text(raw))
            self._cell_buf = []
            self._in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        self._ss_start(t)
        if self._skip_depth:
            return
        ad = {k.lower(): (v or "") for k, v in attrs}
        if t == "table":
            self._tbl_depth += 1
            if self._tbl_depth == 1:
                self._table_rows = []
                self._cur_cells = []
            else:
                self._nested_stack.append([])
            return
        if self._tbl_depth > 1:
            if t == "br" and self._nested_stack:
                self._nested_stack[-1].append(" ")
            return
        if self._tbl_depth == 1:
            if t == "tr":
                self._flush_cell()
            elif t in ("td", "th"):
                self._flush_cell()
                self._in_cell = True
                self._cell_buf = []
            return
        if t == "br":
            self._out.append("\n")
        elif t == "p":
            self._out.append("\n\n")
        elif t in ("h1", "h2", "h3", "h4", "h5", "h6"):
            n = int(t[1]) - 1
            self._out.append("\n\n" + "#" * (n + 1) + " ")
        elif t in ("strong", "b"):
            self._fmt.append("b")
            self._out.append("**")
        elif t in ("em", "i"):
            self._fmt.append("i")
            self._out.append("*")
        elif t == "code" and self._pre_depth == 0:
            self._out.append("`")
        elif t == "pre":
            self._pre_depth += 1
            self._out.append("\n```\n")
        elif t == "ul":
            self._list_stack.append(("ul", 0))
            self._out.append("\n")
        elif t == "ol":
            self._list_stack.append(("ol", 1))
            self._out.append("\n")
        elif t == "li":
            pref = "  " * len(self._list_stack)
            if self._list_stack:
                kind, idx = self._list_stack[-1]
                if kind == "ul":
                    self._out.append(f"{pref}- ")
                else:
                    self._out.append(f"{pref}{idx}. ")
                    self._list_stack[-1] = ("ol", idx + 1)
            else:
                self._out.append("- ")
        elif t == "a":
            self._a_depth += 1
            if self._a_depth == 1:
                self._a_href = ad.get("href", "")
                self._a_buf = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t == "table" and self._tbl_depth > 0:
            if self._tbl_depth > 1:
                if self._nested_stack:
                    parts = self._nested_stack.pop()
                    txt = _normalize_ws("".join(parts))
                    self._tbl_depth -= 1
                    if self._tbl_depth >= 1:
                        if self._in_cell:
                            self._cell_buf.append(txt)
                        else:
                            self._out.append(txt)
                else:
                    self._tbl_depth -= 1
                self._ss_end(t)
                return
            self._flush_cell()
            self._out.append(_rows_to_md_table(self._table_rows))
            self._table_rows = []
            self._cur_cells = []
            self._tbl_depth -= 1
            self._ss_end(t)
            return
        if self._tbl_depth == 1:
            if t in ("td", "th"):
                self._flush_cell()
            elif t == "tr":
                self._flush_cell()
                if self._cur_cells:
                    self._table_rows.append(self._cur_cells)
                self._cur_cells = []
            self._ss_end(t)
            return
        if t in ("strong", "b") and self._fmt and self._fmt[-1] == "b":
            self._out.append("**")
            self._fmt.pop()
        elif t in ("em", "i") and self._fmt and self._fmt[-1] == "i":
            self._out.append("*")
            self._fmt.pop()
        elif t == "code" and self._pre_depth == 0:
            self._out.append("`")
        elif t == "pre":
            self._pre_depth = max(0, self._pre_depth - 1)
            self._out.append("\n```\n")
        elif t in ("ul", "ol"):
            if self._list_stack:
                self._list_stack.pop()
            self._out.append("\n")
        elif t == "li":
            self._out.append("\n")
        elif t in ("h1", "h2", "h3", "h4", "h5", "h6", "p"):
            self._out.append("\n\n")
        elif t == "a" and self._a_depth == 1:
            inner = "".join(self._a_buf)
            inner = unescape(inner)
            h = self._a_href
            if h:
                self._out.append(f"[{inner}]({h})")
            else:
                self._out.append(inner)
            self._a_depth = 0
        elif t == "a":
            self._a_depth = max(0, self._a_depth - 1)
        self._ss_end(t)

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._tbl_depth > 1 and self._nested_stack:
            self._nested_stack[-1].append(data)
            return
        if self._tbl_depth == 1 and self._in_cell:
            self._cell_buf.append(data)
            return
        if self._a_depth >= 1:
            self._a_buf.append(data)
            return
        self._out.append(data)

    def text(self) -> str:
        return "".join(self._out)


def _inline_md_text(raw: str) -> str:
    s = unescape(raw)
    s = s.replace("\n", " ")
    return s.strip()


def _rows_to_md_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    ncols = max((len(r) for r in rows), default=0)
    if ncols == 0:
        return ""
    esc = lambda c: c.replace("|", "\\|")
    lines = []
    header = list(rows[0]) + [""] * (ncols - len(rows[0]))
    header = [esc(c) for c in header[:ncols]]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("| " + " | ".join(["---"] * ncols) + " |")
    for row in rows[1:]:
        cells = list(row) + [""] * (ncols - len(row))
        lines.append("| " + " | ".join(esc(c) for c in cells[:ncols]) + " |")
    return "\n" + "\n".join(lines) + "\n\n"


def _html_to_markdown(html: str) -> str:
    p1 = _MdTableAwareParser()
    p1.feed(html)
    p1.close()
    return p1.text().strip()


class HTMLProcessorTool(SyncTool):
    name = "html_processor"
    description = (
        "Read and analyze HTML files: plain text, links, tables, meta tags, "
        "and conversion to Markdown or plain text."
    )
    category = ToolCategory.DOC
    version = "1.0.0"
    timeout_sec = 60
    aliases = ["html", "html_reader", "html_parser"]
    search_hint = "HTML read parse extract links tables meta convert markdown text"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    path_params = ("file_path",)
    output_path_params = ("output_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "read",
                        "extract_links",
                        "extract_tables",
                        "extract_metadata",
                        "convert",
                    ],
                    "description": "Operation to perform on the HTML file.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the HTML file.",
                },
                "table_index": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Zero-based index of a single table (extract_tables only).",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["markdown", "plain_text"],
                    "description": "Target format for convert operation.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional path to write converted output.",
                },
            },
            "required": ["operation", "file_path"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Processing HTML"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        op = params["operation"]
        path = Path(params["file_path"])
        if not path.is_file():
            raise FileNotFoundError(f"HTML file not found: {path}")

        html = _read_file(path)
        logger.info("html_processor", operation=op, file_path=str(path))

        if op == "read":
            return self._op_read(html)
        if op == "extract_links":
            return self._op_links(html)
        if op == "extract_tables":
            return self._op_tables(html, params.get("table_index"))
        if op == "extract_metadata":
            return self._op_meta(html)
        if op == "convert":
            fmt = params.get("output_format")
            if not fmt:
                raise ValueError("convert requires output_format: markdown or plain_text")
            return self._op_convert(html, fmt, params.get("output_path"))

        raise ValueError(f"Unknown operation: {op}")

    def _op_read(self, html: str) -> dict[str, Any]:
        p = _ReadParser()
        p.feed(html)
        p.close()
        text = _normalize_ws(unescape("".join(p.chunks)))
        title = _normalize_ws(unescape(p.title))
        char_count = len(text)
        word_count = len(text.split()) if text else 0
        return {
            "text": text,
            "title": title,
            "word_count": word_count,
            "char_count": char_count,
        }

    def _op_links(self, html: str) -> dict[str, Any]:
        p = _LinksParser()
        p.feed(html)
        p.close()
        return {"links": p.links}

    def _op_tables(self, html: str, table_index: int | None) -> dict[str, Any]:
        p = _TablesParser()
        p.feed(html)
        p.close()
        tables = p.tables
        if table_index is not None:
            if table_index < 0 or table_index >= len(tables):
                raise IndexError(f"table_index {table_index} out of range (0..{len(tables) - 1})")
            tables = [tables[table_index]]
        return {"tables": tables}

    def _op_meta(self, html: str) -> dict[str, Any]:
        p = _MetaParser()
        p.feed(html)
        p.close()
        return {
            "title": _normalize_ws(unescape(p.title)),
            "description": p.description,
            "keywords": p.keywords,
            "og_tags": p.og_tags,
            "charset": p.charset,
            "other_meta": p.other_meta,
        }

    def _op_convert(self, html: str, fmt: str, output_path: str | None) -> dict[str, Any]:
        if fmt == "plain_text":
            pr = _ReadParser()
            pr.feed(html)
            pr.close()
            content = _normalize_ws(unescape("".join(pr.chunks)))
        else:
            content = _html_to_markdown(html)

        result: dict[str, Any] = {"content": content, "output_format": fmt}
        if output_path:
            out = Path(output_path)
            out.write_text(content, encoding="utf-8")
            result["output_path"] = str(out.resolve())
        return result
