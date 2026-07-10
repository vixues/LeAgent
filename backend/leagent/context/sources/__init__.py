"""Source registry — maps source IDs to factory callables."""

from __future__ import annotations

from leagent.context.sources.base import ContextSource, ResolveContext

__all__ = ["ContextSource", "ResolveContext", "SOURCE_REGISTRY", "get_all_sources"]

SOURCE_REGISTRY: dict[str, type[ContextSource]] = {}

# Eager import of any single source module can populate SOURCE_REGISTRY before
# ``get_all_sources`` runs; ``if not SOURCE_REGISTRY`` would then skip the
# full seed and leave recipe entries like ``session_attachments`` missing.
_REGISTRY_SEEDED: bool = False


def _register(cls: type[ContextSource]) -> type[ContextSource]:
    SOURCE_REGISTRY[cls.id] = cls
    return cls


def get_all_sources() -> dict[str, type[ContextSource]]:
    """Return all registered sources (builtin + plugin)."""
    global _REGISTRY_SEEDED
    if not _REGISTRY_SEEDED:
        _lazy_load()
        _REGISTRY_SEEDED = True
    merged = dict(SOURCE_REGISTRY)
    try:
        from leagent.context.plugin import get_plugin_sources, load_source_plugins

        # Discover drop-in third-party sources (entry points) once, then merge
        # the plugin registry on top of the builtins.
        load_source_plugins()
        merged.update(get_plugin_sources())
    except ImportError:
        pass
    return merged


def _lazy_load() -> None:
    from leagent.context.sources import (  # noqa: F401
        active_project,
        art_playbook,
        capabilities,
        environment,
        gated_policy,
        identity,
        playbooks,
        policies,
        project_memory,
        recall,
        recent_reads,
        session_artifacts,
        session_attachments,
        tool_history,
        user_instructions,
        working_set,
    )
