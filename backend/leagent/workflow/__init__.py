"""Workflow engine package.

Modular architecture:

- :mod:`leagent.workflow.io` — typed primitives, schema, node-output
  envelope, validation, (de)serialization. Single canonical schema —
  no version migration layer.
- :mod:`leagent.workflow.nodes` — abstract :class:`WorkflowNode` base,
  registry, extension/plugin contract, filesystem + entrypoint loader,
  hot-reload watcher, node replacement registry, and built-in nodes.
- :mod:`leagent.workflow.engine` — async :class:`WorkflowExecutor`,
  dynamic-prompt scheduler, cache strategies + cross-worker provider,
  progress/event registry, structured error taxonomy.
- :mod:`leagent.workflow.queue` — pluggable prompt queue (in-memory).
- :mod:`leagent.workflow.worker` — long-lived worker loop consuming
  the queue and driving the executor.
- :mod:`leagent.workflow.server` — FastAPI router, WebSocket handlers,
  event bus, prompt hooks, pydantic request/response schemas.
- :mod:`leagent.workflow.services` — DB-backed
  :class:`WorkflowService` used by the application layer.
- :mod:`leagent.workflow.registry` — flow document registry backed
  by the ``flows`` table.

Runtime data models (``WorkflowState``, ``WorkflowResult``,
``NodeExecutionResult``, etc.) live in :mod:`leagent.workflow.base`
and are re-exported here for consumers that want a flat import path.
"""

from __future__ import annotations

from leagent.workflow.base import (
    ConditionExpression,
    ConditionOperator,
    NodeExecutionResult,
    WorkflowResult,
    WorkflowState,
    WorkflowStatus,
)
from leagent.workflow.engine import (
    BaseCache,
    BasicCache,
    CacheProvider,
    CacheSet,
    DependencyCycleError,
    DynamicPrompt,
    ExecutionList,
    HierarchicalCache,
    LRUCache,
    NodeExecutionError,
    NodeRunner,
    ProgressEvent,
    ProgressRegistry,
    TopologicalSort,
    ValidationError,
    WorkflowEngineError,
    WorkflowExecutor,
    build_cache_set,
)
from leagent.workflow.registry import FlowWorkflowRegistry
from leagent.workflow.services import WorkflowService
from leagent.workflow.io import (
    IO,
    Hidden,
    HiddenHolder,
    NodeOutput,
    Schema,
    WorkflowDocument,
    export,
    graph_hash,
    load,
    to_json,
    to_yaml,
    validate,
)
from leagent.workflow.nodes import (
    HotReloader,
    NodeExtension,
    NodeRegistry,
    NodeReplaceRegistry,
    NodeReplacement,
    WorkflowNode,
    bootstrap,
    get_registry,
    get_replace_registry,
)
from leagent.workflow.queue import (
    InMemoryPromptQueue,
    PromptHistoryEntry,
    PromptItem,
    PromptQueue,
)

__all__ = [
    # IO
    "IO",
    "Hidden",
    "HiddenHolder",
    "NodeOutput",
    "Schema",
    "WorkflowDocument",
    "export",
    "graph_hash",
    "load",
    "to_json",
    "to_yaml",
    "validate",
    # Nodes
    "HotReloader",
    "NodeExtension",
    "NodeRegistry",
    "NodeReplaceRegistry",
    "NodeReplacement",
    "WorkflowNode",
    "bootstrap",
    "get_registry",
    "get_replace_registry",
    # Engine
    "BaseCache",
    "BasicCache",
    "CacheProvider",
    "CacheSet",
    "DependencyCycleError",
    "DynamicPrompt",
    "ExecutionList",
    "HierarchicalCache",
    "LRUCache",
    "NodeExecutionError",
    "NodeRunner",
    "ProgressEvent",
    "ProgressRegistry",
    "TopologicalSort",
    "ValidationError",
    "WorkflowEngineError",
    "WorkflowExecutor",
    "build_cache_set",
    # Queue
    "InMemoryPromptQueue",
    "PromptHistoryEntry",
    "PromptItem",
    "PromptQueue",
    # Services / registry
    "FlowWorkflowRegistry",
    "WorkflowService",
    # Runtime types (from leagent.workflow.base)
    "ConditionExpression",
    "ConditionOperator",
    "NodeExecutionResult",
    "WorkflowResult",
    "WorkflowState",
    "WorkflowStatus",
]
