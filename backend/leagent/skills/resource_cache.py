"""Process-local LRU cache for skill resource file reads (read_skill_resource).

Keys include resolved path and mtime so edits invalidate automatically.
"""

from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from pathlib import Path
from typing import Any

_CACHE_MAX = 384
_resource_payload_cache: OrderedDict[tuple[str, int | float, int], dict[str, Any]] = OrderedDict()


def clear_skill_resource_read_cache() -> None:
    """Testing hook — drop all cached resource payloads."""
    _resource_payload_cache.clear()


def get_cached_resource_payload(key: tuple[str, int | float, int]) -> dict[str, Any] | None:
    """Return a deep copy of a cached payload, or None."""
    if key not in _resource_payload_cache:
        return None
    _resource_payload_cache.move_to_end(key)
    return deepcopy(_resource_payload_cache[key])


def put_cached_resource_payload(key: tuple[str, int | float, int], payload: dict[str, Any]) -> None:
    """Store a deep copy so callers cannot mutate the cache."""
    _resource_payload_cache[key] = deepcopy(payload)
    _resource_payload_cache.move_to_end(key)
    while len(_resource_payload_cache) > _CACHE_MAX:
        _resource_payload_cache.popitem(last=False)


def cache_key_for_path(path: Path, effective_cap: int) -> tuple[str, int | float, int] | None:
    """Build cache key, or None if stat fails (caller should read without cache).

    *effective_cap* must match the byte cap passed to the reader (e.g.
    ``max(1024, min(max_bytes, MAX_CHARS))``).
    """
    try:
        st = path.stat()
    except OSError:
        return None
    resolved = str(path.resolve())
    mkey: int | float
    mtime_ns = getattr(st, "st_mtime_ns", None)
    if mtime_ns is not None:
        mkey = int(mtime_ns)
    else:
        mkey = float(st.st_mtime)
    return (resolved, mkey, effective_cap)
