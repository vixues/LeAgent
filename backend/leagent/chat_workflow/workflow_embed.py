"""Validate and fingerprint workflow graphs embedded in chat messages.

``workflow_embed.data`` uses the same JSON shape as ``Flow.data`` (editor
or canonical). Semantic integrity uses :func:`graph_hash` on the loaded
``WorkflowDocument`` (layout-only ``ui`` is not part of the document).
"""

from __future__ import annotations

import json
from typing import Any

from leagent.workflow.io import WorkflowDocument, WorkflowLoaderError, graph_hash, load, validate
from leagent.workflow.io.authoring import to_canonical


class WorkflowEmbedValidationError(ValueError):
    """Raised when embedded flow data fails loader or graph validation."""


def _strip_ui_shallow(raw: dict[str, Any]) -> dict[str, Any]:
    """Return a copy without top-level ``ui`` (positions only)."""
    return {k: v for k, v in raw.items() if k != "ui"}


def prepare_engine_document(raw: dict[str, Any]) -> WorkflowDocument:
    """Convert editor / Flow.data JSON into a :class:`WorkflowDocument`."""
    cleaned = _strip_ui_shallow(raw)
    try:
        canon = to_canonical(cleaned)
        return load(canon)
    except (WorkflowLoaderError, TypeError, ValueError) as e:
        raise WorkflowEmbedValidationError(str(e)) from e


def validate_workflow_embed(
    raw: dict[str, Any],
    *,
    node_registry: Any,
) -> tuple[WorkflowDocument, str]:
    """Load + validate; return document and ``graph_hash`` digest."""
    doc = prepare_engine_document(raw)
    ok, _outputs, errors = validate(doc, registry=node_registry)
    if not ok:
        detail = json.dumps(errors, ensure_ascii=False)[:4000]
        raise WorkflowEmbedValidationError(f"workflow validation failed: {detail}")
    return doc, graph_hash(doc)


def build_extensions_payload(
    *,
    flow_data: dict[str, Any],
    digest: str,
    flow_id: str | None = None,
    title: str | None = None,
    summary: str | None = None,
) -> dict[str, Any]:
    """Shape stored in ``Message.extensions`` JSON (alongside legacy keys)."""
    payload: dict[str, Any] = {
        "workflow_embed": {
            "data": flow_data,
            "digest": digest,
        },
        "workflow_embed_digest": digest,
    }
    if flow_id:
        payload["workflow_embed_flow_id"] = flow_id
    if title and str(title).strip():
        payload["workflow_embed_title"] = str(title).strip()
    if summary and str(summary).strip():
        payload["workflow_embed_summary"] = str(summary).strip()
    return payload
