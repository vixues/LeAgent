"""Workflow agent-node model override helpers."""

from __future__ import annotations

from typing import Any

from leagent.runtime.definition import AgentDefinition, ModelPolicy


def parse_agent_model_override(raw: Any) -> tuple[str, str] | None:
    """Parse a workflow ``model`` widget value into ``(provider, model)``.

    Accepts ``provider/model``. Empty, ``auto``, or unset values mean "use the
    agent definition default" and return ``None``.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() == "auto":
        return None
    if "/" not in text:
        return None
    provider, _, model = text.partition("/")
    provider = provider.strip()
    model = model.strip()
    if not provider or not model:
        return None
    return provider, model


def apply_model_override(definition: AgentDefinition, raw: Any) -> AgentDefinition:
    """Return ``definition`` with an optional per-node model routing override."""
    parsed = parse_agent_model_override(raw)
    if parsed is None:
        return definition
    provider, model = parsed
    return definition.with_overrides(
        model=definition.model.model_copy(
            update={"provider": provider, "model": model},
        ),
    )


def agent_model_input() -> Any:
    """Shared optional ``model`` socket for agent workflow nodes."""
    from leagent.workflow.io import IO

    return IO.String.Input(
        id="model",
        optional=True,
        default="",
        tooltip=(
            "Chat model as provider/model (e.g. deepseek/deepseek-chat). "
            "Leave empty to use the agent definition default."
        ),
    )


__all__ = [
    "agent_model_input",
    "apply_model_override",
    "parse_agent_model_override",
]
