"""Entry-point plugin discovery for LLM providers + context sources.

Verifies the ComfyUI-style "drop-in registration" path: a distribution
exposing a ``leagent.llm_providers`` / ``leagent.context_sources`` entry
point is discovered and registered without editing core packages.
"""

from __future__ import annotations

import pytest


class _FakeEntryPoint:
    """Minimal stand-in for ``importlib.metadata.EntryPoint``."""

    def __init__(self, name: str, target):
        self.name = name
        self._target = target

    def load(self):
        return self._target

    def __str__(self) -> str:  # used in error logging paths
        return f"FakeEntryPoint({self.name})"


def test_llm_provider_plugin_discovery(monkeypatch):
    from leagent.llm import provider_plugin

    def _fake_factory(**kwargs):  # ProviderFactory shape
        return object()

    fake_ep = _FakeEntryPoint("fake_provider", ("fake_provider", _fake_factory))

    monkeypatch.setattr(
        provider_plugin, "entry_points", lambda *a, **k: [fake_ep]
    )

    provider_plugin.reset_provider_registry()  # clears _entrypoints_loaded
    registered = provider_plugin.load_provider_plugins()

    assert "fake_provider" in registered
    assert "fake_provider" in provider_plugin.list_provider_types()
    # Idempotent: a second call discovers nothing new.
    assert provider_plugin.load_provider_plugins() == []

    provider_plugin.reset_provider_registry()


def test_context_source_plugin_discovery(monkeypatch):
    from leagent.context import plugin

    class _FakeSource:
        id = "fake_source"

    fake_ep = _FakeEntryPoint("fake_source", _FakeSource)

    monkeypatch.setattr(plugin, "entry_points", lambda *a, **k: [fake_ep])

    plugin.reset_plugin_registry()
    registered = plugin.load_source_plugins()

    assert "fake_source" in registered
    assert "fake_source" in plugin.get_plugin_sources()
    # Idempotent.
    assert plugin.load_source_plugins() == []

    plugin.reset_plugin_registry()


def test_domain_model_plugin_discovery(monkeypatch):
    from leagent.llm import domain_registry as dr
    from leagent.llm.domain_registry import DomainModelRegistry, DomainModelResult, DomainModelSpec

    class _PluginAdapter:
        spec = DomainModelSpec(task="upscale", provider="plugin", model="v1")

        async def invoke(self, **params) -> DomainModelResult:
            return DomainModelResult(text="ok")

    fake_ep = _FakeEntryPoint("my_upscale", _PluginAdapter())
    monkeypatch.setattr(dr, "entry_points", lambda *a, **k: [fake_ep])
    dr.reset_domain_registry()

    registered = dr.load_domain_model_plugins()
    assert registered == ["upscale.plugin"]
    assert dr.get_domain_registry().get("upscale", "plugin") is not None
    assert dr.load_domain_model_plugins() == []

    dr.reset_domain_registry()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
