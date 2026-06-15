"""Runtime budgets for interactive and long-running agent work."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

RuntimeProfileName = Literal["standard", "coding_long", "coding_extended"]

_PROFILE_NAMES = {"standard", "coding_long", "coding_extended"}


@dataclass(frozen=True)
class RuntimeBudget:
    """Resolved timing and concurrency limits for an agent run."""

    name: RuntimeProfileName
    task_timeout_sec: int
    conversation_timeout_sec: int
    stream_drain_timeout_sec: int
    max_turns: int
    max_tool_calls_per_turn: int
    tool_timeout_sec: int
    code_execution_default_timeout_sec: float
    code_execution_max_timeout_sec: float
    max_concurrency_per_user: int
    max_concurrency_per_workspace: int


def normalize_runtime_profile(value: Any, *, default: RuntimeProfileName = "standard") -> RuntimeProfileName:
    """Return a supported runtime profile name."""

    text = str(value or "").strip().lower().replace("-", "_")
    if text in _PROFILE_NAMES:
        return text  # type: ignore[return-value]
    return default


def resolve_runtime_budget(
    profile: Any = None,
    *,
    settings: Any | None = None,
) -> RuntimeBudget:
    """Resolve a profile into concrete runtime limits.

    ``settings`` is intentionally typed as ``Any`` to avoid importing the
    settings module from low-level agent code. Callers may pass the cached
    application settings when they already have it.
    """

    if settings is None:
        from leagent.config.settings import get_settings

        settings = get_settings()

    agent = settings.agent
    name = normalize_runtime_profile(profile or getattr(agent, "runtime_profile", "standard"))

    if name == "coding_extended":
        return RuntimeBudget(
            name=name,
            task_timeout_sec=int(agent.extended_task_timeout_sec),
            conversation_timeout_sec=int(agent.extended_task_timeout_sec),
            stream_drain_timeout_sec=int(agent.extended_stream_drain_timeout_sec),
            max_turns=int(agent.extended_max_turns),
            max_tool_calls_per_turn=int(agent.extended_max_tool_calls_per_turn),
            tool_timeout_sec=int(agent.extended_tool_timeout_sec),
            code_execution_default_timeout_sec=float(settings.code_execution_extended_default_timeout_sec),
            code_execution_max_timeout_sec=float(settings.code_execution_extended_max_timeout_sec),
            max_concurrency_per_user=int(agent.extended_max_concurrency_per_user),
            max_concurrency_per_workspace=int(agent.extended_max_concurrency_per_workspace),
        )

    if name == "coding_long":
        return RuntimeBudget(
            name=name,
            task_timeout_sec=int(agent.long_task_timeout_sec),
            conversation_timeout_sec=int(agent.long_task_timeout_sec),
            stream_drain_timeout_sec=int(agent.long_stream_drain_timeout_sec),
            max_turns=int(agent.long_max_turns),
            max_tool_calls_per_turn=int(agent.long_max_tool_calls_per_turn),
            tool_timeout_sec=int(agent.long_tool_timeout_sec),
            code_execution_default_timeout_sec=float(settings.code_execution_long_default_timeout_sec),
            code_execution_max_timeout_sec=float(settings.code_execution_long_max_timeout_sec),
            max_concurrency_per_user=int(agent.long_max_concurrency_per_user),
            max_concurrency_per_workspace=int(agent.long_max_concurrency_per_workspace),
        )

    return RuntimeBudget(
        name="standard",
        task_timeout_sec=int(agent.default_timeout_sec),
        conversation_timeout_sec=int(agent.conversation_timeout_sec),
        stream_drain_timeout_sec=int(agent.stream_drain_timeout_sec),
        max_turns=int(agent.max_iterations),
        max_tool_calls_per_turn=int(agent.max_tool_calls_per_turn),
        tool_timeout_sec=int(agent.default_timeout_sec),
        code_execution_default_timeout_sec=0.0,
        code_execution_max_timeout_sec=0.0,
        max_concurrency_per_user=0,
        max_concurrency_per_workspace=0,
    )


def runtime_budget_tool_extra(
    profile: Any = None,
    *,
    settings: Any | None = None,
) -> dict[str, Any]:
    """Build a ``tool_extra`` fragment carrying profile name and resolved budgets."""

    budget = resolve_runtime_budget(profile, settings=settings)
    return {
        "runtime_profile": budget.name,
        "runtime_budget": {
            "task_timeout_sec": budget.task_timeout_sec,
            "tool_timeout_sec": budget.tool_timeout_sec,
            "code_execution_default_timeout_sec": budget.code_execution_default_timeout_sec,
            "code_execution_max_timeout_sec": budget.code_execution_max_timeout_sec,
        },
    }


def resolve_chat_conversation_timeout_sec(
    *,
    project_path: str | None = None,
    runtime_profile: Any = None,
    settings: Any | None = None,
) -> int:
    """Resolve the SSE conversation wall-clock limit for a chat turn.

    Coding work (explicit profile or bound project folder) uses
    ``coding_long`` (default 3600s) or ``coding_extended`` (7200s) budgets
    instead of the standard 600s interactive cap.
    """

    if settings is None:
        from leagent.config.settings import get_settings

        settings = get_settings()

    explicit = str(runtime_profile or "").strip()
    if explicit:
        name = normalize_runtime_profile(explicit, default="standard")
        if name in ("coding_long", "coding_extended"):
            return resolve_runtime_budget(name, settings=settings).conversation_timeout_sec

    if project_path:
        return resolve_runtime_budget("coding_long", settings=settings).conversation_timeout_sec

    return int(settings.agent.conversation_timeout_sec)
