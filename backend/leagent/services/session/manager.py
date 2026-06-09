"""The session manager that owns chat state for the whole process.

All agent entry points (``/api/v1/chat``, websocket handlers, background
runners) must acquire a session through :class:`SessionManager`. Once
acquired, the manager guarantees:

* A single :class:`asyncio.Lock` per session prevents two concurrent turns
  from stepping on each other's transcript updates.
* The :class:`TieredSessionStore` writes are flushed to the database as soon as
  the lock is released, so durability is never delayed waiting on Redis.
* Uploaded files are tracked as :class:`SessionAttachment` entries with
  server-issued preview / download URLs, so the frontend can render them
  without additional auth round-trips.

This class is deliberately thin: it is the API between the rest of the
system and the storage layer. Business logic (compaction, recall, memory
writes) lives in the agent runtime.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import mimetypes
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncIterator, Iterable
from uuid import UUID, uuid4

from leagent.file.primitives import (
    classify_file_kind,
    sanitize_filename,
)
from leagent.services.auth.signed_url import (
    build_download_url,
    build_preview_url,
)
from leagent.services.session.state import (
    ATTACHMENT_KIND_DOCUMENT,
    ATTACHMENT_KIND_IMAGE,
    ATTACHMENT_KIND_TEXT,
    SessionAttachment,
    SessionMessage,
    SessionState,
)
from leagent.services.session.paths import SessionPathRegistry
from leagent.services.session.store import TieredSessionStore

if TYPE_CHECKING:
    from fastapi import UploadFile

    from leagent.config.settings import Settings
    from leagent.services.cache.service import CacheService
    from leagent.services.database.service import DatabaseService

logger = logging.getLogger(__name__)


class SessionManager:
    """Process-wide owner of :class:`SessionState` objects.

    The manager is injected through :class:`ServiceManager`. Do not
    instantiate it directly from endpoints or agents — always go through
    ``service_manager.session_manager``.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        cache: CacheService | None,
        database: DatabaseService | None,
        file_service: Any | None = None,
    ) -> None:
        self._settings = settings
        self._paths = SessionPathRegistry(settings)
        self._cache = cache
        self._database = database
        self._file_service = file_service
        self._store = TieredSessionStore(settings, cache=cache, database=database)
        self._locks: dict[UUID, asyncio.Lock] = {}
        self._locks_mutex = asyncio.Lock()

    @property
    def store(self) -> TieredSessionStore:
        return self._store

    # -- locks ----------------------------------------------------------

    async def _lock_for(self, session_id: UUID) -> asyncio.Lock:
        async with self._locks_mutex:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[session_id] = lock
            return lock

    @asynccontextmanager
    async def locked(self, session_id: UUID) -> AsyncIterator[SessionState]:
        """Acquire the per-session lock and hand back the current state.

        Yields the hydrated :class:`SessionState`. Any mutations the caller
        performs on it are automatically persisted when the context exits —
        the caller does **not** need to call :meth:`save` explicitly inside
        the ``async with`` block.
        """
        lock = await self._lock_for(session_id)
        async with lock:
            state = await self._store.load(session_id)
            if state is None:
                state = SessionState(session_id=session_id)
            try:
                yield state
            finally:
                await self._store.save(state)

    # -- high-level API -------------------------------------------------

    async def get_or_create(
        self,
        session_id: UUID,
        *,
        user_id: UUID | None = None,
        workspace_id: UUID | None = None,
        flow_id: UUID | None = None,
    ) -> SessionState:
        """Hydrate a session, creating an empty one if necessary."""
        async with self.locked(session_id) as state:
            if state.user_id is None and user_id is not None:
                state.user_id = user_id
            if state.workspace_id is None and workspace_id is not None:
                state.workspace_id = workspace_id
            if state.flow_id is None and flow_id is not None:
                state.flow_id = flow_id
            return state

    async def load(self, session_id: UUID) -> SessionState | None:
        return await self._store.load(session_id)

    async def append_user(
        self,
        session_id: UUID,
        content: str,
        *,
        attachment_ids: Iterable[UUID] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SessionMessage:
        async with self.locked(session_id) as state:
            message = SessionMessage(
                role="user",
                content=content,
                attachment_ids=[str(a) for a in (attachment_ids or [])],
            )
            state.append_message(message)
            if metadata:
                state.metadata.update(metadata)
            return message

    async def append_assistant(
        self,
        session_id: UUID,
        content: str,
        *,
        tool_calls: list[dict[str, Any]] | None = None,
        model: str | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> SessionMessage:
        async with self.locked(session_id) as state:
            message = SessionMessage(
                role="assistant",
                content=content,
                tool_calls=tool_calls,
                model=model,
            )
            state.append_message(message)
            state.usage.add(input_tokens=input_tokens, output_tokens=output_tokens)
            return message

    async def append_tool_result(
        self,
        session_id: UUID,
        *,
        tool_call_id: str,
        content: str,
    ) -> SessionMessage:
        async with self.locked(session_id) as state:
            message = SessionMessage(
                role="tool",
                content=content,
                tool_call_id=tool_call_id,
            )
            state.append_message(message)
            return message

    async def replace_pending_tool_reply(
        self,
        session_id: UUID,
        *,
        tool_call_id: str,
        content: str,
    ) -> bool:
        """If a placeholder ``ask_user`` tool row exists, replace its body; else return False."""
        token = "_wa_pending"
        async with self.locked(session_id) as state:
            for msg in state.messages:
                if (
                    msg.role == "tool"
                    and msg.tool_call_id == tool_call_id
                    and token in (msg.content or "")
                ):
                    msg.content = content
                    return True
            return False

    async def replace_messages(
        self,
        session_id: UUID,
        messages: Iterable[SessionMessage],
    ) -> None:
        async with self.locked(session_id) as state:
            state.replace_messages(messages)

    async def save_file_state(
        self,
        session_id: UUID,
        snapshot: list[dict[str, Any]],
    ) -> None:
        async with self.locked(session_id) as state:
            state.file_state = list(snapshot or [])

    async def set_system_prompt_fingerprint(
        self, session_id: UUID, fingerprint: str
    ) -> None:
        async with self.locked(session_id) as state:
            state.system_prompt_fingerprint = fingerprint

    # -- attachments ----------------------------------------------------

    async def attach_files(
        self,
        session_id: UUID,
        uploads: Iterable[UploadFile],
        *,
        user_id: UUID | None = None,
    ) -> list[SessionAttachment]:
        """Persist uploaded files to disk and register them on the session.

        The method is safe to call before any user message is appended — in
        fact, the ``/api/v1/chat/stream`` handler calls this immediately
        after receiving the multipart form so the attachment IDs are known
        when ``append_user`` records the first turn.
        """
        persisted: list[SessionAttachment] = []
        upload_root = self._paths.ensure_uploads_dir(session_id)

        max_bytes = max(0, int(self._settings.files.max_upload_bytes))

        for upload in uploads:
            if upload is None:
                continue
            filename = upload.filename or f"attachment-{uuid4().hex}"
            safe_name = sanitize_filename(filename, default="attachment")
            attachment_id = uuid4()
            storage_path = upload_root / f"{_attachment_storage_prefix(attachment_id)}_{safe_name}"

            sha = hashlib.sha256()
            size = 0
            try:
                with open(storage_path, "wb") as fh:
                    while True:
                        chunk = await upload.read(1024 * 1024)
                        if not chunk:
                            break
                        sha.update(chunk)
                        size += len(chunk)
                        if max_bytes and size > max_bytes:
                            fh.close()
                            try:
                                storage_path.unlink()
                            except OSError:
                                pass
                            raise ValueError(
                                f"Attachment {filename!r} exceeds the "
                                f"{max_bytes} byte upload limit"
                            )
                        fh.write(chunk)
            finally:
                try:
                    await upload.close()
                except Exception:  # noqa: BLE001
                    pass

            content_type = (
                upload.content_type
                or mimetypes.guess_type(filename)[0]
                or "application/octet-stream"
            )
            kind = classify_file_kind(filename, content_type).value
            attachment = SessionAttachment(
                id=attachment_id,
                session_id=session_id,
                filename=filename,
                storage_path=str(storage_path),
                content_type=content_type,
                kind=kind,
                size=size,
                sha256=sha.hexdigest(),
            )
            self._populate_urls(attachment, user_id=user_id)
            persisted.append(attachment)

        if not persisted:
            return persisted

        async with self.locked(session_id) as state:
            if state.user_id is None and user_id is not None:
                state.user_id = user_id
            for att in persisted:
                state.upsert_attachment(att)

        if self._file_service is not None:
            await self._persist_via_file_service(persisted, user_id=user_id)
        else:
            await self._persist_attachment_rows(persisted, user_id=user_id)
        return persisted

    async def register_external_file(
        self,
        session_id: UUID,
        user_id: UUID | None,
        source_path: str,
        *,
        display_name: str | None = None,
        allowed_roots: Iterable[str | os.PathLike[str]] | None = None,
    ) -> dict[str, Any] | None:
        """Copy a tool-generated file from the path sandbox into session attachments.

        The source path must sit under a configured tool file root. On success
        the file is added like an upload, with DB rows and signed URLs, so the
        chat workspace and ``/api/v1/files`` stay consistent.
        """
        from leagent.file.sandbox import _get_allowed_roots, _is_inside

        try:
            src = Path(source_path).expanduser().resolve()
        except OSError as exc:
            logger.warning(
                "register_external_file_bad_path",
                extra={"source_path": source_path, "session_id": str(session_id), "error": str(exc)},
            )
            return None
        if not src.is_file():
            logger.warning(
                "register_external_file_not_file",
                extra={
                    "session_id": str(session_id),
                    "source_path": source_path,
                    "resolved": str(src),
                    "is_dir": src.is_dir(),
                },
            )
            return None
        extra_roots = tuple(
            Path(root).expanduser().resolve()
            for root in (allowed_roots or ())
            if root
        )
        tool_roots = _get_allowed_roots()
        combined = (*tool_roots, *extra_roots)
        if not _is_inside(src, combined):
            logger.warning(
                "register_external_file_rejected_outside_sandbox",
                extra={
                    "session_id": str(session_id),
                    "resolved_source": str(src),
                    "tool_root_count": len(tool_roots),
                    "tool_roots_sample": [str(p) for p in tool_roots[:3]],
                    "extra_roots": [str(p) for p in extra_roots],
                },
            )
            return None

        label = sanitize_filename(display_name or src.name, default="attachment")

        if self._file_service is not None:
            return await self._register_external_via_service(
                session_id, user_id, src, label=label,
            )

        attachment_id = uuid4()
        upload_root = self._paths.ensure_uploads_dir(session_id)
        storage_path = upload_root / f"{_attachment_storage_prefix(attachment_id)}_{label}"

        try:
            shutil.copy2(src, storage_path)
        except OSError as exc:
            logger.warning("register_external_file_copy_failed: %s", exc)
            return None

        st = storage_path.stat()
        size = int(st.st_size)
        digest = hashlib.sha256()
        with open(storage_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)

        content_type = mimetypes.guess_type(label)[0] or "application/octet-stream"
        kind = classify_file_kind(label, content_type).value
        attachment = SessionAttachment(
            id=attachment_id,
            session_id=session_id,
            filename=label,
            storage_path=str(storage_path),
            content_type=content_type,
            kind=kind,
            size=size,
            sha256=digest.hexdigest(),
            extra={"source_tool_path": str(src)},
        )
        self._populate_urls(attachment, user_id=user_id)

        async with self.locked(session_id) as state:
            if state.user_id is None and user_id is not None:
                state.user_id = user_id
            state.upsert_attachment(attachment)

        await self._persist_attachment_rows((attachment,), user_id=user_id)

        return {
            "id": str(attachment_id),
            "filename": label,
            "name": label,
            "kind": kind,
            "content_type": content_type,
            "size": size,
            "sha256": attachment.sha256,
            "preview_url": attachment.preview_url,
            "download_url": attachment.download_url,
        }

    async def list_attachments(
        self, session_id: UUID, *, user_id: UUID | None = None
    ) -> list[SessionAttachment]:
        state = await self._store.load(session_id)
        if state is None:
            return []
        attachments = list(state.attachments)
        if user_id is not None:
            for attachment in attachments:
                self._populate_urls(attachment, user_id=user_id)
        return attachments

    def build_attachment_manifest(
        self, attachments: Iterable[SessionAttachment]
    ) -> str:
        """Render a machine-parsable manifest for the LLM system prompt.

        The agent sees every attachment even before it has called a tool, so
        it can decide when to invoke ``file_manager`` or ``excel_reader`` on
        the user's files.
        """
        lines: list[str] = []
        for att in attachments:
            stem = Path(att.filename).stem if att.filename else ""
            storage_basename = Path(att.storage_path).name if att.storage_path else ""
            safe_name = storage_basename.split("_", 1)[1] if "_" in storage_basename else storage_basename
            aliases = sorted({
                att.filename.casefold() if att.filename else "",
                stem.casefold() if stem else "",
                storage_basename.casefold(),
                safe_name.casefold(),
                Path(safe_name).stem.casefold() if safe_name else "",
            } - {""})
            parts = [
                f"- id={att.id}",
                f"name={att.filename!r}",
                f"stem={stem!r}",
                f"storage_basename={storage_basename!r}",
                f"kind={att.kind}",
                f"type={att.content_type}",
                f"size={att.size}",
                f"path={att.storage_path}",
                f"aliases={aliases!r}",
            ]
            if att.preview_url:
                parts.append(f"preview={att.preview_url}")
            lines.append(" ".join(parts))
        if not lines:
            return ""
        header = (
            "<session_attachments>\n"
            "The user has attached the following files to this conversation.\n"
            "When the user references an attachment by name, match it to "
            "`name`, `stem`, or `aliases` (case-insensitive), then use the "
            "exact `path` value below in your FIRST file-reading tool call.\n"
            "Do not call list/tree/glob to discover files that are already "
            "listed in this section.\n"
        )
        footer = "\n</session_attachments>"
        return header + "\n".join(lines) + footer

    def _populate_urls(
        self,
        attachment: SessionAttachment,
        *,
        user_id: UUID | None,
    ) -> None:
        try:
            attachment.preview_url = build_preview_url(
                self._settings,
                attachment_id=attachment.id,
                user_id=user_id,
            )
            attachment.download_url = build_download_url(
                self._settings,
                attachment_id=attachment.id,
                user_id=user_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug("signed_url_generation_failed: %s", exc)

    async def _persist_via_file_service(
        self,
        attachments: Iterable[SessionAttachment],
        *,
        user_id: UUID | None,
    ) -> None:
        """Persist attachment DB rows via FileService instead of direct inserts."""
        from leagent.file.primitives import FileScope

        for att in attachments:
            try:
                from leagent.file.service import FileRef
                ref = FileRef(
                    id=att.id,
                    filename=att.filename,
                    storage_key=att.storage_path or "",
                    backend_name="local",
                    content_type=att.content_type or "application/octet-stream",
                    size=att.size,
                    checksum=att.sha256 or "",
                    user_id=user_id,
                    session_id=att.session_id,
                    scope=FileScope.SESSION,
                    category="upload",
                    metadata={"storage_path": att.storage_path or ""},
                )
                await self._file_service._persist_db_row(ref)
            except Exception as exc:  # noqa: BLE001
                logger.warning("file_service_persist_failed: %s", exc)

    async def _register_external_via_service(
        self,
        session_id: UUID,
        user_id: UUID | None,
        src: Path,
        *,
        label: str,
    ) -> dict[str, Any] | None:
        """Register an external file using FileService.register()."""
        from leagent.file.primitives import FileScope

        try:
            ref = await self._file_service.register(
                data=src,
                filename=label,
                scope=FileScope.OUTPUT,
                session_id=session_id,
                user_id=user_id,
                category="tool_output",
            )
        except Exception as exc:
            logger.warning("register_external_via_service_failed: %s", exc)
            return None

        kind = classify_file_kind(label, ref.content_type).value
        attachment = SessionAttachment(
            id=ref.id,
            session_id=session_id,
            filename=label,
            storage_path=ref.metadata.get("storage_path", ref.storage_key),
            content_type=ref.content_type,
            kind=kind,
            size=ref.size,
            sha256=ref.checksum,
            extra={"source_tool_path": str(src)},
        )
        self._populate_urls(attachment, user_id=user_id)

        async with self.locked(session_id) as state:
            if state.user_id is None and user_id is not None:
                state.user_id = user_id
            state.upsert_attachment(attachment)

        return {
            "id": str(ref.id),
            "filename": label,
            "name": label,
            "kind": kind,
            "content_type": ref.content_type,
            "size": ref.size,
            "sha256": ref.checksum,
            "preview_url": attachment.preview_url,
            "download_url": attachment.download_url,
        }

    async def _persist_attachment_rows(
        self,
        attachments: Iterable[SessionAttachment],
        *,
        user_id: UUID | None,
    ) -> None:
        """Insert ``File`` rows linking each attachment to its session.

        Done after the lock is released so Redis writes stay fast. Failures
        are logged but don't roll back the in-memory attachment state —
        worst case, the file is on disk and in the session JSON but not in
        the ``files`` table.
        """
        if self._database is None:
            return
        try:
            from leagent.services.database.models.file import (
                File,
                FileStatus,
                FileType,
            )
        except Exception:  # noqa: BLE001
            return

        try:
            async with self._database.session() as db:
                for att in attachments:
                    if att.kind == ATTACHMENT_KIND_IMAGE:
                        file_type = FileType.IMAGE
                    elif att.kind == ATTACHMENT_KIND_DOCUMENT:
                        file_type = FileType.DOCUMENT
                    elif att.kind == ATTACHMENT_KIND_TEXT:
                        file_type = FileType.DOCUMENT
                    else:
                        file_type = FileType.OTHER
                    db.add(
                        File(
                            id=att.id,
                            session_id=att.session_id,
                            name=att.filename,
                            original_name=att.filename,
                            file_type=file_type,
                            mime_type=att.content_type,
                            size=att.size,
                            checksum=att.sha256,
                            storage_path=att.storage_path,
                            status=FileStatus.PROCESSED,
                            user_id=user_id,
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("attach_files_row_insert_failed: %s", exc)


def _attachment_storage_prefix(attachment_id: UUID) -> str:
    """Filesystem prefix for stored uploads (short on single-machine installs)."""
    try:
        from leagent.config.settings import get_settings

        if get_settings().is_single_machine_profile:
            return str(attachment_id).replace("-", "")[:8]
    except Exception:  # noqa: BLE001
        pass
    return str(attachment_id)



# _safe_filename removed – use leagent.file.primitives.sanitize_filename


__all__ = ["SessionManager"]
