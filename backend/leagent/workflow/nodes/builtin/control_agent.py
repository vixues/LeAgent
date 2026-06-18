"""``Agent.control_agent`` — single-shot workflow control LLM node.

Unlike ReAct-style :class:`Agent.<name>` nodes, Control Agent performs **one**
LLM completion with no tool loop and no exposed chain-of-thought. It is tuned
for workflow orchestration:

* **prompt_generate** — art/image/video prompt synthesis
* **param_generate** — JSON parameters for downstream nodes
* **state_patch** — workflow variable patches
* **route_decision** — lightweight routing hints
* **custom** — free-form multi-template control

Multiple template inputs (``instruction``, ``system_template``,
``context_template``, ``output_contract``, ``examples``) compose the user
message; ``context`` accepts an upstream OBJECT bag (e.g. from ``StartNode``).
"""

from __future__ import annotations

import time
from typing import Any

import structlog

from leagent.prompts.control_agent import (
    compose_control_messages,
    mode_choices,
    try_parse_json_payload,
)
from leagent.workflow.io import IO, Hidden, HiddenHolder, NodeOutput, Schema
from leagent.workflow.nodes.agent_model import agent_model_input, parse_agent_model_override
from leagent.workflow.nodes.base import WorkflowNode
from leagent.workflow.nodes.prompt_resolve import resolve_node_prompt

logger = structlog.get_logger(__name__)


