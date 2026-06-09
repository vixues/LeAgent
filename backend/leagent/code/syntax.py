"""Tool for fast syntax validation of JSON, JSONC, Python, TOML, and YAML."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from leagent.services.syntax_validation import validate_syntax
from leagent.tools.base import SyncTool, ToolCategory, ToolContext

_DEFAULT_MAX_CONTENT_CHARS = 512_000


class SyntaxValidatorTool(SyncTool):
    """Validate JSON / JSONC / Python / TOML / YAML syntax without executing code."""

    name = "syntax_validator"
    description = (
        "Parse-only syntax validation for JSON, JSONC (comments + trailing commas), "
        "Python, TOML, and YAML. Returns line/column diagnostics and a small source "
        "frame plus patch_hint for localized edits. Use hint_filename with inline "
        "content when language=auto so detection follows a virtual path suffix."
    )
    category = ToolCategory.CODE
    version = "1.1.0"
    aliases = ["validate_syntax", "syntax_check", "lint_syntax"]
    search_hint = (
        "syntax validate JSON JSONC Python TOML YAML parse error line column patch"
    )
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 80_000
    path_params = ("file_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "enum": ["auto", "json", "jsonc", "python", "toml", "yaml"],
                    "default": "auto",
                    "description": (
                        "Syntax to validate. `jsonc` strips whole-line // comments and "
                        "trailing commas before parsing. `auto` uses file extension or "
                        "content heuristics (optionally combined with hint_filename)."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "Inline source to validate (unless file_path is set).",
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional file to read and validate. Must be within the path sandbox.",
                },
                "hint_filename": {
                    "type": "string",
                    "description": (
                        "When validating inline `content` with language=auto, optional "
                        "virtual path or suffix (e.g. `values.yaml`, `config.jsonc`) "
                        "to steer language detection."
                    ),
                },
                "context_lines": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "default": 2,
                    "description": "Number of surrounding lines to include in diagnostics.",
                },
                "max_content_chars": {
                    "type": "integer",
                    "minimum": 1024,
                    "maximum": 2_000_000,
                    "default": _DEFAULT_MAX_CONTENT_CHARS,
                    "description": "Reject inputs larger than this many characters (DoS guard).",
                },
            },
            "additionalProperties": False,
        }

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        file_path = params.get("file_path")
        content = params.get("content")
        max_chars = int(params.get("max_content_chars") or _DEFAULT_MAX_CONTENT_CHARS)
        max_chars = max(1024, min(max_chars, 2_000_000))

        if not isinstance(content, str):
            if not isinstance(file_path, str) or not file_path:
                raise ValueError("Either 'content' or 'file_path' is required")
            raw = Path(file_path).read_text(encoding="utf-8-sig")
        else:
            raw = content.lstrip("\ufeff\u200b\u200c\u200d\u2060")

        hint = params.get("hint_filename")
        hint_s = str(hint).strip() if isinstance(hint, str) else ""

        if len(raw) > max_chars:
            diag = {
                "message": (
                    f"Input length {len(raw)} exceeds max_content_chars={max_chars}; "
                    "validate a smaller excerpt or raise the cap."
                ),
                "severity": "error",
                "line": 1,
                "column": 1,
                "end_line": None,
                "end_column": None,
                "offset": None,
                "code": "input_too_large",
                "source_line": "",
                "frame": [],
                "caret": "^",
            }
            return {
                "valid": False,
                "language": str(params.get("language") or "auto"),
                "diagnostics": [diag],
                "primary_error": diag,
                "line_count": 0,
                "char_count": len(raw),
                "source": {
                    "kind": "file" if isinstance(file_path, str) and file_path else "inline",
                    "file_path": file_path if isinstance(file_path, str) else None,
                    "hint_filename": hint_s or None,
                    "max_content_chars": max_chars,
                },
                "patch_hint": _patch_hint(diag),
            }

        detect_name: str | None = None
        if isinstance(file_path, str) and file_path.strip():
            detect_name = file_path.strip()
        elif hint_s:
            detect_name = hint_s

        language = str(params.get("language") or "auto")
        context_lines = int(params.get("context_lines") or 2)
        result = validate_syntax(
            raw,
            language=language,  # type: ignore[arg-type]
            filename=detect_name,
            context_lines=context_lines,
        )
        payload = result.to_dict()
        payload["source"] = {
            "kind": "file" if isinstance(file_path, str) and file_path else "inline",
            "file_path": file_path if isinstance(file_path, str) else None,
            "hint_filename": hint_s or None,
            "max_content_chars": max_chars,
        }
        if payload.get("primary_error"):
            payload["patch_hint"] = _patch_hint(payload["primary_error"])
        else:
            payload["patch_hint"] = None
        return payload


def _patch_hint(primary: dict[str, Any]) -> dict[str, Any]:
    frame = primary.get("frame") or []
    if frame:
        start_line = int(frame[0]["line"])
        end_line = int(frame[-1]["line"])
        replacement_target = "\n".join(str(row["text"]) for row in frame)
    else:
        start_line = end_line = int(primary.get("line") or 1)
        replacement_target = str(primary.get("source_line") or "")
    return {
        "start_line": start_line,
        "end_line": end_line,
        "line": primary.get("line"),
        "column": primary.get("column"),
        "replacement_target": replacement_target,
        "instruction": (
            "Patch only this localized range unless surrounding syntax shows "
            "the error originates elsewhere."
        ),
    }
