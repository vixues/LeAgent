"""Factory that lifts every registered :class:`BaseTool` into a dedicated
:class:`WorkflowNode` subclass.

The generic :class:`ToolCallNode` takes a ``tool_name`` string input and
accepts ``params`` as a free-form ``OBJECT``. That works, but the workflow
editor cannot render typed widgets or wire link compatibility per-tool.

This factory solves that by **auto-generating one palette entry per tool**:

* Node id:       ``Tool.<tool_name>`` (e.g. ``Tool.data_clean``)
* Category:      ``tools/<category>`` (e.g. ``tools/data``)
* Inputs:        derived from the tool's JSON Schema via
                 :func:`leagent.workflow.io.schema_bridge.json_schema_to_inputs`,
                 plus the shared execution controls
                 (``retry_count``, ``retry_delay_sec``, ``output``).
* Output:        a single ``result`` socket typed ``ANY`` (tools return
                 heterogeneous payloads).
* Hidden:        ``UNIQUE_ID``, ``TOOL_CONTEXT``, ``WORKFLOW_STATE`` so the
                 node can resolve templates and reuse the integration's
                 :class:`ToolExecutor`.

At execute time the generated class assembles the parameter dict from the
typed inputs, delegates to ``tool_context.tool_executor.execute``, honours
retries, and optionally stores the result into the workflow state under
the ``output`` variable name. The semantics match :class:`ToolCallNode`
1:1 so the two can coexist — generic string-dispatched tool calls stay
available for users who prefer them.

The generated classes are thin dynamically-constructed subclasses. They
are idempotent per-tool-instance (same schema → same class identity held
inside :data:`_FACTORY_CACHE`) so :func:`register_tool_nodes` can be
called multiple times (e.g. hot reload) without class churn.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, ClassVar, Iterable

import structlog

from leagent.tools.base import BaseTool, ToolCategory
from leagent.tools.registry import ToolRegistry
from leagent.workflow.io import (
    IO,
    Hidden,
    HiddenHolder,
    NodeOutput,
    Schema,
)
from leagent.workflow.io.schema_bridge import json_schema_to_inputs
from leagent.workflow.nodes.base import WorkflowNode
from leagent.workflow.nodes.registry import NodeRegistry

logger = structlog.get_logger(__name__)


# ``output``/``retry_*`` live on every generated node and are not part of
# the tool's own parameter schema. Tools that ship properties with these
# exact names would collide with the control-plane inputs, so the bridge
# drops them before generation.
_RESERVED_INPUT_IDS = frozenset({"retry_count", "retry_delay_sec", "output"})

_NODE_ID_PREFIX = "Tool."

_FACTORY_CACHE: dict[str, type[WorkflowNode]] = {}


def _tool_category_slug(category: ToolCategory | str) -> str:
    if isinstance(category, ToolCategory):
        return category.value
    return str(category or "util")


def _safe_class_name(tool_name: str) -> str:
    """Build a Python-safe class name for the generated node."""
    cleaned = "".join(c if c.isalnum() else "_" for c in tool_name)
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"T_{cleaned}"
    return f"Tool_{cleaned}_Node"


def _describe_tool(tool: BaseTool) -> str:
    base = (tool.description or "").strip()
    category = _tool_category_slug(tool.category)
    aliases = ", ".join(tool.aliases) if tool.aliases else ""
    parts = [base] if base else []
    meta_bits = [f"category={category}"]
    if aliases:
        meta_bits.append(f"aliases={aliases}")
    parts.append("(" + ", ".join(meta_bits) + ")")
    return " ".join(parts).strip()


def _build_schema(tool: BaseTool) -> Schema:
    typed_inputs = json_schema_to_inputs(tool.parameters, drop=_RESERVED_INPUT_IDS)
    category_slug = _tool_category_slug(tool.category)
    display = tool.name.replace("_", " ").title()
    return Schema(
        node_id=f"{_NODE_ID_PREFIX}{tool.name}",
        display_name=f"Tool: {display}",
        category=f"tools/{category_slug}",
        description=_describe_tool(tool),
        inputs=[
            *typed_inputs,
            IO.Int.Input(
                id="retry_count", optional=True, default=0, min=0, max=10,
                tooltip="Retry attempts on transient failure (exponential backoff).",
            ),
            IO.Float.Input(
                id="retry_delay_sec", optional=True, default=1.0,
                min=0.0, max=60.0, step=0.5,
                tooltip="Base delay between retries, doubled each attempt.",
            ),
            IO.String.Input(
                id="output", optional=True,
                tooltip="Optional workflow-state variable to store the result in.",
            ),
        ],
        outputs=[IO.Any.Output(id="result")],
        hidden=[Hidden.UNIQUE_ID, Hidden.TOOL_CONTEXT, Hidden.WORKFLOW_STATE],
        not_idempotent=not tool.is_read_only,
        metadata={
            "tool_name": tool.name,
            "tool_category": category_slug,
            "tool_version": tool.version,
            "tool_aliases": list(tool.aliases or []),
            "tool_is_read_only": tool.is_read_only,
            "tool_is_destructive": tool.is_destructive,
            "auto_generated": True,
        },
    )


def _collect_tool_params(
    schema: Schema,
    inputs: dict[str, Any],
) -> dict[str, Any]:
    """Extract tool parameters from node inputs, dropping control fields."""
    params: dict[str, Any] = {}
    for inp in schema.inputs:
        if inp.id in _RESERVED_INPUT_IDS:
            continue
        if inp.id not in inputs:
            continue
        value = inputs[inp.id]
        if value is None and inp.optional:
            continue
        params[inp.id] = value
    return params


class _GeneratedToolNodeBase(WorkflowNode):
    """Shared execute/schema plumbing for auto-generated tool nodes.

    Subclasses fill in :attr:`TOOL_NAME`; the rest of the behaviour is
    identical across tools and lives here to keep the generated classes
    as thin as possible.
    """

    TOOL_NAME: ClassVar[str] = ""

    @classmethod
    def define_schema(cls) -> Schema:  # pragma: no cover - overridden per tool
        raise NotImplementedError

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        ctx = hidden.tool_context
        if ctx is None or getattr(ctx, "tool_executor", None) is None:
            return NodeOutput(
                error="Tool executor not available",
                metadata={"node_id": hidden.unique_id, "tool": self.TOOL_NAME},
            )

        state = hidden.workflow_state
        schema = self.get_schema()
        params = _collect_tool_params(schema, inputs)
        if state is not None:
            params = state.resolve_template(params)

        retry_count = int(inputs.get("retry_count") or 0)
        retry_delay_sec = float(inputs.get("retry_delay_sec") or 1.0)
        output_var = inputs.get("output")

        tool_context = ctx.get_tool_context(state) if hasattr(ctx, "get_tool_context") else None

        start = time.monotonic()
        last_error: str | None = None
        tool_name = self.TOOL_NAME

        for attempt in range(retry_count + 1):
            try:
                exec_result = await ctx.tool_executor.execute(tool_name, params, tool_context)
                tool_result = exec_result.result
                if tool_result.success:
                    duration_ms = int((time.monotonic() - start) * 1000)
                    if state is not None and output_var:
                        state.set(output_var, tool_result.data)
                    return NodeOutput(
                        values=(tool_result.data,),
                        metadata={
                            "tool": tool_name,
                            "attempts": attempt + 1,
                            "duration_ms": duration_ms,
                            "auto_generated": True,
                        },
                    )
                last_error = tool_result.error or "Tool execution failed"
                logger.warning(
                    "tool_node_failed",
                    tool=tool_name, attempt=attempt + 1, error=last_error,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                logger.error(
                    "tool_node_exception",
                    tool=tool_name, attempt=attempt + 1,
                    error=last_error, exc_info=True,
                )

            if attempt < retry_count:
                await asyncio.sleep(retry_delay_sec * (2 ** attempt))

        duration_ms = int((time.monotonic() - start) * 1000)
        return NodeOutput(
            error=last_error,
            metadata={
                "tool": tool_name,
                "attempts": retry_count + 1,
                "duration_ms": duration_ms,
                "auto_generated": True,
            },
        )


def build_node_class(tool: BaseTool) -> type[WorkflowNode]:
    """Return the generated :class:`WorkflowNode` subclass for ``tool``.

    The result is cached per-``tool.name`` to preserve class identity
    across repeated calls (needed because ``WorkflowNode`` caches its
    compiled schema on the class object).
    """
    node_id = f"{_NODE_ID_PREFIX}{tool.name}"
    cached = _FACTORY_CACHE.get(tool.name)
    if cached is not None and cached.NODE_ID == node_id:
        return cached

    schema = _build_schema(tool)

    def define_schema(cls, _schema=schema) -> Schema:
        return _schema

    cls_name = _safe_class_name(tool.name)
    cls: type[WorkflowNode] = type(
        cls_name,
        (_GeneratedToolNodeBase,),
        {
            "NODE_ID": node_id,
            "TOOL_NAME": tool.name,
            "define_schema": classmethod(define_schema),
            "__doc__": f"Auto-generated workflow node for tool '{tool.name}'.",
        },
    )

    _FACTORY_CACHE[tool.name] = cls
    return cls


def register_tool_nodes(
    node_registry: NodeRegistry,
    tool_registry: ToolRegistry,
    *,
    tools: Iterable[BaseTool] | None = None,
) -> list[str]:
    """Register one generated ``Tool.<name>`` node per registered tool.

    If ``tools`` is omitted, every tool currently in ``tool_registry`` is
    registered. Safe to call repeatedly (existing node classes are reused
    via :data:`_FACTORY_CACHE`).
    """
    registered: list[str] = []
    skipped: list[tuple[str, str]] = []
    source = list(tools) if tools is not None else tool_registry.list_all()

    for tool in source:
        try:
            cls = build_node_class(tool)
            node_registry.register(
                cls, module_path=f"tool_factory:{tool.name}",
            )
            registered.append(cls.NODE_ID)
        except Exception as exc:  # noqa: BLE001
            skipped.append((tool.name, str(exc)))
            logger.error(
                "tool_node_factory_failed",
                tool=tool.name, error=str(exc), exc_info=True,
            )

    logger.info(
        "tool_nodes_registered",
        count=len(registered),
        skipped=len(skipped),
    )
    return registered


def clear_factory_cache() -> None:
    """Reset the generated-node cache.

    Primarily for tests and hot-reload flows that rebuild the tool
    registry with fresh tool instances.
    """
    _FACTORY_CACHE.clear()
