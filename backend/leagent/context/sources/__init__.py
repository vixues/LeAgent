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
    global _REGISTRY_SEEDED
    if not _REGISTRY_SEEDED:
        _lazy_load()
        _REGISTRY_SEEDED = True
    return dict(SOURCE_REGISTRY)


def _lazy_load() -> None:
    from leagent.context.sources import (  # noqa: F401
        active_project,
        capabilities,
        environment,
        identity,
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
