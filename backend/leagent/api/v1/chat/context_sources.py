"""Resolve chat context sources into agent-readable storage paths.

A chat request can carry several kinds of context pointers — a selected UI
folder, explicit ``file_ids``, a coding-project folder, session-level authorized
roots, and inline ``@knowledge:`` mentions. This module resolves each of them
(always user-scoped) into concrete storage paths and prompt notes the agent can
consume, never raising on bad pointers (chat degrades gracefully instead).
"""

from __future__ import annotations

import re
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

import structlog

from leagent.api.v1.chat.paths import dedupe_resolved_paths
from leagent.db import DatabaseService

if TYPE_CHECKING:
    from uuid import UUID

    from leagent.services.chat.service import ChatService

logger = structlog.get_logger(__name__)


async def resolve_folder_context(
    user_id: UUID,
    db: DatabaseService,
    folder_id: str | None = None,
    file_ids_csv: str | None = None,
) -> list[tuple[str, str, str | None]]:
    """Fetch ``(storage_path, name, preview)`` for a folder and/or explicit file ids."""
    from uuid import UUID as _UUID

    from sqlmodel import select as sel

    from leagent.db.models.file import File as FileModel

    results: list[tuple[str, str, str | None]] = []
    raw_ids: list[_UUID] = []
    if file_ids_csv:
        for part in file_ids_csv.split(","):
            part = part.strip()
            if part:
                with suppress(ValueError):
                    raw_ids.append(_UUID(part))

    async with db.session() as session:
        if folder_id:
            try:
                fid = _UUID(folder_id)
            except ValueError:
                fid = None
            if fid:
                stmt = sel(FileModel).where(
                    FileModel.folder_id == fid,
                    FileModel.user_id == user_id,
                    FileModel.is_deleted == False,  # noqa: E712
                )
                rows = (await session.exec(stmt)).all()
                for f in rows:
                    preview = (f.extracted_text or "")[:1500] if f.extracted_text else None
                    results.append((f.storage_path, f.original_name, preview))

        if raw_ids:
            stmt = sel(FileModel).where(
                FileModel.id.in_(raw_ids),
                FileModel.user_id == user_id,
                FileModel.is_deleted == False,  # noqa: E712
            )
            rows = (await session.exec(stmt)).all()
            for f in rows:
                preview = (f.extracted_text or "")[:1500] if f.extracted_text else None
                results.append((f.storage_path, f.original_name, preview))

    return results


def context_item_paths(
    context_items: list[tuple[str, str, str | None]],
) -> list[str]:
    """Project the storage-path column out of :func:`resolve_folder_context` rows."""
    return [path for path, _name, _preview in context_items]


async def resolve_folder_context_note(
    user_id: UUID,
    db: DatabaseService,
    folder_id: str | None,
    *,
    attached_file_count: int,
) -> str | None:
    """Return a short prompt note naming the selected UI folder (with its path)."""
    from uuid import UUID as _UUID

    if not folder_id or not str(folder_id).strip():
        return None
    try:
        fid = _UUID(str(folder_id))
    except ValueError:
        return None

    from sqlmodel import select

    from leagent.db.models import Folder

    async with db.session() as session:
        folder = (
            await session.exec(
                select(Folder).where(
                    Folder.id == fid,
                    Folder.user_id == user_id,
                    Folder.is_deleted == False,  # noqa: E712
                ),
            )
        ).first()
        if not folder:
            return None

        names = [folder.name]
        parent_id = folder.parent_id
        seen = {folder.id}
        while parent_id and parent_id not in seen:
            seen.add(parent_id)
            parent = (
                await session.exec(
                    select(Folder).where(
                        Folder.id == parent_id,
                        Folder.user_id == user_id,
                        Folder.is_deleted == False,  # noqa: E712
                    ),
                )
            ).first()
            if not parent:
                break
            names.insert(0, parent.name)
            parent_id = parent.parent_id

    folder_path = " / ".join(name for name in names if name)
    lines = [
        "\n\nSelected folder context:",
        f"- Folder: {folder_path or str(fid)}",
        f"- Folder ID: {fid}",
        f"- Attached files from this folder: {attached_file_count}",
        "When the user says \"this folder\", interpret it as this selected folder.",
    ]
    return "\n".join(lines)


def chat_project_workspace_note(
    *,
    folder_id: UUID | str,
    files_root: str,
    attached_file_count: int = 0,
) -> str:
    """Prompt note for a chat-project shared file space (all sessions share it)."""
    lines = [
        "\n\nShared project workspace:",
        f"- Catalog folder ID: {folder_id}",
        f"- On-disk files root: {files_root}",
        f"- Attached files from this project folder: {attached_file_count}",
        "All conversations in this chat project share this workspace.",
        "Prefer reading and writing under the project files root; do not invent a per-session silo.",
    ]
    return "\n".join(lines)


