"""Domain-model adapter registry — the plug-in path for non-chat models.

Domain models are task-specific capabilities (image generation, TTS, ASR,
future video/upscaling) backed by provider adapters. Each adapter declares a
:class:`DomainModelSpec` (task, provider, parameter schema, output modality)
and implements ``invoke``. The registry is the single discovery surface:

* ``register(adapter)``                 — programmatic registration
* entry points ``leagent.domain_models`` — third-party distributions
* ``invoke_task(task, provider=..., **params)`` — uniform invocation facade

The workflow node factory (:mod:`leagent.workflow.nodes.domain_model_factory`)
lifts every registered adapter into a ``Model.<task>.<provider>`` palette
node, so adding an adapter automatically adds a typed workflow node — the
ComfyUI-style custom-model onboarding path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

try:
    from importlib.metadata import entry_points
except ImportError:  # pragma: no cover
    from importlib_metadata import entry_points  # type: ignore

from leagent.utils.logging import get_logger

logger = get_logger(__name__)

ENTRYPOINT_GROUP = "leagent.domain_models"


# ---------------------------------------------------------------------------
# Parameter / result / spec types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DomainParam:
    """One adapter parameter, mapped 1:1 onto a workflow node input."""

    id: str
    #: Workflow IO type: STRING, INT, FLOAT, BOOLEAN, COMBO, FILE, AUDIO, IMAGE.
    io_type: str = "STRING"
    required: bool = False
    default: Any = None
    #: For COMBO params: the available choices.
    choices: tuple[str, ...] = ()
    multiline: bool = False
    min: float | None = None
    max: float | None = None
    tooltip: str = ""


@dataclass
class DomainModelResult:
    """Uniform result envelope for a domain-model invocation."""

    success: bool = True
    #: Primary text payload (ASR transcript, captions, ...).
    text: str | None = None
    #: Primary binary payload, base64-encoded (audio bytes, image bytes).
    b64_data: str | None = None
    #: Remote URL alternative to ``b64_data``.
    url: str | None = None
    mime: str = ""
    error: str | None = None
    model: str = ""
    provider: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DomainModelSpec:
    """Static description of one adapter (drives node generation)."""

    #: Logical task id: ``image_gen`` / ``tts`` / ``asr`` / custom.
    task: str
    #: Provider id, e.g. ``dashscope`` / ``openai`` / ``local``.
    provider: str
    #: Default model name passed to ``invoke`` when the caller omits one.
    model: str = ""
    display_name: str = ""
    description: str = ""
    #: Parameters exposed as workflow node inputs (and ``invoke`` kwargs).
    params: tuple[DomainParam, ...] = ()
    #: Primary output modality: ``text`` / ``audio`` / ``image``.
    output: str = "text"
    #: When True, callers may pass a ``_progress(step, total)`` callback to
    #: ``invoke`` for live progress (e.g. diffusion sampling steps).
    supports_progress: bool = False

    @property
    def key(self) -> str:
        return f"{self.task}.{self.provider}"


@runtime_checkable
class DomainModelAdapter(Protocol):
    """Protocol every domain-model adapter implements."""

    spec: DomainModelSpec

    async def invoke(self, **params: Any) -> DomainModelResult:
        """Run the model with the spec-declared parameters."""
        ...


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class DomainModelRegistry:
    """Process-wide registry of domain-model adapters."""

    def __init__(self) -> None:
        self._adapters: dict[str, DomainModelAdapter] = {}

    def register(self, adapter: DomainModelAdapter, *, replace: bool = False) -> None:
        key = adapter.spec.key
        if key in self._adapters and not replace:
            raise ValueError(f"Domain model '{key}' is already registered")
        self._adapters[key] = adapter
        logger.debug("domain_model_registered", key=key)

    def get(self, task: str, provider: str | None = None) -> DomainModelAdapter | None:
        """Look up an adapter by task (+ optional provider).

        Without a provider, the first adapter registered for the task wins.
        """
        if provider:
            return self._adapters.get(f"{task}.{provider}")
        for key, adapter in self._adapters.items():
            if key.split(".", 1)[0] == task:
                return adapter
        return None

    def all(self) -> list[DomainModelAdapter]:
        return list(self._adapters.values())

    def specs(self) -> list[DomainModelSpec]:
        return [a.spec for a in self._adapters.values()]

    def tasks(self) -> list[str]:
        return sorted({a.spec.task for a in self._adapters.values()})

    async def invoke_task(
        self,
        task: str,
        *,
        provider: str | None = None,
        **params: Any,
    ) -> DomainModelResult:
        """Uniform invocation facade: resolve the adapter and run it."""
        adapter = self.get(task, provider)
        if adapter is None:
            available = sorted(self._adapters)
            return DomainModelResult(
                success=False,
                error=(
                    f"No domain model registered for task '{task}'"
                    + (f" provider '{provider}'" if provider else "")
                    + f". Available: {available}"
                ),
            )
        try:
            return await adapter.invoke(**params)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "domain_model_invoke_failed",
                task=task,
                provider=provider or adapter.spec.provider,
                error=str(exc),
                exc_info=True,
            )
            return DomainModelResult(
                success=False,
                error=str(exc),
                model=adapter.spec.model,
                provider=adapter.spec.provider,
            )

    def clear(self) -> None:
        """Remove all adapters (test helper)."""
        self._adapters.clear()


_REGISTRY: DomainModelRegistry | None = None
_entrypoints_loaded = False


def get_domain_registry() -> DomainModelRegistry:
    """Return the process-wide domain-model registry (lazily created)."""
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = DomainModelRegistry()
    return _REGISTRY


def load_domain_model_plugins() -> list[str]:
    """Discover + register adapters from ``leagent.domain_models`` entry points.

    Each entry point target is either an adapter instance, an adapter class
    (zero-arg constructible), or a zero-arg callable returning one of those.
    Idempotent across calls.
    """
    global _entrypoints_loaded
    if _entrypoints_loaded:
        return []
    _entrypoints_loaded = True

    registry = get_domain_registry()
    registered: list[str] = []
    try:
        eps = entry_points(group=ENTRYPOINT_GROUP)
    except TypeError:  # older API shape
        eps = entry_points().get(ENTRYPOINT_GROUP, [])  # type: ignore[attr-defined]
    for ep in eps:
        try:
            target = ep.load()
            adapter = target() if callable(target) and not _is_adapter(target) else target
            if _is_adapter(adapter):
                registry.register(adapter, replace=True)
                registered.append(adapter.spec.key)
            else:
                logger.warning("domain_model_entrypoint_not_adapter", name=str(ep))
        except Exception:  # noqa: BLE001
            logger.error("domain_model_entrypoint_failed", name=str(ep), exc_info=True)
    if registered:
        logger.info("domain_models_loaded", adapters=registered)
    return registered


def _is_adapter(obj: Any) -> bool:
    return hasattr(obj, "spec") and hasattr(obj, "invoke") and not isinstance(obj, type)


def reset_domain_registry() -> None:
    """Reset the registry (test helper)."""
    global _REGISTRY, _entrypoints_loaded
    _REGISTRY = None
    _entrypoints_loaded = False


__all__ = [
    "ENTRYPOINT_GROUP",
    "DomainModelAdapter",
    "DomainModelRegistry",
    "DomainModelResult",
    "DomainModelSpec",
    "DomainParam",
    "get_domain_registry",
    "load_domain_model_plugins",
    "reset_domain_registry",
]
