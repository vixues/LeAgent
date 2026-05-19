"""Process-local LRU cache for :func:`leagent.skills.bundle_payload.build_bundle_payload` results.

Callers (e.g. ``SkillTool``) build a content-revision key; see that module. Not used for
:mod:`leagent.skills.bundled` (builtin skill directories) or :mod:`leagent.skills.referenced_bundle`
(@skill prompt injection — uncached per turn).
"""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from typing import Any

_MAX_ENTRIES = 64
_bundle_cache: OrderedDict[tuple[Any, ...], tuple[str, dict[str, Any]]] = OrderedDict()


def clear_bundle_payload_cache() -> None:
    """Testing hook."""
    _bundle_cache.clear()


def get_cached_bundle(cache_key: tuple[Any, ...]) -> tuple[str, dict[str, Any]] | None:
    if cache_key not in _bundle_cache:
        return None
    _bundle_cache.move_to_end(cache_key)
    body_out, extra = _bundle_cache[cache_key]
    return deepcopy(body_out), deepcopy(extra)


def put_cached_bundle(cache_key: tuple[Any, ...], value: tuple[str, dict[str, Any]]) -> None:
    _bundle_cache[cache_key] = value
    _bundle_cache.move_to_end(cache_key)
    while len(_bundle_cache) > _MAX_ENTRIES:
        _bundle_cache.popitem(last=False)