async def resolve_project_folder_path(
    user_id: UUID,
    db: DatabaseService,
    project_folder_id: str | None,
) -> str | None:
    """Resolve a folder id to its on-disk ``project_path`` (or ``None``).

    Returns ``None`` silently when the id is empty / malformed, the folder
    doesn't exist, the caller doesn't own it, or project mode is off — chat
    should not 4xx for an invalid project pointer; the LLM just runs without
    project context and tools refuse on their own if asked to touch a forbidden
    path.
    """
    from uuid import UUID as _UUID

    if not project_folder_id or not str(project_folder_id).strip():
        return None
    try:
        fid = _UUID(str(project_folder_id))
    except ValueError:
        return None

    from leagent.db.models import Folder
    from leagent.db.sqlite_compat import load_entity_by_id
    from leagent.project.paths import (
        ProjectPathSafetyError,
        resolve_owned_project_folder,
    )

    async with db.session() as session:
        folder = await load_entity_by_id(session, Folder, fid, parent_table="folders")
        if not folder or folder.is_deleted or folder.user_id != user_id:
            return None
        try:
            resolved = resolve_owned_project_folder(folder, user_id)
        except ProjectPathSafetyError as exc:
            logger.info(
                "chat_project_folder_rejected",
                folder_id=str(fid),
                error=str(exc),
            )
            return None
    return str(resolved)


async def authorized_root_paths_for_session(
    chat_svc: ChatService,
    session_id: UUID,
    user_id: UUID,
) -> list[str] | None:
    """Resolved directory paths from a session's ``authorized_roots`` metadata."""
    items = await chat_svc.list_authorized_roots(session_id, user_id=user_id)
    paths: list[str] = []
    for it in items:
        if isinstance(it, dict):
            p = it.get("path")
            if isinstance(p, str) and p.strip():
                paths.append(p.strip())
    deduped = dedupe_resolved_paths(paths)
    return deduped if deduped else None


_KNOWLEDGE_LINE_RE = re.compile(r"@knowledge:([^\n]+)", re.UNICODE)
_UUID_36_RE = re.compile(r"^[0-9a-fA-F-]{36}$", re.IGNORECASE)


def parse_knowledge_line_payload(raw: str) -> tuple[UUID | None, str | None]:
    """Return ``(file_id, original_name)`` from the text after ``@knowledge:``.

    If ``#<uuid>`` is present, the name is the segment before the last ``#`` and
    the tail must be a valid UUID; otherwise the whole string is a display name.
    """
    from uuid import UUID as _UUID

    s = raw.strip()
    if not s:
        return None, None
    if "#" in s:
        name, tail = s.rsplit("#", 1)
        tid = tail.strip()
        if _UUID_36_RE.match(tid):
            with suppress(ValueError):
                return _UUID(tid), (name.strip() or None)
    return None, s or None


async def resolve_knowledge_message_paths(
    user_id: UUID,
    db: DatabaseService,
    message: str,
) -> list[str]:
    """Resolve ``@knowledge:…`` mentions in *message* to indexed document paths.

    When ``#<file_uuid>`` is omitted, matches :attr:`File.original_name` for the
    user (``is_deleted == False``); if multiple rows match, the newest is used
    and a warning is logged.
    """
    from sqlmodel import col, select

    from leagent.db.models.file import File as FileModel

    refs: list[tuple[UUID | None, str | None]] = []
    for m in _KNOWLEDGE_LINE_RE.finditer(message or ""):
        file_id, name = parse_knowledge_line_payload(m.group(1) or "")
        if file_id is not None or (name and name.strip()):
            refs.append((file_id, name))
    if not refs:
        return []

    out: list[str] = []
    async with db.session() as session:
        for file_id, name in refs:
            row = None
            if file_id is not None:
                stmt = select(FileModel).where(
                    FileModel.id == file_id,
                    FileModel.user_id == user_id,
                    FileModel.is_deleted == False,  # noqa: E712
                )
                row = (await session.exec(stmt)).first()
            elif name:
                stmt = (
                    select(FileModel)
                    .where(
                        FileModel.user_id == user_id,
                        FileModel.is_deleted == False,  # noqa: E712
                        FileModel.original_name == name,
                    )
                    .order_by(col(FileModel.created_at).desc())
                )
                rows = list((await session.exec(stmt)).all())
                if len(rows) > 1:
                    logger.warning(
                        "knowledge_ref_ambiguous_name: user_id=%s name=%r count=%s",
                        user_id,
                        name,
                        len(rows),
                    )
                row = rows[0] if rows else None
            if row and row.storage_path:
                with suppress(OSError, RuntimeError, ValueError):
                    out.append(str(Path(row.storage_path).expanduser().resolve()))
    return out
