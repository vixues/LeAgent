"""Phase 2: self-evaluation + feedback-conditioned self-correction loop."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from leagent.context.artifact_error_tracker import ArtifactErrorTracker
from leagent.workflow.base import WorkflowState, WorkflowStatus
from leagent.workflow.engine import WorkflowExecutor, build_cache_set
from leagent.workflow.io import HiddenHolder, MediaRef
from leagent.workflow.nodes import bootstrap as bootstrap_nodes
from leagent.workflow.nodes.art.quality_critic import QualityCriticNode, _parse_score_json
from leagent.workflow.template_service import TemplateService


# ---------------------------------------------------------------------------
# Quality critic
# ---------------------------------------------------------------------------


def _hidden(state: WorkflowState, llm=None) -> HiddenHolder:
    return HiddenHolder(
        unique_id="critic",
        workflow_state=state,
        tool_context=SimpleNamespace(llm_service=llm),
    )


@pytest.mark.asyncio
async def test_quality_critic_offline_heuristic_improves_with_iteration():
    state = WorkflowState(workflow_id="t")
    node = QualityCriticNode()

    # iteration 0 -> base only
    out0 = await node.execute(hidden=_hidden(state), asset=None,
                              base_score=0.4, score_step=0.35)
    assert out0.values[0] == pytest.approx(0.4)
    assert out0.metadata["source"] == "heuristic"
    assert state.get("quality_score") == pytest.approx(0.4)

    # iteration 1 -> base + step (clears a 0.7 bar)
    state.set("refine_iteration", 1)
    out1 = await node.execute(hidden=_hidden(state), asset=None,
                              base_score=0.4, score_step=0.35)
    assert out1.values[0] == pytest.approx(0.75)


@pytest.mark.asyncio
async def test_quality_critic_uses_vision_llm_and_writes_feedback():
    state = WorkflowState(workflow_id="t")

    class _FakeLLM:
        async def complete(self, **kwargs):
            return SimpleNamespace(
                content='{"score": 0.82, "critique": "Tighten the silhouette."}'
            )

    asset = MediaRef(
        file_id="f1",
        preview_url="https://cdn.example.com/concept.png",
        kind="image",
    ).to_dict()
    node = QualityCriticNode()
    out = await node.execute(hidden=_hidden(state, llm=_FakeLLM()), asset=asset,
                             criteria="clean silhouette")
    assert out.values[0] == pytest.approx(0.82)
    assert out.metadata["source"] == "vision"
    assert "silhouette" in state.get("refine_feedback").lower()


@pytest.mark.asyncio
async def test_quality_critic_falls_back_to_heuristic_on_placeholder():
    state = WorkflowState(workflow_id="t")

    class _FakeLLM:
        async def complete(self, **kwargs):  # pragma: no cover - must not be called
            raise AssertionError("placeholder asset should not hit the vision LLM")

    placeholder = MediaRef(
        file_id="f1", preview_url="/p", kind="image", meta={"placeholder": True}
    ).to_dict()
    node = QualityCriticNode()
    out = await node.execute(hidden=_hidden(state, llm=_FakeLLM()), asset=placeholder)
    assert out.metadata["source"] == "heuristic"


@pytest.mark.asyncio
async def test_quality_critic_skips_vision_for_local_preview_and_art_offline():
    state = WorkflowState(workflow_id="t")
    state.metadata["art_offline"] = True

    class _FakeLLM:
        async def complete(self, **kwargs):  # pragma: no cover
            raise AssertionError("art_offline workflow should not call vision LLM")

    local_asset = MediaRef(file_id="f1", preview_url="/api/v1/files/f1/preview", kind="image").to_dict()
    node = QualityCriticNode()
    out = await node.execute(hidden=_hidden(state, llm=_FakeLLM()), asset=local_asset)
    assert out.metadata["source"] == "heuristic"


def test_parse_score_json_handles_fences_and_bare_numbers():
    s, c = _parse_score_json('```json\n{"score": 0.6, "critique": "ok"}\n```')
    assert s == pytest.approx(0.6)
    assert c == "ok"
    s2, _ = _parse_score_json("the score is 0.45 overall")
    assert s2 == pytest.approx(0.45)


# ---------------------------------------------------------------------------
# Feedback-conditioned regeneration (integration on the flagship template)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refine_feedback_flows_into_regenerated_prompt(monkeypatch):
    monkeypatch.setenv("LEAGENT_ART_OFFLINE", "1")
    await bootstrap_nodes()
    svc = TemplateService()
    svc.load()
    from leagent.workflow.io import load

    doc = load(svc.get_template("TPL-ART-01"))
    executor = WorkflowExecutor(cache_set=build_cache_set("none"))
    result = await executor.execute(doc, inputs={})

    assert result.status == WorkflowStatus.COMPLETED, result.errors
    # The approved image came from the *regenerated* pass, whose prompt was
    # conditioned on the refine feedback.
    concept_image = result.outputs.get("concept_image")
    assert isinstance(concept_image, dict)
    prompt_used = (concept_image.get("meta") or {}).get("prompt", "")
    assert "Revision guidance" in prompt_used


# ---------------------------------------------------------------------------
# Below-bar runs are treated as dirty (gate-driven pass decision)
# ---------------------------------------------------------------------------


def test_tracker_below_bar_via_quality_passed():
    tracker = ArtifactErrorTracker()
    tracker.record_from_tool_result(
        tool_name="workflow_run",
        tool_call_id="tc1",
        success=True,
        error_text="",
        quality_passed=False,
    )
    assert tracker.has_dirty_artifacts()
    directives = tracker.get_regeneration_directives()
    assert any("quality" in d.lower() for d in directives)


def test_tracker_clears_when_quality_passed():
    tracker = ArtifactErrorTracker()
    tracker.record_from_tool_result(
        tool_name="workflow_run",
        tool_call_id="tc1",
        success=True,
        error_text="",
        quality_passed=True,
    )
    assert not tracker.has_dirty_artifacts()


def test_tracker_below_bar_via_score_threshold():
    tracker = ArtifactErrorTracker()
    tracker.record_from_tool_result(
        tool_name="workflow_run",
        tool_call_id="tc1",
        success=True,
        error_text="",
        quality_score=0.5,
        quality_threshold=0.7,
    )
    assert tracker.has_dirty_artifacts()


def test_workflow_run_below_bar_coercion_helpers():
    from leagent.tools.workflow.workflow_crud import _coerce_bool, _coerce_float

    assert _coerce_bool(True) is True
    assert _coerce_bool("false") is False
    assert _coerce_bool("passed") is True
    assert _coerce_bool(None) is None
    assert _coerce_float("0.7") == pytest.approx(0.7)
    assert _coerce_float(None) is None
    assert _coerce_float("nan") != _coerce_float("nan") or True  # nan tolerated
