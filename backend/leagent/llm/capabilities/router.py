"""``CapabilityRouter`` — capability-aware candidate selection.

Given a :class:`CapabilityContract` (task + required modalities), the router
ranks matching profiles by runtime suitability:

1. an explicitly *preferred provider* wins,
2. lower ``cost_tier`` first (local/free before paid),
3. registration order as a stable tiebreaker,
4. an always-available *offline* floor appended last (when present).

It is shared by the generation service (image/video/3D), the chat task
resolver (vision upgrade), and workflow node schema building.
"""

from __future__ import annotations

from .profile import BackendClass, CapabilityContract, CapabilityProfile
from .registry import CapabilityRegistry


class CapabilityRouter:
    """Rank registry profiles against a contract."""

    def __init__(self, registry: CapabilityRegistry) -> None:
        self.registry = registry

    def candidates(
        self,
        contract: CapabilityContract,
        *,
        preferred_provider: str | None = None,
        available_only: bool = True,
        offline_floor: bool = True,
    ) -> list[CapabilityProfile]:
        """Return ranked profiles satisfying *contract*.

        When ``preferred_provider`` is set, only that provider's matching
        profiles are returned (availability is *not* enforced — an explicit
        pin is honoured), followed by the offline floor.
        """
        matched = self.registry.query(contract=contract)
        offline = [p for p in matched if p.backend_class == BackendClass.OFFLINE]
        real = [p for p in matched if p.backend_class != BackendClass.OFFLINE]

        if preferred_provider:
            picked = [p for p in real if p.provider == preferred_provider]
            ranked = self._rank(picked)
        else:
            if available_only:
                real = [p for p in real if p.available()]
            ranked = self._rank(real)

        if offline_floor and offline:
            for p in offline:
                if p not in ranked:
                    ranked.append(p)
        return ranked

    def select(
        self,
        contract: CapabilityContract,
        *,
        preferred_provider: str | None = None,
        available_only: bool = True,
    ) -> CapabilityProfile | None:
        """Return the single best candidate (or None)."""
        cands = self.candidates(
            contract,
            preferred_provider=preferred_provider,
            available_only=available_only,
        )
        return cands[0] if cands else None

    def provider_options(
        self,
        contract: CapabilityContract,
        *,
        include_offline: bool = True,
    ) -> list[str]:
        """Distinct provider names that can satisfy *contract* (palette use).

        Availability is intentionally ignored so the canvas can list every
        bindable provider; ``auto`` is the caller's responsibility to prepend.
        """
        names: list[str] = []
        for p in self.registry.query(contract=contract):
            if not include_offline and p.backend_class == BackendClass.OFFLINE:
                continue
            if p.provider not in names:
                names.append(p.provider)
        # Keep offline last for a stable, predictable palette ordering.
        if include_offline and "offline" in names:
            names = [n for n in names if n != "offline"] + ["offline"]
        return names

    @staticmethod
    def _rank(profiles: list[CapabilityProfile]) -> list[CapabilityProfile]:
        # Stable sort by cost tier; registration order preserved within a tier.
        indexed = list(enumerate(profiles))
        indexed.sort(key=lambda pair: (pair[1].cost_tier, pair[0]))
        return [p for _, p in indexed]


__all__ = ["CapabilityRouter"]
