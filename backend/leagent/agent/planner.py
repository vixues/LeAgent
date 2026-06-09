"""TaskPlanner: task decomposition, plan construction, and dependency scheduling.

.. deprecated:: 0.1.0
   The Plan-Execute mode is superseded by the unified SDK runtime
   (:class:`~leagent.sdk.AgentRuntime`). This module is kept for backward
   compatibility but is scheduled for removal. New code should use the
   SDK's ``AgentRuntime.run`` / ``AgentRuntime.stream`` instead.

This module provides the Plan-Execute path used by
:class:`leagent.agent.controller.AgentController._run_plan_execute` and any
workflow that wants a structured, step-wise plan instead of the ReAct-style
``QueryEngine`` turn loop.

The planner is deliberately small:

* :meth:`TaskPlanner.plan` — ask the LLM to produce a structured
  :class:`ExecutionPlan` for a user task.
* :meth:`TaskPlanner.replan` — ask the LLM for the *adjusted remaining
  steps* after a failure. The caller merges them back into the plan so we
  never duplicate completed step IDs.
* :meth:`TaskPlanner.estimate_complexity` — lightweight heuristic used by
  :class:`AgentController` to decide between ReAct and Plan-Execute in
  ``AgentMode.HYBRID``.

Scheduling helpers (:func:`topological_sort`, :func:`get_parallel_groups`,
:func:`schedule_ready`) let the executor dispatch independent steps
concurrently the same way the QueryEngine partitions concurrent-safe tool
calls.

All LLM calls accept an optional ``abort_event`` so a user-triggered
cancellation mid-plan is surfaced as :class:`asyncio.CancelledError`
rather than waiting for the model to finish streaming.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

import structlog

from leagent.agent.base import (
    AgentContext,
    ExecutionPlan,
    PlanStep,
)

if TYPE_CHECKING:
    from leagent.llm import LLMService
    from leagent.memory import AgentMemory
    from leagent.rules import RuleEngine
    from leagent.tools import ToolRegistry

logger = structlog.get_logger(__name__)


PLAN_PROMPT_TEMPLATE = """You are a task planner. Given the user's task, produce a step-by-step execution plan.

Available tools:
{tool_summaries}

{relevant_knowledge}

{applicable_rules}

User task: {task}

Respond with a JSON plan in the following format:
{{
  "goal": "Clear statement of what needs to be accomplished",
  "steps": [
    {{
      "id": 1,
      "description": "Human-readable description of this step",
      "tool": "tool_name or null if no tool needed",
      "params": {{}},
      "depends_on": []
    }}
  ],
  "expected_output": "Description of the expected final output"
}}

Guidelines:
- Break complex tasks into atomic steps
- Identify dependencies between steps (use depends_on)
- Choose the most appropriate tool for each step
- Steps without tools are for reasoning/aggregation
- Keep the plan focused and efficient
- Maximum 10 steps for a single plan

Respond ONLY with the JSON plan, no other text."""


REPLAN_PROMPT_TEMPLATE = """A step in the execution plan has failed. Provide an adjusted plan for the **remaining** work only.

Step that failed:
- ID: {step_id}
- Description: {step_description}
- Error: {error}

Original plan goal: {goal}

Completed steps so far:
{completed_steps}

Rules:
- Do NOT repeat steps that are already completed (their IDs: {completed_ids}).
- You MAY skip the failed step if it is not critical.
- You MAY retry with different parameters.
- You MAY add alternative steps.
- New step IDs must not collide with completed IDs — start numbering from {next_id}.

