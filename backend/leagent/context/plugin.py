"""Context source plugin registry.

Replaces the mutable ``SOURCE_REGISTRY`` dict + ``_register`` helper in
``sources/__init__.py`` with a decorator-based plugin system.  Sources
register via :func:`register_source` (or the ``@source_plugin`` decorator),
are discovered from ``leagent.context_sources`` entry points by
:func:`load_source_plugins`, and are read back via :func:`get_plugin_sources`.

Existing sources continue to work via the legacy ``_register`` path —
this module provides the *additional* plugin entrypoint so third-party
or domain-specific sources can register without editing the sources
package.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

try:  # importlib.metadata is stdlib; older interpreters fall back
    from importlib.metadata import entry_points
except ImportError:  # pragma: no cover
    from importlib_metadata import entry_points  # type: ignore

from leagent.utils.logging import get_logger

if TYPE_CHECKING:
    from leagent.context.sources.base import ContextSource

logger = get_logger(__name__)

ENTRYPOINT_GROUP = "leagent.context_sources"

_PLUGIN_REGISTRY: dict[str, type[ContextSource]] = {}
_entrypoints_loaded = False


def register_source(
    cls: type[ContextSource],
    *,
    replace: bool = False,
) -> type[ContextSource]:
    """Register a context source class by its ``id``.

    Args:
        cls: A class satisfying the :class:`ContextSource` protocol.
        replace: Allow overwriting an existing source registration.

    Returns:
        The same class (for use as a decorator).
    """
    source_id = getattr(cls, "id", None)
    if not source_id:
        raise ValueError(f"Context source {cls.__name__} has no 'id' attribute")
    if source_id in _PLUGIN_REGISTRY and not replace:
        raise ValueError(f"Context source '{source_id}' is already registered")
    _PLUGIN_REGISTRY[source_id] = cls
    return cls


def source_plugin(cls: type[ContextSource]) -> type[ContextSource]:
    """Decorator shorthand for :func:`register_source`."""
    return register_source(cls, replace=True)


def get_plugin_sources() -> dict[str, type[ContextSource]]:
    """Return all sources registered via the plugin system."""
    return dict(_PLUGIN_REGISTRY)


def list_source_plugins() -> list[str]:
    """Return sorted list of plugin source IDs."""
    return sorted(_PLUGIN_REGISTRY)


def load_source_plugins() -> list[str]:
    """Discover + register third-party context sources from entry points.

    Distributions expose a ``leagent.context_sources`` entry point whose
    target is a :class:`ContextSource` subclass, an iterable of them, or a
    zero-arg callable that performs its own ``register_source`` calls.
    Idempotent.
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
            candidates: list[Any]
            if isinstance(target, type):
                candidates = [target]
            elif callable(target):
                result = target()
                candidates = list(result) if result else []
            else:
                candidates = list(target)
            for cls in candidates:
                register_source(cls, replace=True)
                registered.append(getattr(cls, "id", cls.__name__))
        except Exception:  # noqa: BLE001
            logger.error("context_source_entrypoint_failed", name=str(ep), exc_info=True)
    if registered:
        logger.info("context_sources_loaded", sources=registered)
    return registered


def reset_plugin_registry() -> None:
    """Clear the plugin registry (test helper)."""
    global _entrypoints_loaded
    _PLUGIN_REGISTRY.clear()
    _entrypoints_loaded = False


__all__ = [
    "ENTRYPOINT_GROUP",
    "get_plugin_sources",
    "list_source_plugins",
    "load_source_plugins",
    "register_source",
    "reset_plugin_registry",
    "source_plugin",
]
