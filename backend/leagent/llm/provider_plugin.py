"""Provider plugin registry — replaces the if/else factory chain.

Each provider type registers a factory callable via
:func:`register_provider_type`.  ``ProviderConfigService`` (and any other
instantiation site) calls :func:`create_provider` instead of a hardcoded
``if pc.type == ...`` ladder.

Built-in providers are auto-registered on first import of this module.
Third-party providers can register via ``pyproject.toml`` entry-points
(``leagent.llm_providers``) or by calling :func:`register_provider_type`
at startup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

try:  # importlib.metadata is stdlib; older interpreters fall back
    from importlib.metadata import entry_points
except ImportError:  # pragma: no cover
    from importlib_metadata import entry_points  # type: ignore

from leagent.utils.logging import get_logger

if TYPE_CHECKING:
    from leagent.llm.base import LLMProvider

logger = get_logger(__name__)

ENTRYPOINT_GROUP = "leagent.llm_providers"

ProviderFactory = Callable[..., "LLMProvider"]

_REGISTRY: dict[str, ProviderFactory] = {}
_entrypoints_loaded = False


def register_provider_type(
    type_name: str,
    factory: ProviderFactory,
    *,
    replace: bool = False,
) -> None:
    """Register a provider type → factory mapping.

    Args:
        type_name: The ``type`` string from ``providers.yaml``
            (e.g. ``"openai"``, ``"anthropic"``).
        factory: Callable that accepts ``(ProviderConfig, **kwargs)``
            and returns an :class:`LLMProvider`.
        replace: Allow overwriting an existing registration.
    """
    if type_name in _REGISTRY and not replace:
        raise ValueError(f"Provider type '{type_name}' is already registered")
    _REGISTRY[type_name] = factory


def get_provider_factory(type_name: str) -> ProviderFactory | None:
    """Look up a registered factory by type name."""
    return _REGISTRY.get(type_name)


def list_provider_types() -> list[str]:
    """Return sorted list of registered provider type names."""
    return sorted(_REGISTRY)


def create_provider(type_name: str, **kwargs: Any) -> LLMProvider:
    """Instantiate a provider by type name.

    Falls back to ``CustomOpenAIProvider`` for unknown types (preserving
    the old behaviour of treating unknowns as tolerant OpenAI-compatible
    gateways).

    Raises:
        ValueError: If type is unknown and no fallback is available.
    """
    factory = _REGISTRY.get(type_name)
    if factory is None:
        fallback = _REGISTRY.get("custom")
        if fallback is not None:
            logger.info(
                "provider_type_fallback",
                type=type_name,
                fallback="custom",
            )
            return fallback(**kwargs)
        raise ValueError(
            f"Unknown provider type '{type_name}' and no 'custom' fallback registered. "
            f"Available: {list_provider_types()}"
        )
    return factory(**kwargs)


# ── Built-in provider factories ─────────────────────────────────────────

def _register_builtins() -> None:
    """Register the built-in provider types.

    Each factory accepts keyword arguments matching the constructor of its
    provider class.  The ``ProviderConfigService`` extracts the relevant
    kwargs from ``ProviderConfig`` before calling :func:`create_provider`.
    """

    def _openai(**kw: Any) -> LLMProvider:
        from leagent.llm.providers.openai import OpenAIProvider
        return OpenAIProvider(**kw)

    def _anthropic(**kw: Any) -> LLMProvider:
        from leagent.llm.providers.anthropic import AnthropicProvider
        return AnthropicProvider(**kw)

    def _deepseek(**kw: Any) -> LLMProvider:
        from leagent.llm.providers.deepseek import DeepSeekProvider
        return DeepSeekProvider(**kw)

    def _dashscope(**kw: Any) -> LLMProvider:
        from leagent.llm.providers.dashscope import DashScopeProvider
        return DashScopeProvider(**kw)

    def _ollama(**kw: Any) -> LLMProvider:
        from leagent.llm.providers.ollama import OllamaProvider
        return OllamaProvider(**kw)

    def _vllm(**kw: Any) -> LLMProvider:
        from leagent.llm.providers.vllm import VLLMProvider
        return VLLMProvider(**kw)

    def _custom(**kw: Any) -> LLMProvider:
        from leagent.llm.providers.custom import CustomOpenAIProvider
        return CustomOpenAIProvider(**kw)

    for type_name, factory in [
        ("openai", _openai),
        ("azure", _openai),
        ("anthropic", _anthropic),
        ("deepseek", _deepseek),
        ("dashscope", _dashscope),
        ("qwen", _dashscope),
        ("ollama", _ollama),
        ("vllm", _vllm),
        ("custom", _custom),
    ]:
        register_provider_type(type_name, factory, replace=True)


def load_provider_plugins() -> list[str]:
    """Discover + register third-party providers from entry points.

    Distributions expose a ``leagent.llm_providers`` entry point whose target
    is either a ``(type_name, factory)`` tuple, a ``ProviderFactory`` callable
    (registered under the entry-point ``name``), or a zero-arg callable that
    performs its own ``register_provider_type`` calls. Idempotent.
    """
    global _entrypoints_loaded
    if _entrypoints_loaded:
        return []
    _entrypoints_loaded = True

    registered: list[str] = []
    try:
        eps = entry_points(group=ENTRYPOINT_GROUP)
    except TypeError:  # older API shape
        eps = entry_points().get(ENTRYPOINT_GROUP, [])  # type: ignore[attr-defined]
    for ep in eps:
        try:
            target = ep.load()
            if isinstance(target, tuple) and len(target) == 2:
                type_name, factory = target
                register_provider_type(str(type_name), factory, replace=True)
                registered.append(str(type_name))
            elif callable(target):
                # Either a factory registered under the EP name, or a
                # self-registering hook. Treat a returned mapping/None as a hook.
                result = target() if _is_zero_arg(target) else None
                if result is None and not _is_zero_arg(target):
                    register_provider_type(ep.name, target, replace=True)
                    registered.append(ep.name)
        except Exception:  # noqa: BLE001
            logger.error("llm_provider_entrypoint_failed", name=str(ep), exc_info=True)
    if registered:
        logger.info("llm_providers_loaded", providers=registered)
    return registered


def _is_zero_arg(fn: Callable[..., Any]) -> bool:
    import inspect

    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    return all(
        p.default is not inspect.Parameter.empty
        or p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        for p in sig.parameters.values()
    )


_register_builtins()


def reset_provider_registry() -> None:
    """Reset the provider type registry and re-register builtins (test helper)."""
    global _entrypoints_loaded
    _REGISTRY.clear()
    _entrypoints_loaded = False
    _register_builtins()


__all__ = [
    "ENTRYPOINT_GROUP",
    "ProviderFactory",
    "create_provider",
    "get_provider_factory",
    "list_provider_types",
    "load_provider_plugins",
    "register_provider_type",
    "reset_provider_registry",
]
