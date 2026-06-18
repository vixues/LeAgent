"""Populate the process-wide capability registry from all three sources.

This is the discovery surface consumed by the chat capabilities endpoint and
any capability-driven UI. Generation backends register into the same global
registry via :class:`~leagent.llm.generation.service.GenerationService`.
"""

from __future__ import annotations

from typing import Any

from leagent.utils.logging import get_logger

from .adapters import from_domain_spec, from_generation_backend, from_model_spec
from .registry import CapabilityRegistry, get_capability_registry

logger = get_logger(__name__)


def register_generation_capabilities(registry: CapabilityRegistry | None = None) -> list[str]:
    """Register every generation backend's profile into *registry*."""
    registry = registry or get_capability_registry()
    registered: list[str] = []
    try:
        from leagent.llm.generation import get_generation_service

        svc = get_generation_service()
        seen: set[int] = set()
        for kind in ("image", "video", "model3d", "vfx", "audio"):
            for backend in svc.backends_for(kind):
                if id(backend) in seen:
                    continue
                seen.add(id(backend))
                profile = from_generation_backend(backend)
                registry.register(profile, invoker=backend)
                registered.append(profile.id)
    except Exception:  # noqa: BLE001 - generation layer optional at bootstrap
        logger.debug("capability_generation_bootstrap_failed", exc_info=True)
    return registered


def register_domain_capabilities(registry: CapabilityRegistry | None = None) -> list[str]:
    """Register every domain-model adapter's profile into *registry*."""
    registry = registry or get_capability_registry()
    registered: list[str] = []
    try:
        from leagent.llm.domain_models import register_builtin_domain_models
        from leagent.llm.domain_registry import (
            get_domain_registry,
            load_domain_model_plugins,
        )

        domain = get_domain_registry()
        register_builtin_domain_models(domain)
        load_domain_model_plugins()
        for adapter in domain.all():
            profile = from_domain_spec(adapter.spec)
            registry.register(profile, invoker=adapter)
            registered.append(profile.id)
    except Exception:  # noqa: BLE001 - domain registry optional
        logger.debug("capability_domain_bootstrap_failed", exc_info=True)
    return registered


def register_model_capabilities(
    catalog: Any,
    registry: CapabilityRegistry | None = None,
) -> list[str]:
    """Register chat/embedding/image_gen/tts/asr model specs from a catalog.

    ``catalog`` is a :class:`leagent.llm.model_registry.ModelRegistry` (or any
    object exposing ``all_specs()`` / ``specs()`` returning ``ModelSpec``).
    """
    registry = registry or get_capability_registry()
    registered: list[str] = []
    specs = _iter_specs(catalog)
    for spec in specs:
        try:
            profile = from_model_spec(spec)
            registry.register(profile)
            registered.append(profile.id)
        except Exception:  # noqa: BLE001 - skip malformed specs
            logger.debug("capability_model_spec_skip", spec=getattr(spec, "name", spec))
    return registered


def bootstrap_capabilities(catalog: Any | None = None) -> dict[str, list[str]]:
    """Aggregate generation + domain (+ optional catalog) into the global registry."""
    summary: dict[str, list[str]] = {}
    summary["generation"] = register_generation_capabilities()
    summary["domain"] = register_domain_capabilities()
    if catalog is not None:
        summary["models"] = register_model_capabilities(catalog)
    return summary


def _iter_specs(catalog: Any) -> list[Any]:
    for attr in ("all_specs", "specs", "list_specs"):
        fn = getattr(catalog, attr, None)
        if callable(fn):
            try:
                return list(fn())
            except Exception:  # noqa: BLE001
                continue
    return []


__all__ = [
    "bootstrap_capabilities",
    "register_domain_capabilities",
    "register_generation_capabilities",
    "register_model_capabilities",
]
