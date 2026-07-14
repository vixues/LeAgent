"""Disk-backed credential and context_token storage for Weixin iLink."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from leagent.config.constants import LEAGENT_HOME

WEIXIN_HOME = LEAGENT_HOME / "weixin"
ACCOUNTS_DIR = WEIXIN_HOME / "accounts"


def _atomic_json_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp_name, path)
        try:
            path.chmod(0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def account_file(account_id: str) -> Path:
    return ACCOUNTS_DIR / f"{account_id}.json"


def sync_buf_file(account_id: str) -> Path:
    return ACCOUNTS_DIR / f"{account_id}.sync-buf.json"


def save_account(
    *,
    account_id: str,
    token: str,
    base_url: str,
    user_id: str = "",
) -> Path:
    """Persist account credentials under ``LEAGENT_HOME/weixin/accounts/``."""
    payload = {
        "account_id": account_id,
        "token": token,
        "base_url": base_url,
        "user_id": user_id,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = account_file(account_id)
    _atomic_json_write(path, payload)
    return path


def load_account(account_id: str) -> dict[str, Any] | None:
    """Load persisted account credentials."""
    path = account_file(account_id)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def load_sync_buf(account_id: str) -> str:
    path = sync_buf_file(account_id)
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return str(data.get("get_updates_buf") or "")
    except Exception:
        return ""


def save_sync_buf(account_id: str, sync_buf: str) -> None:
    _atomic_json_write(sync_buf_file(account_id), {"get_updates_buf": sync_buf})


class ContextTokenStore:
    """Disk-backed ``context_token`` cache keyed by account + peer."""

    def __init__(self, root: Path | None = None) -> None:
        self._root = root or ACCOUNTS_DIR
        self._root.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, str] = {}

    def _path(self, account_id: str) -> Path:
        return self._root / f"{account_id}.context-tokens.json"

    @staticmethod
    def _key(account_id: str, user_id: str) -> str:
        return f"{account_id}:{user_id}"

    def restore(self, account_id: str) -> int:
        path = self._path(account_id)
        if not path.exists():
            return 0
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return 0
        restored = 0
        if not isinstance(data, dict):
            return 0
        for user_id, token in data.items():
            if isinstance(token, str) and token:
                self._cache[self._key(account_id, str(user_id))] = token
                restored += 1
        return restored

    def get(self, account_id: str, user_id: str) -> str | None:
        return self._cache.get(self._key(account_id, user_id))

    def set(self, account_id: str, user_id: str, token: str) -> None:
        if not token:
            return
        self._cache[self._key(account_id, user_id)] = token
        self._persist(account_id)

    def clear_account(self, account_id: str) -> None:
        prefix = f"{account_id}:"
        keys = [k for k in self._cache if k.startswith(prefix)]
        for key in keys:
            del self._cache[key]
        path = self._path(account_id)
        if path.exists():
            try:
                path.unlink()
            except OSError:
                pass

    def _persist(self, account_id: str) -> None:
        prefix = f"{account_id}:"
        payload = {
            key[len(prefix) :]: value
            for key, value in self._cache.items()
            if key.startswith(prefix)
        }
        _atomic_json_write(self._path(account_id), payload)


class TypingTicketCache:
    """Short-lived typing ticket cache from ``getconfig``."""

    def __init__(self, ttl_seconds: float = 600.0) -> None:
        self._ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[str, float]] = {}

    def get(self, user_id: str) -> str | None:
        entry = self._cache.get(user_id)
        if not entry:
            return None
        if time.time() - entry[1] >= self._ttl_seconds:
            self._cache.pop(user_id, None)
            return None
        return entry[0]

    def set(self, user_id: str, ticket: str) -> None:
        self._cache[user_id] = (ticket, time.time())


class MessageDeduplicator:
    """Sliding-window message ID deduplication."""

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self._ttl_seconds = ttl_seconds
        self._seen: dict[str, float] = {}

    def seen(self, message_id: str) -> bool:
        now = time.time()
        self._evict(now)
        if not message_id:
            return False
        if message_id in self._seen:
            return True
        self._seen[message_id] = now
        return False

    def _evict(self, now: float) -> None:
        expired = [k for k, ts in self._seen.items() if now - ts >= self._ttl_seconds]
        for key in expired:
            del self._seen[key]
