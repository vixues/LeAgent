"""Chat attachment persistence and reference resolution.

Two responsibilities:
  * :func:`attach_chat_files` — persist multipart uploads through
    ``SessionManager.attach_files`` and shape them for the SSE response.
  * :func:`resolve_request_attachment_paths` / :func:`merge_agent_attachment_paths`
    — turn mixed attachment references (id / filename / path) carried on a chat
    request into concrete storage paths the agent can read.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from fastapi import UploadFile

from leagent.api.v1.chat.paths import attachment_local_path_for_sse, dedupe_resolved_paths

logger = structlog.get_logger(__name__)

#: Attachment kinds rendered as inline assistant media (ChatGPT-style output).
_ASSISTANT_MEDIA_KINDS = {"image", "video", "model3d", "audio"}


def build_assistant_media_event(
    workspace_payload: Any,
    *,
    native_image_output: bool,
) -> dict[str, Any] | None:
    """Build an ``assistant_media`` SSE payload from workspace attachments.

    Filters the assistant's produced attachments down to renderable media so
    the frontend can show images / video / 3D inline within the message body
    rather than only as attachment cards. ``native_image_output`` reflects
    whether the active model's capability profile can itself emit image output
    (capability-routed), distinguishing model-native media from tool output.
    """
    if not isinstance(workspace_payload, dict):
        return None
    items = workspace_payload.get("attachments")
    if not isinstance(items, list):
        return None
    media: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").lower()
        ctype = str(item.get("content_type") or item.get("mime") or "").lower()
        if kind in _ASSISTANT_MEDIA_KINDS or ctype.startswith(("image/", "video/", "audio/")):
            media.append(item)
    if not media:
        return None
    return {"attachments": media, "native": bool(native_image_output)}


async def attach_chat_files(
    user_id: UUID,
    session_id: UUID,
    files: list[UploadFile],
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, str]]]:
    """Persist uploads via :meth:`SessionManager.attach_files`.

    Returns ``(attachment_rows, stored_paths, errors)``.
    """
    from leagent.main import get_service_manager

    attachments_out: list[dict[str, Any]] = []
    stored_paths: list[str] = []
    errors: list[dict[str, str]] = []

    if not files:
        return attachments_out, stored_paths, errors

    try:
        sm = get_service_manager()
    except Exception:  # noqa: BLE001
        sm = None

    if sm is None or sm.session_manager is None:
        for upload in files:
            errors.append({
                "file": upload.filename or "unnamed",
                "error": "Session manager unavailable; file rejected",
            })
        return attachments_out, stored_paths, errors

    try:
        persisted = await sm.session_manager.attach_files(
            session_id, files, user_id=user_id,
        )
    except ValueError as exc:
        errors.append({"file": "(batch)", "error": str(exc)})
        return attachments_out, stored_paths, errors
    except Exception as exc:  # noqa: BLE001
        logger.warning("session_attach_files_failed: %s", exc)
        errors.append({"file": "(batch)", "error": str(exc)})
        return attachments_out, stored_paths, errors

    for att in persisted:
        if att.storage_path:
            stored_paths.append(att.storage_path)
        row: dict[str, Any] = {
            "id": str(att.id),
            "filename": att.filename,
            "kind": att.kind,
            "content_type": att.content_type,
            "size": att.size,
            "preview_url": att.preview_url,
            "download_url": att.download_url,
        }
        lp = attachment_local_path_for_sse(att.storage_path)
        if lp:
            row["local_path"] = lp
        attachments_out.append(row)
    return attachments_out, stored_paths, errors


async def resolve_request_attachment_paths(
    session_id: UUID,
    attachment_refs: list[str] | None,
) -> list[str]:
    """Resolve mixed attachment refs (id / path / name) to concrete storage paths."""
    if not attachment_refs:
        return []

    from leagent.main import get_service_manager

    try:
        sm = get_service_manager()
    except Exception:  # noqa: BLE001
        sm = None

    if sm is None or sm.session_manager is None:
        return dedupe_resolved_paths(attachment_refs)

    try:
        session_attachments = await sm.session_manager.list_attachments(session_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("resolve_request_attachment_paths_failed: %s", exc)
        return dedupe_resolved_paths(attachment_refs)

    by_id: dict[str, str] = {}
    by_name: dict[str, str] = {}
    by_basename: dict[str, str] = {}
    for att in session_attachments:
        if not att.storage_path:
            continue
        spath = str(Path(att.storage_path).expanduser().resolve())
        by_id[str(att.id)] = spath
        if att.filename:
            by_name[att.filename.casefold()] = spath
        by_basename[Path(spath).name.casefold()] = spath

    resolved: list[str] = []
    passthrough: list[str] = []
    for ref in attachment_refs:
        if not ref:
            continue
        key = str(ref).strip()
        if not key:
            continue
        mapped = (
            by_id.get(key)
            or by_name.get(key.casefold())
            or by_basename.get(Path(key).name.casefold())
        )
        if mapped:
            resolved.append(mapped)
        else:
            passthrough.append(key)

    return dedupe_resolved_paths(resolved + passthrough)


def merge_agent_attachment_paths(
    base: list[str] | None,
    extra: list[str],
) -> list[str] | None:
    """Combine and de-duplicate two attachment-path lists (``None`` when empty)."""
    combined = (base or []) + extra
    if not combined:
        return None
    return dedupe_resolved_paths(combined) or None
