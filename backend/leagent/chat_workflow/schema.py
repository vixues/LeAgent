"""Pydantic schema and validation for chat workflow cards."""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from leagent.tools.registry import ToolRegistry

_MAX_STEPS = 20
_MAX_TITLE_LEN = 200
_MAX_SUMMARY_LEN = 2000
_MAX_LABEL_LEN = 200
_MAX_HINT_LEN = 500
_MAX_ARGS_JSON_BYTES = 8192
class ChatWorkflowToolAction(BaseModel):
    """Executable step: invoke a registered tool with templated arguments."""

    kind: Literal["tool"] = "tool"
    tool_id: str = Field(..., min_length=1, max_length=128)
    arguments: dict[str, Any] = Field(default_factory=dict)

    @field_validator("arguments", mode="before")
    @classmethod
    def _cap_args_size(cls, v: Any) -> dict[str, Any]:
        if v is None:
            return {}
        if not isinstance(v, dict):
            raise ValueError("arguments must be an object")
        raw = json.dumps(v, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(raw) > _MAX_ARGS_JSON_BYTES:
            raise ValueError(f"arguments JSON exceeds {_MAX_ARGS_JSON_BYTES} bytes")
        return v


class ChatWorkflowStep(BaseModel):
    id: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9_-]+$")
    label: str = Field(..., min_length=1, max_length=_MAX_LABEL_LEN)
    hint: str | None = Field(default=None, max_length=_MAX_HINT_LEN)
    action: ChatWorkflowToolAction


class ChatWorkflowSpec(BaseModel):
    version: Literal[1] = 1
    title: str = Field(..., min_length=1, max_length=_MAX_TITLE_LEN)
    summary: str | None = Field(default=None, max_length=_MAX_SUMMARY_LEN)
    steps: list[ChatWorkflowStep] = Field(
        ...,
        min_length=1,
        max_length=_MAX_STEPS,
    )

    @field_validator("steps")
    @classmethod
    def _unique_step_ids(cls, v: list[ChatWorkflowStep]) -> list[ChatWorkflowStep]:
        ids = [s.id for s in v]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate step id")
        return v


class ValidationError(ValueError):
    """Invalid chat workflow payload."""


def chat_workflow_digest(spec: ChatWorkflowSpec) -> str:
    """Stable SHA-256 over canonical JSON (for run-step verification)."""
    payload = spec.model_dump(mode="json")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _extra_allowlist_from_env() -> frozenset[str]:
    raw = os.environ.get("LEAGENT_CHAT_WORKFLOW_TOOL_ALLOWLIST", "") or ""
    parts = {p.strip() for p in raw.split(",") if p.strip()}
    return frozenset(parts)


def tool_ids_allowed_for_chat_workflow_steps(registry: ToolRegistry) -> frozenset[str]:
    """Tools permitted inside workflow steps: read-only registered + env allowlist."""
    allowed: set[str] = set(_extra_allowlist_from_env())
    for meta in registry.list_tools():
        name = getattr(meta, "name", None) or ""
        if not name:
            continue
        tool = registry.get_optional(name)
        if tool is None:
            continue
        if getattr(tool, "is_read_only", False):
            allowed.add(name)
            for alias in getattr(tool, "aliases", []) or []:
                if alias:
                    allowed.add(alias)
    return frozenset(allowed)


def parse_chat_workflow_spec(
    raw: dict[str, Any],
    *,
    registry: ToolRegistry,
) -> ChatWorkflowSpec:
    """Parse and validate a workflow spec; enforce step tool allowlist."""
    try:
        spec = ChatWorkflowSpec.model_validate(raw)
    except Exception as e:
        raise ValidationError(str(e)) from e
    allowed = tool_ids_allowed_for_chat_workflow_steps(registry)
    for step in spec.steps:
        tid = step.action.tool_id
        if tid not in allowed:
            tool = registry.get_optional(tid)
            if tool is None:
                raise ValidationError(f"unknown tool_id in step {step.id!r}: {tid!r}")
            raise ValidationError(
                f"tool {tid!r} in step {step.id!r} is not allowed in chat workflows "
                "(read-only tools only, unless listed in LEAGENT_CHAT_WORKFLOW_TOOL_ALLOWLIST)",
            )
    return spec


def resolve_argument_templates(
    arguments: dict[str, Any],
    *,
    session_id: str,
    user_id: str,
    user_input: str = "",
) -> dict[str, Any]:
    """Replace ${session_id}, ${user_id}, ${user_input} in string leaves (no eval)."""

    def _sub(s: str) -> str:
        return (
            s.replace("${session_id}", session_id)
            .replace("${user_id}", user_id)
            .replace("${user_input}", user_input)
        )

    def _walk(obj: Any) -> Any:
        if isinstance(obj, str):
            return _sub(obj)
        if isinstance(obj, list):
            return [_walk(x) for x in obj]
        if isinstance(obj, dict):
            return {k: _walk(v) for k, v in obj.items()}
        return obj

    return _walk(dict(arguments or {}))
