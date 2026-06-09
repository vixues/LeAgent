"""Shared registration of tool-produced files as session artifacts.

The agent runtime sees filesystem paths from several places: ordinary tools,
code-execution workspaces, nested subagents, and older ``ArtifactRef`` shaped
payloads. This module is the single place that turns those internal paths into
managed session attachments with UUID preview/download URLs.
"""

from __future__ import annotations

import json
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse
from uuid import UUID

import structlog

from leagent.file.primitives import is_path_inside as _is_path_inside_multi

logger = structlog.get_logger(__name__)

_PREVIEWABLE_MIME_PREFIXES = ("image/", "application/pdf", "text/html")
_PREVIEWABLE_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".pdf", ".html", ".htm",
})


_SINGLE_PATH_KEYS = (
    "file_path",
    "path",
    "output_path",
    "saved_path",
    "saved_to",
    "destination",
    "output_file",
    "target_path",
    "download_path",
)


@dataclass(frozen=True, slots=True)
class ProducedPathCandidate:
    """A concrete file path emitted by a tool result."""

    path: str
    display_name: str | None = None
    allowed_root: str | None = None
    source: str = "tool_result"
    content_type_hint: str | None = None


@dataclass(frozen=True, slots=True)
class RegisteredArtifact:
    """A managed artifact registered on a chat session."""

    path: str
    attachment: dict[str, Any]


def coerce_tool_result_data(raw: Any) -> dict[str, Any]:
    """Normalise loose tool-result data to a mapping for artifact extraction."""

    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        return {"_wa_produced_list": raw}
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        if text[0] in "{[":
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                return {}
            if isinstance(parsed, dict):
                return parsed
            if isinstance(parsed, list):
                return {"_wa_produced_list": parsed}
    return {}


def strip_inline_base64_payloads(value: Any) -> Any:
    """Return ``value`` without inline base64 blobs.

    Generated media should travel as managed file references, not as giant JSON
    strings in tool results, prompt history, or frontend event payloads.
    """

    if isinstance(value, dict):
        return {
            str(k): strip_inline_base64_payloads(v)
            for k, v in value.items()
            if str(k).lower() not in {"base64", "content_base64", "b64_json"}
        }
    if isinstance(value, list):
        return [strip_inline_base64_payloads(item) for item in value]
    return value


def _file_uri_to_path(raw: str) -> str | None:
    parsed = urlparse(raw)
    path_part = unquote(parsed.path) if parsed.path else ""
    return path_part or None


def _resolve_workspace_root(raw: str | None) -> Path | None:
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve()
    except OSError:
        return None


def _path_is_inside(path: Path, root: Path) -> bool:
    try:
        resolved = path.expanduser().resolve()
        return _is_path_inside_multi(resolved, (root,))
    except OSError:
        return False


def extract_produced_path_candidates(
    data: Any,
    *,
    metadata: dict[str, Any] | None = None,
) -> list[ProducedPathCandidate]:
    """Collect file paths from a tool result without registering anything."""

    mapping = coerce_tool_result_data(data)
    meta = metadata or {}
    workspace = mapping.get("workspace") if isinstance(mapping.get("workspace"), str) else None
    workspace_root = _resolve_workspace_root(workspace)
    candidates: list[ProducedPathCandidate] = []

    def add(
        raw: Any,
        display_name: str | None = None,
        *,
        source: str = "tool_result",
        content_type_hint: str | None = None,
    ) -> None:
        if not isinstance(raw, str) or not raw.strip():
            return
        value = raw.strip()
        if value.startswith("file://"):
            converted = _file_uri_to_path(value)
            if not converted:
                return
            value = converted

        path = Path(value).expanduser()
        allowed_root: str | None = None
        try:
            probe: Path | None
            if path.is_absolute():
                probe = path.resolve()
            elif workspace_root is not None:
                probe = (workspace_root / path).resolve()
            else:
                probe = None
            if probe is not None and probe.is_dir():
                return
        except OSError:
            probe = None

        if path.is_absolute():
            if workspace_root is not None and _path_is_inside(path, workspace_root):
                allowed_root = str(workspace_root)
            candidates.append(
                ProducedPathCandidate(
                    path=value,
                    display_name=display_name or path.name,
                    allowed_root=allowed_root,
                    source=source,
                    content_type_hint=content_type_hint,
                ),
            )
            return

        if workspace_root is not None:
            resolved = (workspace_root / path).resolve()
            candidates.append(
                ProducedPathCandidate(
                    path=str(resolved),
                    display_name=display_name or path.name,
                    allowed_root=str(workspace_root),
                    source=source,
                    content_type_hint=content_type_hint,
                ),
            )

    def add_from_mapping(item: dict[str, Any], *, source: str) -> None:
        hint = item.get("mime") or item.get("content_type") or item.get("contentType")
        content_type_hint = hint if isinstance(hint, str) else None
        label = item.get("name") or item.get("filename")
        display_name = label if isinstance(label, str) else None
        for key in _SINGLE_PATH_KEYS:
            add(
                item.get(key),
                display_name=display_name,
                source=f"{source}.{key}",
                content_type_hint=content_type_hint,
            )
        result_data = item.get("result")
        if isinstance(result_data, dict):
            add_from_mapping(result_data, source=f"{source}.result")
        artifact = item.get("artifact")
        if isinstance(artifact, dict):
            uri = artifact.get("uri") or artifact.get("path")
            art_name = artifact.get("name") if isinstance(artifact.get("name"), str) else display_name
            add(uri, display_name=art_name, source=f"{source}.artifact")

    add_from_mapping(mapping, source="data")

    top_list = mapping.get("_wa_produced_list")
    if isinstance(top_list, list):
        for idx, item in enumerate(top_list):
            if isinstance(item, str):
                add(item, source=f"list[{idx}]")
            elif isinstance(item, dict):
                add_from_mapping(item, source=f"list[{idx}]")

    for key in ("produced_files", "files", "artifacts", "images"):
        value = mapping.get(key)
        if not isinstance(value, list):
            continue
        for idx, item in enumerate(value):
            if isinstance(item, str):
                add(item, source=f"{key}[{idx}]")
            elif isinstance(item, dict):
                if item.get("file_id") or item.get("attachment_id"):
                    continue
                add_from_mapping(item, source=f"{key}[{idx}]")

    add_from_mapping(meta, source="metadata")
    return candidates


