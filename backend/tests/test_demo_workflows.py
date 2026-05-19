"""Regression: bundled demo workflow YAML stays canonical and validates."""

from __future__ import annotations

from pathlib import Path

import pytest

from leagent.workflow.io import load, validate
from leagent.workflow.nodes import bootstrap, get_registry

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_DIR = _REPO_ROOT / "config" / "demo-workflows"


def test_demo_yaml_files_exist():
    assert _DEMO_DIR.is_dir(), f"Missing demo directory: {_DEMO_DIR}"
    files = sorted(_DEMO_DIR.glob("demo-*.yaml"))
    assert files, f"No demo-*.yaml under {_DEMO_DIR}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename",
    [
        "demo-news-public.yaml",
        "demo-fx-rates-public.yaml",
    ],
)
async def test_demo_workflows_validate(filename: str):
    await bootstrap()
    path = _DEMO_DIR / filename
    assert path.is_file(), f"Missing {path}"
    doc = load(path)
    ok, output_nodes, errors = validate(doc, registry=get_registry())
    assert ok, errors
    assert "end" in output_nodes


@pytest.mark.asyncio
async def test_demo_workflows_declare_expected_tools():
    await bootstrap()
    doc = load(_DEMO_DIR / "demo-news-public.yaml")
    tools = {s["inputs"].get("tool") for s in doc.nodes.values() if s.get("class_type") == "ToolCallNode"}
    assert "web_search" in tools

    doc2 = load(_DEMO_DIR / "demo-fx-rates-public.yaml")
    tools2 = {s["inputs"].get("tool") for s in doc2.nodes.values() if s.get("class_type") == "ToolCallNode"}
    assert "web_scraper" in tools2
    assert "json_parser" in tools2
