"""Templates are loaded in canonical form and pass ``io.load``."""

from __future__ import annotations

import pytest

from leagent.workflow.io import load
from leagent.workflow.layout import build_ui_block
from leagent.workflow.nodes import bootstrap
from leagent.workflow.template_service import get_template_service


@pytest.mark.asyncio
async def test_all_templates_are_canonical_and_loadable():
    await bootstrap()
    service = get_template_service()
    service.load()

    infos = service.list_templates()
    assert infos, "expected at least one template"

    failed: list[tuple[str, str]] = []
    for info in infos:
        tid = info["id"]
        doc_raw = service.get_template(tid)
        assert doc_raw is not None
        try:
            doc = load(doc_raw)
        except Exception as exc:  # noqa: BLE001
            failed.append((tid, str(exc)))
            continue
        assert doc.nodes, f"template {tid} has no nodes"
        assert isinstance(doc.control, dict)

    assert not failed, f"non-canonical templates: {failed}"


@pytest.mark.asyncio
async def test_template_categories_returned():
    await bootstrap()
    service = get_template_service()
    service.load()
    cats = service.list_categories()
    assert isinstance(cats, list)
    for c in cats:
        assert "id" in c
        assert "count" in c


@pytest.mark.asyncio
async def test_every_template_produces_non_overlapping_layout():
    """Each built-in template must lay out without two nodes sharing a position.

    This guards the auto-layout fix for the "densely packed / overlapping"
    template rendering: every template goes through ``build_ui_block`` on
    apply, so regressions here would reintroduce the old grid collision.
    """
    await bootstrap()
    service = get_template_service()
    service.load()

    for info in service.list_templates():
        tid = info["id"]
        doc = service.get_template(tid)
        assert doc is not None, tid
        ui = build_ui_block(doc)

        assert ui["nodes"], f"template {tid} produced no UI nodes"
        assert len(ui["nodes"]) == len(doc.get("nodes", {})), tid

        seen: dict[tuple[float, float], str] = {}
        for node in ui["nodes"]:
            pos = (node["position"]["x"], node["position"]["y"])
            assert pos not in seen, (
                f"template {tid}: {node['id']} overlaps {seen[pos]} at {pos}"
            )
            seen[pos] = node["id"]

        # Every edge target must resolve to an existing UI node.
        node_ids = {n["id"] for n in ui["nodes"]}
        for edge in ui["edges"]:
            assert edge["source"] in node_ids, (tid, edge)
            assert edge["target"] in node_ids, (tid, edge)
