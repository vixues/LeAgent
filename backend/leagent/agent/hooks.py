"""Agent lifecycle hooks for extensibility and observability."""

from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

import structlog

from leagent.agent.base import (
    AgentContext,
    AgentResponse,
    AgentState,
    ExecutionPlan,
    ExecutionStep,
    StepType,
    ToolCall,
    ToolResult,
)

if TYPE_CHECKING:
    from leagent.memory import AgentMemory
    from leagent.code.artifacts import CodeArtifact

logger = structlog.get_logger(__name__)

T = TypeVar("T")


class AgentHook(ABC):
    """Abstract base class for agent lifecycle hooks.

    Hooks are called at various points during agent execution:
    - on_start: When agent begins processing
    - on_step: After each reasoning/execution step
    - on_tool_call: Before tool execution
    - on_tool_result: After tool execution
    - on_complete: When agent finishes successfully
    - on_error: When an error occurs
    - on_cancel: When execution is cancelled

    Subclass this to implement custom behavior.
    """

    priority: int = 100

    async def on_start(self, context: AgentContext, user_input: str) -> None:
        """Called when agent starts processing a request.

        Args:
            context: Agent execution context.
            user_input: The user's input message.
        """
        pass

    async def on_step(self, context: AgentContext, step: ExecutionStep) -> None:
        """Called after each execution step.

        Args:
            context: Agent execution context.
            step: The step that was just executed.
        """
        pass

    async def on_tool_call(self, context: AgentContext, tool_call: ToolCall) -> None:
        """Called before a tool is executed.

        Args:
            context: Agent execution context.
            tool_call: The tool call about to be executed.
        """
        pass

    async def on_tool_result(
        self,
        context: AgentContext,
        tool_call: ToolCall,
        result: ToolResult,
    ) -> None:
        """Called after a tool returns a result.

        Args:
            context: Agent execution context.
            tool_call: The tool call that was executed.
            result: The result from the tool.
        """
        pass

    async def on_plan_created(self, context: AgentContext, plan: ExecutionPlan) -> None:
        """Called when a new execution plan is created.

        Args:
            context: Agent execution context.
            plan: The newly created plan.
        """
        pass

    async def on_complete(self, context: AgentContext, response: AgentResponse) -> None:
        """Called when agent completes successfully.

        Args:
            context: Agent execution context.
            response: The final agent response.
        """
        pass

    async def on_error(self, context: AgentContext, error: Exception) -> None:
        """Called when an error occurs.

        Args:
            context: Agent execution context.
            error: The exception that occurred.
        """
        pass

    async def on_cancel(self, context: AgentContext) -> None:
        """Called when execution is cancelled.

        Args:
            context: Agent execution context.
        """
        pass

    async def on_code_artifact(self, artifact: "CodeArtifact") -> None:
        """Called when a code artifact is produced (before execution/write).

        Args:
            artifact: The code artifact that was just created.
        """
        pass

    async def on_pre_compact(self, context: AgentContext, reason: str) -> None:
        """Called before transcript compaction runs (Claude ``PreCompact``).

        Args:
            context: Agent execution context.
            reason: Why compaction was triggered (e.g. ``"autocompact"``).
        """
        pass

    async def on_subagent_start(
        self, context: AgentContext, agent_name: str, prompt: str
    ) -> None:
        """Called when a sub-agent is delegated (Claude ``SubagentStart``)."""
        pass

    async def on_subagent_stop(
        self, context: AgentContext, agent_name: str, result: dict[str, Any]
    ) -> None:
        """Called when a delegated sub-agent finishes (Claude ``SubagentStop``)."""
        pass


