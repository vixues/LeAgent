"""Resolve and coerce arguments for chat workflow step execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from leagent.tools.base import BaseTool, ToolContext
from leagent.tools.registry import ToolRegistry, get_registry


def _session_attachment_paths(context: ToolContext) -> list[str]:
    raw = context.extra.get("attachments")
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
    return out


def _pick_attachment_for_param(
    param_name: str,
    tool_name: str,
    attachments: list[str],
) -> str | None:
    if not attachments:
        return None
    if param_name == "file_path" and tool_name == "pdf_reader":
        for path in attachments:
            if path.lower().endswith(".pdf"):
                return path
        if len(attachments) == 1:
            return attachments[0]
        return None
    if len(attachments) == 1:
        return attachments[0]
    return None


def coerce_workflow_step_arguments(
    tool_id: str,
    arguments: dict[str, Any],
    context: ToolContext,
    *,
    registry: ToolRegistry | None = None,
) -> dict[str, Any]:
    """Fill empty path parameters from session attachments when possible."""
    reg = registry or get_registry()
    tool = reg.get_optional(tool_id)
    if tool is None:
        return dict(arguments or {})

    out = dict(arguments or {})
    path_keys = tuple(getattr(tool, "path_params", ()) or ())
    if not path_keys:
        return out

    attachments = _session_attachment_paths(context)
    for key in path_keys:
        val = out.get(key)
        if isinstance(val, str) and val.strip():
            continue
        picked = _pick_attachment_for_param(key, tool.name, attachments)
        if picked:
            out[key] = picked
    return out


def missing_path_input_message(
    tool: BaseTool,
    param_name: str,
    context: ToolContext,
) -> str:
    """User-facing hint when a required path param is still empty after coercion."""
    attachments = _session_attachment_paths(context)
    pdf_names = [
        Path(p).name for p in attachments if isinstance(p, str) and p.lower().endswith(".pdf")
    ]
    file_names = [Path(p).name for p in attachments if isinstance(p, str)]

    base = (
        f"Missing required input `{param_name}` for `{tool.name}`. "
        "Upload a file to this chat session, or enter a filename or path in optional input "
        "(resolved as ${user_input} in step arguments)."
    )
    if pdf_names:
        return base + f" Session PDFs: {', '.join(pdf_names[:5])}."
    if file_names:
        return base + f" Session files: {', '.join(file_names[:5])}."
    return base


def validate_workflow_step_paths(
    tool_id: str,
    arguments: dict[str, Any],
    context: ToolContext,
    *,
    registry: ToolRegistry | None = None,
) -> str | None:
    """Return an error message when required path params are empty; else None."""
    reg = registry or get_registry()
    tool = reg.get_optional(tool_id)
    if tool is None:
        return None

    for key in getattr(tool, "path_params", ()) or ():
        val = arguments.get(key)
        if isinstance(val, str) and val.strip():
            continue
        return missing_path_input_message(tool, key, context)
    return None
