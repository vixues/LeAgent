"""``CapabilityRegistry`` — the single source of truth for backend profiles.

Every model/backend (chat model, domain adapter, generation backend) is
lifted into a :class:`CapabilityProfile` and registered here alongside an
optional *invoker* (the underlying object used to actually run it). Routers
and node-schema builders query this registry instead of maintaining their
own hardcoded provider lists.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from leagent.utils.logging import get_logger

from .profile import CapabilityContract, CapabilityProfile, Modality, TaskType

logger = get_logger(__name__)


@dataclass
class RegisteredCapability:
    """A profile plus its (optional) invoker handle."""

    profile: CapabilityProfile
    invoker: Any | None = None


class CapabilityRegistry:
    """Process-wide (or scoped) registry of capability profiles."""

    def __init__(self) -> None:
        self._entries: dict[str, RegisteredCapability] = {}

    # -- registration ---------------------------------------------------

    def register(
        self,
        profile: CapabilityProfile,
        invoker: Any | None = None,
        *,
        replace: bool = True,
    ) -> None:
        if profile.id in self._entries and not replace:
            raise ValueError(f"Capability '{profile.id}' is already registered")
        self._entries[profile.id] = RegisteredCapability(profile=profile, invoker=invoker)
        logger.debug("capability_registered", id=profile.id, backend_class=profile.backend_class.value)

    def unregister(self, profile_id: str) -> None:
        self._entries.pop(profile_id, None)

    # -- lookup ---------------------------------------------------------

    def get(self, profile_id: str) -> CapabilityProfile | None:
        entry = self._entries.get(profile_id)
        return entry.profile if entry else None

    def get_invoker(self, profile_id: str) -> Any | None:
        entry = self._entries.get(profile_id)
        return entry.invoker if entry else None

    def all(self) -> list[CapabilityProfile]:
        return [e.profile for e in self._entries.values()]

    def providers(self) -> list[str]:
        seen: list[str] = []
        for e in self._entries.values():
            if e.profile.provider not in seen:
                seen.append(e.profile.provider)
        return seen

    def query(
        self,
        *,
        task: TaskType | str | None = None,
        contract: CapabilityContract | None = None,
        input: Modality | str | None = None,  # noqa: A002 - mirrors capability vocab
        output: Modality | str | None = None,
        provider: str | None = None,
        backend_class: Any | None = None,
        available_only: bool = False,
    ) -> list[CapabilityProfile]:
        """Return profiles matching the given filters, in registration order."""
        results: list[CapabilityProfile] = []
        for entry in self._entries.values():
            p = entry.profile
            if contract is not None and not contract.matches(p):
                continue
            if task is not None and not p.supports_task(task):
                continue
            if input is not None and not p.supports_input(input):
                continue
            if output is not None and not p.supports_output(output):
                continue
            if provider is not None and p.provider != provider:
                continue
            if backend_class is not None and p.backend_class != backend_class:
                continue
            if available_only and not p.available():
                continue
            results.append(p)
        return results

    def clear(self) -> None:
        self._entries.clear()


_REGISTRY: CapabilityRegistry | None = None


def get_capability_registry() -> CapabilityRegistry:
    """Return the process-wide capability registry (lazily created)."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = CapabilityRegistry()
    return _REGISTRY


def reset_capability_registry() -> None:
    """Reset the process-wide registry (test helper)."""
    global _REGISTRY
    _REGISTRY = None


__all__ = [
    "CapabilityRegistry",
    "RegisteredCapability",
    "get_capability_registry",
    "reset_capability_registry",
]
