"""Strict tool parameter contract validation helpers.

These utilities detect schema/implementation drift at validation time.
They never mutate parameters — mismatches surface as explicit errors.
"""

from __future__ import annotations

from typing import Any

# Hints for error messages only; never used to rewrite caller input.
WRONG_KEY_HINTS: dict[str, str] = {
    "path": "file_path",
    "filepath": "file_path",
    "file": "file_path",
    "text": "content",
    "body": "content",
    "markdown": "content",
    "items": "todos",
}

# Per-tool operation → required fields (beyond schema-level ``required``).
OPERATION_REQUIRED_FIELDS: dict[str, dict[str, tuple[str, ...]]] = {
    "markdown_processor": {
        "read": ("file_path",),
        "write": ("file_path", "content"),
        "create": ("file_path",),
        "append": ("file_path", "content"),
        "prepend": ("file_path", "content"),
        "insert_section": ("file_path", "section_title", "content"),
        "replace_section": ("file_path", "section_title", "content"),
        "delete_section": ("file_path", "section_title"),
        "extract_toc": ("file_path",),
        "generate_toc": ("file_path",),
        "extract_code_blocks": ("file_path",),
        "format": ("file_path",),
        "convert": ("file_path",),
        "merge": ("file_path", "merge_files"),
        "template": ("file_path", "template_name"),
    },
    "text_processor": {
        "read": ("file_path",),
        "write": ("file_path", "data"),
        "append": ("file_path", "data"),
        "prepend": ("file_path", "data"),
        "insert": ("file_path", "data"),
        "search": ("file_path", "pattern"),
        "replace": ("file_path", "pattern", "replacement"),
        "join": ("file_path", "source_files"),
        "diff": ("file_path", "file_path_2"),
    },
}


def schema_properties(schema: dict[str, Any]) -> set[str]:
    """Return top-level property names declared in a tool JSON schema."""
    props = schema.get("properties")
    if not isinstance(props, dict):
        return set()
    return set(props.keys())


def schema_allows_additional_properties(schema: dict[str, Any]) -> bool:
    """Whether the schema permits keys outside ``properties``."""
    if schema.get("additionalProperties") is False:
        return False
    return True


def detect_unknown_keys(params: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    """Return parameter keys that violate the declared schema contract."""
    allowed = schema_properties(schema)
    if not allowed:
        return []

    unknown: list[str] = []
    strict = not schema_allows_additional_properties(schema)

    for key in params:
        if key in allowed:
            continue
        if strict:
            unknown.append(key)
            continue
        # Permissive schema: still flag known wrong keys when canonical exists.
        hint = suggest_canonical_key(key, schema)
        if hint is not None:
            unknown.append(key)

    return unknown


def suggest_canonical_key(wrong_key: str, schema: dict[str, Any]) -> str | None:
    """Suggest the canonical key for a commonly misnamed parameter."""
    props = schema_properties(schema)
    if wrong_key in props:
        return None

    hinted = WRONG_KEY_HINTS.get(wrong_key)
    if hinted and hinted in props:
        return hinted

    # Schema-aware: path is wrong when file_path is canonical (doc tools).
    if wrong_key == "path" and "file_path" in props and "path" not in props:
        return "file_path"
    if wrong_key == "file_path" and "source_path" in props and "file_path" not in props:
        return "source_path"
    if wrong_key in ("content", "text", "body", "markdown") and "data" in props and "content" not in props:
        return "data"
    if wrong_key in ("data", "text", "body", "markdown") and "content" in props and "data" not in props:
        return "content"
    # Models sometimes invent a ``payload`` wrapper; GenUI tools use ``tree`` / ``patches``.
    if wrong_key == "payload":
        if "tree" in props:
            return "tree"
        if "patches" in props:
            return "patches"

    return None


def format_unknown_key_errors(
    violations: list[str],
    schema: dict[str, Any],
) -> str:
    """Build a single actionable validation error for unknown keys."""
    parts: list[str] = []
    for key in violations:
        hint = suggest_canonical_key(key, schema)
        if hint:
            parts.append(f"unknown key '{key}' — use '{hint}'")
        else:
            parts.append(f"unknown key '{key}'")
    return "Invalid parameters: " + "; ".join(parts) + " (see tool schema)"


def validate_path_params_declared(
    *,
    tool_name: str,
    schema: dict[str, Any],
    path_params: tuple[str, ...],
    output_path_params: tuple[str, ...],
) -> list[str]:
    """Return path-param keys missing from the tool schema."""
    props = schema_properties(schema)
    errors: list[str] = []
    for key in (*path_params, *output_path_params):
        if key and key not in props:
            errors.append(f"{tool_name}: path param '{key}' not in parameters.properties")
    return errors


def operation_required_fields(tool_name: str, operation: str | None) -> tuple[str, ...]:
    """Return extra required fields for a specific tool operation."""
    if not operation:
        return ()
    per_tool = OPERATION_REQUIRED_FIELDS.get(tool_name, {})
    return per_tool.get(operation, ())


def validate_operation_required(
    params: dict[str, Any],
    tool_name: str,
) -> list[str]:
    """Return missing fields required for the requested operation."""
    operation = params.get("operation")
    if not isinstance(operation, str):
        return []

    missing: list[str] = []
    for field in operation_required_fields(tool_name, operation):
        val = params.get(field)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(field)
    return missing


def format_operation_required_errors(missing: list[str]) -> str:
    """Build validation error for operation-conditional required fields."""
    fields = ", ".join(f"'{f}'" for f in missing)
    return f"Invalid parameters: missing required field(s) for this operation: {fields}"
