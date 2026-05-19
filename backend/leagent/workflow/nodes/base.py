"""Abstract ``WorkflowNode`` base class.

Schema-driven. Subclasses declare ``define_schema()`` returning a ``Schema``
instance; the metaclass caches it. ``execute`` is async and must return a
``NodeOutput`` envelope.

Classproperties ``INPUT_TYPES``, ``RETURN_TYPES``, ``RETURN_NAMES``,
``CATEGORY`` emit the frontend-facing metadata for ``/object_info`` and
the validator.

Contract hooks (override per node as needed):

* :meth:`fingerprint_inputs` — replaces the ``IS_CHANGED`` pattern.
  Return a hashable fingerprint (string), or
  :data:`~leagent.workflow.io.contract.NOT_CACHEABLE` to bypass the cache.
* :meth:`check_lazy_status` — return the list of input ids that still
  need to be resolved before :meth:`execute` can run. An empty list means
  "ready to execute". Consulted only when any declared input is
  ``lazy=True``.
"""

from __future__ import annotations

import abc
from typing import Any, ClassVar

from leagent.workflow.io import Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.io.contract import (
    NOT_CACHEABLE,
    default_check_lazy_status,
    default_fingerprint_inputs,
)


class _WorkflowNodeMeta(abc.ABCMeta):
    """Metaclass that lazily caches ``define_schema()`` results per class."""

    def __init__(cls, name: str, bases: tuple[type, ...], namespace: dict[str, Any]):
        super().__init__(name, bases, namespace)
        cls._schema_cache = None


class WorkflowNode(abc.ABC, metaclass=_WorkflowNodeMeta):
    """Abstract base class for all workflow nodes."""

    #: Human-readable identifier registered in the node registry.
    NODE_ID: ClassVar[str] = ""

    #: Set by :func:`nodes.loader.register_module` at load time.
    MODULE_PATH: ClassVar[str] = ""

    @classmethod
    @abc.abstractmethod
    def define_schema(cls) -> Schema:  # pragma: no cover - abstract
        raise NotImplementedError

    @classmethod
    def get_schema(cls) -> Schema:
        if cls._schema_cache is None:
            schema = cls.define_schema().finalize()
            if not schema.node_id and cls.NODE_ID:
                schema.node_id = cls.NODE_ID
            cls._schema_cache = schema
        return cls._schema_cache

    @classmethod
    def invalidate_schema_cache(cls) -> None:
        cls._schema_cache = None

    # ------------------------------------------------------------------
    # V1 compatibility views (mirror ComfyUI's _ComfyNodeBaseInternal)
    # ------------------------------------------------------------------

    @classmethod
    def INPUT_TYPES(cls) -> dict[str, Any]:  # noqa: N802 - ComfyUI convention
        return cls.get_schema().get_info_dict()["input"]

    @classmethod
    def RETURN_TYPES(cls) -> tuple[str, ...]:  # noqa: N802
        return cls.get_schema().return_types()

    @classmethod
    def RETURN_NAMES(cls) -> tuple[str, ...]:  # noqa: N802
        return cls.get_schema().return_names()

    @classmethod
    def CATEGORY(cls) -> str:  # noqa: N802
        return cls.get_schema().category

    @classmethod
    def IS_OUTPUT_NODE(cls) -> bool:  # noqa: N802
        return cls.get_schema().is_output_node

    @classmethod
    def IS_CHANGED(cls, **kwargs: Any) -> Any:  # noqa: N802
        """Legacy alias for :meth:`fingerprint_inputs`.

        Kept for nodes that historically relied on the ``IS_CHANGED``
        convention. The default signals the cache layer that the node
        never considers itself cacheable from this call site.
        """
        return float("nan")

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    @abc.abstractmethod
    async def execute(
        self,
        *,
        hidden: HiddenHolder,
        **inputs: Any,
    ) -> NodeOutput:
        """Execute this node with resolved inputs and hidden context."""

    # ------------------------------------------------------------------
    # Hooks
    # ------------------------------------------------------------------

    async def on_validate(self, inputs: dict[str, Any]) -> list[str]:
        """Optional per-instance validation hook returning error strings."""
        return []

    def fingerprint_inputs(self, **kwargs: Any) -> Any:
        """Return a stable fingerprint used to salt the output cache key.

        Override to bust the cache when an external source changes (file
        mtime, remote API response, secret rotation). Return
        :data:`~leagent.workflow.io.contract.NOT_CACHEABLE` to skip
        caching entirely on this call.
        """
        return default_fingerprint_inputs(self, **kwargs)

    def check_lazy_status(self, **kwargs: Any) -> list[str]:
        """Return input ids still needing resolution before :meth:`execute`.

        Called only when the node's schema declares at least one input with
        ``lazy=True``. Returning an empty list signals the runner that all
        required inputs are resolved and execution can begin.
        """
        return default_check_lazy_status(self, **kwargs)