class HookManager:
    """Manages and dispatches lifecycle hooks.

    Hooks are executed in priority order (lower number = higher priority).
    Errors in hooks are logged but don't stop execution.
    """

    def __init__(self) -> None:
        self._hooks: list[AgentHook] = []
        self._sorted = False

    def register(self, hook: AgentHook) -> None:
        """Register a hook.

        Args:
            hook: The hook to register.
        """
        self._hooks.append(hook)
        self._sorted = False
        logger.debug("hook_registered", hook_class=hook.__class__.__name__)

    def unregister(self, hook: AgentHook) -> None:
        """Unregister a hook.

        Args:
            hook: The hook to unregister.
        """
        if hook in self._hooks:
            self._hooks.remove(hook)
            logger.debug("hook_unregistered", hook_class=hook.__class__.__name__)

    def clear(self) -> None:
        """Remove all registered hooks."""
        self._hooks.clear()
        self._sorted = False

    def filter_by_names(self, names: list[str]) -> HookManager:
        """Return a new manager exposing only hooks matching ``names``.

        A hook matches when ``names`` contains its declared ``name`` attribute
        (if any) or its class name. This lets an :class:`AgentDefinition`
        opt into a named subset of the process-wide hooks (Claude-Code-style
        per-agent hook selection) without mutating the shared manager. An
        empty / falsy ``names`` returns ``self`` unchanged.
        """
        if not names:
            return self
        wanted = set(names)
        child = HookManager()
        for hook in self._hooks:
            hook_name = getattr(hook, "name", None) or hook.__class__.__name__
            if hook_name in wanted:
                child.register(hook)
        return child

    def _ensure_sorted(self) -> None:
        """Sort hooks by priority if needed."""
        if not self._sorted:
            self._hooks.sort(key=lambda h: h.priority)
            self._sorted = True

    async def dispatch_start(self, context: AgentContext, user_input: str) -> None:
        """Dispatch on_start to all hooks."""
        self._ensure_sorted()
        await self._dispatch("on_start", context, user_input)

    async def dispatch_step(self, context: AgentContext, step: ExecutionStep) -> None:
        """Dispatch on_step to all hooks."""
        self._ensure_sorted()
        await self._dispatch("on_step", context, step)

    async def dispatch_tool_call(self, context: AgentContext, tool_call: ToolCall) -> None:
        """Dispatch on_tool_call to all hooks."""
        self._ensure_sorted()
        await self._dispatch("on_tool_call", context, tool_call)

    async def dispatch_tool_result(
        self,
        context: AgentContext,
        tool_call: ToolCall,
        result: ToolResult,
    ) -> None:
        """Dispatch on_tool_result to all hooks."""
        self._ensure_sorted()
        await self._dispatch("on_tool_result", context, tool_call, result)

    async def dispatch_plan_created(
        self,
        context: AgentContext,
        plan: ExecutionPlan,
    ) -> None:
        """Dispatch on_plan_created to all hooks."""
        self._ensure_sorted()
        await self._dispatch("on_plan_created", context, plan)

    async def dispatch_complete(
        self,
        context: AgentContext,
        response: AgentResponse,
    ) -> None:
        """Dispatch on_complete to all hooks."""
        self._ensure_sorted()
        await self._dispatch("on_complete", context, response)

    async def dispatch_error(self, context: AgentContext, error: Exception) -> None:
        """Dispatch on_error to all hooks."""
        self._ensure_sorted()
        await self._dispatch("on_error", context, error)

    async def dispatch_cancel(self, context: AgentContext) -> None:
        """Dispatch on_cancel to all hooks."""
        self._ensure_sorted()
        await self._dispatch("on_cancel", context)

    async def fire_code_artifact(self, artifact: "CodeArtifact") -> None:
        """Dispatch on_code_artifact to all hooks."""
        self._ensure_sorted()
        await self._dispatch("on_code_artifact", artifact)

    async def dispatch_pre_compact(self, context: AgentContext, reason: str) -> None:
        """Dispatch on_pre_compact to all hooks (Claude ``PreCompact``)."""
        self._ensure_sorted()
        await self._dispatch("on_pre_compact", context, reason)

    async def dispatch_subagent_start(
        self, context: AgentContext, agent_name: str, prompt: str
    ) -> None:
        """Dispatch on_subagent_start to all hooks (Claude ``SubagentStart``)."""
        self._ensure_sorted()
        await self._dispatch("on_subagent_start", context, agent_name, prompt)

    async def dispatch_subagent_stop(
        self, context: AgentContext, agent_name: str, result: dict[str, Any]
    ) -> None:
        """Dispatch on_subagent_stop to all hooks (Claude ``SubagentStop``)."""
        self._ensure_sorted()
        await self._dispatch("on_subagent_stop", context, agent_name, result)

    async def _dispatch(self, method_name: str, *args: Any) -> None:
        """Dispatch a method call to all hooks."""
        for hook in self._hooks:
            try:
                method = getattr(hook, method_name, None)
                if method and callable(method):
                    await method(*args)
            except Exception as e:
                logger.warning(
                    "hook_error",
                    hook_class=hook.__class__.__name__,
                    method=method_name,
                    error=str(e),
                )


