"""Phase 7 — art playbook prompt layer + decomposition planner.

Asserts the playbook renders the ontology / node catalog / TPL-ART-01 pattern
/ tool sequence, that the catalog is graph-aware (introspected from the live
node registry after bootstrap), and that the decomposition planner turns a
brief into an ordered, stage-appropriate step list.
"""

from __future__ import annotations

import pytest

from leagent.prompts.art_playbook import (
    ART_TOOL_SEQUENCE,
    build_art_node_catalog,
    looks_like_art_request,
    plan_art_tasks,
    render_art_playbook,
)
from leagent.workflow.nodes import bootstrap as bootstrap_nodes
from leagent.workflow.nodes import get_registry


# -- request gating ---------------------------------------------------------


def test_looks_like_art_request_detects_art_briefs():
    assert looks_like_art_request("Make a 3D model of a fantasy knight")
    assert looks_like_art_request("生成一个角色原画")
    assert looks_like_art_request("design a VFX flipbook for a spell")
    assert not looks_like_art_request("summarise this PDF")
    assert not looks_like_art_request("")


# -- node catalog (graph-aware) ---------------------------------------------


@pytest.mark.asyncio
async def test_node_catalog_is_introspected_from_registry():
    await bootstrap_nodes()
    catalog = build_art_node_catalog(get_registry())
    # Real registered nodes appear by id.
    for node_id in ("Art.ImageGen", "Art.VFXGen", "Art.Mesh3D", "QualityGateNode",
                    "IterativeRefineNode", "AssetExportNode"):
        assert node_id in catalog, node_id
    # Sockets are surfaced (arrow signature).
    assert "->" in catalog


def test_node_catalog_falls_back_without_registry():
    # A bogus registry yields the static catalog rather than raising.
    catalog = build_art_node_catalog(object())
    assert "Art.ImageGen" in catalog
    assert "AssetExportNode" in catalog


# -- full playbook ----------------------------------------------------------


@pytest.mark.asyncio
async def test_render_playbook_contains_all_layers():
    await bootstrap_nodes()
    text = render_art_playbook(get_registry())
    assert "ontology" in text.lower()
    assert "TPL-ART-01" in text
    assert "chat_workflow_embed_emit" in text
    assert "workflow_run" in text
    assert ART_TOOL_SEQUENCE.split("\n", 1)[0] in text


# -- decomposition planner --------------------------------------------------


def test_plan_art_tasks_always_has_concept_gate_and_export():
    steps = plan_art_tasks("a heroic fantasy knight")
    contents = [s["content"] for s in steps]
    assert any("Art.ImageGen" in c for c in contents)
    assert any("QualityGateNode" in c for c in contents)
    assert any("AssetExportNode" in c for c in contents)
    assert all(s["status"] == "pending" for s in steps)
    assert all(s["id"].startswith("art-") for s in steps)


def test_plan_art_tasks_adds_mesh_video_vfx_on_demand():
    steps = plan_art_tasks("knight as a 3D model with a turntable video and a magic VFX flipbook")
    contents = " | ".join(s["content"] for s in steps)
    assert "Art.Mesh3D" in contents
    assert "Art.VideoGen" in contents
    assert "Art.VFXGen" in contents


def test_plan_art_tasks_threads_engine_into_export():
    steps = plan_art_tasks("a sci-fi crate prop for Unity")
    export = [s for s in steps if "AssetExportNode" in s["content"]][0]
    assert "engine=unity" in export["content"]


def test_plan_art_tasks_uses_quoted_subject():
    steps = plan_art_tasks("Design 'a cyberpunk samurai' as game art")
    assert any("a cyberpunk samurai" in s["content"] for s in steps)


def test_plan_minimal_brief_does_not_crash():
    steps = plan_art_tasks("")
    assert len(steps) >= 4


# -- context source wiring --------------------------------------------------


@pytest.mark.asyncio
async def test_art_playbook_source_registered_and_renders_for_art_query():
    from leagent.context.sources import get_all_sources
    from leagent.context.sources.base import ResolveContext

    sources = get_all_sources()
    assert "art_playbook" in sources

    src = sources["art_playbook"]()
    block = await src.resolve(ResolveContext(query="make game art: a fantasy knight 3D model"))
    assert block is not None
    assert "playbook" in block.body.lower()

    # Non-art query with no tools → source stays silent.
    silent = await src.resolve(ResolveContext(query="what's the weather today?"))
    assert silent is None
