"""Helper for persisting tool-produced artifacts through the file layer.

Tools that generate a managed blob (images, screenshots, reports, exports)
must not write bytes directly to disk. They call :func:`register_tool_artifact`
which routes through the single ingress (``FileService.register`` /
``SessionManager.register_artifact_bytes``) and returns an attachment-shaped
dict (``id``, ``storage_path``, ``preview_url``, ``download_url``, ...).

When a session context is available the artifact is also upserted onto the
session so it appears in ``list_session_attachments``; otherwise the bytes are
still persisted as a managed blob via a local-backed ``FileService``.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def _coerce_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


async def register_tool_artifact(
    data: bytes,
    *,
    filename: str,
    content_type: str | None = None,
    session_id: Any | None = None,
    user_id: Any | None = None,
) -> dict[str, Any] | None:
    """Persist *data* as a managed artifact and return its attachment dict.

    Args:
        data: The raw artifact bytes.
        filename: Display/file name for the artifact.
        content_type: Optional MIME type (guessed from *filename* if omitted).
        session_id: Owning chat session, if any.
        user_id: Owning user, if any.

    Returns:
        An attachment-shaped dict (``id``, ``storage_path``, ``preview_url``,
        ``download_url``, ``size`` …) or ``None`` on failure.
    """
    session_uuid = _coerce_uuid(session_id)
    user_uuid = _coerce_uuid(user_id)

    session_manager = None
    if session_uuid is not None:
        try:
            from leagent.services.service_manager import get_service_manager

            sm = get_service_manager()
            session_manager = getattr(sm, "session_manager", None) if sm else None
        except (RuntimeError, AssertionError, ImportError):
            session_manager = None

    if session_manager is not None:
        return await session_manager.register_artifact_bytes(
            session_uuid,
            user_uuid,
            data,
            filename=filename,
            content_type=content_type,
        )

    # No session context: persist as a managed blob without attachment wiring.
    return await _register_without_session(
        data, filename=filename, content_type=content_type, user_uuid=user_uuid
    )


async def _register_without_session(
    data: bytes,
    *,
    filename: str,
    content_type: str | None,
    user_uuid: UUID | None,
) -> dict[str, Any] | None:
    from leagent.config.settings import get_settings
    from leagent.file.primitives import FileScope, sanitize_filename
    from leagent.file.service import FileService
    from leagent.file.storage.local import LocalStorageBackend

    label = sanitize_filename(filename, default="artifact")
    try:
        fs = FileService(
            default_backend=LocalStorageBackend(get_settings().files.upload_dir),
            default_backend_name="local",
        )
        ref = await fs.register(
            data,
            filename=label,
            content_type=content_type,
            scope=FileScope.OUTPUT,
            user_id=user_uuid,
            category="tool_output",
            persist_db_row=False,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("register_tool_artifact_failed: %s", exc)
        return None

    return {
        "id": str(ref.id),
        "filename": label,
        "name": label,
        "content_type": ref.content_type,
        "size": ref.size,
        "sha256": ref.checksum,
        "storage_path": ref.metadata.get("storage_path", ref.storage_key),
    }
