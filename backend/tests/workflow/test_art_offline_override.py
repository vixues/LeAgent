"""``art_offline`` metadata must not override an explicit provider choice."""

from __future__ import annotations

import pytest

from leagent.workflow.nodes.art.base import BaseGenerationNode


class _StubNode(BaseGenerationNode):
    NODE_ID = "Art.ImageGen"
    KIND = "image"


def test_art_offline_does_not_override_explicit_provider():
    state = type("S", (), {"metadata": {"art_offline": True}})()
    assert _StubNode._force_offline(state, "siliconflow") is False
    assert _StubNode._force_offline(state, "http_upscale") is False


def test_art_offline_pins_auto_provider():
    state = type("S", (), {"metadata": {"art_offline": True}})()
    assert _StubNode._force_offline(state, None) is True


def test_env_art_offline_overrides_explicit_provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEAGENT_ART_OFFLINE", "1")
    state = type("S", (), {"metadata": {}})()
    assert _StubNode._force_offline(state, "siliconflow") is True
