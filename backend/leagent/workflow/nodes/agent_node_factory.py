"""Factory that lifts every registered :class:`AgentDefinition` into a
dedicated ``Agent.<name>`` :class:`WorkflowNode` subclass.

This mirrors :mod:`leagent.workflow.nodes.tool_factory` (which generates
``Tool.<name>`` nodes) but for the agent SDK: each entry in the
:class:`~leagent.runtime.AgentRegistry` becomes a first-class palette node
the workflow author can drop in. The generated node resolves its tool /
model / budget policy from the declarative definition and executes through
the unified :class:`~leagent.runtime.AgentRuntime` injected on the
:class:`~leagent.workflow.io.HiddenHolder`.

* Node id:   ``Agent.<name>`` (e.g. ``Agent.coding_agent``)
* Category:  ``agents``
* Inputs:    ``prompt`` (+ optional ``max_turns`` / ``allowed_tools`` /
             ``project_path`` / ``read_only`` / ``output``)
* Outputs:   ``text`` / ``success`` / ``steps_count``
* Hidden:    ``UNIQUE_ID`` / ``TOOL_CONTEXT`` / ``AGENT_RUNTIME`` /
             ``WORKFLOW_STATE``

Execution prefers definition-driven sub-agent delegation
(:meth:`AgentRuntime.delegate`) when a parent ``agent_controller`` is on the
tool context, and otherwise runs the agent standalone
(:meth:`AgentRuntime.run`) using the wired :class:`RuntimeContext` services.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar
from uuid import UUID

import structlog

from leagent.workflow.io import (
    IO,
    Hidden,
    HiddenHolder,
    NodeOutput,
    Schema,
)
from leagent.workflow.nodes.agent_exec import run_agent_node
from leagent.workflow.nodes.base import WorkflowNode

if TYPE_CHECKING:
    from leagent.sdk import AgentDefinition, AgentRegistry
    from leagent.workflow.nodes.registry import NodeRegistry

logger = structlog.get_logger(__name__)

_NODE_ID_PREFIX = "Agent."
_READ_ONLY_PROJECT_TOOLS = (
    "project_read",
    "project_grep",
    "project_glob",
    "project_tree",
)

_FACTORY_CACHE: dict[str, type[WorkflowNode]] = {}


def _safe_class_name(agent_name: str) -> str:
    cleaned = "".join(c if c.isalnum() else "_" for c in agent_name)
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"A_{cleaned}"
    return f"Agent_{cleaned}_Node"


def _as_uuid(raw: Any) -> UUID | None:
    if isinstance(raw, UUID):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            return UUID(raw)
        except ValueError:
            return None
    return None


def _build_schema(definition: AgentDefinition) -> Schema:
    display = definition.name.replace("_", " ").title()
    desc = definition.description or f"Delegate a step to the {display} agent."
    return Schema(
        node_id=f"{_NODE_ID_PREFIX}{definition.name}",
        display_name=f"Agent: {display}",
        category="agents",
        description=desc,
        inputs=[
            IO.String.Input(
                id="prompt",
                multiline=True,
                tooltip=(
                    "Natural-language task for the agent. Include any "
                    "inputs (paths, columns, constraints) directly."
                ),
            ),
            IO.Int.Input(
                id="max_turns",
                optional=True,
                default=definition.max_turns or 0,
                min=0,
                max=80,
                tooltip="Reasoning/acting budget (0 = use the agent default).",
            ),
            IO.Array.Input(
                id="allowed_tools",
                optional=True,
                default=list(definition.tools.allow),
                tooltip="Override the agent's tool whitelist.",
            ),
            IO.String.Input(
                id="project_path",
                optional=True,
                tooltip=(
                    "Absolute project root for project-scale agents "
                    "(e.g. coding_agent). Ignored by agents that don't "
                    "operate on a directory."
                ),
            ),
            IO.Boolean.Input(
                id="read_only",
                optional=True,
                default=False,
                tooltip=(
                    "Restrict a project agent to read-only tools "
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
        metadata={
            "agent_name": definition.name,
            "agent_variant": definition.prompt_variant,
            "auto_generated": True,
        },
    )


class _GeneratedAgentNodeBase(WorkflowNode):
    """Shared execute plumbing for auto-generated ``Agent.<name>`` nodes."""

    AGENT_NAME: ClassVar[str] = ""

    @classmethod
    def define_schema(cls) -> Schema:  # pragma: no cover - overridden per agent
        raise NotImplementedError

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        runtime = hidden.agent_runtime
        if runtime is None:
            return NodeOutput(
                error="Agent runtime not available on the workflow executor",
                metadata={"node_id": hidden.unique_id, "agent": self.AGENT_NAME},
            )

        state = hidden.workflow_state
        prompt = inputs.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return NodeOutput(
                error="Missing required 'prompt' input",
                metadata={"node_id": hidden.unique_id, "agent": self.AGENT_NAME},
            )
        if state is not None:
            prompt = state.resolve_template(prompt)

        max_turns = int(inputs.get("max_turns") or 0) or None
        allowed_raw = inputs.get("allowed_tools")
        allowed = (
            [str(t) for t in allowed_raw]
            if isinstance(allowed_raw, list) and allowed_raw
            else None
        )
        read_only = bool(inputs.get("read_only") or False)
        output_var = inputs.get("output")

        tool_extra: dict[str, Any] | None = None
        cwd: str | None = None
        project_path = inputs.get("project_path")
        if isinstance(project_path, str) and project_path.strip():
            if state is not None:
                project_path = state.resolve_template(project_path)
            path = Path(str(project_path)).expanduser()
            if not path.is_absolute():
                return NodeOutput(
                    error=f"project_path must be absolute, got {project_path!r}",
                    metadata={"node_id": hidden.unique_id, "agent": self.AGENT_NAME},
                )
            try:
                path = path.resolve()
            except OSError as exc:
                return NodeOutput(
                    error=f"Cannot resolve project_path: {exc}",
                    metadata={"node_id": hidden.unique_id, "agent": self.AGENT_NAME},
                )
            if not path.is_dir():
                return NodeOutput(
                    error=f"project_path {project_path!r} is not a directory",
                    metadata={"node_id": hidden.unique_id, "agent": self.AGENT_NAME},
                )
            tool_extra = {"project_roots": [str(path)]}
            cwd = str(path)
            if read_only and allowed is None:
                allowed = list(_READ_ONLY_PROJECT_TOOLS)

        started = time.monotonic()
        result = await run_agent_node(
            hidden=hidden,
            agent_name=self.AGENT_NAME,
            prompt=prompt,
            allowed_tools=allowed,
            max_turns=max_turns,
            tool_extra=tool_extra,
            cwd=cwd,
            output_var=output_var,
            log_event="agent_node_delegate",
            extra_metadata={
                "node_id": hidden.unique_id,
                "auto_generated": True,
            },
        )
        result.metadata.setdefault(
            "duration_ms", int((time.monotonic() - started) * 1000)
        )
        return result


def build_agent_node_class(definition: AgentDefinition) -> type[WorkflowNode]:
    """Return the generated :class:`WorkflowNode` subclass for ``definition``."""
    node_id = f"{_NODE_ID_PREFIX}{definition.name}"
    cached = _FACTORY_CACHE.get(definition.name)
    if cached is not None and node_id == cached.NODE_ID:
        return cached

    schema = _build_schema(definition)

    def define_schema(cls, _schema=schema) -> Schema:
        return _schema

    cls: type[WorkflowNode] = type(
        _safe_class_name(definition.name),
        (_GeneratedAgentNodeBase,),
        {
            "NODE_ID": node_id,
            "AGENT_NAME": definition.name,
            "define_schema": classmethod(define_schema),
            "__doc__": f"Auto-generated workflow node for agent '{definition.name}'.",
        },
    )

    _FACTORY_CACHE[definition.name] = cls
    return cls


def register_agent_nodes(
    node_registry: NodeRegistry,
    agent_registry: AgentRegistry,
) -> list[str]:
    """Register one generated ``Agent.<name>`` node per registered agent."""
    registered: list[str] = []
    skipped: list[tuple[str, str]] = []

    for definition in agent_registry.all():
        try:
            cls = build_agent_node_class(definition)
            node_registry.register(
                cls, module_path=f"agent_factory:{definition.name}",
            )
            registered.append(cls.NODE_ID)
        except Exception as exc:  # noqa: BLE001
            skipped.append((definition.name, str(exc)))
            logger.error(
                "agent_node_factory_failed",
                agent=definition.name, error=str(exc), exc_info=True,
            )

    logger.info(
        "agent_nodes_registered",
        count=len(registered),
        skipped=len(skipped),
    )
    return registered


def clear_factory_cache() -> None:
    """Reset the generated-node cache (tests / hot-reload)."""
    _FACTORY_CACHE.clear()


__all__ = [
    "build_agent_node_class",
    "register_agent_nodes",
    "clear_factory_cache",
]
