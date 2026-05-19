"""High-performance async workflow execution engine.

Public surface:

- :class:`WorkflowExecutor` — top-level orchestrator.
- :class:`ExecutionList` / :class:`DynamicPrompt` / :class:`TopologicalSort`
  — scheduler primitives (exposed mainly for tests and advanced callers).
- :class:`CacheSet` / :func:`build_cache_set` — output caching policy.
- :class:`CacheProvider` / :class:`NullCacheProvider` — cache abstraction.
- :class:`ProgressRegistry` — runtime progress/event bus.
- :mod:`errors` — structured exception taxonomy.
"""

from __future__ import annotations

from .cache_provider import CacheProvider, NullCacheProvider
from .caching import (
    BaseCache,
    BasicCache,
    CacheEntry,
    CacheKeySet,
    CacheKeySetID,
    CacheKeySetInputSignature,
    CacheSet,
    HierarchicalCache,
    LRUCache,
    NullCache,
    RAMPressureCache,
    build_cache_set,
    hash_signature,
    immediate_node_signature,
)
from .errors import (
    BlockedError,
    DependencyCycleError,
    InterruptedError,
    NodeExecutionError,
    ValidationError,
    WorkflowEngineError,
)
from .executor import WorkflowExecutor
from .graph import DynamicPrompt, ExecutionList, ExpandFrame, TopologicalSort
from .progress import (
    CurrentNodeContext,
    NodeProgressState,
    NodeStatus,
    ProgressEvent,
    ProgressHandler,
    ProgressRegistry,
)
from .runner import NodeRunner, NodeRunResult

__all__ = [
    "BaseCache",
    "BasicCache",
    "BlockedError",
    "CacheEntry",
    "CacheKeySet",
    "CacheKeySetID",
    "CacheKeySetInputSignature",
    "CacheProvider",
    "CacheSet",
    "CurrentNodeContext",
    "DependencyCycleError",
    "DynamicPrompt",
    "ExecutionList",
    "ExpandFrame",
    "HierarchicalCache",
    "InterruptedError",
    "LRUCache",
    "NodeExecutionError",
    "NodeProgressState",
    "NodeRunResult",
    "NodeRunner",
    "NodeStatus",
    "NullCache",
    "NullCacheProvider",
    "ProgressEvent",
    "ProgressHandler",
    "ProgressRegistry",
    "RAMPressureCache",
    "TopologicalSort",
    "ValidationError",
    "WorkflowEngineError",
    "WorkflowExecutor",
    "build_cache_set",
    "hash_signature",
    "immediate_node_signature",
]
