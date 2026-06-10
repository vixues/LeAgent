"""Tests for workflow engine runtime models: ConditionExpression and WorkflowState."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from leagent.workflow.base import (
    ConditionExpression,
    ConditionOperator,
    WorkflowState,
    WorkflowStatus,
)

# ===========================================================================
# ConditionExpression
# ===========================================================================


class TestConditionExpression:
    def test_eq_match(self) -> None:
        expr = ConditionExpression(left="status", operator=ConditionOperator.EQ, right="active")
        assert expr.evaluate({"status": "active"}) is True

    def test_eq_no_match(self) -> None:
        expr = ConditionExpression(left="status", operator=ConditionOperator.EQ, right="inactive")
        assert expr.evaluate({"status": "active"}) is False

    def test_ne(self) -> None:
        expr = ConditionExpression(left="x", operator=ConditionOperator.NE, right=5)
        assert expr.evaluate({"x": 10}) is True
        assert expr.evaluate({"x": 5}) is False

    def test_gt(self) -> None:
        expr = ConditionExpression(left="amount", operator=ConditionOperator.GT, right=100)
        assert expr.evaluate({"amount": 200}) is True
        assert expr.evaluate({"amount": 50}) is False

    def test_ge(self) -> None:
        expr = ConditionExpression(left="count", operator=ConditionOperator.GE, right=10)
        assert expr.evaluate({"count": 10}) is True
        assert expr.evaluate({"count": 9}) is False

    def test_lt(self) -> None:
        expr = ConditionExpression(left="score", operator=ConditionOperator.LT, right=50)
        assert expr.evaluate({"score": 30}) is True

    def test_in_operator(self) -> None:
        expr = ConditionExpression(left="role", operator=ConditionOperator.IN, right=["admin", "mod"])
        assert expr.evaluate({"role": "admin"}) is True
        assert expr.evaluate({"role": "user"}) is False

    def test_contains(self) -> None:
        expr = ConditionExpression(left="name", operator=ConditionOperator.CONTAINS, right="john")
        assert expr.evaluate({"name": "john smith"}) is True
        assert expr.evaluate({"name": "jane doe"}) is False

    def test_starts_with(self) -> None:
        expr = ConditionExpression(left="code", operator=ConditionOperator.STARTS_WITH, right="ERR")
        assert expr.evaluate({"code": "ERR_001"}) is True
        assert expr.evaluate({"code": "OK_001"}) is False

    def test_is_null(self) -> None:
        expr = ConditionExpression(left="field", operator=ConditionOperator.IS_NULL)
        assert expr.evaluate({"field": None}) is True
        assert expr.evaluate({"field": "value"}) is False

    def test_is_not_null(self) -> None:
        expr = ConditionExpression(left="field", operator=ConditionOperator.IS_NOT_NULL)
        assert expr.evaluate({"field": "value"}) is True
        assert expr.evaluate({"field": None}) is False

    def test_and_operator(self) -> None:
        sub1 = ConditionExpression(left="x", operator=ConditionOperator.GT, right=5)
        sub2 = ConditionExpression(left="y", operator=ConditionOperator.LT, right=20)
        expr = ConditionExpression(
            left="",
            operator=ConditionOperator.AND,
            conditions=[sub1, sub2],
        )
        assert expr.evaluate({"x": 10, "y": 15}) is True
        assert expr.evaluate({"x": 3, "y": 15}) is False

    def test_or_operator(self) -> None:
        sub1 = ConditionExpression(left="x", operator=ConditionOperator.EQ, right=1)
        sub2 = ConditionExpression(left="x", operator=ConditionOperator.EQ, right=2)
        expr = ConditionExpression(
            left="",
            operator=ConditionOperator.OR,
            conditions=[sub1, sub2],
        )
        assert expr.evaluate({"x": 1}) is True
        assert expr.evaluate({"x": 2}) is True
        assert expr.evaluate({"x": 3}) is False


# ===========================================================================
# WorkflowState
# ===========================================================================


class TestWorkflowState:
    def _state(self) -> WorkflowState:
        return WorkflowState(
            workflow_id="wf-1",
            status=WorkflowStatus.RUNNING,
            inputs={"doc_path": "/tmp/doc.pdf"},
            variables={"counter": 0},
        )

    def test_get_variable(self) -> None:
        state = self._state()
        assert state.variables["counter"] == 0

    def test_set_variable(self) -> None:
        state = self._state()
        state.set("result", "extracted text")
        assert state.variables["result"] == "extracted text"

    def test_fork_creates_child(self) -> None:
        state = self._state()
        child = state.fork(extra_vars={"branch": "A"})
        assert child.parent_state_id == state.id
        assert child.id in state.child_states
        assert child.variables["branch"] == "A"

    def test_fork_inherits_variables(self) -> None:
        state = self._state()
        child = state.fork()
        assert child.variables["counter"] == state.variables["counter"]

    def test_merge_child_states(self) -> None:
        state = self._state()
        child_a = WorkflowState(workflow_id="wf-1", outputs={"result": "A"})
        child_b = WorkflowState(workflow_id="wf-1", outputs={"result": "B"})
        merged = state.merge_child_states([child_a, child_b])
        assert len(merged) == 2

    def test_evaluate_expression(self) -> None:
        state = self._state()
        state.set("amount", 150)
        expr = ConditionExpression(left="amount", operator=ConditionOperator.GT, right=100)
        assert state.evaluate_expression(expr) is True


# ===========================================================================
# Canonical document loading (structure lives in io.loader, not base)
# ===========================================================================


class TestCanonicalDocument:
    def _doc(self) -> dict[str, Any]:
        return {
            "id": "test_wf",
            "name": "Test",
            "nodes": {
                "start": {"class_type": "StartNode", "control": {"next": "process"}},
                "process": {"class_type": "ToolCallNode", "control": {"next": "end"}},
                "end": {"class_type": "EndNode", "control": {}},
            },
            "control": {"start": "start", "end": "end", "edges": []},
        }

    def test_load_canonical(self) -> None:
        from leagent.workflow.io import load

        doc = load(self._doc())
        assert doc.id == "test_wf"
        assert set(doc.nodes) == {"start", "process", "end"}
        assert doc.start_id == "start"

    def test_rejects_list_shaped_nodes(self) -> None:
        from leagent.workflow.io import load
        from leagent.workflow.io.loader import WorkflowLoaderError

        with pytest.raises(WorkflowLoaderError):
            load({"id": "x", "name": "x", "nodes": [{"id": "start", "type": "start"}]})
