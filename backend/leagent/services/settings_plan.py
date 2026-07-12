"""Short-lived inspect plans for configure_settings (confirm-then-apply)."""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

_DEFAULT_TTL_SEC = 600.0


@dataclass
class SettingsPlan:
    plan_id: str
    session_id: str
    changes: list[dict[str, Any]]
    changes_hash: str
    created_at: float = field(default_factory=time.monotonic)
    ttl_sec: float = _DEFAULT_TTL_SEC

    def expired(self) -> bool:
        return (time.monotonic() - self.created_at) > self.ttl_sec


def hash_changes(changes: list[dict[str, Any]]) -> str:
    payload = json.dumps(changes, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SettingsPlanRegistry:
    """In-process plan store keyed by plan_id (single-worker / desktop)."""

    def __init__(self) -> None:
        self._plans: dict[str, SettingsPlan] = {}

    def create(
        self,
        *,
        session_id: str,
        changes: list[dict[str, Any]],
        ttl_sec: float = _DEFAULT_TTL_SEC,
    ) -> SettingsPlan:
        self._purge_expired()
        plan_id = str(uuid.uuid4())
        plan = SettingsPlan(
            plan_id=plan_id,
            session_id=session_id or "",
            changes=list(changes),
            changes_hash=hash_changes(changes),
            ttl_sec=ttl_sec,
        )
        self._plans[plan_id] = plan
        return plan

    def get(self, plan_id: str) -> SettingsPlan | None:
        self._purge_expired()
        plan = self._plans.get(plan_id)
        if plan is None:
            return None
        if plan.expired():
            self._plans.pop(plan_id, None)
            return None
        return plan

    def consume(self, plan_id: str) -> SettingsPlan | None:
        plan = self.get(plan_id)
        if plan is None:
            return None
        self._plans.pop(plan_id, None)
        return plan

    def clear(self) -> None:
        self._plans.clear()

    def _purge_expired(self) -> None:
        dead = [pid for pid, p in self._plans.items() if p.expired()]
        for pid in dead:
            self._plans.pop(pid, None)


_registry: SettingsPlanRegistry | None = None


def get_settings_plan_registry() -> SettingsPlanRegistry:
    global _registry
    if _registry is None:
        _registry = SettingsPlanRegistry()
    return _registry


def reset_settings_plan_registry() -> None:
    global _registry
    if _registry is not None:
        _registry.clear()
    _registry = None
