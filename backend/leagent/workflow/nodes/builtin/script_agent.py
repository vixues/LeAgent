"""``ScriptAgentNode`` — delegate a workflow step to the Script (compute) Agent.

Runs the same restricted ReAct loop as :class:`ScriptAgentTool`: iterative
``code_execution`` in the subprocess sandbox. Use :class:`CodingAgentNode`
when the step needs a real project directory and ``project_*`` tools.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from leagent.agent.script_agent import DEFAULT_SCRIPT_AGENT_TOOLS
from leagent.workflow.io import (
    IO,
    Hidden,
    HiddenHolder,
    NodeOutput,
    Schema,
)
from leagent.workflow.nodes.agent_exec import run_agent_node
from leagent.workflow.nodes.base import WorkflowNode
from leagent.workflow.nodes.agent_model import agent_model_input
from leagent.workflow.nodes.prompt_resolve import resolve_node_prompt

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
                agent_model_input(),
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
                IO.String.Output(id="checkpoint_id"),
                IO.Array.Output(id="activity"),
                IO.Array.Output(id="produced_files"),
            ],
            hidden=[
                Hidden.UNIQUE_ID,
                Hidden.TOOL_CONTEXT,
                Hidden.AGENT_RUNTIME,
                Hidden.WORKFLOW_STATE,
                Hidden.SESSION_ID,
                Hidden.USER_ID,
            ],
            not_idempotent=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        runtime = hidden.agent_runtime
        if runtime is None:
            return NodeOutput(
                error="ScriptAgentNode requires an agent runtime on the workflow executor",
                metadata={"node_id": hidden.unique_id},
            )

        state = hidden.workflow_state
        prompt = resolve_node_prompt(inputs.get("prompt"), state)
        if not prompt:
            return NodeOutput(
                error="Missing required 'prompt' input",
                metadata={"node_id": hidden.unique_id},
            )

        max_iter = int(inputs.get("max_iterations") or 15)
        allowed_raw = inputs.get("allowed_tools") or DEFAULT_SCRIPT_AGENT_TOOLS
        allowed = [str(t) for t in allowed_raw]
        output_var = inputs.get("output")

        started = time.monotonic()
        result = await run_agent_node(
            hidden=hidden,
            agent_name="script_agent",
            prompt=prompt,
            allowed_tools=allowed,
            max_turns=max_iter,
            model=inputs.get("model"),
            output_var=output_var,
            log_event="script_agent_node",
            extra_metadata={"node_id": hidden.unique_id, "sandbox": "subprocess"},
        )
        result.metadata.setdefault(
            "duration_ms", int((time.monotonic() - started) * 1000)
        )
        return result
