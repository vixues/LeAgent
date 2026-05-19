"""Thread-safe registry of ``WorkflowNode`` classes.

Mirrors ComfyUI's ``NODE_CLASS_MAPPINGS`` but with proper encapsulation,
hot-reload support (``unregister`` + ``reload``), and a ``snapshot()``
for the ``/object_info`` endpoint. All mutations take a reentrant lock.
"""

from __future__ import annotations

import threading
from typing import Any, Iterator

import structlog

from leagent.workflow.io import Schema

from .base import WorkflowNode

logger = structlog.get_logger(__name__)


class NodeRegistry:
    """Registry of node classes keyed by their ``node_id``."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._classes: dict[str, type[WorkflowNode]] = {}
        self._display: dict[str, str] = {}
        self._module_index: dict[str, set[str]] = {}  # module_path -> node_ids

    def register(self, cls: type[WorkflowNode], *, module_path: str | None = None) -> None:
        """Register a node class. Duplicates overwrite the previous class."""
        if not issubclass(cls, WorkflowNode):
            raise TypeError(f"{cls!r} is not a WorkflowNode subclass")
        schema = cls.get_schema()
        node_id = schema.node_id or cls.NODE_ID or cls.__name__
        schema.node_id = node_id
        with self._lock:
            prev = self._classes.get(node_id)
            if prev is not None and prev is not cls:
                logger.info("node_registry_override", node_id=node_id, prev=prev.__name__, new=cls.__name__)
            self._classes[node_id] = cls
            self._display[schema.display_name or node_id] = node_id
            if module_path:
                cls.MODULE_PATH = module_path
                self._module_index.setdefault(module_path, set()).add(node_id)
            logger.debug("node_registered", node_id=node_id, module=module_path)

    def unregister(self, node_id: str) -> None:
        with self._lock:
            cls = self._classes.pop(node_id, None)
            if cls is None:
                return
            schema = getattr(cls, "_schema_cache", None)
            if schema:
                self._display.pop(schema.display_name, None)
            if cls.MODULE_PATH:
                mod_set = self._module_index.get(cls.MODULE_PATH)
                if mod_set:
                    mod_set.discard(node_id)
                    if not mod_set:
                        self._module_index.pop(cls.MODULE_PATH, None)
            logger.debug("node_unregistered", node_id=node_id)

    def unregister_module(self, module_path: str) -> list[str]:
        """Unregister all node ids previously loaded from ``module_path``.

        Returns the list of removed node ids.
        """
        with self._lock:
            ids = list(self._module_index.get(module_path, ()))
            for nid in ids:
                self.unregister(nid)
            return ids

    def get(self, node_id: str) -> type[WorkflowNode] | None:
        with self._lock:
            return self._classes.get(node_id)

    def require(self, node_id: str) -> type[WorkflowNode]:
        cls = self.get(node_id)
        if cls is None:
            raise KeyError(f"Node class not registered: {node_id}")
        return cls

    def list_ids(self) -> list[str]:
        with self._lock:
            return list(self._classes.keys())

    def items(self) -> Iterator[tuple[str, type[WorkflowNode]]]:
        with self._lock:
            return iter(list(self._classes.items()))

    def clear(self) -> None:
        with self._lock:
            self._classes.clear()
            self._display.clear()
            self._module_index.clear()

    def schemas(self) -> dict[str, Schema]:
        with self._lock:
            return {nid: cls.get_schema() for nid, cls in self._classes.items()}

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Return the full ``/object_info`` payload."""
        with self._lock:
            return {nid: cls.get_schema().get_info_dict() for nid, cls in self._classes.items()}


_DEFAULT_REGISTRY: NodeRegistry | None = None


def get_registry() -> NodeRegistry:
    """Return the process-wide default registry (lazily constructed)."""
    global _DEFAULT_REGISTRY
    if _DEFAULT_REGISTRY is None:
        _DEFAULT_REGISTRY = NodeRegistry()
    return _DEFAULT_REGISTRY


def reset_registry() -> None:
    global _DEFAULT_REGISTRY
    _DEFAULT_REGISTRY = NodeRegistry()
