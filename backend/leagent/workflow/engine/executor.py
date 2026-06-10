"""Top-level workflow executor.

Combines :class:`ExecutionList`, :class:`NodeRunner`, and the cache set
into a single async pipeline. Entry points:

- :meth:`WorkflowExecutor.execute_async` — run a prompt end-to-end.
- :meth:`WorkflowExecutor.resume` — reattach to a blocked execution.
- :meth:`WorkflowExecutor.cancel` — mark a state id cancelled.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

import structlog

from leagent.workflow.base import (
    NodeExecutionResult,
    WorkflowResult,
    WorkflowState,
    WorkflowStatus,
)
from leagent.workflow.io import (
    Hidden,
    HiddenHolder,
    NodeOutput,
    WorkflowDocument,
    load,
    validate,
)
from leagent.workflow.nodes import NodeRegistry, get_registry

from .cache_provider import CacheProvider, NullCacheProvider
from .caching import CacheKeySetInputSignature, CacheSet, build_cache_set
from .errors import (
    DependencyCycleError,
    NodeExecutionError,
    ValidationError,
)
from .graph import DynamicPrompt, ExecutionList, ExpandFrame, TopologicalSort
from .progress import NodeStatus, ProgressEvent, ProgressHandler, ProgressRegistry
from .runner import NodeRunner, NodeRunResult

logger = structlog.get_logger(__name__)


def _merge_schema_input_defaults(
    doc: WorkflowDocument,
    inputs: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge workflow schema defaults with caller-supplied inputs (user wins)."""
    defaults: dict[str, Any] = {}
    for spec in doc.inputs or []:
        if not isinstance(spec, dict):
            continue
        name = spec.get("name")
        if not name:
            continue
        key = str(name)
        if "default" in spec:
            defaults[key] = spec["default"]
        elif "value" in spec:
            defaults[key] = spec["value"]
    user = dict(inputs or {})
    return {**defaults, **user}