Respond with a JSON plan in the same format as the original, containing ONLY the remaining/adjusted steps."""


# Lightweight keyword weighting used by AgentController to decide ReAct vs
# Plan-Execute in ``AgentMode.HYBRID``. Kept here alongside the planner so
# the scoring rules travel with the planning knowledge.
_COMPLEXITY_KEYWORDS: tuple[tuple[str, int], ...] = (
    ("analyze", 2),
    ("report", 2),
    ("compare", 2),
    ("multiple", 2),
    ("batch", 2),
    ("evaluate", 2),
    ("extract", 1),
    ("summarize", 1),
    ("format", 0),
    ("convert", 0),
)


class TaskPlanner:
    """Plans and decomposes tasks into executable steps.

    Attributes:
        llm: LLM service used for plan generation.
        tools: Tool registry (enabled tools are surfaced to the LLM).
        agent_memory: Optional :class:`AgentMemory` facade used to pull
            relevant past episodes / facts into the planning prompt.
        rule_engine: Optional rule engine for surfacing applicable rule sets.
    """

    def __init__(
        self,
        llm: "LLMService",
        tools: "ToolRegistry | None" = None,
        *,
        agent_memory: "AgentMemory | None" = None,
        rule_engine: "RuleEngine | None" = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.agent_memory = agent_memory
        self.rule_engine = rule_engine

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def plan(
        self,
        task: str,
        context: AgentContext,
        *,
        abort_event: asyncio.Event | None = None,
    ) -> ExecutionPlan:
        """Create an execution plan for a user task.

        Args:
            task: Natural-language task description.
            context: Current agent context (used for logging only).
            abort_event: Optional shared abort signal. When set, the LLM
                call is cancelled and :class:`asyncio.CancelledError` is
                raised.

        Returns:
            An :class:`ExecutionPlan` with one or more :class:`PlanStep`.
        """
        logger.info("planning_task", task_id=str(context.task_id), task=task[:100])

        tool_summaries = self._get_tool_summaries()
        relevant_knowledge = await self._get_relevant_knowledge(
            task, user_id=context.user_id
        )
        applicable_rules = self._get_applicable_rules(task)

        prompt = PLAN_PROMPT_TEMPLATE.format(
            tool_summaries=tool_summaries,
            relevant_knowledge=relevant_knowledge,
            applicable_rules=applicable_rules,
            task=task,
        )

        response = await self._chat_with_abort(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            abort_event=abort_event,
        )

        plan_data = self._parse_plan_response(response.get("content", ""))
        plan = self._build_plan(plan_data)
        self._validate_plan(plan)

        logger.info(
            "plan_created",
            task_id=str(context.task_id),
            goal=plan.goal,
            step_count=len(plan.steps),
        )
        return plan

    async def replan(
        self,
        original_plan: ExecutionPlan,
        failed_step: PlanStep,
        error: str,
        *,
        abort_event: asyncio.Event | None = None,
    ) -> ExecutionPlan | None:
        """Produce an adjusted plan covering the remaining work.

        Unlike the previous implementation, ``replan`` returns a plan
        that contains **only the adjusted/new steps**. It is the caller's
        responsibility to merge these into the original plan (see
        :meth:`merge_replan`), which keeps completed-step bookkeeping in
        one place and avoids the duplicate-ID bug the old code had.

        Returns ``None`` if the LLM response cannot be parsed.
        """
        logger.info(
            "replanning",
            plan_id=str(original_plan.id),
            failed_step=failed_step.id,
            error=error[:100],
        )

        completed_ids = list(original_plan.completed_steps)
        next_id = (max((s.id for s in original_plan.steps), default=0) + 1) if original_plan.steps else 1

        prompt = REPLAN_PROMPT_TEMPLATE.format(
            step_id=failed_step.id,
            step_description=failed_step.description,
            error=error,
            goal=original_plan.goal,
            completed_steps=self._format_completed_steps(original_plan),
            completed_ids=", ".join(str(i) for i in completed_ids) or "(none)",
            next_id=next_id,
        )

        response = await self._chat_with_abort(
            [{"role": "user", "content": prompt}],
            temperature=0.1,
            abort_event=abort_event,
        )

        try:
            plan_data = self._parse_plan_response(response.get("content", ""))
            new_plan = self._build_plan(plan_data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("replan_parse_failed", error=str(exc))
            return None

        # Drop any steps the LLM echoed that conflict with completed IDs.
        completed_set = set(completed_ids)
        new_plan.steps = [s for s in new_plan.steps if s.id not in completed_set]

        logger.info(
            "replan_created",
            plan_id=str(new_plan.id),
            new_step_count=len(new_plan.steps),
        )
        return new_plan

    @staticmethod
    def merge_replan(original: ExecutionPlan, replan: ExecutionPlan) -> ExecutionPlan:
        """Merge an adjustment plan into the original.

        Completed steps are preserved verbatim; the failed step is marked
        ``skipped`` if the replan does not reintroduce it; new steps are
        appended. Mutates ``original`` in place and returns it for
        chaining.
        """
        completed_set = set(original.completed_steps)
        existing_ids = {s.id for s in original.steps}

        # Mark any non-completed, non-replaced step as skipped — the
        # replan represents the new canonical roadmap for pending work.
        replan_ids = {s.id for s in replan.steps}
        for step in original.steps:
            if step.id in completed_set:
                continue
            if step.id not in replan_ids:
                step.status = "skipped"

        # Append new steps (IDs guaranteed to not collide with completed
        # ones thanks to ``replan``'s filter).
        for step in replan.steps:
            if step.id in existing_ids:
                # Replace pending copy.
                for i, existing in enumerate(original.steps):
                    if existing.id == step.id and existing.status == "pending":
                        original.steps[i] = step
                        break
            else:
                original.steps.append(step)

        return original

    def estimate_complexity(self, task: str) -> int:
        """Heuristic score (1-10) used for ReAct/Plan-Execute routing.

        Small, deterministic, and cheap — the whole point is that we
        avoid an extra LLM roundtrip just to classify a request.
        """
        score = 1
        lower = task.lower()
        for keyword, weight in _COMPLEXITY_KEYWORDS:
            if keyword in lower:
                score += weight
        if len(task) > 500:
            score += 2
        elif len(task) > 200:
            score += 1
        return min(score, 10)

    # ------------------------------------------------------------------
    # Context helpers
    # ------------------------------------------------------------------

    def _get_tool_summaries(self) -> str:
        """Format enabled tools for the plan prompt.

        Deny-listed / disabled tools are excluded so the planner cannot
        propose steps the executor will refuse.
        """
        if not self.tools:
            return "No tools available."

        lines: list[str] = []
        get_enabled = getattr(self.tools, "get_enabled_tools", None)
        tools_iter = get_enabled() if callable(get_enabled) else self.tools.list_tools()

        for tool in tools_iter:
            params_str = ""
            params = getattr(tool, "parameters", None)
            if isinstance(params, dict):
                props = params.get("properties") or {}
                if props:
                    param_names = list(props.keys())[:5]
                    params_str = f" (params: {', '.join(param_names)})"
            lines.append(f"- {tool.name}: {tool.description}{params_str}")

        return "\n".join(lines) if lines else "No tools available."

    async def _get_relevant_knowledge(
        self,
        task: str,
        *,
        user_id: Any = None,
    ) -> str:
        """Retrieve planning-relevant context from :class:`AgentMemory`.

        Returns a newline-joined bullet list ready to drop into the
        planning prompt. Empty string when no agent memory is configured
        or the recall returns nothing.
        """
        if self.agent_memory is None:
            return ""

        try:
            bundle = await self.agent_memory.recall(
                task,
                user_id=user_id,
                limit=3,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("knowledge_retrieval_failed", error=str(exc))
            return ""

        if not bundle.entries:
            return ""

        lines = ["Relevant knowledge:"]
        for entry in bundle.entries:
            summary = (getattr(entry, "text", "") or "").strip()
            if not summary:
                continue
            lines.append(f"- [{entry.kind.value}] {summary[:500]}")
        return "\n".join(lines) if len(lines) > 1 else ""

    def _get_applicable_rules(self, task: str) -> str:
        """Surface rule sets whose tags match the task description.

        ``RuleEngine.find_applicable_rules`` is synchronous and takes a
        context dict — we pass the task under ``query`` so tag matching
        can fall through to ``context.get('tags')`` as designed.
        """
        if not self.rule_engine:
            return ""

        try:
            rule_sets = self.rule_engine.find_applicable_rules({"query": task})
        except Exception as exc:  # noqa: BLE001
            logger.warning("rule_retrieval_failed", error=str(exc))
            return ""

        if not rule_sets:
            return ""

        lines = ["Applicable rules:"]
        for rs in rule_sets:
            name = getattr(rs, "name", "") or getattr(rs, "id", "")
            description = getattr(rs, "description", "") or ""
            lines.append(f"- {name}: {description}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Parsing / building
    # ------------------------------------------------------------------

    def _parse_plan_response(self, content: str) -> dict[str, Any]:
        """Parse an LLM plan response, tolerating markdown fences."""
        content = content.strip()

        if content.startswith("```"):
            # Strip ```json ... ``` fences.
            lines = content.split("\n")
            if lines[-1].startswith("```"):
                lines = lines[:-1]
            # drop leading fence
            lines = lines[1:]
            content = "\n".join(lines).strip()
            if content.startswith("json"):
                content = content[4:].strip()

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            logger.warning("plan_parse_failed", error=str(exc), content=content[:200])
            return {
                "goal": "Execute the requested task",
                "steps": [
                    {
                        "id": 1,
                        "description": "Process the request",
                        "tool": None,
                        "params": {},
                        "depends_on": [],
                    }
                ],
                "expected_output": "Task result",
            }

    def _build_plan(self, plan_data: dict[str, Any]) -> ExecutionPlan:
        steps: list[PlanStep] = []
        for step_data in plan_data.get("steps", []):
            steps.append(
                PlanStep(
                    id=step_data.get("id", len(steps) + 1),
                    description=step_data.get("description", ""),
                    tool=step_data.get("tool"),
                    params=step_data.get("params", {}),
                    depends_on=step_data.get("depends_on", []),
                )
            )
        return ExecutionPlan(
            goal=plan_data.get("goal", ""),
            steps=steps,
            expected_output=plan_data.get("expected_output", ""),
        )

    def _validate_plan(self, plan: ExecutionPlan) -> None:
        """Log-only validation (bad refs do not abort planning)."""
        if not plan.steps:
            logger.warning("plan_empty", plan_id=str(plan.id))
            return

        step_ids = {s.id for s in plan.steps}
        for step in plan.steps:
            for dep in step.depends_on:
                if dep not in step_ids:
                    logger.warning(
                        "plan_invalid_dependency",
                        step_id=step.id,
                        missing_dep=dep,
                    )
            if step.tool and self.tools is not None:
                try:
                    self.tools.get(step.tool)
                except Exception:  # noqa: BLE001
                    logger.warning(
                        "plan_unknown_tool",
                        step_id=step.id,
                        tool=step.tool,
                    )

    def _format_completed_steps(self, plan: ExecutionPlan) -> str:
        completed = [s for s in plan.steps if s.status == "completed"]
        if not completed:
            return "No steps completed yet."
        lines: list[str] = []
        for step in completed:
            preview = str(step.result)[:100] if step.result else "OK"
            lines.append(f"- Step {step.id}: {step.description} -> {preview}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # LLM call with abort
    # ------------------------------------------------------------------

    async def _chat_with_abort(
        self,
        messages: list[dict[str, Any]],
        *,
        temperature: float,
        abort_event: asyncio.Event | None,
    ) -> dict[str, Any]:
        """Run an LLM chat call that respects an optional abort event."""
        chat_task = asyncio.create_task(
            self.llm.chat(
                messages=messages,
                temperature=temperature,
            )
        )
        if abort_event is None:
            return await chat_task

        abort_task = asyncio.create_task(abort_event.wait())
        try:
            done, _pending = await asyncio.wait(
                {chat_task, abort_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            if not abort_task.done():
                abort_task.cancel()

        if abort_task in done and not chat_task.done():
            chat_task.cancel()
            try:
                await chat_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            raise asyncio.CancelledError("planner aborted")
        return await chat_task


# ---------------------------------------------------------------------------
# Scheduling helpers (used by Plan-Execute to parallelise independent steps).
# ---------------------------------------------------------------------------


def build_dependency_graph(steps: list[PlanStep]) -> dict[int, list[int]]:
    """Reverse-adjacency: step ID -> step IDs that depend on it."""
    graph: dict[int, list[int]] = {s.id: [] for s in steps}
    for step in steps:
        for dep_id in step.depends_on:
            if dep_id in graph:
                graph[dep_id].append(step.id)
    return graph


def topological_sort(steps: list[PlanStep]) -> list[PlanStep]:
    """Order steps so every step appears after its dependencies.

    On cycle, returns the partial order (cycle members omitted) and logs
    a warning — matches the prior behaviour the tests rely on.
    """
    in_degree = {s.id: len(s.depends_on) for s in steps}
    step_map = {s.id: s for s in steps}
    graph = build_dependency_graph(steps)

    queue = [sid for sid, deg in in_degree.items() if deg == 0]
    result: list[PlanStep] = []

    while queue:
        current = queue.pop(0)
        result.append(step_map[current])
        for dependent in graph[current]:
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    if len(result) != len(steps):
        logger.warning("circular_dependency_detected")
    return result


def get_parallel_groups(steps: list[PlanStep]) -> list[list[PlanStep]]:
    """Group steps into waves that can run in parallel.

    Wave ``i+1`` depends only on steps that have completed in wave
    ``<= i``. Mirrors the concurrency rule the QueryEngine applies to
    tool calls (``is_concurrency_safe``).
    """
    sorted_steps = topological_sort(steps)
    completed: set[int] = set()
    groups: list[list[PlanStep]] = []
    remaining = list(sorted_steps)

    while remaining:
        ready: list[PlanStep] = []
        not_ready: list[PlanStep] = []
        for step in remaining:
            if all(dep in completed for dep in step.depends_on):
                ready.append(step)
            else:
                not_ready.append(step)

        if ready:
            groups.append(ready)
            completed.update(s.id for s in ready)
        remaining = not_ready

        if not ready and remaining:
            # Cycle residue — emit as a final best-effort group.
            groups.append(remaining)
            break

    return groups


def schedule_ready(plan: ExecutionPlan) -> list[PlanStep]:
    """Return the next batch of steps whose dependencies are satisfied.

    Drives the Plan-Execute loop: the controller dispatches this batch
    concurrently (sharing the QueryEngine's partition rules), marks
    completions on the plan, and calls ``schedule_ready`` again until
    :attr:`ExecutionPlan.is_complete`.
    """
    ready: list[PlanStep] = []
    completed = set(plan.completed_steps)
    for step in plan.steps:
        if step.status != "pending":
            continue
        if all(dep in completed for dep in step.depends_on):
            ready.append(step)
    return ready


__all__ = [
    "TaskPlanner",
    "build_dependency_graph",
    "topological_sort",
    "get_parallel_groups",
    "schedule_ready",
]