class LoggingHook(AgentHook):
    """Hook that logs all agent lifecycle events.

    This is useful for debugging and audit trails.
    """

    priority = 10

    def __init__(self, log_level: str = "info") -> None:
        self.log_level = log_level.lower()
        self._log = getattr(logger, self.log_level, logger.info)

    async def on_start(self, context: AgentContext, user_input: str) -> None:
        self._log(
            "agent_start",
            task_id=str(context.task_id),
            session_id=str(context.session_id),
            user_id=str(context.user_id) if context.user_id else None,
            input_preview=user_input[:100] if user_input else "",
        )

    async def on_step(self, context: AgentContext, step: ExecutionStep) -> None:
        self._log(
            "agent_step",
            task_id=str(context.task_id),
            step_type=step.type.value,
            step_id=str(step.id),
            iteration=context.iteration,
        )

    async def on_tool_call(self, context: AgentContext, tool_call: ToolCall) -> None:
        self._log(
            "agent_tool_call",
            task_id=str(context.task_id),
            tool=tool_call.name,
            call_id=tool_call.id,
        )

    async def on_tool_result(
        self,
        context: AgentContext,
        tool_call: ToolCall,
        result: ToolResult,
    ) -> None:
        self._log(
            "agent_tool_result",
            task_id=str(context.task_id),
            tool=tool_call.name,
            success=result.success,
            duration_ms=result.duration_ms,
        )

    async def on_plan_created(self, context: AgentContext, plan: ExecutionPlan) -> None:
        self._log(
            "agent_plan_created",
            task_id=str(context.task_id),
            plan_id=str(plan.id),
            goal=plan.goal[:100] if plan.goal else "",
            step_count=len(plan.steps),
        )

    async def on_complete(self, context: AgentContext, response: AgentResponse) -> None:
        self._log(
            "agent_complete",
            task_id=str(context.task_id),
            success=response.success,
            partial=response.partial,
            steps_count=len(response.steps),
            duration_ms=response.total_duration_ms,
            files_count=len(response.files),
        )

    async def on_error(self, context: AgentContext, error: Exception) -> None:
        logger.error(
            "agent_error",
            task_id=str(context.task_id),
            error_type=type(error).__name__,
            error_message=str(error),
        )

    async def on_cancel(self, context: AgentContext) -> None:
        self._log(
            "agent_cancelled",
            task_id=str(context.task_id),
            iteration=context.iteration,
            elapsed_ms=context.elapsed_ms,
        )

    async def on_code_artifact(self, artifact: "CodeArtifact") -> None:
        self._log(
            "agent_code_artifact",
            artifact_id=artifact.artifact_id,
            kind=artifact.kind.value if hasattr(artifact.kind, "value") else str(artifact.kind),
            language=artifact.language,
            origin_tool=artifact.origin_tool,
            syntax_valid=artifact.syntax_valid,
            source_length=len(artifact.source),
            target_path=artifact.target_path,
        )


# NOTE: the legacy ``MemoryCompactionHook`` was deleted in the session /
# memory redesign. Compaction now happens inside the query loop through
# :mod:`leagent.memory.compact` (``build_microcompact`` / ``build_autocompact``),
# which is driven by token budgets rather than an external hook, so the
# hook was pure dead weight. The :class:`SessionManager` holds the
# authoritative transcript and clamps it before persistence.


