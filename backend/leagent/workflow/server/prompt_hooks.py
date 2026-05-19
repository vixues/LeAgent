"""Request-time hooks applied before a prompt is queued.

Pipeline:
1. ``apply_replacements`` — rewrites deprecated ``class_type`` values.
2. ``validate_prompt`` — runs :func:`io.validate` and surfaces structured errors.
3. ``seed_context`` — injects default ``extra_data`` (user, session, etc.).
"""

from __future__ import annotations

from typing import Any

from ..io import WorkflowDocument, validate
from ..nodes import NodeRegistry, get_registry
from ..nodes.replacement import NodeReplaceRegistry, get_replace_registry


def apply_replacements(
    doc_dict: dict[str, Any],
    *,
    user_id: str | None = None,
    registry: NodeReplaceRegistry | None = None,
) -> tuple[dict[str, Any], list[tuple[str, str, str]]]:
    reg = registry or get_replace_registry()
    return reg.apply_to_document(doc_dict, user_id=user_id)


def validate_prompt(
    doc: WorkflowDocument,
    *,
    node_registry: NodeRegistry | None = None,
) -> tuple[bool, list[str], dict[str, list[dict[str, Any]]]]:
    reg = node_registry or get_registry()
    ok, outputs, errors = validate(doc, registry=reg)
    return ok, outputs, errors


def seed_context(
    extra_data: dict[str, Any] | None,
    *,
    user_id: str | None,
    session_id: str | None = None,
) -> dict[str, Any]:
    data = dict(extra_data or {})
    if user_id is not None and "user_id" not in data:
        data["user_id"] = user_id
    if session_id is not None and "session_id" not in data:
        data["session_id"] = session_id
    return data
