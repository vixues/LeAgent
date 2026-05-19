"""Unit + snapshot coverage for :mod:`leagent.prompts`.

Covers:
* Registry: front-matter parsing + lookup, falls back through candidate
  filenames, caches by mtime.
* Budget (context-level): cost-function minimiser pinning + greedy selection.
* Fingerprint: stable vs full hashes cover the right source slices and
  are order-independent.
* Renderer: Anthropic cache boundary, kill-switch.
* Builder: fallback path (no ContextManager) assembles persona + extras.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import pytest

from leagent.context.budget import minimise, PINNED_THRESHOLD
from leagent.context.types import ContextBlock, ContextScope, RenderTarget
from leagent.prompts.builder import PromptBuilder
from leagent.prompts.context import PromptContext
from leagent.prompts.fingerprint import (
    STABLE_SOURCE_IDS,
    full_fingerprint,
    stable_fingerprint,
)
from leagent.prompts.registry import (
    PromptRegistry,
    PromptTemplateNotFound,
    PromptTemplateParseError,
)
from leagent.prompts.render import AnthropicRenderer, OpenAIRenderer
from leagent.prompts.types import LayerResult, RenderTarget as PromptRenderTarget


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return path


def test_registry_parses_front_matter(tmp_path: Path) -> None:
    _write(
        tmp_path / "smoke.md",
        """
        ---
        name: smoke
        description: Smoke variant
        layers:
          - persona
          - capabilities
        policies:
          - file_access
        budget_chars:
          capabilities: 1234
        tags: [smoke]
        ---

        Persona body text.
        """,
    )

    registry = PromptRegistry(templates_dir=tmp_path)
    variant = registry.get("smoke")

    assert variant.name == "smoke"
    assert variant.variant == "default"
    assert variant.body.startswith("Persona body text")
    assert variant.layers == ["persona", "capabilities"]
    assert variant.policies == ["file_access"]
    assert variant.budget_chars == {"capabilities": 1234}
    assert "smoke" in variant.tags


def test_registry_missing_template_raises(tmp_path: Path) -> None:
    registry = PromptRegistry(templates_dir=tmp_path)
    with pytest.raises(PromptTemplateNotFound):
        registry.get("does_not_exist")


def test_registry_falls_back_to_builtin_templates(tmp_path: Path) -> None:
    registry = PromptRegistry(templates_dir=tmp_path)
    variant = registry.get("default_agent")
    assert variant.name == "default_agent"
    assert "LeAgent" in variant.body


def test_registry_rejects_non_mapping_front_matter(tmp_path: Path) -> None:
    _write(
        tmp_path / "bad.md",
        """
        ---
        - this is a list not a mapping
        ---

        body
        """,
    )
    registry = PromptRegistry(templates_dir=tmp_path)
    with pytest.raises(PromptTemplateParseError):
        registry.get("bad")


# ---------------------------------------------------------------------------
# Budget (cost-function minimiser)
# ---------------------------------------------------------------------------


def _block(
    source_id: str, body_size: int, priority: int = 500, weight: float = 1.0
) -> ContextBlock:
    body = "x" * body_size
    return ContextBlock(
        source_id=source_id,
        kind="identity",
        render_target=RenderTarget.SYSTEM,
        body=body,
        tokens=body_size // 3,
        cost=body_size,
        signature=f"{source_id}:sig",
        priority=priority,
        weight=weight,
    )


def test_budget_pinned_blocks_kept_first() -> None:
    blocks = [
        _block("identity", 100, priority=2000),
        _block("capabilities", 100, priority=1500),
        _block("low_pri", 900, priority=200),
    ]
    result = minimise(blocks, max_chars=210)
    kept_ids = [b.source_id for b in result.kept]
    assert "identity" in kept_ids
    assert "capabilities" in kept_ids
    assert "low_pri" in result.dropped or "low_pri" in result.truncated


def test_budget_truncates_pinned_when_over_cap() -> None:
    blocks = [_block("identity", 500, priority=2000)]
    result = minimise(blocks, max_chars=100)
    assert len(result.kept) == 1
    assert result.kept[0].source_id == "identity"
    assert len(result.kept[0].body) <= 100
    assert "identity" in result.truncated


def test_budget_greedy_selects_by_score() -> None:
    blocks = [
        _block("high_score", 50, priority=800, weight=1.0),
        _block("low_score", 50, priority=100, weight=0.1),
    ]
    result = minimise(blocks, max_chars=70)
    kept_ids = [b.source_id for b in result.kept]
    assert "high_score" in kept_ids
    assert "low_score" not in kept_ids


# ---------------------------------------------------------------------------
# Fingerprint
# ---------------------------------------------------------------------------


def test_stable_hash_excludes_volatile() -> None:
    stable_layers = [
        LayerResult(name="identity", body="persona"),
        LayerResult(name="capabilities", body="tools"),
        LayerResult(name="policies", body="policies"),
        LayerResult(name="project_memory", body="memory"),
    ]
    extra_volatile = stable_layers + [
        LayerResult(name="recall", body="recall changes"),
        LayerResult(name="tool_history", body="history"),
    ]

    h1 = stable_fingerprint(stable_layers, "v1:default")
    h2 = stable_fingerprint(extra_volatile, "v1:default")
    assert h1 == h2


def test_full_hash_reflects_all() -> None:
    layers = [
        LayerResult(name="identity", body="persona"),
        LayerResult(name="recall", body="recall-a"),
    ]
    mutated = [
        LayerResult(name="identity", body="persona"),
        LayerResult(name="recall", body="recall-b"),
    ]
    names = ("identity", "recall")
    assert full_fingerprint(layers, "v1:default", all_names=names) != full_fingerprint(
        mutated, "v1:default", all_names=names
    )


def test_stable_hash_sensitive_to_variant_key() -> None:
    layers = [LayerResult(name="identity", body="persona")]
    assert stable_fingerprint(layers, "a:default") != stable_fingerprint(
        layers, "b:default"
    )


def test_stable_source_ids_includes_project_memory() -> None:
    assert "project_memory" in STABLE_SOURCE_IDS
    assert "recall" not in STABLE_SOURCE_IDS
    assert "tool_history" not in STABLE_SOURCE_IDS


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def test_openai_renderer_single_system_message() -> None:
    layers = [
        LayerResult(name="identity", body="persona"),
        LayerResult(name="capabilities", body="tools"),
    ]
    text, msgs = OpenAIRenderer().render(layers)
    assert msgs == [{"role": "system", "content": "persona\n\ntools"}]
    assert text == "persona\n\ntools"


def test_anthropic_renderer_places_cache_boundary_once() -> None:
    layers = [
        LayerResult(name="identity", body="persona"),
        LayerResult(name="project_memory", body="memory", cache_boundary=True),
        LayerResult(name="recall", body="recall"),
    ]
    _, msgs = AnthropicRenderer().render(layers)
    blocks = msgs[0]["content"]
    cached = [b for b in blocks if "cache_control" in b]
    assert len(cached) == 1
    assert cached[0]["text"].endswith("memory")
    assert blocks[-1]["text"] == "recall"


def test_anthropic_renderer_respects_cache_kill_switch() -> None:
    layers = [
        LayerResult(name="identity", body="persona"),
        LayerResult(name="project_memory", body="memory", cache_boundary=True),
    ]
    _, msgs = AnthropicRenderer(enable_cache_boundaries=False).render(layers)
    assert msgs == [{"role": "system", "content": "persona\n\nmemory"}]


# ---------------------------------------------------------------------------
# Builder (fallback path, no ContextManager)
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_templates(tmp_path: Path) -> Path:
    _write(
        tmp_path / "fixture_agent.md",
        """
        ---
        name: fixture_agent
        description: Test persona
        layers:
          - persona
          - capabilities
          - policies
          - turn_extras
        policies:
          - file_access
        ---

        You are {{agent_name}}. Today is {{current_date}}.
        """,
    )
    _write(
        tmp_path / "policies" / "file_access.md",
        """
        ---
        name: file_access
        ---

        File access policy: only read attached files.
        """,
    )
    return tmp_path


@pytest.mark.asyncio
async def test_builder_fallback_assembles_persona(
    fixture_templates: Path,
) -> None:
    registry = PromptRegistry(templates_dir=fixture_templates)
    builder = PromptBuilder(registry=registry)

    ctx = PromptContext(
        variant="fixture_agent",
        query="hello",
        cwd=".",
        agent_id="fixture",
    )
    built = await builder.build(ctx)
    assert "You are fixture." in built.system_text
    assert built.stable_hash and built.full_hash
    assert built.variant_key == "fixture_agent:default"


@pytest.mark.asyncio
async def test_builder_persona_override(fixture_templates: Path) -> None:
    registry = PromptRegistry(templates_dir=fixture_templates)
    builder = PromptBuilder(registry=registry)

    ctx = PromptContext(
        variant="fixture_agent",
        query="hello",
        persona_override="Custom persona only.",
    )
    built = await builder.build(ctx)
    assert "Custom persona only." in built.system_text


@pytest.mark.asyncio
async def test_builder_turn_extras_appended(fixture_templates: Path) -> None:
    registry = PromptRegistry(templates_dir=fixture_templates)
    builder = PromptBuilder(registry=registry)
    ctx = PromptContext(
        variant="fixture_agent",
        query="hi",
        append_extra="WORKFLOW_NODE=report",
    )
    built = await builder.build(ctx)
    assert "WORKFLOW_NODE=report" in built.system_text
