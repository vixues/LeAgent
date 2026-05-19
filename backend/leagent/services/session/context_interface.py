"""Standardized context interface for session data access.

Provides a clean protocol that :class:`ContextManager` and other
context assembly components use to retrieve session state. Decouples
context building from the :class:`SessionManager` implementation details.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

if TYPE_CHECKING:
    from leagent.services.session.state import (
        SessionAttachment,
        SessionMessage,
        SessionState,
    )

logger = logging.getLogger(__name__)


class SessionContextProvider(Protocol):
    """Protocol for session data access used by context assembly."""

    async def get_messages(
        self,
        session_id: UUID,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list["SessionMessage"]:
        """Retrieve messages, most recent last."""
        ...

    async def get_summary(self, session_id: UUID) -> str | None:
        """Return the compacted history summary, if available."""
        ...

    async def get_attachments(self, session_id: UUID) -> list["SessionAttachment"]:
        """Return all file attachments for the session."""
        ...

    async def get_file_ref_ids(self, session_id: UUID) -> list[str]:
        """Return file reference IDs managed by the file manager."""
        ...

    async def get_metadata(self, session_id: UUID) -> dict[str, Any]:
        """Return session metadata (pins, authorized roots, etc.)."""
        ...

    async def get_state(self, session_id: UUID) -> "SessionState | None":
        """Return the full session state (for backward compat)."""
        ...


class DefaultSessionContextProvider:
    """Default implementation backed by :class:`SessionManager`.

    Provides the :class:`SessionContextProvider` contract using the
    existing session infrastructure. Future implementations can swap
    in optimized backends (e.g. direct DB queries, cached snapshots).
    """

    def __init__(self, session_manager: Any) -> None:
        self._sm = session_manager

    async def get_messages(
        self,
        session_id: UUID,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list["SessionMessage"]:
        state = await self._sm.load(session_id)
        if state is None:
            return []
        messages = list(state.messages)
        if offset:
            messages = messages[offset:]
        if limit is not None:
            messages = messages[:limit]
        return messages

    async def get_summary(self, session_id: UUID) -> str | None:
        state = await self._sm.load(session_id)
        if state is None:
            return None
        for msg in state.messages:
            if msg.role == "system" and "[Summary of earlier conversation]" in (msg.content or ""):
                return msg.content
        return None

    async def get_attachments(self, session_id: UUID) -> list["SessionAttachment"]:
        state = await self._sm.load(session_id)
        if state is None:
            return []
        return list(state.attachments)

    async def get_file_ref_ids(self, session_id: UUID) -> list[str]:
        state = await self._sm.load(session_id)
        if state is None:
            return []
        ids: list[str] = []
        for att in state.attachments:
            ids.append(str(att.id))
        return ids

    async def get_metadata(self, session_id: UUID) -> dict[str, Any]:
        state = await self._sm.load(session_id)
        if state is None:
            return {}
        return dict(state.metadata)

    async def get_state(self, session_id: UUID) -> "SessionState | None":
        return await self._sm.load(session_id)


class CachedSessionContextProvider:
    """Caching decorator over any :class:`SessionContextProvider`.

    Caches frequently accessed session data (messages, attachments)
    in-memory for the duration of a single turn to avoid redundant
    store lookups when multiple context sources query the same session.
    """

    def __init__(self, inner: SessionContextProvider) -> None:
        self._inner = inner
        self._state_cache: dict[UUID, Any] = {}

    async def _load_state(self, session_id: UUID) -> Any:
        if session_id not in self._state_cache:
            self._state_cache[session_id] = await self._inner.get_state(session_id)
        return self._state_cache[session_id]

    async def get_messages(
        self,
        session_id: UUID,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> list["SessionMessage"]:
        state = await self._load_state(session_id)
        if state is None:
            return []
        messages = list(state.messages)
        if offset:
            messages = messages[offset:]
        if limit is not None:
            messages = messages[:limit]
        return messages

    async def get_summary(self, session_id: UUID) -> str | None:
        state = await self._load_state(session_id)
        if state is None:
            return None
        for msg in state.messages:
            if msg.role == "system" and "[Summary of earlier conversation]" in (msg.content or ""):
                return msg.content
        return None

    async def get_attachments(self, session_id: UUID) -> list["SessionAttachment"]:
        state = await self._load_state(session_id)
        if state is None:
            return []
        return list(state.attachments)

    async def get_file_ref_ids(self, session_id: UUID) -> list[str]:
        state = await self._load_state(session_id)
        if state is None:
            return []
        return [str(att.id) for att in state.attachments]

    async def get_metadata(self, session_id: UUID) -> dict[str, Any]:
        state = await self._load_state(session_id)
        if state is None:
            return {}
        return dict(state.metadata)

    async def get_state(self, session_id: UUID) -> "SessionState | None":
        return await self._load_state(session_id)

    def invalidate(self, session_id: UUID | None = None) -> None:
        """Clear cached state for a session or all sessions."""
        if session_id is not None:
            self._state_cache.pop(session_id, None)
        else:
            self._state_cache.clear()
