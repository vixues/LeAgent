"""Session-centric services for LeAgent.

The :mod:`leagent.services.session` package owns every piece of state that
is attached to a single chat session:

* :class:`SessionState` — the authoritative, serialisable snapshot of a
  conversation (messages, attachments, file-state cache, token usage, and the
  system-prompt fingerprint).
* :class:`SessionAttachment` — structured description of a user-uploaded
  file that the agent may read via tools.
* :class:`TieredSessionStore` — 3-layer persistence (in-process LRU → Redis
  → relational database, SQLite by default) that keeps sessions warm while
  always having a durable copy.
* :class:`SessionManager` — the public service exposed via ``ServiceManager``
  that API handlers and the agent runtime use to read/write session state.
"""

from leagent.services.session.manager import SessionManager
from leagent.services.session.artifacts import (
    ArtifactRegistrar,
    ProducedPathCandidate,
    RegisteredArtifact,
)
from leagent.services.session.paths import SessionPathRegistry, get_session_path_registry
from leagent.services.session.state import (
    ATTACHMENT_KIND_DOCUMENT,
    ATTACHMENT_KIND_IMAGE,
    ATTACHMENT_KIND_OTHER,
    ATTACHMENT_KIND_TEXT,
    SessionAttachment,
    SessionMessage,
    SessionState,
    SessionUsage,
)
from leagent.services.session.store import TieredSessionStore
from leagent.services.session.context_interface import (
    CachedSessionContextProvider,
    DefaultSessionContextProvider,
    SessionContextProvider,
)

__all__ = [
    "ATTACHMENT_KIND_DOCUMENT",
    "ATTACHMENT_KIND_IMAGE",
    "ATTACHMENT_KIND_OTHER",
    "ATTACHMENT_KIND_TEXT",
    "ArtifactRegistrar",
    "ProducedPathCandidate",
    "RegisteredArtifact",
    "CachedSessionContextProvider",
    "DefaultSessionContextProvider",
    "SessionAttachment",
    "SessionPathRegistry",
    "SessionContextProvider",
    "SessionManager",
    "SessionMessage",
    "SessionState",
    "SessionUsage",
    "TieredSessionStore",
    "get_session_path_registry",
]
