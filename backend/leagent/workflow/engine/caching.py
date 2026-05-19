"""In-memory cache strategies for node outputs.

Four cache classes cover the common policies:

- :class:`NullCache` — disable caching entirely.
- :class:`BasicCache` — unbounded dict, survives one run only.
- :class:`HierarchicalCache` — nested per subgraph expansion frame so
  expanded nodes can be skipped on a subsequent run without colliding
  with the parent frame's cache.
- :class:`LRUCache` — bounded by entry count.
- :class:`RAMPressureCache` — bounded by (approximate) RAM usage.

The cache *key* comes from :class:`CacheKeySet`. Two canonical subclasses:

- :class:`CacheKeySetID` — keys by ``(node_id, class_type)`` only.
  Appropriate for idempotent nodes whose outputs depend purely on static
  inputs.
- :class:`CacheKeySetInputSignature` — keys by the immediate-input
  signature plus the ancestor signatures (``IS_CHANGED`` values of all
  upstream nodes). Appropriate when outputs depend on upstream values.

Policy is selected by :class:`CacheSet`. A process-wide default is
constructed by :func:`build_cache_set` using the ``WORKFLOW_CACHE_MODE``
config key (classic / lru / ram / none).
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable


# ---------------------------------------------------------------------------
# Signature helpers
# ---------------------------------------------------------------------------


def _canonical(value: Any) -> Any:
    """Recursively canonicalize a value for signature hashing."""
    if isinstance(value, dict):
        return {k: _canonical(value[k]) for k in sorted(value)}
    if isinstance(value, list):
        return [_canonical(v) for v in value]
    if isinstance(value, tuple):
        return [_canonical(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def hash_signature(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def immediate_node_signature(
    node_id: str,
    node_def: dict[str, Any],
    node_cls: Any = None,
) -> str:
    """Signature based on the node's immediate inputs + ``IS_CHANGED`` result.

    Link values are kept as-is (``[upstream, slot]``) because the upstream
    signature is folded in by :class:`CacheKeySetInputSignature`.
    """
    cls_name = node_def.get("class_type", "")
    immediate_inputs: dict[str, Any] = {}
    for k, v in (node_def.get("inputs") or {}).items():
        if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
            immediate_inputs[k] = ["LINK", v[0], v[1]]
        else:
            immediate_inputs[k] = v
    is_changed: Any = None
    if node_cls is not None and hasattr(node_cls, "IS_CHANGED"):
        try:
            is_changed = node_cls.IS_CHANGED(**immediate_inputs)
        except Exception:  # noqa: BLE001
            is_changed = None
    if node_cls is not None and getattr(node_cls.get_schema(), "not_idempotent", False):
        immediate_inputs["__node_id__"] = node_id
    return hash_signature({"class": cls_name, "inputs": immediate_inputs, "is_changed": is_changed})


# ---------------------------------------------------------------------------
# Cache key sets
# ---------------------------------------------------------------------------


class CacheKeySet:
    """Resolves a hashable cache key for a given node id."""

    def signature(self, node_id: str) -> str:  # pragma: no cover - abstract
        raise NotImplementedError


class CacheKeySetID(CacheKeySet):
    """Keys purely by ``(node_id, class_type)``."""

    def __init__(self, prompt: Any) -> None:
        self._prompt = prompt

    def signature(self, node_id: str) -> str:
        node = self._prompt.get(node_id) or {}
        return hash_signature({"node_id": node_id, "class_type": node.get("class_type", "")})


class CacheKeySetInputSignature(CacheKeySet):
    """Signature = immediate signature ⊕ ancestor signatures, recursively."""

    def __init__(self, prompt: Any, registry: Any | None = None) -> None:
        self._prompt = prompt
        self._registry = registry
        self._memo: dict[str, str] = {}

    def invalidate(self, node_id: str) -> None:
        self._memo.pop(node_id, None)

    def signature(self, node_id: str) -> str:
        if node_id in self._memo:
            return self._memo[node_id]
        node = self._prompt.get(node_id)
        if not node:
            sig = hash_signature({"missing": node_id})
            self._memo[node_id] = sig
            return sig
        cls = self._registry.get(node.get("class_type", "")) if self._registry else None
        immediate = immediate_node_signature(node_id, node, cls)

        upstream_sigs: list[tuple[str, str]] = []
        for k, v in (node.get("inputs") or {}).items():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], str):
                upstream_sigs.append((k, self.signature(v[0])))

        sig = hash_signature({
            "immediate": immediate,
            "upstream": sorted(upstream_sigs),
        })
        self._memo[node_id] = sig
        return sig


# ---------------------------------------------------------------------------
# Caches
# ---------------------------------------------------------------------------


@dataclass
class CacheEntry:
    value: Any
    size_bytes: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseCache:
    """Interface shared by all cache flavours."""

    def get(self, key: str) -> CacheEntry | None:  # pragma: no cover - abstract
        raise NotImplementedError

    def set(self, key: str, entry: CacheEntry) -> None:  # pragma: no cover
        raise NotImplementedError

    def clear(self) -> None:  # pragma: no cover
        raise NotImplementedError

    def __contains__(self, key: str) -> bool:
        return self.get(key) is not None


class NullCache(BaseCache):
    def get(self, key: str) -> CacheEntry | None:
        return None

    def set(self, key: str, entry: CacheEntry) -> None:
        return

    def clear(self) -> None:
        return


class BasicCache(BaseCache):
    def __init__(self) -> None:
        self._store: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            return self._store.get(key)

    def set(self, key: str, entry: CacheEntry) -> None:
        with self._lock:
            self._store[key] = entry

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class LRUCache(BaseCache):
    def __init__(self, max_size: int = 128) -> None:
        self.max_size = max_size
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is not None:
                self._store.move_to_end(key)
            return entry

    def set(self, key: str, entry: CacheEntry) -> None:
        with self._lock:
            self._store[key] = entry
            self._store.move_to_end(key)
            while len(self._store) > self.max_size:
                self._store.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


class RAMPressureCache(BaseCache):
    def __init__(self, ram_budget_mb: int = 256) -> None:
        self.budget_bytes = ram_budget_mb * 1024 * 1024
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._used = 0
        self._lock = threading.RLock()

    def get(self, key: str) -> CacheEntry | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is not None:
                self._store.move_to_end(key)
            return entry

    def set(self, key: str, entry: CacheEntry) -> None:
        size = entry.size_bytes or _estimate_size(entry.value)
        entry.size_bytes = size
        with self._lock:
            if key in self._store:
                self._used -= self._store[key].size_bytes
            self._store[key] = entry
            self._store.move_to_end(key)
            self._used += size
            while self._used > self.budget_bytes and self._store:
                _, evicted = self._store.popitem(last=False)
                self._used -= evicted.size_bytes

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._used = 0


class HierarchicalCache(BaseCache):
    """Top-level cache with per-subgraph subcaches.

    Callers scoped to an expansion frame ask :meth:`subcache` for a nested
    :class:`BaseCache` so that ephemeral ids (``{parent}:{idx}:...``) are
    isolated.
    """

    def __init__(self, factory: Callable[[], BaseCache]) -> None:
        self._factory = factory
        self._top: BaseCache = factory()
        self._children: dict[str, "HierarchicalCache"] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> CacheEntry | None:
        return self._top.get(key)

    def set(self, key: str, entry: CacheEntry) -> None:
        self._top.set(key, entry)

    def clear(self) -> None:
        with self._lock:
            self._top.clear()
            self._children.clear()

    def subcache(self, scope: str) -> "HierarchicalCache":
        with self._lock:
            child = self._children.get(scope)
            if child is None:
                child = HierarchicalCache(self._factory)
                self._children[scope] = child
            return child


def _estimate_size(value: Any) -> int:
    try:
        return sys.getsizeof(json.dumps(_canonical(value)))
    except Exception:  # noqa: BLE001
        return sys.getsizeof(value)


# ---------------------------------------------------------------------------
# CacheSet (policy bundle)
# ---------------------------------------------------------------------------


@dataclass
class CacheSet:
    """Bundle of named caches passed to the runner.

    - ``outputs`` — memoizes ``NodeOutput`` values (keyed by input signature).
    - ``objects`` — memoizes live node instances (keyed by node_id) so we
      reuse the same Python object across runs of a not-idempotent node.
    - ``ui`` — holds UI payloads for ``executed`` events.
    """

    outputs: BaseCache
    objects: BasicCache = field(default_factory=BasicCache)
    ui: BasicCache = field(default_factory=BasicCache)

    def all(self) -> Iterable[BaseCache]:
        yield self.outputs
        yield self.objects
        yield self.ui

    def clear(self) -> None:
        for cache in self.all():
            cache.clear()


def build_cache_set(mode: str = "classic", **options: Any) -> CacheSet:
    """Construct a :class:`CacheSet` from a mode string.

    Supported modes: ``classic`` (BasicCache), ``lru``, ``ram``, ``none``.
    """
    mode = (mode or "classic").lower()
    if mode == "none":
        outputs: BaseCache = NullCache()
    elif mode == "lru":
        outputs = LRUCache(max_size=int(options.get("lru_size", 128)))
    elif mode == "ram":
        outputs = RAMPressureCache(ram_budget_mb=int(options.get("ram_mb", 256)))
    elif mode == "hierarchical":
        factory_name = options.get("factory", "basic")
        factory: Callable[[], BaseCache]
        if factory_name == "lru":
            size = int(options.get("lru_size", 128))
            factory = lambda: LRUCache(max_size=size)  # noqa: E731
        elif factory_name == "ram":
            mb = int(options.get("ram_mb", 256))
            factory = lambda: RAMPressureCache(ram_budget_mb=mb)  # noqa: E731
        else:
            factory = BasicCache
        outputs = HierarchicalCache(factory)
    else:
        outputs = BasicCache()
    return CacheSet(outputs=outputs)