class ControlAgentNode(WorkflowNode):
    """Single-shot control LLM for workflow orchestration tasks."""

    NODE_ID = "Agent.control_agent"

    @classmethod
    def define_schema(cls) -> Schema:
        return Schema(
            node_id=cls.NODE_ID,
            display_name="Agent: Control Agent",
            category="agents",
            description=(
                "Direct LLM control step for workflows: prompt/parameter "
                "generation, state patches, and routing — no tool loop, "
                "no visible reasoning. Supports multiple prompt templates."
            ),
            inputs=[
                IO.Combo.Input(
                    id="mode",
                    choices=mode_choices(),
                    default="custom",
                    tooltip="Preset orchestration task (loads default templates).",
                ),
                IO.String.Input(
                    id="instruction",
                    multiline=True,
                    tooltip=(
                        "Primary task directive. Supports ${input.*} and "
                        "${variables.*} template expressions."
                    ),
                ),
                IO.String.Input(
                    id="system_template",
                    optional=True,
                    multiline=True,
                    tooltip="Optional system prompt override (mode default when blank).",
                ),
                IO.String.Input(
                    id="context_template",
                    optional=True,
                    multiline=True,
                    default="${context}",
                    tooltip=(
                        "How to render the linked context object into the prompt."
                    ),
                ),
                IO.String.Input(
                    id="output_contract",
                    optional=True,
                    multiline=True,
                    tooltip="Output shape / JSON schema hint for the model.",
                ),
                IO.String.Input(
                    id="examples",
                    optional=True,
                    multiline=True,
                    tooltip="Optional few-shot examples appended to the user message.",
                ),
                IO.Object.Input(
                    id="context",
                    optional=True,
                    tooltip="Upstream context bag (link from Start or Transform).",
                ),
                IO.String.Input(
                    id="target",
                    optional=True,
                    tooltip=(
                        "Target node type or variable prefix "
                        "(param_generate / route_decision)."
                    ),
                ),
                agent_model_input(),
                IO.Combo.Input(
                    id="response_format",
                    choices=["json", "text"],
                    default="json",
                    tooltip="Parse model output as JSON object when possible.",
                ),
                IO.Boolean.Input(
                    id="apply_to_state",
                    optional=True,
                    default=True,
                    tooltip="Merge parsed JSON keys into workflow variables.",
                ),
                IO.String.Input(
                    id="output",
                    optional=True,
                    tooltip="Workflow variable for the raw text response.",
                ),
                IO.String.Input(
                    id="json_output",
                    optional=True,
                    tooltip="Workflow variable for the parsed JSON object.",
                ),
            ],
            outputs=[
                IO.String.Output(id="text"),
                IO.Object.Output(id="data"),
                IO.Boolean.Output(id="success"),
            ],
            hidden=[
                Hidden.UNIQUE_ID,
                Hidden.TOOL_CONTEXT,
                Hidden.WORKFLOW_STATE,
            ],
            not_idempotent=True,
            metadata={
                "agent_name": "control_agent",
                "control_agent": True,
                "single_shot": True,
            },
        )

    async def execute(self, *, hidden: HiddenHolder, **inputs: Any) -> NodeOutput:
        ctx = hidden.tool_context
        llm = getattr(ctx, "llm_service", None) if ctx else None
        if llm is None:
            return NodeOutput(error="LLM service not available")

        state = hidden.workflow_state
        mode = str(inputs.get("mode") or "custom")

        instruction = resolve_node_prompt(inputs.get("instruction"), state)
        if not instruction and mode == "custom":
            return NodeOutput(
                error="Missing 'instruction' for custom mode",
                metadata={"node_id": hidden.unique_id, "mode": mode},
            )

        context_raw = inputs.get("context")
        if isinstance(context_raw, dict):
            context = context_raw
        elif context_raw is not None and state is not None:
            context = state.resolve_template(context_raw)
        else:
            context = context_raw

        system_msg, user_msg = compose_control_messages(
            mode=mode,
            instruction=instruction,
            system_template=inputs.get("system_template") or "",
            context_template=inputs.get("context_template") or "",
            output_contract=inputs.get("output_contract") or "",
            examples=inputs.get("examples") or "",
            context=context,
            state=state,
            target=str(inputs.get("target") or ""),
        )

        provider_override: str | None = None
        model_override: str | None = None
        parsed_model = parse_agent_model_override(inputs.get("model"))
        if parsed_model is not None:
            provider_override, model_override = parsed_model

        response_format = str(inputs.get("response_format") or "json").lower()
        apply_to_state = bool(inputs.get("apply_to_state", True))

        started = time.monotonic()
        try:
            from leagent.llm import ChatMessage

            messages = [
                ChatMessage.system(system_msg),
                ChatMessage.user(user_msg),
            ]
            response = await llm.complete(
                messages=messages,
                provider=provider_override,
                model=model_override,
                temperature=0.2,
                max_tokens=4096,
            )
            text = (response.content or "").strip()
            duration_ms = int((time.monotonic() - started) * 1000)

            data: dict[str, Any] = {}
            parse_ok = False
            if response_format == "json":
                parsed = try_parse_json_payload(text)
                if parsed is not None:
                    data = parsed
                    parse_ok = True
            else:
                parse_ok = bool(text)

            if state is not None:
                if apply_to_state and data:
                    for key, value in data.items():
                        if isinstance(key, str) and key:
                            state.set(key, value)
                if inputs.get("output"):
                    state.set(str(inputs["output"]), text)
                if inputs.get("json_output") and data:
                    state.set(str(inputs["json_output"]), data)

            meta: dict[str, Any] = {
                "node_id": hidden.unique_id,
                "mode": mode,
                "duration_ms": duration_ms,
                "response_format": response_format,
                "json_parsed": parse_ok,
                "single_shot": True,
            }
            if provider_override:
                meta["model_provider"] = provider_override
            if model_override:
                meta["model"] = model_override
            if data:
                meta["data_keys"] = list(data.keys())[:32]

            success = parse_ok if response_format == "json" else bool(text)
            if response_format == "json" and not parse_ok:
                logger.warning(
                    "control_agent_json_parse_failed",
                    node_id=hidden.unique_id,
                    preview=text[:240],
                )

            return NodeOutput(
                values=(text, data, success),
                metadata=meta,
            )
        except Exception as exc:  # noqa: BLE001
            duration_ms = int((time.monotonic() - started) * 1000)
            logger.error(
                "control_agent_failed",
                error=str(exc),
                duration_ms=duration_ms,
                exc_info=True,
            )
            return NodeOutput(
                error=str(exc),
                metadata={"node_id": hidden.unique_id, "duration_ms": duration_ms},
            )


__all__ = ["ControlAgentNode"]
