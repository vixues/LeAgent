"""``ScriptNode`` — run a short Python snippet in the in-process sandbox.

The node is the lightweight companion of the out-of-process
``CodeExecutionTool``: it solves the "just let me glue these two tool
calls with three lines of Python" use case without requiring a
subprocess or Docker. Code executes inside
:mod:`leagent.tools._sandbox.inproc`, which wraps
:mod:`RestrictedPython` with a curated builtins/imports set.

The node exposes three sockets:

* ``result``  — whichever value the script binds to the name ``result``
  (or the full locals dict when ``emit_locals`` is true).
* ``stdout``  — captured ``print`` output (truncated at 64 KB).
* ``stderr``  — reserved for future runtimes; always an empty string in
  the in-process tier so the downstream wiring is stable between
  sandbox backends.

All of the dangerous knobs (``allow_modules``, timeout, stdout limit)
are kept tight by default; operators who need more latitude should use
``CodeExecutionTool`` instead.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools._sandbox.inproc import (
    ScriptExecutionError,
    ScriptTimeoutError,
    execute_script,
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


class ScriptNode(WorkflowNode):
    """Execute a Python snippet in the restricted in-process sandbox."""

    NODE_ID = "ScriptNode"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id="ScriptNode",
            display_name="Script",
            category="workflow/code",
            description=(
                "Run a short Python snippet in the restricted in-process "
                "sandbox. Assign to `result` to emit a value. Use the "
                "CodeExecutionTool for heavier workloads."
            ),
            inputs=[
                IO.String.Input(
                    id="source",
                    multiline=True,
                    tooltip="Python source. Assign to 'result' to emit a value.",
                ),
                IO.Object.Input(
                    id="inputs",
                    optional=True,
                    default={},
                    tooltip=(
                        "Mapping of variable name → value injected as "
                        "module-level globals before the snippet runs."
                    ),
                ),
                IO.Float.Input(
                    id="timeout_sec",
                    optional=True,
                    default=5.0,
                    min=0.1,
                    max=30.0,
                    step=0.5,
                    tooltip="Wall-clock budget for the script (seconds).",
                ),
                IO.Array.Input(
                    id="allow_modules",
                    optional=True,
                    default=[],
                    tooltip=(
                        "Extra stdlib modules to whitelist (on top of math, "
                        "json, statistics, re, datetime, itertools, etc.)."
                    ),
                ),
                IO.Boolean.Input(
                    id="emit_locals",
                    optional=True,
                    default=False,
                    tooltip="If true, emit the full locals dict as `result`.",
                ),
                IO.String.Input(
                    id="output",
                    optional=True,
                    tooltip="Workflow-state variable to store the result in.",
                ),
            ],
            outputs=[
                IO.Any.Output(id="result"),
                IO.String.Output(id="stdout"),
                IO.String.Output(id="stderr"),
            ],
            hidden=[Hidden.UNIQUE_ID, Hidden.WORKFLOW_STATE],
            not_idempotent=True,
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        source = inputs.get("source")
        if not isinstance(source, str) or not source.strip():
            return NodeOutput(
                error="Missing required 'source' input",
                metadata={"node_id": hidden.unique_id},
            )

        state = hidden.workflow_state
        raw_inputs = inputs.get("inputs") or {}
        if state is not None:
            raw_inputs = state.resolve_template(raw_inputs)
        if not isinstance(raw_inputs, dict):
            return NodeOutput(
                error="'inputs' must be an object of name→value pairs",
                metadata={"node_id": hidden.unique_id},
            )

        timeout_sec = float(inputs.get("timeout_sec") or 5.0)
        allow_modules = inputs.get("allow_modules") or []
        if not isinstance(allow_modules, (list, tuple)):
            return NodeOutput(
                error="'allow_modules' must be an array of module names",
                metadata={"node_id": hidden.unique_id},
            )
        emit_locals = bool(inputs.get("emit_locals") or False)
        output_var = inputs.get("output")

        try:
            script_result = await execute_script(
                source,
                inputs=raw_inputs,
                timeout_sec=timeout_sec,
                allow_modules=[str(m) for m in allow_modules],
            )
        except ScriptTimeoutError as exc:
            logger.warning("script_node_timeout", node=hidden.unique_id, error=str(exc))
            return NodeOutput(
                error=str(exc),
                metadata={
                    "node_id": hidden.unique_id,
                    "reason": "timeout",
                    "timeout_sec": timeout_sec,
                },
            )
        except ScriptExecutionError as exc:
            logger.warning("script_node_error", node=hidden.unique_id, error=str(exc))
            return NodeOutput(
                error=str(exc),
                metadata={"node_id": hidden.unique_id, "reason": "script_error"},
            )

        emitted = script_result.locals if emit_locals else script_result.result
        if state is not None and output_var:
            state.set(output_var, emitted)

        return NodeOutput(
            values=(emitted, script_result.stdout, ""),
            metadata={
                "duration_ms": script_result.duration_ms,
                "truncated_stdout": script_result.truncated_stdout,
                "emit_locals": emit_locals,
                "sandbox": "inproc",
            },
        )