def is_previewable_produced_file(path: Path, *, mime: str | None = None) -> bool:
    """Return whether a produced file should be exposed in the chat file workspace."""
    guessed = mime or mimetypes.guess_type(path.name)[0] or ""
    if guessed.startswith(_PREVIEWABLE_MIME_PREFIXES):
        return True
    return path.suffix.lower() in _PREVIEWABLE_EXTENSIONS


def _resolve_produced_entry_path(raw_path: str, workspace_root: Path | None) -> Path | None:
    path = Path(raw_path).expanduser()
    try:
        if path.is_absolute():
            resolved = path.resolve()
        elif workspace_root is not None:
            resolved = (workspace_root / path).resolve()
        else:
            return None
    except OSError:
        return None
    return resolved if resolved.is_file() else None


def _session_uploads_dir(session_id: str) -> Path | None:
    try:
        from leagent.services.session.paths import get_session_path_registry

        return get_session_path_registry().uploads_dir(UUID(str(session_id)))
    except (ValueError, TypeError, ImportError):
        return None


def _path_under_uploads(path: Path, uploads: Path) -> bool:
    try:
        return path.resolve().is_relative_to(uploads.resolve())
    except (OSError, ValueError):
        return False


def _code_execution_allowed_roots(workspace_root: Path | None) -> tuple[str, ...]:
    roots: list[str] = []
    if workspace_root is not None:
        roots.append(str(workspace_root))
    try:
        from leagent.file.sandbox import _system_temp_roots

        roots.extend(str(root) for root in _system_temp_roots())
    except ImportError:
        pass
    return tuple(roots)


