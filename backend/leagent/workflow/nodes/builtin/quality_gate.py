"""``QualityGateNode`` — score an asset and route pass / fail.

The evaluation gate of the self-correction loop. It derives a quality
``score`` for the upstream asset and routes to ``control.pass_node`` when
``score >= threshold`` else ``control.fail_node`` (typically an
:class:`IterativeRefineNode` back-edge).

Scoring strategy (first match wins):

1. An explicit ``score`` input (e.g. wired from an LLM critique node).
2. A deterministic heuristic that *improves with the refine iteration*
   (``base + step * iteration``) so offline / demo pipelines exercise the
   full generate -> evaluate -> regenerate loop reproducibly.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema

from leagent.workflow.nodes.base import WorkflowNode

logger = structlog.get_logger(__name__)


class QualityGateNode(WorkflowNode):
    NODE_ID = "QualityGateNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="QualityGateNode",
            display_name="Quality Gate",
            category="art/evaluate",
            description=(
                "Score an upstream asset against a quality bar and route to "
                "control.pass_node or control.fail_node (self-correction loop)."
            ),
            inputs=[
                IO.Any.Input(id="asset", optional=True,
                             tooltip="The asset (image/video/mesh) being evaluated."),
                IO.Float.Input(id="score", optional=True, min=0.0, max=1.0,
                               tooltip="Explicit quality score; overrides the heuristic."),
                IO.Float.Input(id="threshold", optional=True, default=0.7, min=0.0, max=1.0,
                               tooltip="Minimum score required to pass."),
                IO.String.Input(id="criteria", optional=True, multiline=True,
                                tooltip="Human-readable acceptance criteria."),
                IO.String.Input(id="iteration_var", optional=True, default="refine_iteration",
                                tooltip="State variable holding the refine iteration count."),
                IO.Float.Input(id="base_score", optional=True, default=0.45, min=0.0, max=1.0,
                               tooltip="Heuristic base score at iteration 0."),
                IO.Float.Input(id="score_step", optional=True, default=0.3, min=0.0, max=1.0,
                               tooltip="Heuristic score gain per refine iteration."),
            ],
            outputs=[
                IO.Float.Output(id="score"),
                IO.Boolean.Output(id="passed"),
                IO.Any.Output(id="asset"),
            ],
            hidden=[Hidden.UNIQUE_ID, Hidden.WORKFLOW_STATE],
            control_flow=True,
            not_idempotent=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        state = hidden.workflow_state
        node_id = hidden.unique_id
        threshold = float(inputs.get("threshold") if inputs.get("threshold") is not None else 0.7)

        score = self._resolve_score(inputs, state)
        passed = score >= threshold

        if state is not None:
            state.set("quality_score", round(score, 4))
            state.set("quality_passed", passed)

        control = _control_for(hidden, node_id)
        pass_node = control.get("pass_node") or _first_then(control)
        fail_node = control.get("fail_node") or control.get("else_node") or control.get("else")
        target = pass_node if passed else fail_node

        logger.info(
            "quality_gate", node_id=node_id, score=round(score, 4),
            threshold=threshold, passed=passed, target=target,
        )
        return NodeOutput(
            values=(round(score, 4), passed, inputs.get("asset")),
            next_node=target,
            metadata={"score": round(score, 4), "threshold": threshold, "passed": passed},
        )

    def _resolve_score(self, inputs: dict[str, Any], state: Any) -> float:
        explicit = inputs.get("score")
        if explicit is not None:
            try:
                return max(0.0, min(float(explicit), 1.0))
            except (ValueError, TypeError):
                pass
        iteration = 0
        if state is not None:
            var = str(inputs.get("iteration_var") or "refine_iteration")
            try:
                iteration = int(state.get(var, 0) or 0)
            except (ValueError, TypeError):
                iteration = 0
        base = float(inputs.get("base_score") if inputs.get("base_score") is not None else 0.45)
        step = float(inputs.get("score_step") if inputs.get("score_step") is not None else 0.3)
        return max(0.0, min(base + step * iteration, 1.0))


def _first_then(control: dict[str, Any]) -> str | None:
    for cond in control.get("conditions", []) or []:
        target = cond.get("then_node") or cond.get("then")
        if target:
            return target
    return None


def _control_for(hidden: HiddenHolder, node_id: str | None) -> dict[str, Any]:
    if not node_id:
        return {}
    prompt = hidden.prompt or {}
    node = prompt.get(node_id) if isinstance(prompt, dict) else None
    if isinstance(node, dict):
        return node.get("control", {}) or {}
    return {}
