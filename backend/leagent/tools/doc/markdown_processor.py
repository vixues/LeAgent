"""Markdown file processing: parse structure, TOC, code fences, and convert."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

_HEADING_LINE = re.compile(r"^(#{1,6})\s+(.+)$")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
_CODE_FENCE = re.compile(r"^```([^\n`]*)\r?\n(.*?)^```\s*$", re.MULTILINE | re.DOTALL)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


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


class MarkdownProcessorTool(SyncTool):
    name = "markdown_processor"
    description = (
        "Read and parse Markdown files, extract TOC and fenced code blocks, "
        "and convert to HTML or plain text."
    )
    category = ToolCategory.DOC
    version = "1.0.0"
    timeout_sec = 60
    aliases = ["markdown", "md", "md_reader"]
    search_hint = "Markdown read parse TOC headings code blocks convert HTML text"
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
                    "enum": ["read", "extract_toc", "extract_code_blocks", "convert"],
                    "description": "Operation to perform on the Markdown file.",
                },
                "file_path": {
                    "type": "string",
                    "description": "Path to the Markdown file.",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "Maximum heading depth for extract_toc (default: 3).",
                    "minimum": 1,
                    "maximum": 6,
                    "default": 3,
                },
                "language": {
                    "type": "string",
                    "description": "Optional language tag filter for extract_code_blocks.",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["html", "plain_text"],
                    "description": "Output format for convert.",
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
        return "Processing Markdown"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        operation = params["operation"]
        file_path = Path(params["file_path"])

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if not file_path.is_file():
            raise ValueError(f"Not a file: {file_path}")

        logger.info("markdown_processor", operation=operation, file_path=str(file_path))

        raw = _read_text(file_path)
        lines = raw.splitlines()

        if operation == "read":
            headings = _parse_headings(lines)
            links = _parse_links(raw)
            images = _parse_images(raw)
            code_blocks = _parse_code_blocks(raw)
            words = re.findall(r"\S+", raw)
            return {
                "raw_text": raw,
                "headings": headings,
                "links": links,
                "images": images,
                "code_blocks": code_blocks,
                "word_count": len(words),
                "line_count": len(lines),
            }

        if operation == "extract_toc":
            max_depth = int(params.get("max_depth", 3))
            headings = _parse_headings(lines)
            toc = _nest_toc(headings, max_depth)
            return {"toc": toc, "max_depth": max_depth}

        if operation == "extract_code_blocks":
            lang_filter = params.get("language")
            lang_filter_norm = (lang_filter or "").strip().lower() or None
            blocks = _code_blocks_with_lines(raw)
            if lang_filter_norm:
                blocks = [
                    b
                    for b in blocks
                    if (b.get("language") or "").strip().lower() == lang_filter_norm
                ]
            return {"code_blocks": blocks}

        if operation == "convert":
            fmt = params.get("output_format")
            if fmt not in ("html", "plain_text"):
                raise ValueError("convert requires output_format: html or plain_text")
            if fmt == "html":
                content = _markdown_to_html(raw)
            else:
                content = _markdown_to_plain(raw)
            out_path = params.get("output_path")
            written = False
            if out_path:
                outp = Path(out_path)
                outp.parent.mkdir(parents=True, exist_ok=True)
                outp.write_text(content, encoding="utf-8")
                written = True
            return {
                "content": content,
                "output_format": fmt,
                "output_path": str(out_path) if out_path else None,
                "written": written,
            }

        raise ValueError(f"Unknown operation: {operation}")