class WorkflowExecutor:
    """Orchestrates a single workflow execution.

    Keeps only transient state; a long-lived instance is safe to reuse
    across runs (matches the worker-process pattern).
    """

    def __init__(
        self,
        *,
        tool_registry: Any = None,
        tool_executor: Any = None,
        llm_service: Any = None,
        review_service: Any = None,
        workflow_registry: Any = None,
        agent_controller: Any = None,
        agent_runtime: Any = None,
        cache_set: CacheSet | None = None,
        cache_provider: CacheProvider | None = None,
        node_registry: NodeRegistry | None = None,
        progress_handlers: list[ProgressHandler] | None = None,
        cache_mode: str = "classic",
    ) -> None:
        self.tool_registry = tool_registry
        self.tool_executor = tool_executor
        self.llm_service = llm_service
        self.review_service = review_service
        self.workflow_registry = workflow_registry
        self.agent_controller = agent_controller
        self.agent_runtime = agent_runtime
        self.cache_set = cache_set or build_cache_set(cache_mode)
        self.cache_provider = cache_provider or NullCacheProvider()
        self.node_registry = node_registry or get_registry()
        self._progress_handlers: list[ProgressHandler] = list(progress_handlers or [])
        self._active_lists: dict[str, ExecutionList] = {}
        self._states: dict[str, WorkflowState] = {}
        self._abort_events: dict[str, asyncio.Event] = {}

    # ------------------------------------------------------------------
    # Convenience facade
    # ------------------------------------------------------------------

    async def execute(self, definition: Any, inputs: dict[str, Any] | None = None) -> WorkflowResult:
        """Run a workflow and return a :class:`WorkflowResult`.

        ``definition`` may be a :class:`WorkflowDocument`, a canonical
        document dict, or a path — anything :func:`io.load` accepts.
        """
        doc = _ensure_document(definition)
        prompt_id = str(uuid4())
        return await self.execute_async(doc, inputs or {}, prompt_id=prompt_id)

    async def execute_async(
        self,
        doc: WorkflowDocument,
        inputs: dict[str, Any],
        *,
        prompt_id: str,
        extra_data: dict[str, Any] | None = None,
        outputs_to_execute: list[str] | None = None,
        resume_state: WorkflowState | None = None,
        abort_event: asyncio.Event | None = None,
    ) -> WorkflowResult:
        """Main entry point.

        ``resume_state`` continues a paused run on its existing state so
        accumulated variables (``__resume__<node>`` answers, stashed agent
        checkpoints) survive into the re-run. ``abort_event`` lets a parent
        run (subworkflow) share its abort signal with the child.
        """

        ok, output_nodes, errors = validate(doc, registry=self.node_registry)
        if not ok:
            raise ValidationError("Workflow validation failed", errors=errors)

        if outputs_to_execute:
            output_nodes = [n for n in outputs_to_execute if n in doc.nodes] or output_nodes

        merged_inputs = _merge_schema_input_defaults(doc, inputs)

        if resume_state is not None:
            state = resume_state
            state.status = WorkflowStatus.RUNNING
            state.completed_at = None
            for key, value in merged_inputs.items():
                state.variables.setdefault(key, value)
        else:
            state = WorkflowState(
                workflow_id=doc.id or prompt_id,
                status=WorkflowStatus.RUNNING,
                inputs=dict(merged_inputs),
                variables=dict(merged_inputs),
                started_at=datetime.utcnow(),
            )
        # Propagate extra_data (user_id, session_id, tenant, auth) onto the
        # state so per-node helpers (tool_context builder, audit trail) can
        # read them without having to thread HiddenHolder everywhere.
        if extra_data:
            state.metadata.update(
                {k: v for k, v in extra_data.items() if v is not None}
            )
            state.metadata["prompt_id"] = prompt_id
        state_id = str(state.id)
        self._states[state_id] = state
        # Per-run abort signal: ``cancel`` sets it so in-flight long-running
        # nodes (agent turns) stop instead of running to completion. A parent
        # run may supply its own event so cancellation reaches subworkflows.
        if abort_event is None:
            abort_event = self._abort_events.get(state_id) or asyncio.Event()
        self._abort_events[state_id] = abort_event

        progress = ProgressRegistry(prompt_id=prompt_id)
        for h in self._progress_handlers:
            progress.add_handler(h)

        progress.emit(ProgressEvent(type="execution_start", prompt_id=prompt_id,
                                     data={"workflow_id": doc.id, "outputs": output_nodes}))

        prompt = DynamicPrompt(doc.nodes)
        topo = TopologicalSort(prompt)
        exec_list = ExecutionList(prompt, topo)
        self._active_lists[state_id] = exec_list

        for out_id in output_nodes:
            exec_list.add_node(out_id)
        if cycles := exec_list.detect_cycles():
            raise DependencyCycleError(f"Dependency cycles detected: {cycles}")

        cache_keys = CacheKeySetInputSignature(prompt, registry=self.node_registry)
        await self.cache_provider.on_prompt_start(prompt_id)

        runner = NodeRunner(
            registry=self.node_registry,
            output_cache=self.cache_set.outputs,
            object_cache=self.cache_set.objects,
            cache_keys=cache_keys,
            progress=progress,
            cache_provider=self.cache_provider,
        )

        hidden = HiddenHolder(
            prompt=doc.nodes,
            dynprompt=prompt,
            execution_id=prompt_id,
            user_id=(extra_data or {}).get("user_id"),
            session_id=(extra_data or {}).get("session_id"),
            tool_context=_ContextShim(self),
            llm_service=self.llm_service,
            review_service=self.review_service,
            agent_runtime=self.agent_runtime,
            workflow_state=state,
            logger=logger,
            progress=progress,
            abort_event=abort_event,
        )

        upstream_values: dict[tuple[str, int], Any] = {}
        start_ts = time.monotonic()
        errors_list: list[str] = []
        try:
            await self._run_loop(exec_list, runner, doc, hidden, state,
                                  upstream_values, progress, prompt_id, errors_list,
                                  cache_keys)
        finally:
            await self.cache_provider.on_prompt_end(prompt_id)
            self._active_lists.pop(state_id, None)
            self._abort_events.pop(state_id, None)

        duration_ms = int((time.monotonic() - start_ts) * 1000)
        state.completed_at = datetime.utcnow()

        if errors_list:
            state.status = WorkflowStatus.FAILED
        elif state.status not in (WorkflowStatus.WAITING_HUMAN, WorkflowStatus.PAUSED,
                                  WorkflowStatus.CANCELLED):
            state.status = WorkflowStatus.COMPLETED

        # Resolve declared outputs from document.outputs
        resolved_outputs = self._resolve_outputs(doc, state)
        progress.emit(ProgressEvent(
            type="execution_success" if state.status == WorkflowStatus.COMPLETED else f"execution_{state.status.value}",
            prompt_id=prompt_id,
            data={"duration_ms": duration_ms, "outputs": resolved_outputs,
                  "errors": errors_list},
        ))

        return WorkflowResult(
            workflow_id=doc.id or prompt_id,
            state_id=state.id,
            status=state.status,
            outputs=resolved_outputs or dict(state.outputs),
            errors=errors_list,
            execution_history=list(state.execution_history),
            duration_ms=duration_ms,
            metadata={"prompt_id": prompt_id},
        )

    # ------------------------------------------------------------------
    # Main scheduler loop
    # ------------------------------------------------------------------

    async def _run_loop(
        self,
        exec_list: ExecutionList,
        runner: NodeRunner,
        doc: WorkflowDocument,
        hidden: HiddenHolder,
        state: WorkflowState,
        upstream_values: dict[tuple[str, int], Any],
        progress: ProgressRegistry,
        prompt_id: str,
        errors_list: list[str],
        cache_keys: CacheKeySetInputSignature,
    ) -> None:
        start_id = doc.start_id
        if start_id in doc.nodes:
            exec_list.add_node(start_id)

        while not exec_list.is_done():
            node_id = await exec_list.stage_node_execution()
            if node_id is None:
                break
            node_def = exec_list.prompt.get(node_id)
            if node_def is None:
                exec_list.complete_node_execution(node_id)
                continue
            state.current_node = node_id

            # ComfyUI-style node modes: ``mute`` skips the node entirely,
            # ``bypass`` passes type-matching inputs straight through to the
            # outputs. Both are stored on ``meta.mode`` by the editor.
            mode = _node_mode(node_def)
            if mode in ("mute", "bypass"):
                progress.set_status(node_id, NodeStatus.SKIPPED,
                                    metadata={"mode": mode})
                result = NodeRunResult(
                    _mode_passthrough_output(
                        self.node_registry, node_def, upstream_values, mode,
                    ),
                    duration_ms=0,
                )
            else:
                try:
                    result = await runner.run(node_id, node_def, upstream_values, hidden)
                except NodeExecutionError as exc:
                    errors_list.append(f"{node_id}: {exc}")
                    state.error_stack.append(f"{node_id}: {exc}")
                    exec_list.fail_node_execution(node_id)
                    state.record_execution(NodeExecutionResult(
                        node_id=node_id, status=WorkflowStatus.FAILED, error=str(exc),
                    ))
                    control = node_def.get("control", {}) or {}
                    if control.get("error_handler"):
                        exec_list.select_branch(node_id, control["error_handler"])
                        exec_list.add_node(control["error_handler"])
                    continue

            output = result.output or NodeOutput()

            # Populate upstream_values (slot-indexed tuple)
            for slot, val in enumerate(output.as_tuple()):
                upstream_values[(node_id, slot)] = val

            # Control-flow routing
            control = node_def.get("control", {}) or {}
            class_type = node_def.get("class_type", "")

            if output.error and not result.cached:
                errors_list.append(f"{node_id}: {output.error}")
                state.error_stack.append(f"{node_id}: {output.error}")
                exec_list.fail_node_execution(node_id)
                state.record_execution(NodeExecutionResult(
                    node_id=node_id, status=WorkflowStatus.FAILED, error=output.error,
                    duration_ms=result.duration_ms,
                ))
                if control.get("error_handler"):
                    exec_list.select_branch(node_id, control["error_handler"])
                    exec_list.add_node(control["error_handler"])
                continue

            if output.block_execution:
                exec_list.add_external_block(node_id, output.block_execution)
                state.status = WorkflowStatus.WAITING_HUMAN if output.block_execution == "awaiting_review" else WorkflowStatus.PAUSED
                state.record_execution(NodeExecutionResult(
                    node_id=node_id, status=state.status, output=output.values,
                    duration_ms=result.duration_ms, metadata=output.metadata,
                ))
                # Tell clients which node blocked and why (e.g. the agent's
                # question + checkpoint id) so the UI can offer a resume box.
                progress.set_status(node_id, NodeStatus.BLOCKED)
                progress.emit(ProgressEvent(
                    type="execution_blocked",
                    prompt_id=prompt_id,
                    node_id=node_id,
                    data={"tag": output.block_execution,
                          "ui": _sanitize_ui(output.ui),
                          "metadata": output.metadata},
                ))
                return  # pause the run; caller drives resume

            if output.expand:
                frame = ExpandFrame(parent_id=node_id, call_idx=_next_call_idx(exec_list, node_id),
                                     nodes=output.expand.get("nodes", {}))
                added = exec_list.prompt.add_expanded(frame)
                for nid in added:
                    cache_keys.invalidate(nid)
                    exec_list.add_node(nid)

            # Choose next branch
            if output.next_node is not None or class_type == "ConditionNode":
                exec_list.select_branch(node_id, output.next_node)
                if output.next_node:
                    exec_list.add_node(output.next_node)
            else:
                next_id = control.get("next")
                if next_id:
                    exec_list.select_branch(node_id, next_id)
                    exec_list.add_node(next_id)

            exec_list.complete_node_execution(node_id)
            state.record_execution(NodeExecutionResult(
                node_id=node_id,
                status=WorkflowStatus.COMPLETED,
                output=_first_value(output),
                duration_ms=result.duration_ms,
                next_node=output.next_node or control.get("next"),
                metadata=output.metadata,
            ))

            progress.emit(ProgressEvent(
                type="executed",
                prompt_id=prompt_id,
                node_id=node_id,
                data={"values": list(output.as_tuple()),
                      "ui": _sanitize_ui(output.ui),
                      "metadata": output.metadata, "cached": result.cached},
            ))

    # ------------------------------------------------------------------
    # Lifecycle controls
    # ------------------------------------------------------------------

    async def cancel(self, state_id: UUID) -> bool:
        exec_list = self._active_lists.get(str(state_id))
        if exec_list is None:
            return False
        exec_list.cancel()
        # Abort in-flight long-running nodes (agent turns) too.
        abort_event = self._abort_events.get(str(state_id))
        if abort_event is not None:
            abort_event.set()
        state = self._states.get(str(state_id))
        if state is not None:
            state.status = WorkflowStatus.CANCELLED
        return True

    async def pause(self, state_id: UUID) -> bool:
        state = self._states.get(str(state_id))
        if state is None:
            return False
        state.status = WorkflowStatus.PAUSED
        state.paused_at = datetime.utcnow()
        return True

    async def resume(
        self,
        definition: Any,
        state_id: UUID,
        resume_data: dict[str, Any] | None = None,
        *,
        prompt_id: str | None = None,
    ) -> WorkflowResult:
        """Resume a paused/blocked run. ``resume_data`` may include
        ``{approved: bool, comments: str, ...}`` for human review or
        ``{answer: str}`` for an agent ``awaiting_user_input`` pause.
        ``prompt_id`` keeps the resumed run on the original event channel."""
        doc = _ensure_document(definition)
        state = self._states.get(str(state_id))
        if state is None:
            state = WorkflowState(workflow_id=doc.id or str(state_id),
                                  status=WorkflowStatus.RUNNING,
                                  inputs={}, variables={})
            self._states[str(state.id)] = state
        blocked_nodes: set[str] = set()
        exec_list = self._active_lists.get(str(state.id))
        if exec_list is not None:
            for node_id, tags in list(exec_list.state.blocked.items()):
                blocked_nodes.add(node_id)
                for tag in list(tags):
                    exec_list.release_external_block(node_id, tag=tag)
        # A paused run's ExecutionList is already torn down; the node that
        # paused is recorded on the state, so resume data still reaches it
        # when the fresh run re-executes that node.
        if state.current_node:
            blocked_nodes.add(state.current_node)
        for node_id in blocked_nodes:
            state.variables[f"__resume__{node_id}"] = resume_data or {}
        # Re-run on the same state so __resume__ answers and stashed agent
        # checkpoints survive; the output cache skips already-computed nodes.
        effective_prompt_id = (
            prompt_id
            or str(state.metadata.get("prompt_id") or "")
            or str(state.id)
        )
        return await self.execute_async(
            doc, state.inputs, prompt_id=effective_prompt_id, resume_state=state,
        )

    def register_progress_handler(self, handler: ProgressHandler) -> None:
        self._progress_handlers.append(handler)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_outputs(self, doc: WorkflowDocument, state: WorkflowState) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for out in doc.outputs or []:
            name = out.get("name")
            expr = out.get("value_expr") or out.get("value")
            if not name:
                continue
            if expr is None:
                resolved[name] = state.outputs.get(name) or state.variables.get(name)
            else:
                resolved[name] = state.resolve_template(expr)
        if not resolved:
            resolved = dict(state.outputs or {})
        return resolved


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _node_mode(node_def: dict[str, Any]) -> str:
    """Read the editor-assigned node mode (``""``, ``mute`` or ``bypass``)."""
    meta = node_def.get("meta") or {}
    if not isinstance(meta, dict):
        return ""
    mode = meta.get("mode")
    return mode if isinstance(mode, str) else ""


