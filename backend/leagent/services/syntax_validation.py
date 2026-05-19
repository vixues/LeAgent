"""Syntax validation helpers for agent-generated JSON and Python.

The validator is deliberately parse-only: it never executes generated
code.  It returns compact diagnostics with exact line/column positions
and a small source frame so agents can target localized patches instead
of regenerating large files blindly.

Supports **YAML** (via PyYAML ``safe_load``) and **JSONC** (best-effort:
BOM strip, whole-line ``//`` comments removed, trailing commas relaxed)
in addition to JSON, Python, and TOML.
"""

from __future__ import annotations

import ast
import json
import re
import tomllib
from dataclasses import dataclass
from typing import Any, Literal

try:
    import yaml as _yaml
except ImportError:  # pragma: no cover - PyYAML is a declared dependency
    _yaml = None  # type: ignore[assignment]

Language = Literal["json", "jsonc", "python", "toml", "yaml"]

__all__ = [
    "Diagnostic",
    "SyntaxValidationResult",
    "detect_language",
    "validate_syntax",
]


@dataclass(frozen=True)
class Diagnostic:
    """Single syntax diagnostic with patch-oriented source context."""

    message: str
    severity: str
    line: int
    column: int
    end_line: int | None = None
    end_column: int | None = None
    offset: int | None = None
    code: str | None = None
    source_line: str = ""
    frame: list[dict[str, Any]] | None = None
    caret: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "severity": self.severity,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
            "offset": self.offset,
            "code": self.code,
            "source_line": self.source_line,
            "frame": self.frame or [],
            "caret": self.caret,
        }


@dataclass(frozen=True)
class SyntaxValidationResult:
    """Structured syntax validation result."""

    valid: bool
    language: Language
    diagnostics: list[Diagnostic]
    line_count: int
    char_count: int

    def to_dict(self) -> dict[str, Any]:
        diagnostics = [d.to_dict() for d in self.diagnostics]
        return {
            "valid": self.valid,
            "language": self.language,
            "diagnostics": diagnostics,
            "primary_error": diagnostics[0] if diagnostics else None,
            "line_count": self.line_count,
            "char_count": self.char_count,
        }


def detect_language(*, content: str, filename: str | None = None) -> Language:
    """Best-effort language detection for supported syntaxes."""

    lower_name = (filename or "").lower()
    if lower_name.endswith((".py", ".pyw")):
        return "python"
    if lower_name.endswith((".toml",)):
        return "toml"
    if lower_name.endswith((".yaml", ".yml")):
        return "yaml"
    if lower_name.endswith(".jsonc"):
        return "jsonc"
    if lower_name.endswith((".json", ".ipynb")):
        return "json"

    stripped = content.lstrip("\ufeff\u200b\u200c\u200d\u2060")
    if re.match(r"^%YAML\s+[12]\.[12]\b", stripped) or stripped.startswith("---"):
        return "yaml"
    if stripped.startswith(("{", "[")):
        return "json"
    return "python"


def validate_syntax(
    content: str,
    *,
    language: Language | Literal["auto"] = "auto",
    filename: str | None = None,
    context_lines: int = 2,
) -> SyntaxValidationResult:
    """Validate JSON, JSONC, Python, TOML, or YAML and return localized diagnostics."""

    selected: Language = (
        detect_language(content=content, filename=filename)
        if language == "auto"
        else language
    )
    context_lines = max(0, min(int(context_lines), 10))
    if selected == "json":
        diagnostics = _validate_json(content, context_lines=context_lines)
    elif selected == "python":
        diagnostics = _validate_python(
            content,
            filename=filename or "<string>",
            context_lines=context_lines,
        )
    elif selected == "toml":
        diagnostics = _validate_toml(content, context_lines=context_lines)
    elif selected == "yaml":
        diagnostics = _validate_yaml(content, context_lines=context_lines)
    elif selected == "jsonc":
        diagnostics = _validate_jsonc(content, context_lines=context_lines)
    else:
        raise ValueError(f"Unsupported language: {language!r}")

    return SyntaxValidationResult(
        valid=not diagnostics,
        language=selected,
        diagnostics=diagnostics,
        line_count=len(content.splitlines()) if content else 0,
        char_count=len(content),
    )


def _validate_json(content: str, *, context_lines: int) -> list[Diagnostic]:
    text = _strip_json_prefix(content)
    try:
        json.loads(text)
    except json.JSONDecodeError as exc:
        return [
            _diagnostic_from_position(
                content,
                message=exc.msg,
                line=exc.lineno,
                column=exc.colno,
                offset=exc.pos,
                code="json_syntax_error",
                context_lines=context_lines,
            )
        ]
    return []


