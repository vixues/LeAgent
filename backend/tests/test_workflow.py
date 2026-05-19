"""Tests for workflow engine: base models, workflow loader, WorkflowState,
and the workflow-worker bootstrap path."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from leagent.workflow.base import (
    BranchCondition,
    ConditionExpression,
    ConditionOperator,
    EdgeType,
    NodeType,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowState,
    WorkflowStatus,
)
from leagent.workflow.io import WorkflowDocument, WorkflowLoaderError, load


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
# Workflow Loader (load)
# ===========================================================================


VALID_WORKFLOW_YAML = """
id: test_workflow
name: Test Workflow
description: A simple test workflow
nodes:
  start:
    class_type: StartNode
    inputs: {}
    meta:
      name: Start
      description: Entry point
    control: {}
  process:
    class_type: ToolCallNode
    inputs:
      tool: pdf_reader
      params:
        file_path: "${input.doc_path}"
    meta:
      name: Process Document
      description: Process a document
    control:
      next: end
  end:
    class_type: EndNode
    inputs: {}
    meta:
      name: End
      description: Exit point
    control: {}
control:
  start: start
  end: end
  edges:
    - source: start
      target: process
    - source: process
      target: end
inputs:
  - name: doc_path
    type: string
    required: true
outputs:
  - name: result
    from_node: process
    field: text
"""

INVALID_WORKFLOW_YAML = """
not_a_workflow:
  - item: 1
"""


class TestWorkflowLoader:
    def test_load_valid_yaml(self) -> None:
        wf = load(VALID_WORKFLOW_YAML)
        assert isinstance(wf, WorkflowDocument)
        assert wf.id == "test_workflow"
        assert len(wf.nodes) == 3

    def test_load_node_class_types(self) -> None:
        wf = load(VALID_WORKFLOW_YAML)
        class_types = {spec["class_type"] for spec in wf.nodes.values()}
        assert "StartNode" in class_types
        assert "EndNode" in class_types
        assert "ToolCallNode" in class_types

    def test_load_edges(self) -> None:
        wf = load(VALID_WORKFLOW_YAML)
        assert len(wf.control.get("edges", [])) == 2

    def test_invalid_yaml_raises(self) -> None:
        with pytest.raises((WorkflowLoaderError, Exception)):
            load(INVALID_WORKFLOW_YAML)

    def test_load_from_file(self, tmp_path) -> None:
        workflow_file = tmp_path / "workflow.yaml"
        workflow_file.write_text(VALID_WORKFLOW_YAML, encoding="utf-8")
        wf = load(workflow_file)
        assert wf.name == "Test Workflow"

    def test_missing_file_raises(self) -> None:
        with pytest.raises((WorkflowLoaderError, FileNotFoundError, Exception)):
            load("/nonexistent/workflow.yaml")

    def test_load_json_workflow(self) -> None:
        import json
        data = {
            "id": "json_wf",
            "name": "JSON Workflow",
            "description": "",
            "nodes": {
                "start": {
                    "class_type": "StartNode",
                    "inputs": {},
                    "meta": {"name": "Start"},
                    "control": {},
                },
                "end": {
                    "class_type": "EndNode",
                    "inputs": {},
                    "meta": {"name": "End"},
                    "control": {},
                },
            },
            "control": {
                "start": "start",
                "end": "end",
                "edges": [{"source": "start", "target": "end"}],
            },
        }
        wf = load(json.dumps(data))
        assert wf.id == "json_wf"


# ===========================================================================
# WorkflowDefinition
# ===========================================================================


class TestWorkflowDefinition:
    def _wf(self) -> WorkflowDefinition:
        nodes = [
            WorkflowNode(id="start", type=NodeType.START, name="Start"),
            WorkflowNode(id="process", type=NodeType.TOOL_CALL, name="Process"),
            WorkflowNode(id="end", type=NodeType.END, name="End"),
        ]
        edges = [
            WorkflowEdge(source="start", target="process"),
            WorkflowEdge(source="process", target="end"),
        ]
        return WorkflowDefinition(
            id="test_wf",
            name="Test",
            nodes=nodes,
            edges=edges,
        )

    def test_get_node(self) -> None:
        wf = self._wf()
        node = wf.get_node("process")
        assert node is not None
        assert node.type == NodeType.TOOL_CALL

    def test_get_nonexistent_node(self) -> None:
        wf = self._wf()
        assert wf.get_node("nonexistent") is None

    def test_get_start_node(self) -> None:
        wf = self._wf()
        start = wf.get_start_node()
        assert start is not None
        assert start.type == NodeType.START

    def test_get_next_nodes(self) -> None:
        wf = self._wf()
        outgoing = wf.get_outgoing_edges("start")
        assert len(outgoing) == 1
        target_node = wf.get_node(outgoing[0].target)
        assert target_node is not None
        assert target_node.id == "process"

    def test_validate_no_errors_for_valid(self) -> None:
        wf = self._wf()
        errors = wf.validate_structure()
        assert len(errors) == 0


# ===========================================================================
# Workflow worker bootstrap
# ===========================================================================


class TestWorkflowWorkerBootstrap:
    def test_worker_init_service_manager_fallback(self) -> None:
        """The workflow worker must initialise ServiceManager when it's not
        already set up (i.e. when not running under the FastAPI lifespan).

        Before the fix, ``get_service_manager()`` raised ``RuntimeError``
        and the worker crashed immediately.
        """
        from leagent.workflow.cli import workflow_worker as ww_module

        source = __import__("inspect").getsource(ww_module._run)
        assert "init_service_manager" in source, (
            "_run() must fall back to init_service_manager when "
            "get_service_manager raises RuntimeError"
        )


# ===========================================================================
# Migration b8c9d0e1f2a3 ordering
# ===========================================================================


class TestMigrationFileSessionIdOrder:
    def test_add_column_before_delete(self) -> None:
        """The migration must add ``session_id`` before any SQL that
        references it. The original bug ran a DELETE on the column before
        the ADD COLUMN, crashing with ``UndefinedColumnError``."""
        import ast
        from pathlib import Path

        migration = Path(
            __file__
        ).resolve().parent.parent / (
            "leagent/alembic/versions/b8c9d0e1f2a3_file_session_id_fk.py"
        )
        if not migration.is_file():
            pytest.skip("Migration file not present in this branch.")
        source = migration.read_text(encoding="utf-8")
        tree = ast.parse(source)

        upgrade_fn = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
                upgrade_fn = node
                break
        assert upgrade_fn is not None

        first_stmt = upgrade_fn.body[0]
        assert isinstance(first_stmt, ast.With), (
            "First statement in upgrade() must be the batch_alter_table "
            "that adds session_id, not a DELETE"
        )
        assert "add_column" in ast.dump(first_stmt), (
            "First batch_alter_table must call add_column"
        )
