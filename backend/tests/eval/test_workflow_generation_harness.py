"""Structured harness eval for agent-driven game-art workflow generation.

Each :class:`Scenario` stands in for a workflow the agent would *generate*
from a one-line idea (concept -> image -> quality gate -> bounded
self-correction -> 3D/video -> export). The shipped flagship + demo graphs
are the canonical reference outputs; the harness freezes the guarantees the
plan calls for, all hermetic and credential-free (``LEAGENT_ART_OFFLINE``):

* the graph declares the expected **first-class** art / control nodes,
* it is a valid canonical document the agent could ``workflow_save`` /
  ``chat_workflow_embed_emit`` (validates + a **stable digest**),
* it executes end-to-end to ``COMPLETED`` on the deterministic offline
  backend, clearing the ``quality_score`` bar, and
* the **self-correction loop actually fires**: the first concept image
  misses the gate and the bounded refine back-edge regenerates it.

This is the engine-side counterpart to the scripted-LLM ``EngineTrace``
integration tests — it benchmarks the *generated artifact*, not the prose.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from leagent.bootstrap.tools import bootstrap_tools
from leagent.chat_workflow.workflow_embed import validate_workflow_embed
from leagent.tools.executor import ToolExecutor
from leagent.tools.registry import get_registry
from leagent.workflow.base import WorkflowStatus
from leagent.workflow.engine.caching import build_cache_set
from leagent.workflow.engine.executor import WorkflowExecutor
from leagent.workflow.io import load
from leagent.workflow.nodes import bootstrap as bootstrap_nodes
from leagent.workflow.nodes import get_registry as get_node_registry
from leagent.workflow.template_service import TemplateService

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEMO_DIR = _REPO_ROOT / "config" / "demo-workflows"


def _load_template(template_id: str):
    svc = TemplateService()
    svc.load()
    raw = svc.get_template(template_id)
    assert raw is not None, f"template {template_id} not found"
    return load(raw)


def _load_demo(filename: str):
    return load(_DEMO_DIR / filename)


@dataclass
class Scenario:
    """One agent workflow-generation benchmark case."""

    name: str
    loader: Callable[[], object]
    expected_classes: set[str]
    min_quality: float = 0.7
    inputs: dict = field(default_factory=dict)
    # The image regen node id and the minimum number of times it must run for
    # the self-correction loop to count as exercised.
    refine_node_id: str = "image"
    min_refine_runs: int = 2


SCENARIOS: list[Scenario] = [
    Scenario(
        name="flagship-hero-knight",
        loader=lambda: _load_template("TPL-ART-01"),
        expected_classes={
            "Art.ImageGen",
            "QualityGateNode",
            "IterativeRefineNode",
            "Art.Mesh3D",
            "Art.VideoGen",
            "AssetExportNode",
        },
        min_quality=0.7,
    ),
    Scenario(
        name="demo-treasure-chest",
        loader=lambda: _load_demo("demo-art-pipeline.yaml"),
        expected_classes={
            "Art.ImageGen",
            "QualityGateNode",
            "IterativeRefineNode",
            "Art.Mesh3D",
            "AssetExportNode",
        },
        min_quality=0.7,
    ),
]

_IDS = [s.name for s in SCENARIOS]


@pytest.fixture(scope="module")
async def executor() -> WorkflowExecutor:
    await bootstrap_tools()
    await bootstrap_nodes()
    reg = get_registry()
    return WorkflowExecutor(
        tool_registry=reg,
        tool_executor=ToolExecutor(registry=reg, service_manager=None),
        cache_set=build_cache_set("none"),
    )


@pytest.fixture(autouse=True)
def _force_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEAGENT_ART_OFFLINE", "1")


@pytest.mark.parametrize("scenario", SCENARIOS, ids=_IDS)
def test_scenario_declares_first_class_nodes(scenario: Scenario) -> None:
    doc = scenario.loader()
    class_types = {spec.get("class_type") for spec in doc.nodes.values()}
    missing = scenario.expected_classes - class_types
    assert not missing, f"{scenario.name} missing first-class nodes: {missing}"


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS, ids=_IDS)
async def test_scenario_graph_is_saveable_with_stable_digest(scenario: Scenario) -> None:
    """The generated graph validates as a canonical doc (agent workflow_save /
    embed path) and hashes deterministically across reloads."""
    await bootstrap_nodes()
    node_reg = get_node_registry()
    canonical = scenario.loader().to_dict()

    _doc1, digest1 = validate_workflow_embed(canonical, node_registry=node_reg)
    _doc2, digest2 = validate_workflow_embed(canonical, node_registry=node_reg)
    assert digest1 == digest2, "graph digest must be deterministic"
    assert len(digest1) == 64, "graph_hash should be a sha256 hex digest"


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS, ids=_IDS)
async def test_scenario_self_corrects_to_completion_offline(
    executor: WorkflowExecutor,
    scenario: Scenario,
) -> None:
    """Run the generated workflow end-to-end: it must self-correct (regenerate
    the concept image after a gate miss) and finish above the quality bar."""
    doc = scenario.loader()
    result = await executor.execute(doc, inputs=scenario.inputs)

    assert result.status == WorkflowStatus.COMPLETED, (scenario.name, result.errors)
    assert not result.errors, scenario.name

    # The self-correction back-edge fired: the image node ran more than once.
    image_runs = [h for h in result.execution_history if h.node_id == scenario.refine_node_id]
    assert len(image_runs) >= scenario.min_refine_runs, (
        f"{scenario.name}: expected the refine loop to regenerate "
        f"'{scenario.refine_node_id}' >= {scenario.min_refine_runs}x, "
        f"got {len(image_runs)}"
    )

    # The quality gate ultimately cleared the bar.
    score = float(result.outputs["quality_score"])
    assert score >= scenario.min_quality, (scenario.name, score)


@pytest.mark.asyncio
@pytest.mark.parametrize("scenario", SCENARIOS, ids=_IDS)
async def test_scenario_exports_engine_ready_manifest(
    executor: WorkflowExecutor,
    scenario: Scenario,
) -> None:
    """AssetExport collates the produced assets into an engine-ready manifest."""
    doc = scenario.loader()
    result = await executor.execute(doc, inputs=scenario.inputs)
    assert result.status == WorkflowStatus.COMPLETED, (scenario.name, result.errors)

    manifest = result.outputs["manifest"]
    assert isinstance(manifest, dict)
    assert manifest["asset_count"] >= 2
    kinds = {a["kind"] for a in manifest["assets"]}
    # Every scenario produces at least an image + a 3D mesh.
    assert {"image", "model3d"}.issubset(kinds), (scenario.name, kinds)
