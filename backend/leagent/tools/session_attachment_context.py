"""Session attachment paths and lookup tables for ToolContext.extra.

Mirrors the logic previously embedded in AgentController so chat workflow
step runs, agents, and tests share one implementation.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)

_STORED_UUID_PREFIX = re.compile(
    r"^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})_(.+)$",
    re.IGNORECASE,
)


def normalize_attachment_paths(paths: list[str]) -> list[str]:
    """Normalize and de-duplicate attachment paths for tool context."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        if not isinstance(raw, str) or not raw.strip():
            continue
        if not Path(raw).is_absolute():
            logger.warning("attachment_path_not_absolute", value=raw)
            continue
        try:
            resolved = str(Path(raw).expanduser().resolve())
        except Exception:  # noqa: BLE001
            logger.warning("attachment_path_resolve_failed", value=raw)
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        normalized.append(resolved)
    return normalized


def attachment_aliases_from_path(storage_path: str) -> set[str]:
    aliases: set[str] = set()
    name = Path(storage_path).name
    if not name:
        return aliases
    aliases.add(name)
    stem = Path(name).stem
    if stem:
        aliases.add(stem)
    if "_" in name:
        suffix = name.split("_", 1)[1]
        if suffix:
            aliases.add(suffix)
            suffix_stem = Path(suffix).stem
            if suffix_stem:
                aliases.add(suffix_stem)
    return aliases


def attachment_aliases(attachment: Any) -> set[str]:
    aliases: set[str] = set()
    filename = str(getattr(attachment, "filename", "") or "").strip()
    if filename:
        aliases.add(filename)
        stem = Path(filename).stem
        if stem:
            aliases.add(stem)
    storage_path = str(getattr(attachment, "storage_path", "") or "").strip()
    if storage_path:
        aliases.update(attachment_aliases_from_path(storage_path))
    return aliases


def normalise_attachment_alias(value: str) -> str:
    compact: list[str] = []
    for ch in value.casefold():
        if ch.isalnum():
            compact.append(ch)
    return "".join(compact)


def build_attachment_lookup(
    *,
    session_attachments: list[Any],
    normalized_attachments: list[str],
) -> dict[str, dict[str, str]]:
    """Build attachment lookup tables keyed by id and normalized name."""
    by_id: dict[str, str] = {}
    by_name: dict[str, str] = {}

    for att in session_attachments:
        storage_path = getattr(att, "storage_path", "")
        if not isinstance(storage_path, str) or not storage_path:
            continue
        normalized_path = normalize_attachment_paths([storage_path])
        if not normalized_path:
            continue
        resolved_path = normalized_path[0]

        att_id = str(getattr(att, "id", "") or "").strip()
        if att_id:
            by_id.setdefault(att_id, resolved_path)

        for alias in attachment_aliases(att):
            key = normalise_attachment_alias(alias)
            if key:
                by_name.setdefault(key, resolved_path)

    for resolved_path in normalized_attachments:
        for alias in attachment_aliases_from_path(resolved_path):
            key = normalise_attachment_alias(alias)
            if key:
                by_name.setdefault(key, resolved_path)

    for resolved_path in normalized_attachments:
        base = Path(resolved_path).name
        m = _STORED_UUID_PREFIX.match(base)
        if m:
            by_id.setdefault(m.group(1).lower(), resolved_path)
            suffix = m.group(2)
            if suffix:
                synthetic = str(Path("/__wa_virtual__") / suffix)
                for alias in attachment_aliases_from_path(synthetic):
                    key = normalise_attachment_alias(alias)
                    if key:
                        by_name.setdefault(key, resolved_path)

    lookup: dict[str, dict[str, str]] = {}
    if by_id:
        lookup["by_id"] = by_id
    if by_name:
        lookup["by_name"] = by_name
    return lookup


def build_tool_extra_for_attachment_paths(
    session_attachments: list[Any],
    merged_paths: list[str],
) -> dict[str, Any]:
    """Return ``attachments`` / ``attachment_lookup`` entries for ToolContext.extra.

    *merged_paths* should be the deduplicated union of session storage paths
    and any extra paths (e.g. knowledge files merged for this turn).
    """
    normalized = normalize_attachment_paths(merged_paths)
    tool_extra: dict[str, Any] = {}
    if normalized:
        tool_extra["attachments"] = normalized
    lookup = build_attachment_lookup(
        session_attachments=session_attachments,
        normalized_attachments=normalized,
    )
    if lookup:
        tool_extra["attachment_lookup"] = lookup
    return tool_extra


async def tool_extra_for_chat_session(
    session_manager: Any,
    session_id: UUID,
    *,
    extra_paths: list[str] | None = None,
) -> dict[str, Any]:
    """Load session attachments and build tool ``extra`` for that chat session."""
    try:
        session_attachments = await session_manager.list_attachments(session_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("session_attachments_load_failed", error=str(exc))
        return {}

    session_paths = [
        att.storage_path for att in session_attachments if getattr(att, "storage_path", None)
    ]
    merged = list(session_paths)
    if extra_paths:
        for path in extra_paths:
            if path and path not in merged:
                merged.append(path)

    return build_tool_extra_for_attachment_paths(session_attachments, merged)