async def ingest_previewable_produced_files(
    context: Any,
    produced_files: list[dict[str, Any]],
    *,
    workspace: str | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Copy previewable ``code_execution`` outputs into session uploads.

    Returns updated ``produced_files`` entries (paths rewritten to managed
    storage when registration succeeds) and UI-ready ``managed_artifacts``.
    """
    session_id = getattr(context, "session_id", None)
    if not session_id or not produced_files:
        return produced_files, []

    try:
        session_uuid = UUID(str(session_id))
    except (ValueError, TypeError):
        return produced_files, []

    user_uuid: UUID | None = None
    user_id = getattr(context, "user_id", None)
    if user_id:
        try:
            user_uuid = UUID(str(user_id))
        except (ValueError, TypeError):
            user_uuid = None

    session_manager: Any | None = None
    try:
        from leagent.main import get_service_manager

        sm = get_service_manager()
        session_manager = getattr(sm, "session_manager", None) if sm else None
    except (RuntimeError, AssertionError):
        session_manager = None

    if session_manager is None:
        return produced_files, []

    workspace_root = _resolve_workspace_root(workspace)
    uploads = _session_uploads_dir(str(session_id))
    allowed_roots = _code_execution_allowed_roots(workspace_root)
    updated: list[dict[str, Any]] = []
    managed: list[dict[str, Any]] = []

    for raw_entry in produced_files:
        if not isinstance(raw_entry, dict):
            continue
        if raw_entry.get("file_id") or raw_entry.get("attachment_id"):
            updated.append(dict(raw_entry))
            continue

        raw_path = str(raw_entry.get("path") or raw_entry.get("file_path") or "").strip()
        if not raw_path:
            updated.append(dict(raw_entry))
            continue

        resolved = _resolve_produced_entry_path(raw_path, workspace_root)
        if resolved is None:
            updated.append(dict(raw_entry))
            continue

        mime = raw_entry.get("mime") if isinstance(raw_entry.get("mime"), str) else None
        if not is_previewable_produced_file(resolved, mime=mime):
            updated.append(dict(raw_entry))
            continue

        if uploads is not None and _path_under_uploads(resolved, uploads):
            entry = dict(raw_entry)
            entry["path"] = str(resolved)
            updated.append(entry)
            continue

        reg = await session_manager.register_external_file(
            session_uuid,
            user_uuid,
            str(resolved),
            display_name=raw_entry.get("name") or resolved.name,
            allowed_roots=allowed_roots or None,
        )
        if reg is None:
            logger.info(
                "code_execution_produced_register_skipped",
                extra={"session_id": str(session_id), "source_path": str(resolved)},
            )
            updated.append(dict(raw_entry))
            continue

        storage = Path(str(reg.get("storage_path") or "")).expanduser()
        entry = dict(raw_entry)
        entry["path"] = str(storage) if storage.is_file() else str(resolved)
        entry["source_path"] = str(resolved)
        entry["file_id"] = str(reg.get("id") or "")
        if reg.get("preview_url"):
            entry["preview_url"] = reg["preview_url"]
        if reg.get("download_url"):
            entry["download_url"] = reg["download_url"]
        entry["managed"] = True
        updated.append(entry)
        managed.append(dict(reg))
        logger.info(
            "code_execution_produced_registered",
            extra={
                "session_id": str(session_id),
                "source_path": str(resolved),
                "storage_path": entry["path"],
                "file_id": entry.get("file_id"),
            },
        )

    return updated, managed


class ArtifactRegistrar:
    """Register tool-produced paths through ``SessionManager``."""

    def __init__(self, session_manager: Any | None) -> None:
        self._session_manager = session_manager

    async def register_tool_result(
        self,
        *,
        session_id: UUID,
        user_id: UUID | None,
        data: Any,
        metadata: dict[str, Any] | None = None,
        seen_paths: set[str] | None = None,
        produced_files: list[Any] | None = None,
    ) -> list[RegisteredArtifact]:
        if self._session_manager is None:
            return []

        registered: list[RegisteredArtifact] = []

        if produced_files:
            for ref in produced_files:
                storage_path = (
                    ref.metadata.get("storage_path", ref.storage_key)
                    if hasattr(ref, "metadata")
                    else str(ref)
                )
                try:
                    key = str(Path(storage_path).expanduser().resolve())
                except OSError:
                    continue
                if seen_paths is not None and key in seen_paths:
                    continue
                att_dict = {
                    "id": str(ref.id) if hasattr(ref, "id") else str(ref),
                    "filename": getattr(ref, "filename", Path(storage_path).name),
                    "name": getattr(ref, "filename", Path(storage_path).name),
                    "kind": getattr(ref, "category", "other"),
                    "content_type": getattr(ref, "content_type", "application/octet-stream"),
                    "size": getattr(ref, "size", 0),
                    "sha256": getattr(ref, "checksum", ""),
                }
                if seen_paths is not None:
                    seen_paths.add(key)
                registered.append(RegisteredArtifact(path=key, attachment=att_dict))
            if registered:
                return registered

        for candidate in extract_produced_path_candidates(data, metadata=metadata):
            try:
                key = str(Path(candidate.path).expanduser().resolve())
            except OSError:
                continue
            if seen_paths is not None and key in seen_paths:
                continue
            out = await self._session_manager.register_external_file(
                session_id,
                user_id,
                candidate.path,
                display_name=candidate.display_name or Path(candidate.path).name,
                allowed_roots=(candidate.allowed_root,) if candidate.allowed_root else None,
            )
            if out is None:
                continue
            if seen_paths is not None:
                seen_paths.add(key)
            registered.append(RegisteredArtifact(path=key, attachment=out))
        return registered


def attachment_dicts(items: Iterable[RegisteredArtifact]) -> list[dict[str, Any]]:
    """Return UI-safe attachment payloads from registered artifacts."""

    return [dict(item.attachment) for item in items]


__all__ = [
    "ArtifactRegistrar",
    "ProducedPathCandidate",
    "RegisteredArtifact",
    "attachment_dicts",
    "coerce_tool_result_data",
    "extract_produced_path_candidates",
    "ingest_previewable_produced_files",
    "is_previewable_produced_file",
    "strip_inline_base64_payloads",
]
