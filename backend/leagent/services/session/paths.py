"""Canonical filesystem paths for session-scoped runtime data."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from leagent.config.settings import Settings, get_settings


@dataclass(frozen=True, slots=True)
class SessionPathRegistry:
    """Resolve managed roots used by chat, tools, and code execution."""

    settings: Settings

    @property
    def upload_root(self) -> Path:
        return Path(self.settings.files.upload_dir).expanduser().resolve()

    def uploads_dir(self, session_id: UUID | str) -> Path:
        return self.upload_root / str(session_id)

    def ensure_uploads_dir(self, session_id: UUID | str) -> Path:
        path = self.uploads_dir(session_id)
        path.mkdir(parents=True, exist_ok=True)
        return path


def get_session_path_registry(settings: Settings | None = None) -> SessionPathRegistry:
    return SessionPathRegistry(settings or get_settings())


__all__ = ["SessionPathRegistry", "get_session_path_registry"]
