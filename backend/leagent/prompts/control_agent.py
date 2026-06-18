"""Prompt catalog for the workflow **Control Agent** node.

The Control Agent is a *single-shot* LLM step (no tool loop, no chain-of-thought
exposed) tuned for workflow orchestration: prompt synthesis, parameter JSON,
state patches, and lightweight routing hints for downstream nodes.
"""

from __future__ import annotations

from typing import Any

#: Supported control modes (``ControlAgentNode`` ``mode`` input).
CONTROL_MODES: tuple[str, ...] = (
    "prompt_generate",
    "param_generate",
    "state_patch",
    "route_decision",
    "custom",
)

MODE_SPECS: dict[str, dict[str, str]] = {
    "prompt_generate": {
        "title": "Prompt generation",
        "system": (
            "You are Control Agent — a workflow orchestration assistant.\n"
            "Task: synthesize production-ready generation prompts for downstream "
            "image/video/3D art nodes.\n"
            "Rules:\n"
            "- Output ONLY the requested format; no reasoning preamble.\n"
            "- Be concrete: subject, style, lighting, camera, materials.\n"
            "- Prefer English prompt text unless the instruction specifies another language.\n"
            "- When JSON is requested, return a single valid JSON object."
        ),
        "instruction_default": (
            "Generate an image-generation prompt from the workflow brief.\n"
            "Brief: ${input.prompt}"
        ),
        "output_contract_default": (
            '{"prompt":"string","negative_prompt":"string","style_tags":["string"]}'
        ),
    },
    "param_generate": {
        "title": "Parameter generation",
        "system": (
            "You are Control Agent — a workflow parameter synthesizer.\n"
            "Task: emit JSON parameters for a target workflow node based on the "
            "brief and upstream context.\n"
            "Rules:\n"
            "- Keys must match the target node's input widget names when known.\n"
            "- Use sensible defaults; omit keys that should stay at node defaults.\n"
            "- Output ONLY valid JSON; no markdown fences or commentary."
        ),
        "instruction_default": (
            "Generate node parameters for target: ${input.target_node}.\n"
            "Brief: ${input.prompt}"
        ),
        "output_contract_default": (
            '{"prompt":"string","provider":"auto|offline|...","width":1024,"height":1024}'
        ),
    },
    "state_patch": {
        "title": "State patch",
        "system": (
            "You are Control Agent — a workflow state writer.\n"
            "Task: produce a flat JSON object of workflow variables to merge "
            "into the run state for downstream nodes.\n"
            "Rules:\n"
            "- Keys are variable names; values are JSON scalars/objects/arrays.\n"
            "- Do not nest under a wrapper key unless the instruction requires it.\n"
            "- Output ONLY valid JSON."
        ),
        "instruction_default": "Derive workflow variables from the current context.",
        "output_contract_default": '{"refine_feedback":"string","quality_bar":0.7}',
    },
    "route_decision": {
        "title": "Route decision",
        "system": (
            "You are Control Agent — a workflow router.\n"
            "Task: choose the next control action for the graph.\n"
            "Rules:\n"
            "- Output JSON with: action (continue|retry|branch|stop), "
            "optional branch_id, optional reason (short).\n"
            "- No chain-of-thought; reason is one sentence max."
        ),
        "instruction_default": "Decide the next workflow step from the execution context.",
        "output_contract_default": (
            '{"action":"continue|retry|branch|stop","branch_id":"string|null",'
            '"reason":"string"}'
        ),
    },
    "custom": {
        "title": "Custom",
        "system": (
            "You are Control Agent — a direct workflow LLM step.\n"
            "Follow the user instruction exactly. No tool use. "
            "No visible reasoning — deliver the result only."
        ),
        "instruction_default": "",
        "output_contract_default": "",
    },
}


def mode_choices() -> list[str]:
    return list(CONTROL_MODES)


def resolve_template_field(raw: Any, state: Any | None) -> str:
    """Resolve a template string against workflow state."""
    if raw is None:
        return ""
    text = str(raw)
    if state is None:
        return text.strip()
    resolved = state.resolve_template(text)
    if resolved is None:
        return ""
    if isinstance(resolved, str):
        return resolved.strip()
    return str(resolved).strip()


def format_context_block(context: Any, *, template: str, state: Any | None) -> str:
    """Render the optional context template with ``context`` bound."""
    import json

    if not template.strip():
        if context is None:
            return ""
        if isinstance(context, (dict, list)):
            return json.dumps(context, ensure_ascii=False, indent=2)
        return str(context)

    if state is None:
        return template.strip()

    from leagent.workflow.base import _resolve_template

    ctx: dict[str, Any] = {
        "input": getattr(state, "inputs", {}) or {},
        "inputs": getattr(state, "inputs", {}) or {},
        "variables": getattr(state, "variables", {}) or {},
        "outputs": getattr(state, "outputs", {}) or {},
        "context": context,
    }
    ctx.update(ctx["inputs"])
    ctx.update(ctx["variables"])
    ctx.update(ctx["outputs"])
    if isinstance(context, dict):
        ctx.update(context)

    resolved = _resolve_template(template, ctx)
    if isinstance(resolved, str):
        return resolved.strip()
    if resolved is not None:
        return str(resolved).strip()
    return ""


def compose_control_messages(
    *,
    mode: str,
    instruction: str,
    system_template: str,
    context_template: str,
    output_contract: str,
    examples: str,
    context: Any,
    state: Any | None,
    target: str,
) -> tuple[str, str]:
    """Build ``(system_message, user_message)`` for a single completion."""
    spec = MODE_SPECS.get(mode) or MODE_SPECS["custom"]

    system = resolve_template_field(system_template, state).strip()
    if not system:
        system = spec["system"]

    parts: list[str] = []

    instr = resolve_template_field(instruction, state).strip()
    if not instr:
        default_instr = spec.get("instruction_default") or ""
        if default_instr and state is not None:
            instr = resolve_template_field(default_instr, state).strip()
        elif default_instr:
            instr = default_instr.strip()

    if instr:
        parts.append(f"## Instruction\n{instr}")

    if target and str(target).strip():
        parts.append(f"## Target\n{str(target).strip()}")

    ctx_block = format_context_block(
        context, template=context_template, state=state,
    )
    if ctx_block:
        parts.append(f"## Context\n{ctx_block}")

    contract = resolve_template_field(output_contract, state).strip()
    if not contract:
        contract = (spec.get("output_contract_default") or "").strip()
    if contract:
        parts.append(f"## Output contract\n{contract}")

    ex = resolve_template_field(examples, state).strip()
    if ex:
        parts.append(f"## Examples\n{ex}")

    user = "\n\n".join(parts).strip()
    if not user:
        user = "Complete the control task."
    return system, user


def try_parse_json_payload(text: str) -> dict[str, Any] | None:
    """Best-effort JSON object extraction from a model response."""
    import json
    import re

    raw = (text or "").strip()
    if not raw:
        return None

    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        try:
            parsed = json.loads(fence.group(1).strip())
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        except json.JSONDecodeError:
            return None
    return None


__all__ = [
    "CONTROL_MODES",
    "MODE_SPECS",
    "compose_control_messages",
    "format_context_block",
    "mode_choices",
    "resolve_template_field",
    "try_parse_json_payload",
]