class MetricsHook(AgentHook):
    """Hook that collects and reports metrics.

    Tracks:
    - Task duration
    - Step counts by type
    - Tool success/failure rates
    - Token usage
    """

    priority = 20

    def __init__(self) -> None:
        self._task_metrics: dict[UUID, dict[str, Any]] = {}

    async def on_start(self, context: AgentContext, user_input: str) -> None:
        self._task_metrics[context.task_id] = {
            "start_time": time.perf_counter(),
            "steps_by_type": {},
            "tool_calls": 0,
            "tool_successes": 0,
            "tool_failures": 0,
            "input_tokens": len(user_input) // 3,
        }

    async def on_step(self, context: AgentContext, step: ExecutionStep) -> None:
        metrics = self._task_metrics.get(context.task_id)
        if not metrics:
            return

        step_type = step.type.value
        metrics["steps_by_type"][step_type] = metrics["steps_by_type"].get(step_type, 0) + 1

    async def on_tool_result(
        self,
        context: AgentContext,
        tool_call: ToolCall,
        result: ToolResult,
    ) -> None:
        metrics = self._task_metrics.get(context.task_id)
        if not metrics:
            return

        metrics["tool_calls"] += 1
        if result.success:
            metrics["tool_successes"] += 1
        else:
            metrics["tool_failures"] += 1

    async def on_complete(self, context: AgentContext, response: AgentResponse) -> None:
        metrics = self._task_metrics.pop(context.task_id, None)
        if not metrics:
            return

        duration_sec = time.perf_counter() - metrics["start_time"]

        logger.info(
            "task_metrics",
            task_id=str(context.task_id),
            duration_sec=round(duration_sec, 2),
            steps_by_type=metrics["steps_by_type"],
            tool_calls=metrics["tool_calls"],
            tool_success_rate=(
                metrics["tool_successes"] / metrics["tool_calls"]
                if metrics["tool_calls"] > 0
                else 0
            ),
            total_steps=sum(metrics["steps_by_type"].values()),
        )

    async def on_error(self, context: AgentContext, error: Exception) -> None:
        self._task_metrics.pop(context.task_id, None)


class TaskHistoryHook(AgentHook):
    """Record finished task outcomes into :class:`AgentMemory` via the formation policy.

    The formation policy scores the turn across multiple signals (tool
    outcomes, complexity, user intent) and decides what to write —
    episodic, procedural, or semantic memory. User likes remain a
    positive reinforcement signal but are no longer the exclusive gate.
    """

    priority = 90

    def __init__(self, agent_memory: "AgentMemory | None" = None) -> None:
        self.agent_memory = agent_memory

    async def on_complete(self, context: AgentContext, response: AgentResponse) -> None:
        """Evaluate the completed turn via :meth:`AgentMemory.observe_turn`."""
        if self.agent_memory is None:
            return

        from leagent.memory.formation import TriggerKind, TurnObservation

        tool_names: list[str] = []
        tool_successes = 0
        tool_failures = 0
        for step in context.steps:
            if step.type == StepType.TOOL_CALL and step.tool_call:
                tool_names.append(step.tool_call.name)
            if step.type == StepType.TOOL_RESULT and step.tool_result:
                if step.tool_result.success:
                    tool_successes += 1
                else:
                    tool_failures += 1

        user_text = ""
        for step in context.steps:
            if step.type == StepType.THOUGHT and step.thought:
                user_text = step.thought[:400]
                break

        obs = TurnObservation(
            session_id=context.session_id,
            user_id=context.user_id,
            trigger=TriggerKind.TURN_COMPLETE,
            user_text=user_text,
            assistant_text=(response.text or "")[:800],
            tool_names=tool_names,
            tool_success_count=tool_successes,
            tool_failure_count=tool_failures,
            total_steps=len(context.steps),
            duration_ms=response.total_duration_ms,
            tags=[f"path:{p}" for p in self._extract_paths(context)[:48]],
        )

        try:
            await self.agent_memory.observe_turn(obs)
        except Exception as exc:
            logger.warning(
                "task_history_hook_observe_failed",
                error=str(exc),
                task_id=str(context.task_id),
            )

    def _extract_paths(self, context: AgentContext) -> list[str]:
        """Extract file paths touched during the task for episode tags."""
        paths: list[str] = []
        seen: set[str] = set()
        for step in context.steps:
            if step.type == StepType.TOOL_RESULT and step.tool_result:
                for item in (step.tool_result.data or {}).get("files", []):
                    p = item if isinstance(item, str) else str(item)
                    if p and p not in seen:
                        seen.add(p)
                        paths.append(p)
        return paths

    def _build_task_summary(
        self,
        context: AgentContext,
        response: AgentResponse,
    ) -> dict[str, str]:
        """Build a summary of the task for storage."""
        input_summary = ""
        for step in context.steps:
            if step.type == StepType.THOUGHT and step.thought:
                input_summary = step.thought[:200]
                break

        output_summary = response.text[:200] if response.text else "No output"

        return {"input": input_summary, "output": output_summary}

    def _infer_task_type(self, context: AgentContext) -> str:
        """Infer the type of task from context."""
        tool_names = set()
        for step in context.steps:
            if step.type == StepType.TOOL_CALL and step.tool_call:
                tool_names.add(step.tool_call.name)

        if any("pdf" in t or "word" in t or "excel" in t for t in tool_names):
            return "document_processing"
        if any("web" in t or "scrape" in t for t in tool_names):
            return "web_automation"
        if any("data" in t or "validate" in t for t in tool_names):
            return "data_processing"
        if any("report" in t or "generate" in t for t in tool_names):
            return "generation"

        return "general"


