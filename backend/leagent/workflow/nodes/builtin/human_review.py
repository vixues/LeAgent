"""``HumanReviewNode`` — pause execution until an external reviewer resolves."""

from __future__ import annotations

from typing import Any

import structlog

from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.nodes.base import WorkflowNode

logger = structlog.get_logger(__name__)


class HumanReviewNode(WorkflowNode):
    NODE_ID = "HumanReviewNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="HumanReviewNode",
            display_name="Human Review",
            category="workflow/human",
            description=(
                "Return block_execution='awaiting_review' so the scheduler adds "
                "an external block. An approval/rejection POST resumes the run."
            ),
            inputs=[
                IO.String.Input(id="reviewer"),
                IO.String.Input(id="review_prompt", optional=True, multiline=True),
                IO.Int.Input(id="timeout_sec", optional=True, default=86400, min=0),
                IO.String.Input(id="output", optional=True),
            ],
            outputs=[IO.Object.Output(id="request")],
            hidden=[Hidden.UNIQUE_ID, Hidden.REVIEW_SERVICE, Hidden.WORKFLOW_STATE, Hidden.EXECUTION_ID],
            control_flow=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        reviewer = inputs.get("reviewer")
        if not reviewer:
            return NodeOutput(error="Missing 'reviewer' input")

        state = hidden.workflow_state
        review_data = {
            "execution_id": hidden.execution_id,
            "state_id": str(state.id) if state is not None else None,
            "node_id": hidden.unique_id,
            "reviewer": reviewer,
            "prompt": state.resolve_template(inputs.get("review_prompt")) if state is not None and inputs.get("review_prompt") else inputs.get("review_prompt"),
            "context": dict(state.variables) if state is not None else {},
            "timeout_sec": int(inputs.get("timeout_sec") or 86400),
        }

        review_svc = hidden.review_service
        review_request_id: str | None = None
        if review_svc is not None:
            try:
                rr = await review_svc.create_review(review_data)
                review_request_id = rr.get("id")
                if state is not None:
                    state.review_request_id = review_request_id
                    state.review_data = review_data
            except Exception as exc:  # noqa: BLE001
                logger.error("review_service_error", error=str(exc), exc_info=True)

        logger.info("human_review_requested", reviewer=reviewer, node_id=hidden.unique_id)

        return NodeOutput(
            values=(review_data,),
            block_execution="awaiting_review",
            ui={"review": review_data, "review_request_id": review_request_id},
            metadata={"reviewer": reviewer, "review_request_id": review_request_id},
        )
