"""Tests for ProviderConfigService validation and default-model consistency."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from leagent.llm.provider_config import (
    PROVIDER_PRESETS,
    ProviderConfigService,
    ProviderConfigValidationError,
)


def _svc(yaml_text: str, tmp_path: Path) -> ProviderConfigService:
    p = tmp_path / "providers.yaml"
    p.write_text(textwrap.dedent(yaml_text).lstrip(), encoding="utf-8")
    return ProviderConfigService(providers_path=p)


def test_set_default_rejects_unknown_model(tmp_path: Path) -> None:
    svc = _svc(
        """
        default_provider: ""
        default_model: ""
        providers:
          - name: acme
            type: custom
            enabled: true
            base_url: https://api.example.com/v1
            models:
              - name: model-a
              - name: model-b
        """,
        tmp_path,
    )
    with pytest.raises(ProviderConfigValidationError, match="not an enabled model"):
        svc.set_default("acme", "qwen-max")


def _v2_yaml(
    *,
    default_provider: str = "acme",
    default_model: str = "model-a",
    chat_provider: str | None = None,
    chat_model: str | None = None,
) -> str:
    cp = chat_provider if chat_provider is not None else default_provider
    cm = chat_model if chat_model is not None else default_model
    return f"""
        version: 2
        default_task: chat
        default_provider: {default_provider}
        default_model: {default_model}
        routing:
          tasks:
            chat:
              provider: {cp}
              model: {cm}
        providers:
          - name: acme
            type: custom
            enabled: true
            base_url: https://api.example.com/v1
            models:
              - name: model-a
                kind: chat
                capabilities:
                  input: [text]
                  output: [text]
              - name: model-b
                kind: chat
                capabilities:
                  input: [text]
                  output: [text]
        """


def test_set_default_syncs_chat_task_routing(tmp_path: Path) -> None:
    svc = _svc(_v2_yaml(chat_model="model-a"), tmp_path)
    svc.set_default("acme", "model-b")
    assert svc.get_default().model == "model-b"
    raw = svc._load_yaml()
    assert raw["routing"]["tasks"]["chat"]["model"] == "model-b"
    assert raw["default_model"] == "model-b"


def test_set_default_accepts_enabled_model(tmp_path: Path) -> None:
    svc = _svc(
        """
        default_provider: ""
        default_model: ""
        providers:
          - name: acme
            type: custom
            enabled: true
            base_url: https://api.example.com/v1
            models:
              - name: model-a
        """,
        tmp_path,
    )
    d = svc.set_default("acme", "model-a")
    assert d.provider == "acme"
    assert d.model == "model-a"


def test_set_default_rejects_disabled_model(tmp_path: Path) -> None:
    svc = _svc(
        """
        default_provider: ""
        default_model: ""
        providers:
          - name: acme
            type: custom
            enabled: true
            base_url: https://api.example.com/v1
            models:
              - name: "on"
              - name: "off"
                enabled: false
        """,
        tmp_path,
    )
    with pytest.raises(ProviderConfigValidationError, match="not an enabled model"):
        svc.set_default("acme", "off")


def test_create_provider_requires_models(tmp_path: Path) -> None:
    svc = ProviderConfigService(providers_path=tmp_path / "providers.yaml")
    with pytest.raises(ProviderConfigValidationError, match="At least one model"):
        svc.create_provider(
            {
                "name": "solo",
                "type": "custom",
                "base_url": "https://x/v1",
                "models": [],
            }
        )


def test_create_provider_rejects_duplicate_model_names(tmp_path: Path) -> None:
    svc = ProviderConfigService(providers_path=tmp_path / "providers.yaml")
    with pytest.raises(ProviderConfigValidationError, match="Duplicate model name"):
        svc.create_provider(
            {
                "name": "solo",
                "type": "custom",
                "base_url": "https://x/v1",
                "models": [{"name": "a"}, {"name": "a"}],
            }
        )


def test_custom_api_preset_exposes_api_key_field() -> None:
    assert PROVIDER_PRESETS["custom"]["requires_api_key"] is True


def test_update_provider_clears_stale_default(tmp_path: Path) -> None:
    svc = _svc(
        """
        default_provider: acme
        default_model: old-model
        providers:
          - name: acme
            type: custom
            enabled: true
            base_url: https://api.example.com/v1
            models:
              - name: old-model
              - name: keep-me
        """,
        tmp_path,
    )
    svc.update_provider(
        "acme",
        {"models": [{"name": "keep-me"}]},
    )
    raw = svc._load_yaml()
    assert raw.get("default_provider") == ""
    assert raw.get("default_model") == ""


def test_update_provider_promotes_default_when_empty(tmp_path: Path) -> None:
    svc = _svc(
        """
        default_provider: ""
        default_model: ""
        providers:
          - name: deepseek
            type: deepseek
            enabled: true
            base_url: https://api.deepseek.com
            models:
              - name: deepseek-v4-flash
              - name: deepseek-v4-pro
        """,
        tmp_path,
    )
    svc.update_provider("deepseek", {"api_key": "sk-xyz"})
    raw = svc._load_yaml()
    assert raw.get("default_provider") == "deepseek"
    assert raw.get("default_model") == "deepseek-v4-flash"


def test_create_provider_promotes_default_when_empty(tmp_path: Path) -> None:
    svc = ProviderConfigService(providers_path=tmp_path / "providers.yaml")
    svc.create_provider(
        {
            "name": "deepseek",
            "type": "deepseek",
            "enabled": True,
            "api_key": "sk-xyz",
            "base_url": "https://api.deepseek.com",
            "models": [{"name": "deepseek-v4-flash"}],
        }
    )
    raw = svc._load_yaml()
    assert raw.get("default_provider") == "deepseek"
    assert raw.get("default_model") == "deepseek-v4-flash"
