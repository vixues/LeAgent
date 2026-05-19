"""``ScriptAgentNode`` — delegate a workflow step to the Script (compute) Agent.

Runs the same restricted ReAct loop as :class:`ScriptAgentTool`: iterative
``code_execution`` in the subprocess sandbox. Use :class:`CodingAgentNode`
when the step needs a real project directory and ``project_*`` tools.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import structlog

from leagent.agent.script_agent import (
    DEFAULT_SCRIPT_AGENT_TOOLS,
    build_script_execution_agent,
)
from leagent.workflow.io import (
    IO,
    Hidden,
    HiddenHolder,
    NodeOutput,
    Schema,
)
from leagent.workflow.nodes.base import WorkflowNode

logger = structlog.get_logger(__name__)


class ScriptAgentNode(WorkflowNode):
    """Workflow node that delegates a step to the Script (compute) Agent."""

    NODE_ID = "ScriptAgentNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="ScriptAgentNode",
            display_name="Script Agent",
            category="workflow/code",
            description=(
                "Invoke the Script Agent: a ReAct agent that iteratively "
                "runs Python in the subprocess sandbox until it produces a "
                "result. For ad-hoc computation and file generation in the "
                "session workspace — not for editing a full on-disk project "
                "(use Coding Agent for that)."
            ),
            inputs=[
                IO.String.Input(
                    id="prompt",
                    multiline=True,
                    tooltip=(
                        "Natural-language description of the task. "
                        "Include any inputs the agent needs (artifact "
                        "URIs, column names, constraints) directly in "
                        "the prompt."
                    ),
                ),
                IO.Int.Input(
                    id="max_iterations",
                    optional=True,
                    default=15,
                    min=1,
                    max=30,
                    tooltip="Reasoning/acting budget.",
                ),
                IO.Array.Input(
                    id="allowed_tools",
                    optional=True,
                    default=list(DEFAULT_SCRIPT_AGENT_TOOLS),
                    tooltip="Whitelist of tool names the agent may use.",
                ),
                IO.String.Input(
                    id="output",
                    optional=True,
                    tooltip="Workflow-state variable for the final text.",
                ),
            ],
            outputs=[
                IO.String.Output(id="text"),
                IO.Boolean.Output(id="success"),
                IO.Int.Output(id="steps_count"),
            ],
            hidden=[Hidden.UNIQUE_ID, Hidden.TOOL_CONTEXT, Hidden.WORKFLOW_STATE],
            not_idempotent=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        ctx = hidden.tool_context
        parent_agent = getattr(ctx, "agent_controller", None) if ctx else None
        if parent_agent is None:
            return NodeOutput(
                error="ScriptAgentNode requires an agent_controller on the tool context",
                metadata={"node_id": hidden.unique_id},
            )

        state = hidden.workflow_state
        prompt = inputs.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return NodeOutput(
                error="Missing required 'prompt' input",
                metadata={"node_id": hidden.unique_id},
            )
        if state is not None:
            prompt = state.resolve_template(prompt)

        max_iter = int(inputs.get("max_iterations") or 15)
        allowed = inputs.get("allowed_tools") or DEFAULT_SCRIPT_AGENT_TOOLS
        output_var = inputs.get("output")

        started = time.monotonic()
        try:
            agent = build_script_execution_agent(
                parent=parent_agent,
                allowed_tools=[str(t) for t in allowed],
                max_iterations=max_iter,
            )
            response = await agent.run(prompt, uuid4())
        except Exception as exc:  # noqa: BLE001
            logger.error("script_agent_node_error", error=str(exc), exc_info=True)
            return NodeOutput(
                error=str(exc),
                metadata={
                    "node_id": hidden.unique_id,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                },
            )

        if state is not None and output_var:
            state.set(output_var, response.text)

        return NodeOutput(
            values=(
                response.text,
                bool(response.success),
                int(response.tool_calls_count or 0),
            ),
            metadata={
                "duration_ms": int((time.monotonic() - started) * 1000),
                "partial": bool(response.partial),
                "sandbox": "subprocess",
            },
        )
