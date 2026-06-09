"""``TaskHandler`` for durable, retryable uploaded-file processing.

Replaces the previous fire-and-forget ``BackgroundTasks.add_task`` path: file
text extraction / indexing now runs as a persisted :class:`Task` (``IMPORT``
type) so the work survives a restart (see :func:`recover_pending_file_jobs`) and
retries on transient failure instead of being silently lost.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from leagent.db.models.task import TaskContext, TaskType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from leagent.services.service_manager import ServiceManager

logger = logging.getLogger(__name__)

_MAX_ATTEMPTS = 3


class FileProcessingTaskHandler:
    """Process an uploaded file (extract text / index) with bounded retries."""

    name = "file_processing_handler"
    task_type: TaskType = TaskType.IMPORT

    def __init__(self, service_manager: "ServiceManager | None" = None) -> None:
        self._sm = service_manager

    async def spawn(
        self,
        task_ctx: TaskContext,
        params: dict[str, Any],
        session: "AsyncSession",
    ) -> dict[str, Any]:
        file_id = str(params.get("file_id") or "").strip()
        storage_path = params.get("storage_path")
        mime_type = params.get("mime_type")
        original_name = params.get("original_name")
        if not file_id or not storage_path:
            raise ValueError("file_processing task requires 'file_id' and 'storage_path'")

        sm = self._sm
        if sm is None:
            from leagent.services.service_manager import get_service_manager

            sm = get_service_manager()

        processor = getattr(sm, "file_processing", None)
        if processor is None:
            logger.warning("file_processing_service_unavailable file_id=%s", file_id)
            return {"file_id": file_id, "skipped": True}

        last_err: Exception | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            if task_ctx.abort_event.is_set():
                return {"file_id": file_id, "aborted": True}
            try:
                await processor.process_and_update_db(
                    file_id=file_id,
                    file_path=storage_path,
                    mime_type=mime_type,
                    original_name=original_name,
                )
                return {"file_id": file_id, "attempt": attempt}
            except Exception as exc:  # noqa: BLE001 - retried below
                last_err = exc
                task_ctx.append_output(
                    f"file processing attempt {attempt}/{_MAX_ATTEMPTS} failed: {exc}\n"
                )
                logger.warning(
                    "file_processing_attempt_failed file_id=%s attempt=%s err=%s",
                    file_id,
                    attempt,
                    exc,
                )
                if attempt < _MAX_ATTEMPTS:
                    await asyncio.sleep(min(2 ** attempt, 10))

        raise RuntimeError(
            f"file processing failed after {_MAX_ATTEMPTS} attempts: {last_err}"
        )

    async def kill(self, task_id: str, session: "AsyncSession") -> None:
        return None
