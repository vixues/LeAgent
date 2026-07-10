"""Unit tests for the RelevanceGate gating primitive."""

from __future__ import annotations

from leagent.context.relevance import RelevanceGate

GATE = RelevanceGate(
    name="demo",
    hints=("dashboard", "画布", "emit_ui_tree"),
    opt_in_keys=("demo", "enable_demo"),
)


def test_query_hint_match_is_case_insensitive():
    assert GATE.matches("Build me a DASHBOARD")
    assert GATE.matches("生成一个画布")
    assert GATE.matches("call emit_ui_tree please")


def test_irrelevant_query_does_not_match():
    assert not GATE.matches("summarise this PDF")
    assert not GATE.matches("")
    assert not GATE.matches(None)


def test_template_vars_opt_in_forces_match():
    assert GATE.matches("hello", template_vars={"demo": True})
    assert GATE.matches("hello", template_vars={"enable_demo": 1})
    # Falsy / unrelated keys do not open the gate.
    assert not GATE.matches("hello", template_vars={"demo": False})
    assert not GATE.matches("hello", template_vars={"other": True})


def test_workflow_hint_match():
    assert GATE.matches("hello", workflow_hint="render a dashboard card")
    assert not GATE.matches("hello", workflow_hint="export a CSV")


def test_opted_in_independent_of_query():
    assert GATE.opted_in(template_vars={"demo": True})
    assert GATE.opted_in(workflow_hint="a dashboard please")
    assert not GATE.opted_in(template_vars={"demo": False})
    assert not GATE.opted_in()


def test_empty_gate_never_matches_on_text():
    empty = RelevanceGate(name="empty")
    assert not empty.matches("dashboard")
    assert not empty.matches("anything", workflow_hint="dashboard")
    # But explicit opt-in still works only if keys are configured.
    assert not empty.matches("x", template_vars={"demo": True})
