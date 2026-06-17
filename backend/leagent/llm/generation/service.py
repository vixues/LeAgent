"""``GenerationService`` — unified image / video / 3D generation facade.

Registry of :class:`~leagent.llm.generation.base.GenerationBackend`
strategies keyed by media kind, with:

- **provider override** — caller may pin a specific backend.
- **failover** — ordered candidate backends; the next is tried when one
  fails, with the always-available ``offline`` backend as the floor.
- **retry** — per-backend exponential backoff for transient failures.

This closes the reliability gap of the old ``generate_image`` path (no
retry, no failover) and is consumed directly by hand-authored art nodes.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from leagent.llm.capabilities import (
    CapabilityContract,
    CapabilityRegistry,
    CapabilityRouter,
    from_generation_backend,
    kind_to_output,
    kind_to_task,
)
from leagent.utils.logging import get_logger

from .backends import (
    HttpMesh3DBackend,
    HttpVideoBackend,
    ImageProviderBackend,
    LocalDiffusionBackend,
    OfflineGenerationBackend,
)
from .base import GenerationBackend, GenerationOutput

logger = get_logger(__name__)


def _contract_for_kind(kind: str) -> CapabilityContract | None:
    task = kind_to_task(kind)
    if task is None:
        return None
    output = kind_to_output(kind)
    outputs = frozenset({output}) if output is not None else frozenset()
    return CapabilityContract(task=task, outputs=outputs)


class GenerationService:
    """Strategy registry + reliability layer for media generation.

    Candidate selection is delegated to the capability layer: each backend is
    lifted into a :class:`~leagent.llm.capabilities.CapabilityProfile` and the
    :class:`~leagent.llm.capabilities.CapabilityRouter` ranks candidates
    (preferred provider → cost tier → registration order, offline floor last).
    The retry / failover / offline-floor reliability behaviour is unchanged.
    """

    def __init__(self, *, allow_offline_fallback: bool = True) -> None:
        self._by_kind: dict[str, list[GenerationBackend]] = {}
        self._offline = OfflineGenerationBackend()
        self._allow_offline_fallback = allow_offline_fallback
        self._registry = CapabilityRegistry()
        self._router = CapabilityRouter(self._registry)
        self._registry.register(
            from_generation_backend(self._offline), invoker=self._offline
        )

    # -- registration ---------------------------------------------------

    def register(self, backend: GenerationBackend, *, prepend: bool = False) -> None:
        for kind in backend.kinds:
            bucket = self._by_kind.setdefault(kind, [])
            if prepend:
                bucket.insert(0, backend)
            else:
                bucket.append(backend)
        self._registry.register(from_generation_backend(backend), invoker=backend)

    def backends_for(self, kind: str) -> list[GenerationBackend]:
        return list(self._by_kind.get(kind, []))

    def providers_for(self, kind: str) -> list[str]:
        """Ordered provider names available for a kind (offline last)."""
        if self._force_offline():
            return [self._offline.name]
        names = [b.name for b in self._by_kind.get(kind, []) if b.available()]
        if self._allow_offline_fallback and self._offline.name not in names:
            names.append(self._offline.name)
        return names

    def palette_providers(self, kind: str) -> list[str]:
        """All bindable provider names for a kind (availability ignored).

        Used to populate workflow node ``provider`` combos dynamically so the
        canvas lists every interchangeable backend, not a hardcoded subset.
        """
        contract = _contract_for_kind(kind)
        if contract is None:
            return [self._offline.name]
        return self._router.provider_options(contract)

    # -- invocation -----------------------------------------------------

    @staticmethod
    def _force_offline() -> bool:
        """When set, pin every kind to the deterministic offline backend.

        Lets CI / harness runs stay hermetic and digest-stable even when
        real provider credentials happen to be present in the environment.
        """
        return os.environ.get("LEAGENT_ART_OFFLINE", "").strip() not in ("", "0", "false", "False")

    def _candidates(self, kind: str, provider: str | None) -> list[GenerationBackend]:
        if self._force_offline():
            return [self._offline]
        if provider and provider == self._offline.name:
            return [self._offline]
        contract = _contract_for_kind(kind)
        if contract is None:
            return []
        profiles = self._router.candidates(
            contract,
            preferred_provider=provider,
            available_only=provider is None,
            offline_floor=self._allow_offline_fallback,
        )
        candidates: list[GenerationBackend] = []
        for profile in profiles:
            invoker = self._registry.get_invoker(profile.id)
            if invoker is not None and invoker not in candidates:
                candidates.append(invoker)
        return candidates

    async def generate(
        self,
        *,
        kind: str,
        prompt: str,
        provider: str | None = None,
        max_retries: int = 2,
        retry_delay_sec: float = 1.0,
        **params: Any,
    ) -> GenerationOutput:
        """Generate one asset, trying candidate backends with retries."""
        if kind not in ("image", "video", "model3d"):
            return GenerationOutput.failure(kind, f"unsupported kind '{kind}'")

        candidates = self._candidates(kind, provider)
        if not candidates:
            return GenerationOutput.failure(kind, f"no backend available for '{kind}'")

        last_error = "no backend produced output"
        for backend in candidates:
            for attempt in range(max(0, max_retries) + 1):
                try:
                    out = await backend.generate(kind=kind, prompt=prompt, **params)
                    if out.success and (out.data or out.meta.get("url")):
                        out.meta.setdefault("attempts", attempt + 1)
                        return out
                    last_error = out.error or last_error
                except Exception as exc:  # noqa: BLE001
                    last_error = str(exc)
                    logger.warning(
                        "generation_backend_failed",
                        backend=backend.name, kind=kind, attempt=attempt, error=last_error,
                    )
                if attempt < max_retries:
                    await asyncio.sleep(retry_delay_sec * (2 ** attempt))
            logger.info("generation_backend_failover", failed=backend.name, kind=kind)

        return GenerationOutput.failure(kind, last_error, provider=provider or "")


def build_default_generation_service() -> GenerationService:
    """Construct a service wired with the built-in backends.

    Real providers are registered ahead of the offline floor; each
    declares ``available()`` so credential-less environments transparently
    fall through to deterministic offline generation.
    """
    svc = GenerationService()
    svc.register(LocalDiffusionBackend())
    svc.register(ImageProviderBackend("openai"))
    svc.register(ImageProviderBackend("dashscope"))
    svc.register(HttpVideoBackend())
    svc.register(HttpMesh3DBackend())
    return svc


_SERVICE: GenerationService | None = None


def get_generation_service() -> GenerationService:
    """Return the process-wide generation service (lazily created)."""
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = build_default_generation_service()
    return _SERVICE


def reset_generation_service() -> None:
    """Reset the process-wide service (test helper)."""
    global _SERVICE
    _SERVICE = None


__all__ = [
    "GenerationService",
    "build_default_generation_service",
    "get_generation_service",
    "reset_generation_service",
]
