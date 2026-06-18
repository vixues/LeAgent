"""Tests for TaskPlanner: scheduling helpers, parse/build, plan/replan, memory/rule plumbing."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from leagent.agent.base import AgentContext, ExecutionPlan, PlanStep
from leagent.agent.planner import (
    TaskPlanner,
    build_dependency_graph,
    get_parallel_groups,
    schedule_ready,
    topological_sort,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _steps(*specs: tuple[int, list[int]]) -> list[PlanStep]:
    """Create a list of PlanStep from (id, depends_on) specs."""
    return [PlanStep(id=sid, description=f"Step {sid}", depends_on=deps) for sid, deps in specs]


def _mock_llm(response_content: str) -> MagicMock:
    llm = MagicMock()
    llm.chat = AsyncMock(return_value={"content": response_content})
    return llm


# ===========================================================================
# topological_sort
# ===========================================================================


class TestTopologicalSort:
    def test_linear_chain(self) -> None:
        steps = _steps((1, []), (2, [1]), (3, [2]))
        ordered = topological_sort(steps)
        ids = [s.id for s in ordered]
        assert ids.index(1) < ids.index(2) < ids.index(3)

    def test_parallel_independent(self) -> None:
        steps = _steps((1, []), (2, []), (3, []))
        ordered = topological_sort(steps)
        ids = {s.id for s in ordered}
        assert ids == {1, 2, 3}

    def test_diamond_shape(self) -> None:
        # 1 -> 2, 3 -> 4
        steps = _steps((1, []), (2, [1]), (3, [1]), (4, [2, 3]))
        ordered = topological_sort(steps)
        ids = [s.id for s in ordered]
        assert ids[0] == 1
        assert ids[-1] == 4

    def test_cycle_detection_returns_partial(self) -> None:
        # A cycle: 1->2->3->1
        steps = _steps((1, [3]), (2, [1]), (3, [2]))
        # With cycle, topological_sort returns a partial list (fewer than 3)
        ordered = topological_sort(steps)
        assert len(ordered) < 3  # cycle detected → fewer nodes returned

    def test_single_step_no_deps(self) -> None:
        steps = _steps((1, []))
        ordered = topological_sort(steps)
        assert len(ordered) == 1

    def test_all_steps_returned_without_cycle(self) -> None:
        steps = _steps((1, []), (2, [1]), (3, [1]), (4, [2, 3]))
        ordered = topological_sort(steps)
        assert len(ordered) == 4


# ===========================================================================
# get_parallel_groups
# ===========================================================================


class TestGetParallelGroups:
    def test_all_independent_one_group(self) -> None:
        steps = _steps((1, []), (2, []), (3, []))
        groups = get_parallel_groups(steps)
        assert len(groups) == 1
        assert len(groups[0]) == 3

    def test_linear_chain_sequential_groups(self) -> None:
        steps = _steps((1, []), (2, [1]), (3, [2]))
        groups = get_parallel_groups(steps)
        assert len(groups) == 3
        assert groups[0][0].id == 1
        assert groups[1][0].id == 2
        assert groups[2][0].id == 3

    def test_diamond_two_parallel_steps(self) -> None:
        steps = _steps((1, []), (2, [1]), (3, [1]), (4, [2, 3]))
        groups = get_parallel_groups(steps)
        # Group 1: step 1 | Group 2: steps 2&3 | Group 3: step 4
        assert len(groups) == 3
        parallel_ids = {s.id for s in groups[1]}
        assert 2 in parallel_ids and 3 in parallel_ids


# ===========================================================================
# build_dependency_graph
# ===========================================================================


class TestBuildDependencyGraph:
    def test_linear_chain(self) -> None:
        steps = _steps((1, []), (2, [1]), (3, [2]))
        graph = build_dependency_graph(steps)
        assert 1 in graph[1] == [] or graph[1] == [2]
        assert 2 in graph[2] or graph[2] == [3]

    def test_all_independent(self) -> None:
        steps = _steps((1, []), (2, []), (3, []))
        graph = build_dependency_graph(steps)
        for sid in [1, 2, 3]:
            assert graph[sid] == []

    def test_diamond(self) -> None:
        steps = _steps((1, []), (2, [1]), (3, [1]), (4, [2, 3]))
        graph = build_dependency_graph(steps)
        # step 1 is depended on by steps 2 and 3
        assert set(graph[1]) == {2, 3}
        assert graph[2] == [4]
        assert graph[3] == [4]
        assert graph[4] == []


# ===========================================================================
# TaskPlanner._parse_plan_response
# ===========================================================================


class TestParsePlanResponse:
    def _planner(self) -> TaskPlanner:
        return TaskPlanner(llm=_mock_llm(""))

    def test_valid_json(self) -> None:
        planner = self._planner()
        plan_json = json.dumps({
            "goal": "Do something useful",
            "steps": [
                {"id": 1, "description": "First step", "tool": None, "params": {}, "depends_on": []},
                {"id": 2, "description": "Second step", "tool": "pdf_reader", "params": {"file_path": "/f.pdf"}, "depends_on": [1]},
            ],
            "expected_output": "Processed data",
        })
        result = planner._parse_plan_response(plan_json)
        assert result["goal"] == "Do something useful"
        assert len(result["steps"]) == 2

    def test_json_wrapped_in_code_block(self) -> None:
        planner = self._planner()
        plan_json = json.dumps({"goal": "Test", "steps": [], "expected_output": ""})
        wrapped = f"```json\n{plan_json}\n```"
        result = planner._parse_plan_response(wrapped)
        assert result["goal"] == "Test"

    def test_malformed_json_returns_fallback(self) -> None:
        planner = self._planner()
        result = planner._parse_plan_response("This is not JSON at all!")
        # Should return fallback plan with at least one step
        assert "goal" in result
        assert "steps" in result
        assert len(result["steps"]) >= 1

    def test_empty_string_returns_fallback(self) -> None:
        planner = self._planner()
        result = planner._parse_plan_response("")
        assert "steps" in result

    def test_partial_json_returns_fallback(self) -> None:
        planner = self._planner()
        result = planner._parse_plan_response('{"goal": "incomplete"')
        assert "steps" in result


# ===========================================================================
# TaskPlanner._build_plan
# ===========================================================================


class TestBuildPlan:
    def _planner(self) -> TaskPlanner:
        return TaskPlanner(llm=_mock_llm(""))

    def test_build_plan_from_data(self) -> None:
        planner = self._planner()
        data = {
            "goal": "Read and summarize a PDF",
            "steps": [
                {"id": 1, "description": "Read PDF", "tool": "pdf_reader", "params": {}, "depends_on": []},
                {"id": 2, "description": "Summarize", "tool": None, "params": {}, "depends_on": [1]},
            ],
            "expected_output": "Summary",
        }
        plan = planner._build_plan(data)
        assert isinstance(plan, ExecutionPlan)
        assert plan.goal == "Read and summarize a PDF"
        assert len(plan.steps) == 2
        assert plan.steps[0].tool == "pdf_reader"
        assert plan.steps[1].depends_on == [1]

    def test_build_plan_empty_steps(self) -> None:
        planner = self._planner()
        data = {"goal": "Simple task", "steps": [], "expected_output": ""}
        plan = planner._build_plan(data)
        assert plan.goal == "Simple task"
        assert len(plan.steps) == 0


# ===========================================================================
# TaskPlanner.plan — integration with mock LLM
# ===========================================================================


@pytest.mark.asyncio
class TestTaskPlannerPlan:
    async def test_plan_creates_execution_plan(self) -> None:
        plan_json = json.dumps({
            "goal": "Process documents",
            "steps": [
                {"id": 1, "description": "Read the document", "tool": "pdf_reader", "params": {}, "depends_on": []},
            ],
            "expected_output": "Text extracted",
        })
        llm = _mock_llm(plan_json)
        planner = TaskPlanner(llm=llm)
        ctx = AgentContext(task_id=uuid4(), session_id=uuid4())

        plan = await planner.plan("Read and process a PDF file", ctx)
        assert isinstance(plan, ExecutionPlan)
        assert plan.goal == "Process documents"
        assert len(plan.steps) == 1

    async def test_plan_falls_back_on_llm_malformed_response(self) -> None:
        llm = _mock_llm("definitely not json here")
        planner = TaskPlanner(llm=llm)
        ctx = AgentContext(task_id=uuid4(), session_id=uuid4())

        plan = await planner.plan("some task", ctx)
        assert isinstance(plan, ExecutionPlan)
        assert len(plan.steps) >= 1  # fallback plan


# ===========================================================================
# schedule_ready
# ===========================================================================


class TestScheduleReady:
    def test_returns_initial_roots(self) -> None:
        plan = ExecutionPlan(
            goal="t",
            steps=_steps((1, []), (2, []), (3, [1])),
        )
        ready = schedule_ready(plan)
        assert {s.id for s in ready} == {1, 2}

    def test_hides_completed(self) -> None:
        plan = ExecutionPlan(
            goal="t",
            steps=_steps((1, []), (2, [1])),
        )
        plan.mark_step_completed(1, result="ok")
        ready = schedule_ready(plan)
        assert [s.id for s in ready] == [2]

    def test_no_ready_when_blocked(self) -> None:
        plan = ExecutionPlan(
            goal="t",
            steps=_steps((1, []), (2, [1])),
        )
        plan.mark_step_failed(1, "boom")  # pending/failed -> 2 blocked
        ready = schedule_ready(plan)
        # Step 2 depends on 1 which is not completed → not ready.
        assert ready == []

    def test_skipped_steps_not_returned(self) -> None:
        plan = ExecutionPlan(goal="t", steps=_steps((1, []), (2, [])))
        plan.steps[0].status = "skipped"
        ready = schedule_ready(plan)
        assert {s.id for s in ready} == {2}


# ===========================================================================
# TaskPlanner.estimate_complexity (synchronous heuristic)
# ===========================================================================


class TestEstimateComplexity:
    def test_simple_task(self) -> None:
        planner = TaskPlanner(llm=_mock_llm(""))
        assert planner.estimate_complexity("translate hello") <= 3

    def test_multi_keyword_task(self) -> None:
        planner = TaskPlanner(llm=_mock_llm(""))
        score = planner.estimate_complexity(
            "analyze and compare multiple reports"
        )
        assert score >= 6

    def test_score_capped_at_ten(self) -> None:
        planner = TaskPlanner(llm=_mock_llm(""))
        long_input = (
            "analyze report compare multiple batch evaluate extract summarize" * 20
        )
        assert planner.estimate_complexity(long_input) == 10


# ===========================================================================
# TaskPlanner memory + rule-engine plumbing (regression for API fix)
# ===========================================================================


from enum import Enum


class _EntryKind(Enum):
    EPISODE = "episode"
    FACT = "fact"
    PROCEDURE = "procedure"


@dataclass
class _FakeEntry:
    text: str
    kind: _EntryKind = _EntryKind.FACT


@dataclass
class _FakeBundle:
    entries: list[_FakeEntry]


class _FakeAgentMemory:
    """Stand-in for :class:`leagent.memory.AgentMemory`.

    We only exercise ``recall()`` from the planner path, so the shim is
    intentionally minimal — just enough to record call args and hand back
    canned bundles (or raise).
    """

    def __init__(self, entries: list[_FakeEntry] | Exception) -> None:
        self._entries = entries
        self.calls: list[dict[str, Any]] = []

    async def recall(self, query: str, **kwargs: Any) -> _FakeBundle:
        self.calls.append({"query": query, **kwargs})
        if isinstance(self._entries, Exception):
            raise self._entries
        return _FakeBundle(entries=self._entries)


@dataclass
class _FakeRuleSet:
    id: str
    name: str
    description: str


class _FakeRuleEngine:
    def __init__(self, rule_sets: list[_FakeRuleSet]) -> None:
        self._rule_sets = rule_sets
        self.calls: list[dict[str, Any]] = []

    def find_applicable_rules(
        self,
        context: dict[str, Any],
        *,
        tags: list[str] | None = None,
    ) -> list[_FakeRuleSet]:
        self.calls.append({"context": context, "tags": tags})
        return self._rule_sets


@pytest.mark.asyncio
class TestPlannerKnowledgeRetrieval:
    async def test_recall_is_used_with_limit_and_entries(self) -> None:
        memory = _FakeAgentMemory(
            entries=[
                _FakeEntry("precedent A", kind=_EntryKind.FACT),
                _FakeEntry("precedent B", kind=_EntryKind.EPISODE),
            ]
        )
        planner = TaskPlanner(llm=_mock_llm(""), agent_memory=memory)

        text = await planner._get_relevant_knowledge("refund policy")
        assert "precedent A" in text
        assert "precedent B" in text

        # Regression: recall() receives the verbatim task query and the
        # planner's hard-coded limit=3 — we must not regress to the old
        # long_term.search(top_k=...) API.
        assert memory.calls[0]["query"] == "refund policy"
        assert memory.calls[0]["limit"] == 3
        assert "top_k" not in memory.calls[0]

    async def test_recall_failure_is_swallowed(self) -> None:
        memory = _FakeAgentMemory(entries=RuntimeError("disconnected"))
        planner = TaskPlanner(llm=_mock_llm(""), agent_memory=memory)
        text = await planner._get_relevant_knowledge("anything")
        assert text == ""


class TestPlannerRuleRetrieval:
    def test_find_applicable_rules_called_with_dict(self) -> None:
        rs = _FakeRuleSet(id="refunds", name="Refunds", description="refund flow")
        rule_engine = _FakeRuleEngine([rs])
        planner = TaskPlanner(llm=_mock_llm(""), rule_engine=rule_engine)  # type: ignore[arg-type]

        text = planner._get_applicable_rules("how do refunds work")
        assert "Refunds" in text
        # Regression: rule engine takes a dict context, not a bare string.
        assert isinstance(rule_engine.calls[0]["context"], dict)
        assert rule_engine.calls[0]["context"]["query"] == "how do refunds work"


# ===========================================================================
# TaskPlanner.replan + merge_replan
# ===========================================================================


@pytest.mark.asyncio
class TestTaskPlannerReplan:
    async def test_replan_drops_completed_ids(self) -> None:
        completed_step = PlanStep(id=1, description="done", status="completed")
        failed_step = PlanStep(id=2, description="boom")
        plan = ExecutionPlan(
            goal="g",
            steps=[completed_step, failed_step],
            completed_steps=[1],
        )
        # LLM echoes step 1 + adds step 3 — the planner must drop step 1.
        llm = _mock_llm(json.dumps({
            "goal": "g",
            "steps": [
                {"id": 1, "description": "echoed", "tool": None, "params": {}, "depends_on": []},
                {"id": 3, "description": "new step", "tool": None, "params": {}, "depends_on": []},
            ],
            "expected_output": "",
        }))
        planner = TaskPlanner(llm=llm)

        revised = await planner.replan(plan, failed_step, "boom")
        assert revised is not None
        assert {s.id for s in revised.steps} == {3}

    async def test_merge_replan_marks_skipped_steps(self) -> None:
        original = ExecutionPlan(
            goal="g",
            steps=_steps((1, []), (2, []), (3, [])),
            completed_steps=[1],
        )
        original.steps[0].status = "completed"

        revised = ExecutionPlan(goal="g", steps=_steps((4, [])))
        merged = TaskPlanner.merge_replan(original, revised)

        statuses = {s.id: s.status for s in merged.steps}
        assert statuses[1] == "completed"
        # Pending steps not re-echoed by the replan get marked skipped.
        assert statuses[2] == "skipped"
        assert statuses[3] == "skipped"
        assert 4 in statuses  # new step appended
        assert statuses[4] == "pending"


# ===========================================================================
# TaskPlanner.plan abort propagation
# ===========================================================================


@pytest.mark.asyncio
class TestPlannerAbort:
    async def test_abort_event_cancels_plan(self) -> None:
        abort = asyncio.Event()

        async def _slow_chat(**_kw: Any) -> dict[str, Any]:
            await asyncio.sleep(5)
            return {"content": "{}"}

        llm = MagicMock()
        llm.chat = AsyncMock(side_effect=_slow_chat)
        planner = TaskPlanner(llm=llm)
        ctx = AgentContext(task_id=uuid4(), session_id=uuid4())

        # Trigger the abort very shortly after kicking off planning.
        async def _trip() -> None:
            await asyncio.sleep(0.01)
            abort.set()

        async def _go() -> None:
            await planner.plan("x", ctx, abort_event=abort)

        with pytest.raises(asyncio.CancelledError):
            await asyncio.gather(_go(), _trip())
