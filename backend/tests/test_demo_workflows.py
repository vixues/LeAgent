"""Regression: bundled demo workflow YAML stays canonical and validates."""

from __future__ import annotations

from pathlib import Path

import pytest

from leagent.workflow.io import load, validate
from leagent.workflow.nodes import bootstrap, get_registry

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEMO_DIR = _REPO_ROOT / "config" / "demo-workflows"

_ALL_DEMOS = sorted(p.name for p in _DEMO_DIR.glob("demo-*.yaml"))


def test_demo_yaml_files_exist():
    assert _DEMO_DIR.is_dir(), f"Missing demo directory: {_DEMO_DIR}"
    assert len(_ALL_DEMOS) >= 6, f"Expected at least 6 demo-*.yaml under {_DEMO_DIR}"


@pytest.mark.parametrize("filename", _ALL_DEMOS)
def test_demo_workflows_load(filename: str):
    path = _DEMO_DIR / filename
    doc = load(path)
    assert doc.id
    assert doc.nodes


@pytest.mark.parametrize(
    ("filename", "expected_classes"),
    [
        ("demo-news-public.yaml", {"ToolCallNode"}),
        ("demo-fx-rates-public.yaml", {"ToolCallNode"}),
        ("demo-asr-agent-summary.yaml", {"Model.asr.local", "ScriptAgentNode"}),
        ("demo-local-tts.yaml", {"Model.tts.local"}),
        ("demo-local-sdxl-txt2img.yaml", {"Art.ImageGen"}),
        (
            "demo-art-pipeline.yaml",
            {"Art.ImageGen", "QualityGateNode", "IterativeRefineNode", "Art.Mesh3D", "AssetExportNode"},
        ),
        ("demo-agent-pause-resume.yaml", {"ScriptAgentNode"}),
    ],
)
def test_demo_workflows_declare_expected_node_classes(filename: str, expected_classes: set[str]):
    doc = load(_DEMO_DIR / filename)
    class_types = {spec.get("class_type") for spec in doc.nodes.values()}
    for cls in expected_classes:
        assert cls in class_types, f"{filename} missing {cls}; got {class_types}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "filename",
    [
        "demo-news-public.yaml",
        "demo-fx-rates-public.yaml",
    ],
)
async def test_demo_workflows_validate_with_registry(filename: str):
    await bootstrap()
    path = _DEMO_DIR / filename
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


@pytest.mark.asyncio
async def test_domain_model_demos_validate_when_nodes_registered(monkeypatch):
    """Domain-model demos validate once local audio nodes are bootstrapped."""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("LEAGENT_DIFFUSION_ENABLED", "0")
    monkeypatch.setenv("LEAGENT_LOCAL_ASR_URL", "http://localhost:8000")
    monkeypatch.setenv("LEAGENT_LOCAL_TTS_URL", "http://localhost:8880")

    await bootstrap()
    reg = get_registry()
    for filename in ("demo-asr-agent-summary.yaml", "demo-local-tts.yaml"):
        doc = load(_DEMO_DIR / filename)
        ok, _outputs, errors = validate(doc, registry=reg)
        assert ok, errors