def _mode_passthrough_output(
    registry: NodeRegistry,
    node_def: dict[str, Any],
    upstream_values: dict[tuple[str, int], Any],
    mode: str,
) -> NodeOutput:
    """Synthesize a :class:`NodeOutput` for muted / bypassed nodes.

    ``mute`` produces no output values. ``bypass`` maps each declared output
    slot to the first linked input whose wire type is compatible — mirroring
    ComfyUI's BYPASS pass-through semantics.
    """
    if mode != "bypass":
        return NodeOutput(values=None, metadata={"mode": mode})

    node_cls = registry.get(node_def.get("class_type", ""))
    if node_cls is None:
        return NodeOutput(values=None, metadata={"mode": mode})
    schema = node_cls.get_schema()

    from leagent.workflow.io.types import types_compatible

    # Resolve linked input values + their wire types (literals pass too).
    resolved: list[tuple[str, Any]] = []  # (io_type, value)
    input_types = {inp.id: inp.get_io_type() for inp in schema.inputs}
    for key, value in (node_def.get("inputs") or {}).items():
        if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
            up_id, slot = value
            resolved.append((input_types.get(key, "*"),
                             upstream_values.get((up_id, int(slot)))))

    values: list[Any] = []
    for out in schema.outputs:
        out_type = out.get_io_type()
        passed: Any = None
        for in_type, value in resolved:
            if value is not None and types_compatible(in_type, out_type):
                passed = value
                break
        values.append(passed)
    return NodeOutput(values=tuple(values), metadata={"mode": mode})