class RateLimitHook(AgentHook):
    """Hook that enforces rate limits on agent execution.

    Prevents abuse by limiting the number of tasks per user/session.
    """

    priority = 5

    def __init__(
        self,
        *,
        max_tasks_per_minute: int = 10,
        max_tasks_per_hour: int = 100,
    ) -> None:
        self.max_tasks_per_minute = max_tasks_per_minute
        self.max_tasks_per_hour = max_tasks_per_hour
        self._task_timestamps: dict[UUID, list[datetime]] = {}

    async def on_start(self, context: AgentContext, user_input: str) -> None:
        user_key = context.user_id or context.session_id
        now = datetime.utcnow()

        if user_key not in self._task_timestamps:
            self._task_timestamps[user_key] = []

        timestamps = self._task_timestamps[user_key]
        timestamps = [
            ts for ts in timestamps
            if (now - ts).seconds < 3600
        ]
        self._task_timestamps[user_key] = timestamps

        recent_minute = [ts for ts in timestamps if (now - ts).seconds < 60]

        if len(recent_minute) >= self.max_tasks_per_minute:
            raise RateLimitError(
                f"Rate limit exceeded: {self.max_tasks_per_minute} tasks per minute"
            )

        if len(timestamps) >= self.max_tasks_per_hour:
            raise RateLimitError(
                f"Rate limit exceeded: {self.max_tasks_per_hour} tasks per hour"
            )

        timestamps.append(now)


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""

    pass


class TraceHook(AgentHook):
    """Observer-only hook that augments the durable agent running-trace.

    Tool open/close is primarily recorded from ``run_loop`` events; this hook
    covers compact / subagent boundaries that are not always mirrored as
    ``AgentEvent`` frames.
    """

    priority = 15

    async def on_pre_compact(self, context: AgentContext, reason: str) -> None:
        try:
            from leagent.telemetry.trace import get_trace_recorder

            get_trace_recorder().record_compact(reason)
        except Exception:
            logger.debug("trace_hook_compact_failed", exc_info=True)

    async def on_subagent_start(
        self, context: AgentContext, agent_name: str, prompt: str
    ) -> None:
        try:
            from leagent.telemetry.trace import get_trace_recorder

            get_trace_recorder().record_subagent(
                agent_name=agent_name, phase="start", prompt=prompt
            )
        except Exception:
            logger.debug("trace_hook_subagent_start_failed", exc_info=True)

    async def on_subagent_stop(
        self, context: AgentContext, agent_name: str, result: dict[str, Any]
    ) -> None:
        try:
            from leagent.telemetry.trace import get_trace_recorder

            preview = None
            if isinstance(result, dict):
                preview = str(result.get("text") or result.get("summary") or "")[:2000]
            get_trace_recorder().record_subagent(
                agent_name=agent_name, phase="stop", result_preview=preview
            )
        except Exception:
            logger.debug("trace_hook_subagent_stop_failed", exc_info=True)


def create_default_hooks(
    agent_memory: "AgentMemory | None" = None,
) -> list[AgentHook]:
    """Create the default hook lineup the controller uses by default.

    Always starts with ``LoggingHook`` + ``MetricsHook`` so every deployed
    instance has observability. When ``agent_memory`` is provided, the
    ``TaskHistoryHook`` is appended so finished turns become
    :class:`Procedure` rows the planner can rank next time.
    """
    hooks: list[AgentHook] = [
        LoggingHook(log_level="info"),
        MetricsHook(),
        TraceHook(),
    ]

    if agent_memory is not None:
        hooks.append(TaskHistoryHook(agent_memory))

    return hooks