def _validate_toml(content: str, *, context_lines: int) -> list[Diagnostic]:
    try:
        tomllib.loads(content)
    except tomllib.TOMLDecodeError as exc:
        msg = str(exc) or "invalid TOML"
        line, col = 1, 1
        if "line" in msg.lower():
            m = re.search(r"line\s+(\d+)", msg, re.I)
            if m:
                line = int(m.group(1))
            m2 = re.search(r"column\s+(\d+)", msg, re.I)
            if m2:
                col = int(m2.group(1))
        return [
            _diagnostic_from_position(
                content,
                message=msg,
                line=line,
                column=col,
                code="toml_syntax_error",
                context_lines=context_lines,
            )
        ]
    return []


def _strip_json_prefix(raw: str) -> str:
    return raw.lstrip("\ufeff\u200b\u200c\u200d\u2060")


def _repair_trailing_commas(raw: str) -> str:
    """Remove trailing commas before ``}`` / ``]`` outside JSON strings."""
    out: list[str] = []
    in_string = False
    escaped = False
    i = 0
    while i < len(raw):
        ch = raw[i]
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue

        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue

        if ch == ",":
            j = i + 1
            while j < len(raw) and raw[j].isspace():
                j += 1
            if j < len(raw) and raw[j] in "}]":
                i += 1
                continue

        out.append(ch)
        i += 1
    return "".join(out)


def _jsonc_preprocess(raw: str) -> str:
    """Best-effort JSONC → strict JSON text (no unquoted keys)."""
    text = _strip_json_prefix(raw)
    lines_out: list[str] = []
    for line in text.splitlines():
        if line.lstrip().startswith("//"):
            continue
        lines_out.append(line)
    return _repair_trailing_commas("\n".join(lines_out))


def _validate_jsonc(content: str, *, context_lines: int) -> list[Diagnostic]:
    relaxed = _jsonc_preprocess(content)
    try:
        json.loads(relaxed)
    except json.JSONDecodeError as exc:
        return [
            _diagnostic_from_position(
                content,
                message=exc.msg,
                line=exc.lineno,
                column=exc.colno,
                offset=exc.pos,
                code="jsonc_syntax_error",
                context_lines=context_lines,
            )
        ]
    return []


def _validate_yaml(content: str, *, context_lines: int) -> list[Diagnostic]:
    if _yaml is None:
        return [
            Diagnostic(
                message="PyYAML is not installed; cannot validate YAML.",
                severity="error",
                line=1,
                column=1,
                code="yaml_unavailable",
                source_line="",
                frame=[],
                caret="^",
            )
        ]
    try:
        _yaml.safe_load(content)
    except _yaml.YAMLError as exc:  # type: ignore[union-attr]
        line, col = 1, 1
        mark = getattr(exc, "problem_mark", None) or getattr(exc, "context_mark", None)
        if mark is not None:
            line = int(mark.line) + 1
            col = int(mark.column) + 1
        msg = str(exc).strip().split("\n")[0][:800]
        return [
            _diagnostic_from_position(
                content,
                message=msg or "YAML parse error",
                line=line,
                column=col,
                code="yaml_syntax_error",
                context_lines=context_lines,
            )
        ]
    return []


def _validate_python(
    content: str,
    *,
    filename: str,
    context_lines: int,
) -> list[Diagnostic]:
    try:
        ast.parse(content, filename=filename)
    except SyntaxError as exc:
        line = int(exc.lineno or 1)
        column = int(exc.offset or 1)
        return [
            _diagnostic_from_position(
                content,
                message=exc.msg or "invalid syntax",
                line=line,
                column=column,
                end_line=getattr(exc, "end_lineno", None),
                end_column=getattr(exc, "end_offset", None),
                code="python_syntax_error",
                context_lines=context_lines,
            )
        ]
    return []


def _diagnostic_from_position(
    content: str,
    *,
    message: str,
    line: int,
    column: int,
    offset: int | None = None,
    end_line: int | None = None,
    end_column: int | None = None,
    code: str,
    context_lines: int,
) -> Diagnostic:
    lines = content.splitlines()
    source_line = lines[line - 1] if 1 <= line <= len(lines) else ""
    frame = _source_frame(lines, line=line, context_lines=context_lines)
    caret_width = 1
    if end_line in (None, line) and end_column is not None:
        caret_width = max(1, end_column - column)
    caret = " " * max(0, column - 1) + "^" * caret_width
    return Diagnostic(
        message=message,
        severity="error",
        line=line,
        column=column,
        end_line=end_line,
        end_column=end_column,
        offset=offset,
        code=code,
        source_line=source_line,
        frame=frame,
        caret=caret,
    )


def _source_frame(
    lines: list[str],
    *,
    line: int,
    context_lines: int,
) -> list[dict[str, Any]]:
    if not lines:
        return []
    start = max(1, line - context_lines)
    end = min(len(lines), line + context_lines)
    return [
        {
            "line": lineno,
            "text": lines[lineno - 1],
            "is_error_line": lineno == line,
        }
        for lineno in range(start, end + 1)
    ]
