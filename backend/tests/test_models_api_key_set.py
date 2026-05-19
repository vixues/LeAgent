"""Tests for provider API key presence in /models/providers responses."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from leagent.api.v1.models import _compute_api_key_set
from leagent.llm.provider_config import ProviderConfig, ProviderConfigService


def _fake_llm(**keys: str) -> SimpleNamespace:
    return SimpleNamespace(
        tier1_api_key=keys.get("tier1_api_key", ""),
        tier2_api_key=keys.get("tier2_api_key", ""),
        openai_api_key=keys.get("openai_api_key", ""),
        anthropic_api_key=keys.get("anthropic_api_key", ""),
        dashscope_api_key=keys.get("dashscope_api_key", ""),
        deepseek_api_key=keys.get("deepseek_api_key", ""),
    )


def test_compute_from_yaml_literal(tmp_path) -> None:
    svc = ProviderConfigService(providers_path=tmp_path / "empty.yaml")
    pc = ProviderConfig(
        name="d",
        type="deepseek",
        api_key="sk-from-yaml",
        models=[{"name": "deepseek-v4-flash"}],
    )
    assert _compute_api_key_set(pc, svc) is True


def test_compute_from_env_reference_when_unset(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = ProviderConfigService(providers_path=tmp_path / "empty.yaml")
    monkeypatch.delenv("MISSING_KEY", raising=False)
    pc = ProviderConfig(
        name="d",
        type="deepseek",
        api_key="${MISSING_KEY}",
        models=[{"name": "deepseek-v4-flash"}],
    )
    with patch("leagent.config.settings.get_settings", return_value=SimpleNamespace(llm=_fake_llm())):
        assert _compute_api_key_set(pc, svc) is False


def test_compute_fallback_deepseek_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = ProviderConfigService(providers_path=tmp_path / "empty.yaml")
    pc = ProviderConfig(
        name="my-deepseek",
        type="deepseek",
        api_key="",
        models=[{"name": "deepseek-v4-flash"}],
    )
    llm = _fake_llm(deepseek_api_key="sk-env")
    with patch("leagent.config.settings.get_settings", return_value=SimpleNamespace(llm=llm)):
        assert _compute_api_key_set(pc, svc) is True


def test_compute_tier_alias_name(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    svc = ProviderConfigService(providers_path=tmp_path / "empty.yaml")
    pc = ProviderConfig(
        name="tier2",
        type="deepseek",
        api_key="",
        models=[{"name": "deepseek-v4-flash"}],
    )
    llm = _fake_llm(tier2_api_key="k-tier")
    with patch("leagent.config.settings.get_settings", return_value=SimpleNamespace(llm=llm)):
        assert _compute_api_key_set(pc, svc) is True
