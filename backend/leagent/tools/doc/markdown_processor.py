"""Markdown Processor Tool — full-featured markdown reading, writing, and authoring.

Provides professional markdown document lifecycle management:
- Read & parse: headings, TOC, links, images, code blocks, frontmatter
- Write: save markdown content directly to file
- Create: build structured markdown from parameters (title, sections, metadata)
- Append/Prepend: add content to existing documents
- Insert/Replace section: surgical editing by heading
- Merge: combine multiple markdown files
- Template: generate from predefined document templates
- Convert: export to HTML or plain text
- Format: prettify and normalize markdown
"""

from __future__ import annotations

import html
import re
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

_HEADING_LINE = re.compile(r"^(#{1,6})\s+(.+)$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_CODE_FENCE = re.compile(r"^```([^\n`]*)\r?\n(.*?)^```\s*$", re.MULTILINE | re.DOTALL)
_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_TRAILING_SPACES = re.compile(r"[ \t]+$", re.MULTILINE)
_MULTIPLE_BLANK = re.compile(r"\n{3,}")
_TABLE_ROW = re.compile(r"^\|(.+)\|$")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _write_text(path: Path, content: str) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return len(content)


def _parse_headings(lines: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, line in enumerate(lines, start=1):
        m = _HEADING_LINE.match(line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            out.append({"level": level, "text": text, "line": i})
    return out


def _parse_links(text: str) -> list[dict[str, str]]:
    return [{"text": t, "url": u} for t, u in _LINK.findall(text)]


def _parse_images(text: str) -> list[dict[str, str]]:
    return [{"alt": a, "src": s} for a, s in _IMAGE.findall(text)]


def _parse_code_blocks(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    for m in _CODE_FENCE.finditer(text):
        lang = (m.group(1) or "").strip()
        code = m.group(2)
        if code.endswith("\n"):
            code = code[:-1]
        blocks.append({"language": lang, "code": code})
    return blocks


def _code_blocks_with_lines(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in _CODE_FENCE.finditer(text):
        lang = (m.group(1) or "").strip()
        code = m.group(2)
        if code.endswith("\n"):
            code = code[:-1]
        line_number = text[: m.start()].count("\n") + 1
        out.append({"language": lang, "code": code, "line_number": line_number})
    return out


def _parse_frontmatter(text: str) -> dict[str, str] | None:
    m = _FRONTMATTER.match(text)
    if not m:
        return None
    fm: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            fm[key.strip()] = val.strip().strip('"').strip("'")
    return fm


def _nest_toc(headings: list[dict[str, Any]], max_depth: int) -> list[dict[str, Any]]:
    root: list[dict[str, Any]] = []
    stack: list[tuple[int, dict[str, Any]]] = []
    for h in headings:
        if h["level"] > max_depth:
            continue
        node: dict[str, Any] = {
            "level": h["level"],
            "text": h["text"],
            "line": h["line"],
            "children": [],
        }
        while stack and stack[-1][0] >= h["level"]:
            stack.pop()
        if not stack:
            root.append(node)
        else:
            stack[-1][1]["children"].append(node)
        stack.append((h["level"], node))
    return root


def _inline_markdown_to_html(text: str) -> str:
    def repl_code(m: re.Match[str]) -> str:
        return f"<code>{html.escape(m.group(1))}</code>"

    s = re.sub(r"`([^`]+)`", repl_code, text)
    s = re.sub(
        r"\*\*([^*]+)\*\*",
        lambda m: f"<strong>{html.escape(m.group(1))}</strong>",
        s,
    )
    s = re.sub(
        r"(?<!\*)\*([^*]+)\*(?!\*)",
        lambda m: f"<em>{html.escape(m.group(1))}</em>",
        s,
    )

    def repl_link(m: re.Match[str]) -> str:
        label = html.escape(m.group(1))
        url = html.escape(m.group(2), quote=True)
        return f'<a href="{url}">{label}</a>'

    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", repl_link, s)
    return s


def _markdown_to_html(md: str) -> str:
    lines = md.splitlines()
    html_parts: list[str] = []
    para_buf: list[str] = []
    in_code = False
    code_buf: list[str] = []
    code_lang = ""

    def flush_para() -> None:
        nonlocal para_buf
        if para_buf:
            joined = " ".join(para_buf)
            html_parts.append(f"<p>{_inline_markdown_to_html(joined)}</p>")
            para_buf = []

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_para()
            if not in_code:
                in_code = True
                code_lang = stripped[3:].strip()
                code_buf = []
            else:
                in_code = False
                code = "\n".join(code_buf)
                lang_attr = ""
                if code_lang:
                    lang_attr = f' class="language-{html.escape(code_lang)}"'
                html_parts.append(f"<pre><code{lang_attr}>{html.escape(code)}</code></pre>")
            i += 1
            continue
        if in_code:
            code_buf.append(line)
            i += 1
            continue
        hm = re.match(r"^(#{1,6})\s+(.+)$", line)
        if hm:
            flush_para()
            level = len(hm.group(1))
            inner = _inline_markdown_to_html(hm.group(2).strip())
            html_parts.append(f"<h{level}>{inner}</h{level}>")
            i += 1
            continue
        if not stripped:
            flush_para()
            i += 1
            continue
        para_buf.append(stripped)
        i += 1
    flush_para()
    return "\n".join(html_parts)


def _markdown_to_plain(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    in_code = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            out.append(line)
            continue
        s = line
        s = re.sub(r"^#{1,6}\s+", "", s)
        s = re.sub(r"`([^`]+)`", r"\1", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", s)
        s = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"\1", s)
        out.append(s)
    return "\n".join(out)


def _format_markdown(text: str) -> str:
    """Normalize and prettify markdown text."""
    result = _TRAILING_SPACES.sub("", text)
    result = _MULTIPLE_BLANK.sub("\n\n", result)
    lines = result.splitlines()
    formatted: list[str] = []
    for i, line in enumerate(lines):
        formatted.append(line)
        if _HEADING_LINE.match(line):
            if i + 1 < len(lines) and lines[i + 1].strip():
                formatted.append("")
    result = "\n".join(formatted)
    if not result.endswith("\n"):
        result += "\n"
    return result


def _find_section_range(
    lines: list[str], section_title: str
) -> tuple[int, int] | None:
    """Find the line range [start, end) for a section by its heading text."""
    start_idx: int | None = None
    start_level: int = 0
    for i, line in enumerate(lines):
        m = _HEADING_LINE.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
            if start_idx is None:
                if title.lower() == section_title.lower():
                    start_idx = i
                    start_level = level
            else:
                if level <= start_level:
                    return (start_idx, i)
    if start_idx is not None:
        return (start_idx, len(lines))
    return None


def _build_table(headers: list[str], rows: list[list[str]], align: str | None = None) -> str:
    """Build a markdown table from headers and rows."""
    if not headers:
        return ""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(cell))

    def pad(val: str, width: int) -> str:
        return val.ljust(width)

    header_line = "| " + " | ".join(pad(h, col_widths[i]) for i, h in enumerate(headers)) + " |"

    if align == "center":
        sep_line = "| " + " | ".join(":" + "-" * (w - 2) + ":" if w > 2 else ":-:" for w in col_widths) + " |"
    elif align == "right":
        sep_line = "| " + " | ".join("-" * (w - 1) + ":" for w in col_widths) + " |"
    else:
        sep_line = "| " + " | ".join("-" * w for w in col_widths) + " |"

    body_lines = []
    for row in rows:
        cells = []
        for i in range(len(headers)):
            val = row[i] if i < len(row) else ""
            cells.append(pad(val, col_widths[i]))
        body_lines.append("| " + " | ".join(cells) + " |")

    return "\n".join([header_line, sep_line] + body_lines)


def _build_list(items: list[Any], ordered: bool = False, indent: int = 0) -> str:
    """Build a markdown list (ordered or unordered), supports nested lists."""
    lines: list[str] = []
    prefix_space = "  " * indent
    for i, item in enumerate(items, start=1):
        if isinstance(item, dict):
            text = item.get("text", str(item))
            children = item.get("children", [])
        elif isinstance(item, (list, tuple)) and len(item) >= 1:
            text = str(item[0])
            children = item[1] if len(item) > 1 and isinstance(item[1], list) else []
        else:
            text = str(item)
            children = []

        marker = f"{i}." if ordered else "-"
        lines.append(f"{prefix_space}{marker} {text}")
        if children:
            lines.append(_build_list(children, ordered=ordered, indent=indent + 1))
    return "\n".join(lines)


_TEMPLATES: dict[str, dict[str, Any]] = {
    "story": {
        "structure": ["title", "meta", "body"],
        "description": "Creative writing / story template",
    },
    "report": {
        "structure": ["title", "meta", "summary", "sections", "conclusion"],
        "description": "Formal report template",
    },
    "notes": {
        "structure": ["title", "meta", "body"],
        "description": "Quick notes template",
    },
    "article": {
        "structure": ["title", "meta", "abstract", "sections", "references"],
        "description": "Article / blog post template",
    },
    "meeting": {
        "structure": ["title", "meta", "attendees", "agenda", "notes", "action_items"],
        "description": "Meeting minutes template",
    },
    "readme": {
        "structure": ["title", "badges", "description", "installation", "usage", "api", "license"],
        "description": "Project README template",
    },
    "changelog": {
        "structure": ["title", "entries"],
        "description": "CHANGELOG template",
    },
}


class MarkdownProcessorTool(SyncTool):
    name = "markdown_processor"
    description = (
        "Professional Markdown document processor: read/parse structure, "
        "write/create/append markdown files, insert/replace/delete sections, "
        "build tables and lists, apply templates (story/report/article/meeting/readme/changelog), "
        "merge multiple files, format/prettify, generate TOC, and convert to HTML/plain text. "
        "Use this tool to directly create and edit markdown documents without writing code."
    )
    category = ToolCategory.DOC
    version = "2.0.0"
    timeout_sec = 60
    aliases = ["markdown", "md", "md_writer", "md_reader"]
    search_hint = (
        "Markdown read write create save author document TOC headings code blocks "
        "convert HTML text template story report notes article section table list format"
    )
    is_concurrency_safe = True
    is_read_only = False
    is_destructive = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000
    path_params = ("file_path_2", "merge_files")
    output_path_params = ("file_path", "output_path")

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "read",
                        "write",
                        "create",
                        "append",
                        "prepend",
                        "insert_section",
                        "replace_section",
                        "delete_section",
                        "extract_toc",
                        "generate_toc",
                        "extract_code_blocks",
                        "build_table",
                        "build_list",
                        "merge",
                        "format",
                        "convert",
                        "template",
                    ],
                    "description": (
                        "Operation: read|write|create|append|prepend|insert_section|"
                        "replace_section|delete_section|extract_toc|generate_toc|"
                        "extract_code_blocks|build_table|build_list|merge|format|convert|template"
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the Markdown file (for read/write/append/prepend/insert/replace/delete/format/convert/merge output).",
                },
                "content": {
                    "type": "string",
                    "description": "Markdown text content for write/append/prepend/insert_section operations.",
                },
                "title": {
                    "type": "string",
                    "description": "Document title for create/template operations.",
                },
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "level": {"type": "integer", "minimum": 1, "maximum": 6},
                            "content": {"type": "string"},
                        },
                    },
                    "description": "Sections array for create operation. Each has heading, level (default 2), and content.",
                },
                "metadata": {
                    "type": "object",
                    "description": "YAML frontmatter key-value pairs for create/template (e.g. author, date, tags).",
                },
                "section_title": {
                    "type": "string",
                    "description": "Target section heading for insert_section/replace_section/delete_section.",
                },
                "position": {
                    "type": "string",
                    "enum": ["before", "after", "replace"],
                    "description": "Where to insert relative to section_title (default: after).",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum heading depth for TOC (default: 3).",
                    "minimum": 1,
                    "maximum": 6,
                },
                "language": {
                    "type": "string",
                    "description": "Language filter for extract_code_blocks.",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["html", "plain_text"],
                    "description": "Output format for convert operation.",
                },
                "output_path": {
                    "type": "string",
                    "description": "Optional path to write output (for convert/generate_toc).",
                },
                "merge_files": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of file paths to merge (for merge operation).",
                },
                "separator": {
                    "type": "string",
                    "description": "Separator between merged files (default: '\\n\\n---\\n\\n').",
                },
                "template_name": {
                    "type": "string",
                    "enum": ["story", "report", "notes", "article", "meeting", "readme", "changelog"],
                    "description": "Template to use for template operation.",
                },
                "template_data": {
                    "type": "object",
                    "description": "Data to populate template fields (varies by template).",
                },
                "headers": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Column headers for build_table.",
                },
                "rows": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "string"}},
                    "description": "Table rows for build_table (array of arrays).",
                },
                "align": {
                    "type": "string",
                    "enum": ["left", "center", "right"],
                    "description": "Table column alignment (default: left).",
                },
                "items": {
                    "type": "array",
                    "description": "Items for build_list. Strings or objects with {text, children}.",
                },
                "ordered": {
                    "type": "boolean",
                    "description": "Whether to create an ordered (numbered) list. Default false.",
                },
                "file_path_2": {
                    "type": "string",
                    "description": "Second file for operations that need two paths.",
                },
            },
            "required": ["operation"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "processing")
        return f"Markdown: {op}"

    def recover_raw_args(self, raw: str) -> dict[str, Any] | None:
        from leagent.tools.doc._recovery import recover_doc_tool_args

        return recover_doc_tool_args(raw, content_key="content")

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        operation = self.require_param(params, "operation")
        logger.info("markdown_processor", operation=operation)

        dispatch = {
            "read": self._read,
            "write": self._write,
            "create": self._create,
            "append": self._append,
            "prepend": self._prepend,
            "insert_section": self._insert_section,
            "replace_section": self._replace_section,
            "delete_section": self._delete_section,
            "extract_toc": self._extract_toc,
            "generate_toc": self._generate_toc,
            "extract_code_blocks": self._extract_code_blocks,
            "build_table": self._build_table,
            "build_list": self._build_list,
            "merge": self._merge,
            "format": self._format,
            "convert": self._convert,
            "template": self._template,
        }
        if operation not in dispatch:
            raise ValueError(f"Unknown operation: {operation}")
        return dispatch[operation](params)

    def _read(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(self.require_param(params, "file_path"))
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not file_path.is_file():
            raise ValueError(f"Not a file: {file_path}")

        raw = _read_text(file_path)
        lines = raw.splitlines()
        headings = _parse_headings(lines)
        links = _parse_links(raw)
        images = _parse_images(raw)
        code_blocks = _parse_code_blocks(raw)
        frontmatter = _parse_frontmatter(raw)
        words = re.findall(r"\S+", raw)
        return {
            "raw_text": raw,
            "headings": headings,
            "links": links,
            "images": images,
            "code_blocks": code_blocks,
            "frontmatter": frontmatter,
            "word_count": len(words),
            "line_count": len(lines),
            "char_count": len(raw),
        }

    def _write(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(self.require_param(params, "file_path"))
        content = params.get("content")
        if content is None:
            raise ValueError("'content' is required for write operation")

        chars = _write_text(file_path, content)
        return {
            "success": True,
            "file_path": str(file_path),
            "chars_written": chars,
            "line_count": content.count("\n") + (1 if content and not content.endswith("\n") else 0),
            "size_bytes": file_path.stat().st_size,
        }

    def _create(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(self.require_param(params, "file_path"))
        title = params.get("title", "Untitled")
        sections = params.get("sections") or []
        metadata = params.get("metadata")
        body_content = params.get("content")

        parts: list[str] = []

        if metadata:
            fm_lines = ["---"]
            for k, v in metadata.items():
                if isinstance(v, list):
                    fm_lines.append(f"{k}:")
                    for item in v:
                        fm_lines.append(f"  - {item}")
                else:
                    fm_lines.append(f"{k}: {v}")
            fm_lines.append("---")
            parts.append("\n".join(fm_lines))

        parts.append(f"# {title}")

        # When content is provided as a raw string and no sections, use it as document body
        if body_content and not sections:
            parts.append(body_content)
        else:
            for sec in sections:
                heading = sec.get("heading", "")
                level = sec.get("level", 2)
                content = sec.get("content", "")
                prefix = "#" * level
                parts.append(f"{prefix} {heading}")
                if content:
                    parts.append(content)

        doc = "\n\n".join(parts) + "\n"
        chars = _write_text(file_path, doc)
        return {
            "success": True,
            "file_path": str(file_path),
            "chars_written": chars,
            "sections_count": len(sections),
            "has_frontmatter": metadata is not None,
        }

    def _append(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(self.require_param(params, "file_path"))
        content = params.get("content")
        if content is None:
            raise ValueError("'content' is required for append operation")

        existing = ""
        if file_path.exists():
            existing = _read_text(file_path)

        separator = "\n\n" if existing and not existing.endswith("\n\n") else ("\n" if existing and not existing.endswith("\n") else "")
        new_content = existing + separator + content
        chars = _write_text(file_path, new_content)
        return {
            "success": True,
            "file_path": str(file_path),
            "total_chars": chars,
            "appended_chars": len(content),
        }

    def _prepend(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(self.require_param(params, "file_path"))
        content = params.get("content")
        if content is None:
            raise ValueError("'content' is required for prepend operation")

        existing = ""
        if file_path.exists():
            existing = _read_text(file_path)

        separator = "\n\n" if existing and not existing.startswith("\n") else ""
        new_content = content + separator + existing
        chars = _write_text(file_path, new_content)
        return {
            "success": True,
            "file_path": str(file_path),
            "total_chars": chars,
            "prepended_chars": len(content),
        }

    def _insert_section(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(self.require_param(params, "file_path"))
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        section_title = params.get("section_title")
        content = params.get("content")
        position = params.get("position", "after")
        if not section_title:
            raise ValueError("'section_title' is required")
        if content is None:
            raise ValueError("'content' is required")

        raw = _read_text(file_path)
        lines = raw.splitlines()
        rng = _find_section_range(lines, section_title)
        if rng is None:
            raise ValueError(f"Section not found: '{section_title}'")

        start, end = rng
        insert_lines = content.splitlines()

        if position == "before":
            new_lines = lines[:start] + [""] + insert_lines + [""] + lines[start:]
        elif position == "replace":
            new_lines = lines[:start] + insert_lines + lines[end:]
        else:
            new_lines = lines[:end] + [""] + insert_lines + [""] + lines[end:]

        new_content = "\n".join(new_lines)
        chars = _write_text(file_path, new_content)
        return {
            "success": True,
            "file_path": str(file_path),
            "position": position,
            "section_title": section_title,
            "chars_written": chars,
        }

    def _replace_section(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(self.require_param(params, "file_path"))
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        section_title = params.get("section_title")
        content = params.get("content")
        if not section_title:
            raise ValueError("'section_title' is required")
        if content is None:
            raise ValueError("'content' is required")

        raw = _read_text(file_path)
        lines = raw.splitlines()
        rng = _find_section_range(lines, section_title)
        if rng is None:
            raise ValueError(f"Section not found: '{section_title}'")

        start, end = rng
        heading_line = lines[start]
        replacement_lines = [heading_line, ""] + content.splitlines()
        new_lines = lines[:start] + replacement_lines + lines[end:]
        new_content = "\n".join(new_lines)
        chars = _write_text(file_path, new_content)
        return {
            "success": True,
            "file_path": str(file_path),
            "section_title": section_title,
            "chars_written": chars,
        }

    def _delete_section(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(self.require_param(params, "file_path"))
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        section_title = params.get("section_title")
        if not section_title:
            raise ValueError("'section_title' is required")

        raw = _read_text(file_path)
        lines = raw.splitlines()
        rng = _find_section_range(lines, section_title)
        if rng is None:
            raise ValueError(f"Section not found: '{section_title}'")

        start, end = rng
        new_lines = lines[:start] + lines[end:]
        new_content = "\n".join(new_lines)
        chars = _write_text(file_path, new_content)
        return {
            "success": True,
            "file_path": str(file_path),
            "section_title": section_title,
            "lines_removed": end - start,
            "chars_written": chars,
        }

    def _extract_toc(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(self.require_param(params, "file_path"))
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        raw = _read_text(file_path)
        lines = raw.splitlines()
        max_depth = int(params.get("max_depth", 3))
        headings = _parse_headings(lines)
        toc = _nest_toc(headings, max_depth)
        return {"toc": toc, "max_depth": max_depth, "heading_count": len(headings)}

    def _generate_toc(self, params: dict[str, Any]) -> dict[str, Any]:
        """Generate a markdown TOC string and optionally insert it into the file."""
        file_path = Path(self.require_param(params, "file_path"))
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        raw = _read_text(file_path)
        lines = raw.splitlines()
        max_depth = int(params.get("max_depth", 3))
        headings = _parse_headings(lines)

        toc_lines: list[str] = []
        for h in headings:
            if h["level"] > max_depth:
                continue
            indent = "  " * (h["level"] - 1)
            anchor = re.sub(r"[^\w\s-]", "", h["text"].lower())
            anchor = re.sub(r"\s+", "-", anchor.strip())
            toc_lines.append(f"{indent}- [{h['text']}](#{anchor})")

        toc_md = "\n".join(toc_lines)
        result: dict[str, Any] = {"toc_markdown": toc_md, "heading_count": len(headings)}

        output_path = params.get("output_path")
        if output_path:
            _write_text(Path(output_path), toc_md + "\n")
            result["output_path"] = output_path
            result["written"] = True

        return result

    def _extract_code_blocks(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(self.require_param(params, "file_path"))
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        raw = _read_text(file_path)
        lang_filter = params.get("language")
        lang_filter_norm = (lang_filter or "").strip().lower() or None
        blocks = _code_blocks_with_lines(raw)
        if lang_filter_norm:
            blocks = [
                b for b in blocks
                if (b.get("language") or "").strip().lower() == lang_filter_norm
            ]
        return {"code_blocks": blocks, "count": len(blocks)}

    def _build_table(self, params: dict[str, Any]) -> dict[str, Any]:
        headers = params.get("headers")
        rows = params.get("rows")
        if not headers:
            raise ValueError("'headers' is required for build_table")
        if rows is None:
            rows = []

        align = params.get("align", "left")
        table_md = _build_table(headers, rows, align)

        file_path = params.get("file_path")
        if file_path:
            fp = Path(file_path)
            if fp.exists():
                existing = _read_text(fp)
                sep = "\n\n" if existing and not existing.endswith("\n\n") else ("\n" if existing and not existing.endswith("\n") else "")
                _write_text(fp, existing + sep + table_md + "\n")
            else:
                _write_text(fp, table_md + "\n")

        return {
            "success": True,
            "table_markdown": table_md,
            "columns": len(headers),
            "rows": len(rows),
            "file_path": file_path,
        }

    def _build_list(self, params: dict[str, Any]) -> dict[str, Any]:
        items = params.get("items")
        if not items:
            raise ValueError("'items' is required for build_list")

        ordered = params.get("ordered", False)
        list_md = _build_list(items, ordered=ordered)

        file_path = params.get("file_path")
        if file_path:
            fp = Path(file_path)
            if fp.exists():
                existing = _read_text(fp)
                sep = "\n\n" if existing and not existing.endswith("\n\n") else ("\n" if existing and not existing.endswith("\n") else "")
                _write_text(fp, existing + sep + list_md + "\n")
            else:
                _write_text(fp, list_md + "\n")

        return {
            "success": True,
            "list_markdown": list_md,
            "item_count": len(items),
            "ordered": ordered,
            "file_path": file_path,
        }

    def _merge(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = params.get("file_path")
        merge_files = params.get("merge_files")
        if not merge_files:
            raise ValueError("'merge_files' is required for merge operation")
        if not file_path:
            raise ValueError("'file_path' (output) is required for merge operation")

        separator = params.get("separator", "\n\n---\n\n")
        parts: list[str] = []
        for fp in merge_files:
            p = Path(fp)
            if not p.exists():
                raise FileNotFoundError(f"Merge source not found: {fp}")
            parts.append(_read_text(p).strip())

        merged = separator.join(parts) + "\n"
        chars = _write_text(Path(file_path), merged)
        return {
            "success": True,
            "file_path": file_path,
            "files_merged": len(merge_files),
            "chars_written": chars,
        }

    def _format(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(self.require_param(params, "file_path"))
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        raw = _read_text(file_path)
        formatted = _format_markdown(raw)
        chars = _write_text(file_path, formatted)
        return {
            "success": True,
            "file_path": str(file_path),
            "chars_written": chars,
            "original_chars": len(raw),
        }

    def _convert(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = Path(self.require_param(params, "file_path"))
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        fmt = params.get("output_format")
        if fmt not in ("html", "plain_text"):
            raise ValueError("convert requires output_format: html or plain_text")

        raw = _read_text(file_path)
        if fmt == "html":
            content = _markdown_to_html(raw)
        else:
            content = _markdown_to_plain(raw)

        out_path = params.get("output_path")
        written = False
        if out_path:
            _write_text(Path(out_path), content)
            written = True

        return {
            "content": content,
            "output_format": fmt,
            "output_path": out_path,
            "written": written,
        }

    def _template(self, params: dict[str, Any]) -> dict[str, Any]:
        file_path = params.get("file_path")
        template_name = params.get("template_name")
        if not template_name:
            raise ValueError("'template_name' is required")
        if template_name not in _TEMPLATES:
            raise ValueError(f"Unknown template: {template_name}. Available: {list(_TEMPLATES.keys())}")

        data = params.get("template_data") or {}
        title = params.get("title") or data.get("title", "Untitled")
        metadata = params.get("metadata") or data.get("metadata")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        parts: list[str] = []

        if metadata or template_name in ("report", "article", "meeting"):
            fm = metadata or {}
            if "date" not in fm:
                fm["date"] = now
            if "title" not in fm:
                fm["title"] = title
            fm_lines = ["---"]
            for k, v in fm.items():
                if isinstance(v, list):
                    fm_lines.append(f"{k}:")
                    for item in v:
                        fm_lines.append(f"  - {item}")
                else:
                    fm_lines.append(f"{k}: {v}")
            fm_lines.append("---")
            parts.append("\n".join(fm_lines))

        parts.append(f"# {title}")

        if template_name == "story":
            body = data.get("body") or data.get("content", "")
            if body:
                parts.append(body)
            else:
                parts.append("*Write your story here...*")

        elif template_name == "report":
            summary = data.get("summary", "")
            if summary:
                parts.append("## Summary\n")
                parts.append(summary)
            else:
                parts.append("## Summary\n")
                parts.append("*Executive summary goes here.*")

            sections = data.get("sections") or []
            for sec in sections:
                if isinstance(sec, dict):
                    h = sec.get("heading", "Section")
                    c = sec.get("content", "")
                    parts.append(f"## {h}\n")
                    parts.append(c if c else "*Content goes here.*")
                else:
                    parts.append(f"## {sec}\n")

            conclusion = data.get("conclusion", "")
            parts.append("## Conclusion\n")
            parts.append(conclusion if conclusion else "*Conclusion goes here.*")

        elif template_name == "notes":
            body = data.get("body") or data.get("content", "")
            if body:
                parts.append(body)
            else:
                parts.append("## Notes\n")
                parts.append("- ")

        elif template_name == "article":
            abstract = data.get("abstract", "")
            if abstract:
                parts.append("## Abstract\n")
                parts.append(f"> {abstract}")

            sections = data.get("sections") or []
            for sec in sections:
                if isinstance(sec, dict):
                    h = sec.get("heading", "Section")
                    c = sec.get("content", "")
                    parts.append(f"## {h}\n")
                    parts.append(c if c else "")
                else:
                    parts.append(f"## {sec}\n")

            refs = data.get("references") or []
            if refs:
                parts.append("## References\n")
                for i, ref in enumerate(refs, 1):
                    parts.append(f"{i}. {ref}")

        elif template_name == "meeting":
            attendees = data.get("attendees") or []
            if attendees:
                parts.append("## Attendees\n")
                parts.append("\n".join(f"- {a}" for a in attendees))

            agenda = data.get("agenda") or []
            if agenda:
                parts.append("## Agenda\n")
                parts.append("\n".join(f"{i}. {item}" for i, item in enumerate(agenda, 1)))

            notes = data.get("notes") or data.get("content", "")
            parts.append("## Discussion Notes\n")
            parts.append(notes if notes else "*Notes here...*")

            action_items = data.get("action_items") or []
            parts.append("## Action Items\n")
            if action_items:
                parts.append("\n".join(f"- [ ] {item}" for item in action_items))
            else:
                parts.append("- [ ] ")

        elif template_name == "readme":
            desc = data.get("description", "")
            parts.append(f"\n{desc}" if desc else "\n*Project description*")

            installation = data.get("installation", "")
            parts.append("## Installation\n")
            if installation:
                parts.append(f"```bash\n{installation}\n```")
            else:
                parts.append("```bash\n# Installation steps\n```")

            usage = data.get("usage", "")
            parts.append("## Usage\n")
            parts.append(usage if usage else "*Usage examples*")

            api = data.get("api", "")
            if api:
                parts.append("## API\n")
                parts.append(api)

            license_text = data.get("license", "MIT")
            parts.append("## License\n")
            parts.append(license_text)

        elif template_name == "changelog":
            entries = data.get("entries") or []
            if entries:
                for entry in entries:
                    version = entry.get("version", "0.0.0")
                    date = entry.get("date", now.split(" ")[0])
                    changes = entry.get("changes") or []
                    parts.append(f"## [{version}] - {date}\n")
                    for change in changes:
                        ctype = change.get("type", "Changed")
                        items = change.get("items") or []
                        parts.append(f"### {ctype}\n")
                        parts.append("\n".join(f"- {item}" for item in items))
            else:
                parts.append(f"## [Unreleased] - {now.split(' ')[0]}\n")
                parts.append("### Added\n\n- ")

        doc = "\n\n".join(parts) + "\n"
        result: dict[str, Any] = {
            "success": True,
            "template": template_name,
            "content": doc,
        }

        if file_path:
            chars = _write_text(Path(file_path), doc)
            result["file_path"] = file_path
            result["chars_written"] = chars

        return result
