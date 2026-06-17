"""Per-node execution pipeline.

Runs a single node's lifecycle: cache lookup, input resolution,
lazy-input check, ``execute``, ``NodeOutput`` finalization. Calls into the
:class:`ProgressRegistry` and the optional :class:`CacheProvider` around
each step.
"""

from __future__ import annotations

import time
from typing import Any

from leagent.workflow.io import Hidden, HiddenHolder, NodeOutput
from leagent.workflow.io.contract import NOT_CACHEABLE
from leagent.workflow.nodes import NodeRegistry

from .cache_provider import CacheProvider, NullCacheProvider
from .caching import BaseCache, CacheEntry, CacheKeySet
from .errors import NodeExecutionError, WorkflowEngineError
from .progress import CurrentNodeContext, NodeStatus, ProgressRegistry


class NodeRunResult:
    __slots__ = ("output", "cached", "duration_ms", "error")

    def __init__(self, output: NodeOutput | None, *, cached: bool = False,
                 duration_ms: int = 0, error: str | None = None) -> None:
        self.output = output
        self.cached = cached
        self.duration_ms = duration_ms
        self.error = error


class NodeRunner:
    """Executes a single node per call. Stateless apart from injected deps."""

    def __init__(
        self,
        *,
        registry: NodeRegistry,
        output_cache: BaseCache,
        object_cache: BaseCache,
        cache_keys: CacheKeySet,
        progress: ProgressRegistry,
        cache_provider: CacheProvider | None = None,
    ) -> None:
        self.registry = registry
        self.output_cache = output_cache
        self.object_cache = object_cache
        self.cache_keys = cache_keys
        self.progress = progress
        self.cache_provider = cache_provider or NullCacheProvider()

    async def run(
        self,
        node_id: str,
        node_def: dict[str, Any],
        upstream_values: dict[tuple[str, int], Any],
        hidden: HiddenHolder,
    ) -> NodeRunResult:
        """Execute a single node. Resolves link inputs from ``upstream_values``."""

        class_type = node_def.get("class_type", "")
        node_cls = self.registry.get(class_type)
        if node_cls is None:
            return NodeRunResult(None, error=f"Unknown node class: {class_type}")

        schema = node_cls.get_schema()

        # -------------------- input marshalling --------------------
        resolved_inputs: dict[str, Any] = {}
        for key_name, value in (node_def.get("inputs") or {}).items():
            # Single link reference: [upstream_id, slot]
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                up_id, slot = value
                resolved_inputs[key_name] = upstream_values.get((up_id, int(slot)))
                continue

            # Multi-link reference (ARRAY input): [[upstream_id, slot], ...]
            if (
                isinstance(value, list)
                and value
                and all(
                    isinstance(item, list)
                    and len(item) == 2
                    and isinstance(item[0], str)
                    for item in value
                )
            ):
                out: list[Any] = []
                for up_id, slot in value:
                    out.append(upstream_values.get((up_id, int(slot))))
                resolved_inputs[key_name] = out
                continue

            resolved_inputs[key_name] = value

        # -------------------- instance memoization --------------------
        instance_entry = self.object_cache.get(node_id)
        if instance_entry is None:
            instance = node_cls()
            self.object_cache.set(node_id, CacheEntry(value=instance))
        else:
            instance = instance_entry.value

        # -------------------- cache lookup (fingerprint-aware) --------------------
        fingerprint: Any = None
        cacheable = not schema.not_idempotent
        if cacheable:
            try:
                fingerprint = instance.fingerprint_inputs(**resolved_inputs)
            except Exception:
                fingerprint = None
            if fingerprint is NOT_CACHEABLE:
                cacheable = False

        base_key = self.cache_keys.signature(node_id)
        key = base_key if fingerprint in (None, NOT_CACHEABLE) else f"{base_key}#{fingerprint}"

        if cacheable:
            cached = self.output_cache.get(key)
            if cached is None:
                provider_hit = await self.cache_provider.on_lookup(key)
                if provider_hit is not None:
                    cached = CacheEntry(value=_output_from_payload(provider_hit))
            if cached is not None:
                self.progress.set_status(node_id, NodeStatus.CACHED)
                return NodeRunResult(cached.value, cached=True)

        # -------------------- lazy input resolution --------------------
        has_lazy = any(getattr(inp, "lazy", False) for inp in schema.inputs)
        if has_lazy:
            try:
                pending = instance.check_lazy_status(**resolved_inputs)
            except Exception:  # noqa: BLE001
                pending = []
            missing = [iid for iid in pending if iid not in resolved_inputs
                       or resolved_inputs[iid] is None]
            for iid in missing:
                resolved_inputs.setdefault(iid, None)

        scoped_hidden = hidden.with_unique_id(node_id)
        self.progress.set_status(node_id, NodeStatus.RUNNING)
        start = time.monotonic()
        try:
            with CurrentNodeContext(node_id):
                output = await instance.execute(hidden=scoped_hidden, **resolved_inputs)
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.monotonic() - start) * 1000)
            self.progress.set_status(node_id, NodeStatus.ERROR, error=str(exc))
            raise NodeExecutionError(str(exc), node_id=node_id) from exc

        if not isinstance(output, NodeOutput):
            output = NodeOutput(values=output)

        duration_ms = int((time.monotonic() - start) * 1000)

        if getattr(output, "expand", None) and not schema.enable_expand:
            raise WorkflowEngineError(
                f"Node '{node_id}' ({class_type}) returned NodeOutput.expand "
                "but its Schema did not set enable_expand=True",
            )

        if output.error:
            self.progress.set_status(node_id, NodeStatus.ERROR, error=output.error,
                                     metadata={"duration_ms": duration_ms})
            return NodeRunResult(output, duration_ms=duration_ms, error=output.error)

        if output.block_execution:
            self.progress.set_status(node_id, NodeStatus.BLOCKED,
                                     metadata={"tag": output.block_execution,
                                               "duration_ms": duration_ms})
            return NodeRunResult(output, duration_ms=duration_ms)

        # -------------------- cache writeback --------------------
        if cacheable:
            self.output_cache.set(key, CacheEntry(value=output))
            if self.cache_provider.should_cache(key, node_def):
                await self.cache_provider.on_store(key, _payload_from_output(output))

        self.progress.set_status(node_id, NodeStatus.SUCCESS,
                                 metadata={"duration_ms": duration_ms, **output.metadata})
        return NodeRunResult(output, duration_ms=duration_ms)


def _payload_from_output(output: NodeOutput) -> dict[str, Any]:
    return {
        "values": list(output.as_tuple()),
        "ui": output.ui,
        "metadata": output.metadata,
        "next_node": output.next_node,
    }


def _output_from_payload(payload: Any) -> NodeOutput:
    if isinstance(payload, dict):
        return NodeOutput(
            values=tuple(payload.get("values") or ()),
            ui=payload.get("ui"),
            metadata=dict(payload.get("metadata", {}) or {}),
            next_node=payload.get("next_node"),
        )
    return NodeOutput(values=payload)
