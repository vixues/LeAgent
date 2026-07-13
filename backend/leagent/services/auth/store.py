"""Durable security store for instance access password and local auth state.

Persists under ``$LEAGENT_HOME/security.json`` (mode 0600). This is the
single source of truth for the compulsory access-password gate (Phase 1)
and whether first-run setup has completed.
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from leagent.config.constants import LEAGENT_HOME
from leagent.utils.crypto import hash_password, verify_password

_LOCK = threading.RLock()
_DEFAULT_FILENAME = "security.json"


@dataclass
class SecurityStoreData:
    """On-disk security control-plane state."""

    setup_complete: bool = False
    access_password_hash: str = ""
    require_unlock_on_desktop: bool = False
    #: Optional revocation list of JWT ``jti`` values (short-lived; best-effort).
    revoked_jtis: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> SecurityStoreData:
        if not raw:
            return cls()
        return cls(
            setup_complete=bool(raw.get("setup_complete", False)),
            access_password_hash=str(raw.get("access_password_hash") or ""),
            require_unlock_on_desktop=bool(raw.get("require_unlock_on_desktop", False)),
            revoked_jtis=list(raw.get("revoked_jtis") or []),
        )


def security_store_path(home: Path | None = None) -> Path:
    root = home or LEAGENT_HOME
    return Path(root) / _DEFAULT_FILENAME


class SecurityStore:
    """Thread-safe read/write helper for ``security.json``."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or security_store_path()

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> SecurityStoreData:
        with _LOCK:
            if not self._path.is_file():
                return SecurityStoreData()
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return SecurityStoreData()
            if not isinstance(raw, dict):
                return SecurityStoreData()
            return SecurityStoreData.from_dict(raw)

    def save(self, data: SecurityStoreData) -> None:
        with _LOCK:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(data.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            tmp.replace(self._path)
            try:
                self._path.chmod(0o600)
            except OSError:
                pass

    def is_setup_complete(self) -> bool:
        data = self.load()
        return bool(data.setup_complete and data.access_password_hash)

    def set_access_password(self, password: str, *, require_unlock_on_desktop: bool = False) -> None:
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters")
        data = self.load()
        data.access_password_hash = hash_password(password)
        data.setup_complete = True
        data.require_unlock_on_desktop = require_unlock_on_desktop
        self.save(data)

    def verify_access_password(self, password: str) -> bool:
        data = self.load()
        if not data.access_password_hash:
            return False
        return verify_password(password, data.access_password_hash)

    def change_access_password(self, current: str, new_password: str) -> None:
        if not self.verify_access_password(current):
            raise PermissionError("Current password is incorrect")
        self.set_access_password(
            new_password,
            require_unlock_on_desktop=self.load().require_unlock_on_desktop,
        )

    def revoke_jti(self, jti: str, *, max_keep: int = 256) -> None:
        if not jti:
            return
        data = self.load()
        if jti not in data.revoked_jtis:
            data.revoked_jtis.append(jti)
            if len(data.revoked_jtis) > max_keep:
                data.revoked_jtis = data.revoked_jtis[-max_keep:]
            self.save(data)

    def is_jti_revoked(self, jti: str) -> bool:
        if not jti:
            return False
        return jti in self.load().revoked_jtis


_store: SecurityStore | None = None


def get_security_store() -> SecurityStore:
    global _store
    if _store is None:
        _store = SecurityStore()
    return _store


def reset_security_store_for_tests(path: Path | None = None) -> SecurityStore:
    """Replace the process-wide store (tests only)."""
    global _store
    _store = SecurityStore(path=path) if path is not None else SecurityStore()
    return _store
