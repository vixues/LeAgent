"""``CodingAgentNode`` — workflow node for the project-scale coding agent.

Mirrors :class:`leagent.workflow.nodes.builtin.script_agent.ScriptAgentNode`
but targets :class:`leagent.agent.coding_agent.CodingAgentTool`. The
key extra input is ``project_path`` — an absolute on-disk directory the
agent will treat as its repository root.

Use this node when a workflow step needs an agent that can edit
multiple files, run tests, and verify its work, rather than the
single-snippet computation the existing ScriptAgentNode is tuned for.
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from leagent.agent.coding_agent import DEFAULT_CODING_AGENT_TOOLS
from leagent.workflow.io import (
    IO,
    Hidden,
    HiddenHolder,
    NodeOutput,
    Schema,
)
from leagent.workflow.nodes.agent_exec import run_agent_node
from leagent.workflow.nodes.base import WorkflowNode

logger = structlog.get_logger(__name__)

_READ_ONLY_PROJECT_TOOLS = (
    "project_read",
    "project_grep",
    "project_glob",
    "project_tree",
)


class CodingAgentNode(WorkflowNode):
    """Workflow node that delegates a step to the Coding Agent."""

    NODE_ID = "CodingAgentNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="CodingAgentNode",
            display_name="Coding Agent",
            category="workflow/code",
            description=(
                "Invoke the project-scale Coding Agent: a ReAct sub-"
                "agent that can read/grep/glob/tree, edit files with "
                "uniqueness-checked str-replace or unified-diff, run "
                "build/test/git commands, and iterate until the task "
                "is verified. Use for implementations, refactors, bug "
                "fixes, and scaffolding — anything bigger than a "
                "single-snippet computation."
            ),
            inputs=[
                IO.String.Input(
                    id="prompt",
                    multiline=True,
                    tooltip=(
                        "Engineering task in natural language. Be "
                        "concrete: name the feature, files, expected "
                        "behaviour, and verification command."
                    ),
                ),
                IO.String.Input(
                    id="project_path",
                    tooltip=(
                        "Absolute path to the project root directory. "
                        "Required."
                    ),
                ),
                IO.Int.Input(
                    id="max_iterations",
                    optional=True,
                    default=40,
                    min=1,
                    max=80,
                    tooltip="Reasoning/acting budget.",
                ),
                IO.Array.Input(
                    id="allowed_tools",
                    optional=True,
                    default=list(DEFAULT_CODING_AGENT_TOOLS),
                    tooltip="Whitelist of tool names the agent may use.",
                ),
                IO.Boolean.Input(
                    id="read_only",
                    optional=True,
                    default=False,
                    tooltip=(
                        "Restrict the agent to investigation tools "
                        "(read/grep/glob/tree)."
                    ),
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
                error="CodingAgentNode requires an agent runtime on the workflow executor.",
                metadata={"node_id": hidden.unique_id},
            )

        state = hidden.workflow_state
        prompt = inputs.get("prompt")
        project_path = inputs.get("project_path")
        if not isinstance(prompt, str) or not prompt.strip():
            return NodeOutput(
                error="Missing required 'prompt' input",
                metadata={"node_id": hidden.unique_id},
            )
        if not isinstance(project_path, str) or not project_path.strip():
            return NodeOutput(
                error="Missing required 'project_path' input",
                metadata={"node_id": hidden.unique_id},
            )
        if state is not None:
            prompt = state.resolve_template(prompt)
            project_path = state.resolve_template(project_path)

        max_iter = int(inputs.get("max_iterations") or 40)
        max_iter = max(1, min(80, max_iter))
        read_only = bool(inputs.get("read_only") or False)
        allowed_raw = inputs.get("allowed_tools") or DEFAULT_CODING_AGENT_TOOLS
        if read_only and (
            not inputs.get("allowed_tools")
            or list(inputs["allowed_tools"]) == list(DEFAULT_CODING_AGENT_TOOLS)
        ):
            allowed_raw = _READ_ONLY_PROJECT_TOOLS
        allowed = [str(t) for t in allowed_raw]
        output_var = inputs.get("output")

        from pathlib import Path

        path = Path(project_path).expanduser()
        if not path.is_absolute():
            return NodeOutput(
                error=f"`project_path` must be absolute. Got {project_path!r}.",
                metadata={"node_id": hidden.unique_id},
            )
        try:
            path = path.resolve()
        except OSError as exc:
            return NodeOutput(
                error=f"Cannot resolve project_path: {exc}",
                metadata={"node_id": hidden.unique_id},
            )
        if not path.is_dir():
            return NodeOutput(
                error=f"project_path {project_path!r} is not a directory.",
                metadata={"node_id": hidden.unique_id},
            )

        started = time.monotonic()
        extra_meta: dict[str, Any] = {
            "node_id": hidden.unique_id,
            "project_path": str(path),
        }
        parent_run_id = None
        if hidden.extra_data and isinstance(hidden.extra_data, dict):
            parent_run_id = hidden.extra_data.get("run_id")

        from leagent.runtime.execution_factory import begin_execution, end_execution
        from leagent.runtime.execution_run import ExecutionScope

        session_id = None
        user_id = None
        if hidden.extra_data and isinstance(hidden.extra_data, dict):
            session_id = hidden.extra_data.get("session_id")
            user_id = hidden.extra_data.get("user_id")

        exec_run = begin_execution(
            scope=ExecutionScope.WORKFLOW,
            session_id=str(session_id) if session_id else None,
            user_id=str(user_id) if user_id else None,
            parent_run_id=str(parent_run_id) if parent_run_id else None,
        )
        extra_meta["run_id"] = exec_run.run_id

        try:
            result = await run_agent_node(
                hidden=hidden,
                agent_name="coding_agent",
                prompt=prompt,
                allowed_tools=allowed,
                max_turns=max_iter,
                tool_extra={
                    "project_roots": [str(path)],
                    "run_id": exec_run.run_id,
                },
                cwd=str(path),
                output_var=output_var,
                log_event="coding_agent_node",
                extra_metadata=extra_meta,
            )
        finally:
            end_execution(exec_run.run_id)
        result.metadata.setdefault(
            "duration_ms", int((time.monotonic() - started) * 1000)
        )
        return result
