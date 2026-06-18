"""Unified capability layer — one contract for every model/backend.

This package consolidates the three previously separate "capability"
descriptions (chat ``ModelCapabilities``, domain-model ``DomainModelSpec``,
generation ``GenerationBackend``) behind a single
:class:`CapabilityProfile` + :class:`CapabilityRegistry`, queried through a
capability-aware :class:`CapabilityRouter`.

See :mod:`leagent.llm.capabilities.profile` for the core types.
"""

from __future__ import annotations

from .adapters import (
    from_domain_spec,
    from_generation_backend,
    from_model_spec,
    kind_to_output,
    kind_to_task,
)
from .profile import (
    BackendClass,
    CapabilityContract,
    CapabilityProfile,
    Modality,
    TaskType,
)
from .provider_stats import (
    ProviderStat,
    ProviderStatsStore,
    get_provider_stats,
    reset_provider_stats,
)
from .registry import (
    CapabilityRegistry,
    RegisteredCapability,
    get_capability_registry,
    reset_capability_registry,
)
from .router import CapabilityRouter

__all__ = [
    "BackendClass",
    "CapabilityContract",
    "CapabilityProfile",
    "CapabilityRegistry",
    "CapabilityRouter",
    "Modality",
    "ProviderStat",
    "ProviderStatsStore",
    "RegisteredCapability",
    "TaskType",
    "from_domain_spec",
    "from_generation_backend",
    "from_model_spec",
    "get_capability_registry",
    "get_provider_stats",
    "kind_to_output",
    "kind_to_task",
    "reset_capability_registry",
    "reset_provider_stats",
]
