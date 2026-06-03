"""Tests for ProviderConfigService validation and chat task routing."""

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


def _v2_yaml(
    *,
    chat_provider: str = "",
    chat_model: str = "",
    providers_block: str,
) -> str:
    return f"""
        version: 2
        default_task: chat
        routing:
          tasks:
            chat:
              provider: {chat_provider}
              model: {chat_model}
        providers:
{providers_block}
        """


_ACME_PROVIDERS = """
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


def test_set_default_rejects_unknown_model(tmp_path: Path) -> None:
    svc = _svc(_v2_yaml(providers_block=_ACME_PROVIDERS), tmp_path)
    with pytest.raises(ProviderConfigValidationError, match="not an enabled model"):
        svc.set_default("acme", "qwen-max")


def test_set_default_syncs_chat_task_routing(tmp_path: Path) -> None:
    svc = _svc(
        _v2_yaml(chat_provider="acme", chat_model="model-a", providers_block=_ACME_PROVIDERS),
        tmp_path,
    )
    svc.set_default("acme", "model-b")
    assert svc.get_default().model == "model-b"
    raw = svc._load_yaml()
    assert raw["routing"]["tasks"]["chat"]["model"] == "model-b"
    assert raw["routing"]["tasks"]["chat"]["provider"] == "acme"


def test_set_default_accepts_enabled_model(tmp_path: Path) -> None:
    svc = _svc(_v2_yaml(providers_block=_ACME_PROVIDERS), tmp_path)
    d = svc.set_default("acme", "model-a")
    assert d.provider == "acme"
    assert d.model == "model-a"


def test_set_default_rejects_disabled_model(tmp_path: Path) -> None:
    providers = """
          - name: acme
            type: custom
            enabled: true
            base_url: https://api.example.com/v1
            models:
              - name: "on"
                kind: chat
                capabilities:
                  input: [text]
                  output: [text]
              - name: "off"
                kind: chat
                enabled: false
                capabilities:
                  input: [text]
                  output: [text]
    """
    svc = _svc(_v2_yaml(providers_block=providers), tmp_path)
    with pytest.raises(ProviderConfigValidationError, match="not an enabled model"):
        svc.set_default("acme", "off")


def test_create_provider_requires_models(tmp_path: Path) -> None:
    svc = _svc(
        _v2_yaml(
            chat_provider="seed",
            chat_model="seed-model",
            providers_block="""
          - name: seed
            type: custom
            enabled: true
            base_url: https://seed.example.com/v1
            models:
              - name: seed-model
                kind: chat
                capabilities:
                  input: [text]
                  output: [text]
            """,
        ),
        tmp_path,
    )
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
    svc = _svc(
        _v2_yaml(
            chat_provider="seed",
            chat_model="seed-model",
            providers_block="""
          - name: seed
            type: custom
            enabled: true
            base_url: https://seed.example.com/v1
            models:
              - name: seed-model
                kind: chat
                capabilities:
                  input: [text]
                  output: [text]
            """,
        ),
        tmp_path,
    )
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
        _v2_yaml(
            chat_provider="acme",
            chat_model="old-model",
            providers_block="""
          - name: acme
            type: custom
            enabled: true
            base_url: https://api.example.com/v1
            models:
              - name: old-model
                kind: chat
                capabilities:
                  input: [text]
                  output: [text]
              - name: keep-me
                kind: chat
                capabilities:
                  input: [text]
                  output: [text]
            """,
        ),
        tmp_path,
    )
    svc.update_provider(
        "acme",
        {"models": [{"name": "keep-me", "kind": "chat", "capabilities": {"input": ["text"], "output": ["text"]}}]},
    )
    raw = svc._load_yaml()
    chat = raw["routing"]["tasks"]["chat"]
    assert chat["provider"] == ""
    assert chat["model"] == ""


def test_update_provider_promotes_default_when_empty(tmp_path: Path) -> None:
    deepseek_providers = """
          - name: deepseek
            type: deepseek
            enabled: true
            base_url: https://api.deepseek.com
            models:
              - name: deepseek-v4-flash
                kind: chat
                capabilities:
                  input: [text]
                  output: [text]
                  tool_call: true
              - name: deepseek-v4-pro
                kind: chat
                capabilities:
                  input: [text]
                  output: [text]
                  tool_call: true
    """
    svc = _svc(_v2_yaml(providers_block=deepseek_providers), tmp_path)
    svc.update_provider("deepseek", {"api_key": "sk-xyz"})
    raw = svc._load_yaml()
    chat = raw["routing"]["tasks"]["chat"]
    assert chat["provider"] == "deepseek"
    assert chat["model"] == "deepseek-v4-flash"


def test_create_provider_promotes_default_when_empty(tmp_path: Path) -> None:
    svc = _svc(
        _v2_yaml(
            providers_block="""
          - name: seed
            type: custom
            enabled: false
            base_url: https://seed.example.com/v1
            models:
              - name: seed-model
                kind: chat
                capabilities:
                  input: [text]
                  output: [text]
            """,
        ),
        tmp_path,
    )
    svc.create_provider(
        {
            "name": "deepseek",
            "type": "deepseek",
            "enabled": True,
            "api_key": "sk-xyz",
            "base_url": "https://api.deepseek.com",
            "models": [
                {
                    "name": "deepseek-v4-flash",
                    "kind": "chat",
                    "capabilities": {"input": ["text"], "output": ["text"], "tool_call": True},
                }
            ],
        }
    )
    raw = svc._load_yaml()
    chat = raw["routing"]["tasks"]["chat"]
    assert chat["provider"] == "deepseek"
    assert chat["model"] == "deepseek-v4-flash"
