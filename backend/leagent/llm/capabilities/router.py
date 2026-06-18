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

    def __init__(self, registry: CapabilityRegistry, *, stats: object | None = None) -> None:
        self.registry = registry
        # Optional provider-performance store used to bias ranking by live
        # reliability/quality within a cost tier. Defaults to the global store.
        if stats is None:
            try:
                from .provider_stats import get_provider_stats

                stats = get_provider_stats()
            except Exception:  # noqa: BLE001 - stats are best-effort
                stats = None
        self.stats = stats

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
            ranked = self._rank(picked, contract)
        else:
            if available_only:
                real = [p for p in real if p.available()]
            ranked = self._rank(real, contract)

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

    def _rank(
        self,
        profiles: list[CapabilityProfile],
        contract: CapabilityContract | None = None,
    ) -> list[CapabilityProfile]:
        # Stable sort by cost tier first (cheap/local before paid), then by
        # observed reliability (production self-optimization), then by
        # registration order. Unobserved providers get a neutral score so the
        # ordering is unchanged until real feedback accrues.
        task = contract.task.value if contract is not None else ""
        indexed = list(enumerate(profiles))

        def _reliability(profile: CapabilityProfile) -> float:
            if self.stats is None or not task:
                return 0.5
            try:
                return float(self.stats.reliability(task, profile.provider))
            except Exception:  # noqa: BLE001
                return 0.5

        # Negate reliability so higher reliability sorts earlier; round to keep
        # tiny floating noise from reordering otherwise-equal providers.
        indexed.sort(key=lambda pair: (
            pair[1].cost_tier,
            -round(_reliability(pair[1]), 3),
            pair[0],
        ))
        return [p for _, p in indexed]


__all__ = ["CapabilityRouter"]
