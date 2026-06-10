"""Built-in domain-model adapters (TTS / ASR / image generation).

Each adapter implements the :class:`~leagent.llm.domain_registry.DomainModelAdapter`
protocol. :func:`register_builtin_domain_models` wires the adapters whose
provider credentials are configured into the process-wide registry; it is
called from the workflow bootstrap so every registered adapter automatically
becomes a ``Model.<task>.<provider>`` workflow node.
"""

from __future__ import annotations

import os

from leagent.llm.domain_registry import DomainModelRegistry, get_domain_registry
from leagent.utils.logging import get_logger

logger = get_logger(__name__)


def register_builtin_domain_models(
    registry: DomainModelRegistry | None = None,
) -> list[str]:
    """Register built-in adapters for providers with configured credentials.

    Returns the list of registered ``task.provider`` keys. Safe to call
    multiple times (re-registration replaces).
    """
    registry = registry or get_domain_registry()
    registered: list[str] = []

    dashscope_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if dashscope_key:
        from .dashscope_audio import DashScopeASRAdapter, DashScopeTTSAdapter
        from .image import DashScopeImageGenAdapter

        for adapter in (
            DashScopeTTSAdapter(api_key=dashscope_key),
            DashScopeASRAdapter(api_key=dashscope_key),
            DashScopeImageGenAdapter(api_key=dashscope_key),
        ):
            registry.register(adapter, replace=True)
            registered.append(adapter.spec.key)

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if openai_key:
        from .openai_audio import OpenAIASRAdapter, OpenAITTSAdapter

        for adapter in (
            OpenAITTSAdapter(api_key=openai_key),
            OpenAIASRAdapter(api_key=openai_key),
        ):
            registry.register(adapter, replace=True)
            registered.append(adapter.spec.key)

    # Self-hosted diffusion (import-gated on the optional `diffusion` extra).
    if os.environ.get("LEAGENT_DIFFUSION_ENABLED", "1").strip() != "0":
        from .diffusion import diffusers_available

        if diffusers_available():
            from .diffusion.adapter import DiffusersTxt2ImgAdapter

            adapter = DiffusersTxt2ImgAdapter()
            registry.register(adapter, replace=True)
            registered.append(adapter.spec.key)

    # Self-hosted audio servers (env-gated on their base URLs).
    if os.environ.get("LEAGENT_LOCAL_ASR_URL", "").strip():
        from .local_audio import LocalWhisperASRAdapter

        adapter = LocalWhisperASRAdapter()
        registry.register(adapter, replace=True)
        registered.append(adapter.spec.key)

    if os.environ.get("LEAGENT_LOCAL_TTS_URL", "").strip():
        from .local_audio import LocalTTSAdapter

        adapter = LocalTTSAdapter()
        registry.register(adapter, replace=True)
        registered.append(adapter.spec.key)

    if registered:
        logger.info("builtin_domain_models_registered", adapters=registered)
    return registered


__all__ = ["register_builtin_domain_models"]
