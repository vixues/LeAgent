"""Session-scoped staging for large tool arguments (side channel for tool-call JSON).

The OpenAI-style ``function.arguments`` channel is a single JSON object; embedding
multi-megabyte ``source`` / ``content`` / ``diff`` strings forces the model to
escape newlines and quotes. **Staging is not “binary storage”** — it keeps bulk
UTF-8 **out of the prompt, out of JSON, and out of tool parameters** so the model
passes short ids instead.

Flow:

1. ``tool_argument_blob`` with ``action=create`` → receive ``blob_id``.
2. ``action=append`` with ``chunk`` (plain UTF-8, up to ~1 MB per call) **or**
   ``chunk_base64`` (standard base64 of UTF-8 bytes — only when plain ``chunk``
   would break JSON quoting).
3. ``action=finalize`` → mark blob read-only; required before consumption.
4. Pass ``source_blob_id`` / ``content_blob_id`` / ``diff_blob_id`` /
   ``old_string_blob_id`` / ``new_string_blob_id`` / ``html_blob_id`` /
   ``html_files_blob_id`` into ``code_execution`` / ``project_write`` /
   ``project_apply_patch`` / ``project_edit`` / ``canvas_publish`` instead of inlining
   large bodies in JSON.

When ``FILES_TOOL_ARGUMENT_BLOB_PERSIST=true`` (see ``FilesSettings.tool_argument_blob_persist``),
finalized non-empty blobs are written under ``<upload_dir>/tool-argument-blobs/<session>/`` and
can be consumed after a process restart until ``take`` deletes the file.

See ``backend/docs/code-gen-tool-args-parsing.md`` for the parse pipeline map.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

_MAX_BLOB_BYTES = 4 * 1024 * 1024
_MAX_APPEND_CHARS = 1_048_576
# ~1 MB UTF-8 as base64 (4 chars per 3 bytes) + margin
_MAX_APPEND_BASE64_CHARS = 1_400_000
_MAX_BLOBS = 2_000
_PRUNE_TARGET = 1_500
_BLOB_ID_RE = re.compile(r"^[a-f0-9]{8,64}$")


def _persist_enabled() -> bool:
    try:
        from leagent.config.settings import get_settings

        return bool(get_settings().files.tool_argument_blob_persist)
    except Exception:  # noqa: BLE001 — settings may be absent in some unit harnesses
        return False


def _blob_disk_path(session_id: str, blob_id: str) -> Path | None:
    bid = str(blob_id).strip().lower()
    if not _BLOB_ID_RE.fullmatch(bid):
        return None
    from leagent.config.settings import get_settings

    root = Path(get_settings().files.upload_dir).expanduser().resolve(strict=False)
    sid = re.sub(r"[^a-zA-Z0-9._\-]", "_", str(session_id))[:200]
    out = (root / "tool-argument-blobs" / sid / f"{bid}.bin").resolve()
    try:
        out.relative_to(root.resolve())
    except ValueError:
        return None
    return out


def _try_unlink_disk_blob(session_id: str, blob_id: str) -> None:
    path = _blob_disk_path(session_id, blob_id)
    if path is None or not path.is_file():
        return
    try:
        path.unlink()
    except OSError:
        logger.warning("tool_argument_blob_disk_unlink_failed", path=str(path))


def _session_key(context: ToolContext) -> str:
    return str(context.session_id or "").strip() or "__no_session__"


@dataclass
class _BlobRecord:
    data: bytearray = field(default_factory=bytearray)
    finalized: bool = False
    updated_at: float = 0.0


def _resolve_append_chunk(params: dict[str, Any]) -> tuple[str | None, str]:
    """Return ``(error_message, utf8_text)`` for an append action.

    If ``chunk_base64`` is non-empty after strip, it wins over ``chunk`` (safer for
    HTML/JSX where JSON escaping of ``"`` is error-prone).
    """
    b64_raw = params.get("chunk_base64")
    if isinstance(b64_raw, str) and b64_raw.strip():
        if len(b64_raw) > _MAX_APPEND_BASE64_CHARS:
            return (
                f"chunk_base64 exceeds {_MAX_APPEND_BASE64_CHARS} characters; "
                "split into smaller appends.",
                "",
            )
        try:
            raw = base64.b64decode(b64_raw.strip(), validate=True)
        except (binascii.Error, ValueError):
            return (
                "chunk_base64: invalid base64 (use standard base64 only, no data: URL prefix).",
                "",
            )
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            return ("chunk_base64: decoded bytes are not valid UTF-8.", "")
        if len(text) > _MAX_APPEND_CHARS:
            return (
                f"Decoded text exceeds {_MAX_APPEND_CHARS} characters; split into smaller appends.",
                "",
            )
        return None, text

    chunk = params.get("chunk")
    if isinstance(chunk, str):
        if len(chunk) > _MAX_APPEND_CHARS:
            return (
                f"chunk exceeds {_MAX_APPEND_CHARS} characters; split into smaller appends "
                "or use chunk_base64.",
                "",
            )
        return None, chunk

    return (
        "For append pass either `chunk` (UTF-8 text) or `chunk_base64` (standard base64 of "
        "UTF-8 bytes). Prefer `chunk_base64` for HTML, SVG, or JSX so the JSON string does "
        "not contain raw double quotes from markup.",
        "",
    )


class ToolArgumentBlobStore:
    """In-process blob buffers keyed by ``(session_id, blob_id)``."""

    _lock = asyncio.Lock()
    _blobs: dict[tuple[str, str], _BlobRecord] = {}

    @classmethod
    async def create(cls, session_id: str) -> str:
        blob_id = uuid4().hex
        key = (session_id, blob_id)
        async with cls._lock:
            cls._blobs[key] = _BlobRecord(updated_at=time.monotonic())
            await cls._maybe_prune_unlocked()
        return blob_id

    @classmethod
    async def append(cls, session_id: str, blob_id: str, chunk: str) -> dict[str, Any]:
        if len(chunk) > _MAX_APPEND_CHARS:
            return {
                "ok": False,
                "error": f"chunk exceeds {_MAX_APPEND_CHARS} characters; split into smaller appends.",
            }
        key = (session_id, blob_id)
        async with cls._lock:
            rec = cls._blobs.get(key)
            if rec is None:
                return {"ok": False, "error": f"Unknown blob_id {blob_id!r}; call create first."}
            if rec.finalized:
                return {"ok": False, "error": "Blob is finalized; create a new blob to append."}
            chunk_b = chunk.encode("utf-8")
            if len(rec.data) + len(chunk_b) > _MAX_BLOB_BYTES:
                return {
                    "ok": False,
                    "error": f"Blob would exceed {_MAX_BLOB_BYTES} bytes; finalize or discard.",
                }
            rec.data.extend(chunk_b)
            rec.updated_at = time.monotonic()
            total = len(rec.data)
            await cls._maybe_prune_unlocked()
        return {"ok": True, "total_bytes": total}

    @classmethod
    async def finalize(cls, session_id: str, blob_id: str) -> dict[str, Any]:
        key = (session_id, blob_id)
        async with cls._lock:
            rec = cls._blobs.get(key)
            if rec is None:
                return {"ok": False, "error": f"Unknown blob_id {blob_id!r}."}
            if rec.finalized:
                return {"ok": True, "total_bytes": len(rec.data), "already_finalized": True}
            data_bytes = bytes(rec.data)
            use_disk = _persist_enabled() and len(data_bytes) > 0
            path = _blob_disk_path(session_id, blob_id) if use_disk else None
            if use_disk and path is not None:
                path.parent.mkdir(parents=True, exist_ok=True)

                def _write() -> None:
                    path.write_bytes(data_bytes)

                try:
                    await asyncio.to_thread(_write)
                except OSError as exc:
                    logger.warning("tool_argument_blob_disk_write_failed", error=str(exc))
                    rec.finalized = True
                    rec.updated_at = time.monotonic()
                    return {"ok": True, "total_bytes": len(rec.data), "persisted": False}
                del cls._blobs[key]
                return {"ok": True, "total_bytes": len(data_bytes), "persisted": True}
            rec.finalized = True
            rec.updated_at = time.monotonic()
            return {"ok": True, "total_bytes": len(rec.data)}

    @classmethod
    async def find_session_for_blob(cls, blob_id: str) -> str | None:
        """Return the session_id owning a non-finalized *blob_id*, or None."""
        async with cls._lock:
            for (sid, bid), rec in cls._blobs.items():
                if bid == blob_id and not rec.finalized:
                    return sid
        return None

    @classmethod
    async def find_any_session_for_blob(cls, blob_id: str) -> str | None:
        """Return session_id for *blob_id* (finalized or not), or None."""
        bid = str(blob_id or "").strip()
        if not bid:
            return None
        async with cls._lock:
            for (sid, stored_bid), _rec in cls._blobs.items():
                if stored_bid == bid:
                    return sid
        return None

    @classmethod
    async def discard(cls, session_id: str, blob_id: str) -> dict[str, Any]:
        key = (session_id, blob_id)
        async with cls._lock:
            existed = cls._blobs.pop(key, None) is not None
        _try_unlink_disk_blob(session_id, blob_id)
        return {"ok": True, "removed": existed}

    @classmethod
    async def take_utf8_text(cls, session_id: str, blob_id: str) -> str | None:
        """Return decoded text and remove the blob (single consumer)."""
        key = (session_id, blob_id)
        async with cls._lock:
            rec = cls._blobs.get(key)
            if rec is None:
                pass
            elif not rec.finalized:
                logger.warning("tool_argument_blob_take_not_finalized", blob_id=blob_id)
                return None
            else:
                del cls._blobs[key]
        if rec is not None:
            try:
                return rec.data.decode("utf-8")
            except UnicodeDecodeError:
                logger.warning("tool_argument_blob_decode_error", blob_id=blob_id)
                return None
        path = _blob_disk_path(session_id, blob_id)
        if path is None or not path.is_file():
            return None

        def _read() -> bytes:
            return path.read_bytes()

        try:
            raw = await asyncio.to_thread(_read)
        except OSError:
            logger.warning("tool_argument_blob_disk_read_failed", path=str(path))
            return None
        try:
            path.unlink()
        except OSError:
            logger.warning("tool_argument_blob_disk_unlink_failed", path=str(path))
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning("tool_argument_blob_decode_error", blob_id=blob_id)
            return None

    @classmethod
    async def _maybe_prune_unlocked(cls) -> None:
        if len(cls._blobs) <= _MAX_BLOBS:
            return
        items = sorted(cls._blobs.items(), key=lambda kv: float(kv[1].updated_at or 0.0))
        drop = len(items) - _PRUNE_TARGET
        for i in range(max(0, drop)):
            del cls._blobs[items[i][0]]


class ToolArgumentBlobTool(BaseTool):
    """Chunked UTF-8 blob staging to avoid huge JSON strings in tool calls."""

    name = "tool_argument_blob"
    description = (
        "Fallback staging for large UTF-8 when direct tool-call JSON fails. "
        "**Do not use for routine HTML pages** — prefer "
        "`canvas_publish(mode=html, html=\"…\")` inline first (one tool call; "
        "the runtime auto-stages recovered HTML as a blob when needed). "
        "When blob staging is required: `action=create_and_finalize` with plain "
        "`chunk` (preferred) or `chunk_base64` only when quotes break JSON. "
        "Multi-step `create` → `append` → `finalize` is only when output was "
        "truncated mid-stream or the body exceeds one append (~1 MB). "
        "Pass `source_blob_id` / `content_blob_id` / `diff_blob_id` / "
        "`html_blob_id` / `html_files_blob_id` / `old_string_blob_id` / "
        "`new_string_blob_id` into consuming tools instead of inlining megabytes."
    )
    category = ToolCategory.UTIL
    version = "1.0.0"
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = "block"
    max_result_size_chars = 8_000
    timeout_sec = 30

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "append", "finalize", "discard", "create_and_finalize"],
                    "description": "create | append | finalize | discard | create_and_finalize",
                },
                "blob_id": {
                    "type": "string",
                    "description": "Required for append, finalize, discard.",
                },
                "chunk": {
                    "type": "string",
                    "description": (
                        "UTF-8 fragment for append (up to ~1 MB). Preferred over "
                        "`chunk_base64` for HTML when JSON escaping is manageable."
                    ),
                },
                "chunk_base64": {
                    "type": "string",
                    "description": (
                        "Standard base64 (RFC 4648) of UTF-8 bytes; no `data:` prefix. "
                        "Max ~1.4M characters of base64 per call. Use only when plain "
                        "`chunk` would break JSON (unescaped quotes in markup)."
                    ),
                },
            },
            "required": ["action"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        action = (params or {}).get("action")
        return f"Blob {action}" if action else "Blob staging"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        action = str(params.get("action") or "").strip().lower()
        sid = _session_key(context)
        if action == "create":
            blob_id = await ToolArgumentBlobStore.create(sid)
            return {"ok": True, "blob_id": blob_id}

        if action == "create_and_finalize":
            return await self._create_and_finalize(params, sid)

        blob_id_raw = params.get("blob_id")
        if not isinstance(blob_id_raw, str) or not blob_id_raw.strip():
            return {"ok": False, "error": "`blob_id` is required for this action."}
        blob_id = blob_id_raw.strip()
        if action == "append":
            if params.get("_chunk_ingested"):
                return {
                    "ok": True,
                    "total_bytes": int(params.get("_ingested_bytes") or 0),
                    "note": "chunk was streamed directly into blob store",
                }
            err, text = _resolve_append_chunk(params)
            if err:
                return {"ok": False, "error": err}
            return await ToolArgumentBlobStore.append(sid, blob_id, text)
        if action == "finalize":
            return await ToolArgumentBlobStore.finalize(sid, blob_id)
        if action == "discard":
            return await ToolArgumentBlobStore.discard(sid, blob_id)
        return {"ok": False, "error": f"Unknown action {action!r}."}

    @staticmethod
    async def _create_and_finalize(
        params: dict[str, Any], sid: str,
    ) -> dict[str, Any]:
        """Create, append, and finalize a blob in a single call."""
        if params.get("_chunk_ingested"):
            blob_id_raw = params.get("blob_id")
            blob_id = str(blob_id_raw).strip() if isinstance(blob_id_raw, str) else ""
            return {
                "ok": True,
                "blob_id": blob_id,
                "total_bytes": int(params.get("_ingested_bytes") or 0),
                "note": "chunk was streamed directly into blob store",
            }
        err, text = _resolve_append_chunk(params)
        if err:
            return {"ok": False, "error": err}
        blob_id = await ToolArgumentBlobStore.create(sid)
        append_result = await ToolArgumentBlobStore.append(sid, blob_id, text)
        if not append_result.get("ok"):
            await ToolArgumentBlobStore.discard(sid, blob_id)
            return append_result
        fin_result = await ToolArgumentBlobStore.finalize(sid, blob_id)
        if not fin_result.get("ok"):
            return fin_result
        return {
            "ok": True,
            "blob_id": blob_id,
            "total_bytes": fin_result.get("total_bytes", 0),
        }


async def resolve_blob_text(
    context: ToolContext,
    blob_id: str,
    *,
    allow_empty: bool = False,
) -> str:
    """Load and consume a finalized blob; raises ValueError on failure.

    When ``allow_empty`` is True, an empty or whitespace-only blob is accepted
    (used for ``project_edit`` ``new_string_blob_id`` when deleting matched text).
    """
    sid = _session_key(context)
    bid = str(blob_id or "").strip()
    if not bid:
        raise ValueError("Empty blob_id.")
    text = await ToolArgumentBlobStore.take_utf8_text(sid, bid)
    if text is None:
        alt_sid = await ToolArgumentBlobStore.find_any_session_for_blob(bid)
        if alt_sid and alt_sid != sid:
            text = await ToolArgumentBlobStore.take_utf8_text(alt_sid, bid)
            if text is not None:
                logger.info(
                    "tool_argument_blob_consumed_cross_session",
                    blob_id=bid,
                    requested_session=sid,
                    resolved_session=alt_sid,
                )
        if text is None and sid != "__streaming_ingest__":
            text = await ToolArgumentBlobStore.take_utf8_text("__streaming_ingest__", bid)
            if text is not None:
                logger.info(
                    "tool_argument_blob_consumed_legacy_ingest",
                    blob_id=bid,
                    requested_session=sid,
                )
    if text is None:
        raise ValueError(
            f"Unknown, expired, or not-finalized blob_id {bid!r}. "
            "Call `tool_argument_blob` finalize before consuming."
        )
    if not allow_empty and not text.strip():
        raise ValueError("Blob is empty.")
    logger.info("tool_argument_blob_consumed", blob_id=bid, allow_empty=allow_empty)
    return text