def _sanitize_ui(ui: dict[str, Any] | None) -> dict[str, Any] | None:
    """Validate an embedded ``gen_ui`` tree on ``NodeOutput.ui`` before emission.

    Nodes may attach a full GenUI component tree under ``ui["gen_ui"]``; it is
    validated against the shared chat GenUI schema (and normalized) so the
    frontend can render it directly. Invalid trees are dropped rather than
    failing the run.
    """
    if not isinstance(ui, dict) or "gen_ui" not in ui:
        return ui
    out = dict(ui)
    tree = out.get("gen_ui")
    if not isinstance(tree, dict):
        out.pop("gen_ui", None)
        return out
    try:
        from leagent.services.gen_ui.schema import validate_ui_tree

        max_depth, max_nodes = 96, 2000
        try:
            from leagent.config.settings import get_settings

            canvas = getattr(get_settings(), "canvas", None)
            if canvas is not None:
                max_depth = int(getattr(canvas, "max_tree_depth", max_depth))
                max_nodes = int(getattr(canvas, "max_nodes_per_tree", max_nodes))
        except Exception:  # noqa: BLE001
            pass
        out["gen_ui"] = validate_ui_tree(tree, max_depth=max_depth, max_nodes=max_nodes)
    except Exception:  # noqa: BLE001
        logger.warning("workflow_gen_ui_invalid", exc_info=True)
        out.pop("gen_ui", None)
    return out


