"""Playbook id normalization for runtime context attachment."""

from __future__ import annotations

from typing import Any

__all__ = [
    "coerce_playbook_ids",
    "playbook_ids_from_context",
    "playbook_ids_from_message_extensions",
]


def coerce_playbook_ids(value: Any) -> list[str]:
    """Normalize a single id, id list, or empty value to a deduped id list."""
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (list, tuple, set, frozenset)):
        out: list[str] = []
        for item in value:
            out.extend(coerce_playbook_ids(item))
        return out
    text = str(value).strip()
    return [text] if text else []


def playbook_ids_from_context(
    *,
    playbook_ids: list[str] | None = None,
    tool_extra: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[str]:
    """Collect playbook ids from explicit args, tool_extra, or workflow metadata."""
    ordered: list[str] = []
    seen: set[str] = set()

    def _add(raw: Any) -> None:
        for pid in coerce_playbook_ids(raw):
            if pid not in seen:
                seen.add(pid)
                ordered.append(pid)

    if playbook_ids:
        _add(playbook_ids)
    for mapping in (tool_extra, metadata):
        if not mapping:
            continue
        _add(mapping.get("playbook_ids"))
        _add(mapping.get("playbook_id"))
    return ordered


def playbook_ids_from_message_extensions(
    extensions: dict[str, Any] | None,
) -> list[str]:
    """Extract playbook ids stored on a chat message extensions blob."""
    if not extensions:
        return []
    return playbook_ids_from_context(metadata=extensions)
