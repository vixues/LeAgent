"""``ParallelNode`` — fan out multiple branches concurrently."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.nodes.base import WorkflowNode

logger = structlog.get_logger(__name__)


class ParallelNode(WorkflowNode):
    NODE_ID = "ParallelNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="ParallelNode",
            display_name="Parallel",
            category="workflow/control",
            description=(
                "Fan out to branches declared in control.branches. Each branch "
                "may run a ``for_each`` expansion and select a merge strategy."
            ),
            inputs=[
                IO.Combo.Input(id="merge_strategy", optional=True, default="collect",
                                choices=["collect", "merge", "first", "last"]),
                IO.String.Input(id="output", optional=True),
            ],
            outputs=[IO.Array.Output(id="results")],
            hidden=[Hidden.UNIQUE_ID, Hidden.WORKFLOW_STATE, Hidden.TOOL_CONTEXT,
                    Hidden.LOGGER, Hidden.DYNPROMPT],
            control_flow=True,
            not_idempotent=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        from .condition import _control_for  # local reuse

        state = hidden.workflow_state
        control = _control_for(hidden, hidden.unique_id)
        branches = control.get("branches", []) or []
        if not branches:
            return NodeOutput(error="Parallel node has no branches defined")

        strategy = inputs.get("merge_strategy") or control.get("merge_strategy") or "collect"

        start = time.monotonic()
        tasks: list[asyncio.Task[dict[str, Any]]] = []
        executor = getattr(hidden.tool_context, "workflow_executor", None) if hidden.tool_context else None

        for branch in branches:
            if branch.get("for_each"):
                items = state.resolve_template(branch["for_each"]) if state is not None else branch["for_each"]
                if not isinstance(items, (list, tuple)):
                    items = [items]
                for idx, item in enumerate(items):
                    branch_state = state.fork({"item": item, "index": idx}) if state is not None else None
                    tasks.append(asyncio.create_task(
                        _execute_branch(branch, branch_state, executor, hidden),
                        name=f"{branch.get('id', 'branch')}_{idx}",
                    ))
            else:
                branch_state = state.fork() if state is not None else None
                tasks.append(asyncio.create_task(
                    _execute_branch(branch, branch_state, executor, hidden),
                    name=branch.get("id", "branch"),
                ))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        duration_ms = int((time.monotonic() - start) * 1000)
        merged = _merge(results, strategy)

        if state is not None and inputs.get("output"):
            state.set(inputs["output"], merged)

        failed = [r for r in results if isinstance(r, Exception) or (isinstance(r, dict) and r.get("error"))]

        return NodeOutput(
            values=(merged,),
            metadata={"branch_count": len(branches), "task_count": len(tasks),
                      "failed_count": len(failed), "duration_ms": duration_ms,
                      "strategy": strategy},
        )


async def _execute_branch(branch: dict[str, Any], branch_state: Any, executor: Any,
                          hidden: HiddenHolder) -> dict[str, Any]:
    try:
        if executor and branch.get("nodes"):
            for node_id in branch["nodes"]:
                await executor.execute_single_node_async(node_id, branch_state, hidden)
        return {
            "branch_id": branch.get("id", ""),
            "status": "completed",
            "outputs": dict(getattr(branch_state, "outputs", {}) or {}),
            "variables": dict(getattr(branch_state, "variables", {}) or {}),
        }
    except Exception as exc:  # noqa: BLE001
        logger.error("branch_execution_failed", branch_id=branch.get("id"), error=str(exc), exc_info=True)
        return {"branch_id": branch.get("id", ""), "status": "failed", "error": str(exc)}


def _merge(results: list[Any], strategy: str) -> Any:
    valid = [r for r in results if isinstance(r, dict) and not r.get("error")]
    match strategy:
        case "collect":
            return [r.get("outputs", r) for r in valid]
        case "merge":
            out: dict[str, Any] = {}
            for r in valid:
                outputs = r.get("outputs", {})
                if isinstance(outputs, dict):
                    out.update(outputs)
            return out
        case "first":
            return valid[0].get("outputs") if valid else None
        case "last":
            return valid[-1].get("outputs") if valid else None
        case _:
            return [r for r in results if isinstance(r, dict)]