_call_idx_counter: dict[str, int] = {}


def _next_call_idx(exec_list: ExecutionList, node_id: str) -> int:
    n = _call_idx_counter.get(node_id, 0)
    _call_idx_counter[node_id] = n + 1
    return n


def _first_value(output: NodeOutput) -> Any:
    vals = output.as_tuple()
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    return list(vals)


def _ensure_document(definition: Any) -> WorkflowDocument:
    if isinstance(definition, WorkflowDocument):
        return definition
    if isinstance(definition, dict):
        return load(definition)
    if hasattr(definition, "model_dump"):
        return load(definition.model_dump())
    return load(definition)


class _ContextShim:
    """Provides node-expected attributes without leaking the full executor.

    The shim also exposes :meth:`get_tool_context` which builds a fully
    populated :class:`~leagent.tools.base.ToolContext` using the workflow
    state's ``metadata`` (populated from ``execute_async(extra_data=...)``).
    When the service manager is reachable, it is threaded through so tools
    can reach DB, Redis, MinIO, and the LLM service.
    """

    def __init__(self, executor: WorkflowExecutor) -> None:
        self.tool_registry = executor.tool_registry
        self.tool_executor = executor.tool_executor
        self.llm_service = executor.llm_service
        self.review_service = executor.review_service
        self.workflow_registry = executor.workflow_registry
        self.agent_controller = executor.agent_controller
        self.agent_runtime = executor.agent_runtime
        self.workflow_executor = executor

    def get_tool_context(self, state: WorkflowState | None) -> Any:
        try:
            from leagent.tools.context import build_tool_context
        except Exception:  # noqa: BLE001
            return None
        if state is None:
            return None
        service_manager = None
        try:
            from leagent.services.service_manager import get_service_manager
            service_manager = get_service_manager()
        except Exception:  # noqa: BLE001
            service_manager = None
        user_id = state.metadata.get("user_id")
        session_id = state.metadata.get("session_id") or str(state.id)
        task_id = state.metadata.get("task_id") or state.workflow_id
        return build_tool_context(
            service_manager=service_manager,
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            extra={"workflow_state": state},
        )
