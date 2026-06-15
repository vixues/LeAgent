"""Resolve and coerce arguments for chat workflow step execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from leagent.tools.base import BaseTool, ToolContext
from leagent.tools.contract import schema_properties, suggest_canonical_key
from leagent.tools.registry import ToolRegistry, get_registry

_CSV_TOOLS = frozenset({"csv_processor", "csv", "tsv", "csv_reader"})
_DATA_CLEAN_TOOLS = frozenset({"data_clean", "clean", "preprocess", "data_preprocess"})
_DATA_CLEAN_OP_ALIASES: dict[str, str] = {
    "clean": "remove_duplicates",
    "preprocess": "remove_duplicates",
    "dedupe": "remove_duplicates",
    "dedup": "remove_duplicates",
    "trim": "trim_whitespace",
    "fill_nulls": "fill_missing",
    "drop_nulls": "drop_missing",
}


def _has_operations(arguments: dict[str, Any]) -> bool:
    ops = arguments.get("operations")
    return isinstance(ops, list) and len(ops) > 0


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
    if param_name in ("file_path", "source_path") and tool_name in _CSV_TOOLS:
        for path in attachments:
            lower = path.lower()
            if lower.endswith((".csv", ".tsv", ".txt")):
                return path
        if len(attachments) == 1:
            return attachments[0]
        return None
    if len(attachments) == 1:
        return attachments[0]
    return None


def _schema_path_keys(tool: BaseTool) -> tuple[str, ...]:
    schema = tool.parameters
    props = schema_properties(schema)
    keys: list[str] = []
    for key in (*getattr(tool, "path_params", ()), *getattr(tool, "output_path_params", ())):
        if key and key in props and key not in keys:
            keys.append(key)
    if "file_path" in props and "file_path" not in keys:
        keys.append("file_path")
    if "source_path" in props and "source_path" not in keys:
        keys.append("source_path")
    return tuple(keys)


def normalize_workflow_step_arguments(
    tool_id: str,
    arguments: dict[str, Any],
    *,
    registry: ToolRegistry | None = None,
) -> dict[str, Any]:
    """Rename common LLM mis-keys and reshape singular ops before tool validation."""
    reg = registry or get_registry()
    tool = reg.get_optional(tool_id)
    if tool is None:
        return dict(arguments or {})

    out = dict(arguments or {})
    schema = tool.parameters
    props = schema_properties(schema)
    tool_names = {tool.name, *list(getattr(tool, "aliases", ()) or [])}

    if any(name in _DATA_CLEAN_TOOLS for name in tool_names):
        if "operation" in out and not _has_operations(out):
            op_val = out.pop("operation")
            if isinstance(op_val, str) and op_val.strip():
                op_type = _DATA_CLEAN_OP_ALIASES.get(op_val.strip(), op_val.strip())
                op_obj: dict[str, Any] = {"type": op_type}
                for key in (
                    "columns",
                    "keep",
                    "fill_value",
                    "fill_strategy",
                    "axis",
                    "how",
                    "thresh",
                    "type_map",
                ):
                    if key in out:
                        op_obj[key] = out.pop(key)
                out["operations"] = [op_obj]
        if not _has_operations(out) and "operations" in out:
            out.pop("operations", None)

    for key in list(out.keys()):
        if key in props:
            continue
        hint: str | None = None
        if key == "source_path" and "file_path" in props and "source_path" not in props:
            hint = "file_path"
        elif key == "file_path" and "source_path" in props and "file_path" not in props:
            hint = "source_path"
        else:
            hint = suggest_canonical_key(key, schema)
        if hint and hint in props:
            if hint not in out or out.get(hint) in (None, ""):
                out[hint] = out.pop(key)
            else:
                out.pop(key, None)

    if tool.name in _CSV_TOOLS and out.get("file_path") and not out.get("operation"):
        out["operation"] = "read"
    if tool.name in _CSV_TOOLS and out.get("source_path") and not out.get("file_path"):
        out["file_path"] = out.pop("source_path")
        if not out.get("operation"):
            out["operation"] = "read"

    return out


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
    path_keys = _schema_path_keys(tool)
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
    csv_names = [
        Path(p).name
        for p in attachments
        if isinstance(p, str) and p.lower().endswith((".csv", ".tsv"))
    ]

    base = (
        f"Missing required input `{param_name}` for `{tool.name}`. "
        "Upload a file to this chat session, or pick / enter a filename in the workflow card input "
        "(resolved as ${user_input} in step arguments)."
    )
    if csv_names:
        return base + f" Session CSV files: {', '.join(csv_names[:5])}."
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

    schema = tool.parameters
    props = schema_properties(schema)
    operation = arguments.get("operation")
    write_ops = {"write", "convert"}
    read_ops = {"read", "query", "stats"}

    for key in _schema_path_keys(tool):
        if key == "output_path" and operation not in write_ops:
            continue
        if key == "file_path" and operation in write_ops and not arguments.get("file_path"):
            continue
        if key == "file_path" and operation in read_ops:
            val = arguments.get(key)
            if isinstance(val, str) and val.strip():
                continue
            return missing_path_input_message(tool, key, context)
        if key in getattr(tool, "path_params", ()) or key == "source_path":
            val = arguments.get(key)
            if isinstance(val, str) and val.strip():
                continue
            if key in props:
                return missing_path_input_message(tool, key, context)
    return None
