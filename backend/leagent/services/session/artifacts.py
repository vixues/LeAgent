"""Shared registration of tool-produced files as session artifacts.

The agent runtime sees filesystem paths from several places: ordinary tools,
code-execution workspaces, nested subagents, and older ``ArtifactRef`` shaped
payloads. This module is the single place that turns those internal paths into
managed session attachments with UUID preview/download URLs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import unquote, urlparse
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


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
        return resolved == root or resolved.is_relative_to(root)
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
                add_from_mapping(item, source=f"{key}[{idx}]")

    add_from_mapping(meta, source="metadata")
    return candidates


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
    ) -> list[RegisteredArtifact]:
        if self._session_manager is None:
            return []

        registered: list[RegisteredArtifact] = []
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
    "strip_inline_base64_payloads",
]
