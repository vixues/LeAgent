"""Database-backed :class:`FlowWorkflowRegistry`.

Loads a :class:`WorkflowDocument` from the ``flows`` table and migrates
older payloads on the fly via :func:`io.load`.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import structlog

from .io import WorkflowDocument, load

logger = structlog.get_logger(__name__)


class FlowWorkflowRegistry:
    """Resolves a flow id → :class:`WorkflowDocument`."""

    def __init__(self, db: Any) -> None:
        self._db = db

    async def get(self, workflow_id: str) -> WorkflowDocument | None:
        from sqlmodel import select
        from leagent.services.database.models.flow import Flow

        async with self._db.session() as session:
            try:
                flow_uuid = UUID(workflow_id)
                flow = await session.get(Flow, flow_uuid)
            except (ValueError, AttributeError):
                result = await session.exec(
                    select(Flow).where(Flow.name == workflow_id, Flow.is_deleted == False)
                )
                flow = result.first()

            if not flow or not flow.data:
                return None

            try:
                raw = json.loads(flow.data)
                doc = load(raw)
                if not doc.id:
                    doc.id = str(flow.id)
                return doc
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "flow_document_load_failed",
                    flow_id=str(flow.id),
                    error=str(exc),
                )
                return None
