"""Tests for one-shot v2 migration (no runtime tier compatibility)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from leagent.config.tier_env_guard import detect_legacy_tier_env
from leagent.config.migrate_v2 import (
    migrate_env_file,
    migrate_providers_yaml,
    run_migration,
)
from leagent.llm.providers_schema import PROVIDERS_CONFIG_VERSION


def test_detect_legacy_tier_env() -> None:
    env = {
        "DEEPSEEK_API_KEY": "sk-x",
        "WORKAGENT_LLM__TIER1_API_KEY": "sk-y",
        "LEAGENT_LLM__TIER2_MODEL": "m",
    }
    found = detect_legacy_tier_env(env)
    assert "WORKAGENT_LLM__TIER1_API_KEY" in found
    assert "LEAGENT_LLM__TIER2_MODEL" in found
    assert "DEEPSEEK_API_KEY" not in found


def test_migrate_env_file_drops_tier_and_preserves_deepseek(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=sk-existing",
                "WORKAGENT_LLM__TIER1_API_KEY=sk-tier1",
                "WORKAGENT_LLM__TIER2_API_KEY=sk-tier2",
                "WORKAGENT_LLM__TIER1_MODEL=deepseek-chat",
                "WORKAGENT_LLM__TIER1_ENDPOINT=https://api.deepseek.com/v1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    _, removed, added = migrate_env_file(env)
    text = env.read_text(encoding="utf-8")
    assert "WORKAGENT_LLM__TIER" not in text
    assert "LLM_TIER1" not in text and "LLM_TIER2" not in text
    assert "DEEPSEEK_API_KEY=sk-existing" in text
    assert "WORKAGENT_LLM__TIER1_API_KEY" in removed
    assert "DASHSCOPE_API_KEY" in added
    assert "DEEPSEEK_MODEL" in added


def test_migrate_providers_yaml_v1_to_v2(tmp_path: Path) -> None:
    path = tmp_path / "providers.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "default_provider": "deepseek",
                "default_model": "deepseek-v4-pro",
                "providers": [
                    {
                        "name": "deepseek",
                        "type": "deepseek",
                        "enabled": True,
                        "models": [
                            {
                                "name": "deepseek-v4-pro",
                                "tier": "tier1",
                                "context_window": 1_000_000,
                                "supports_tools": True,
                            },
                            {
                                "name": "deepseek-v4-flash",
                                "tier": "tier2",
                                "context_window": 128_000,
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    normalized, changed, _backup = migrate_providers_yaml(path, in_place=True)
    assert changed is True
    assert normalized["version"] == PROVIDERS_CONFIG_VERSION
    tasks = normalized["routing"]["tasks"]
    assert tasks["chat"] == {"provider": "deepseek", "model": "deepseek-v4-pro"}
    assert tasks["fast"] == {"provider": "deepseek", "model": "deepseek-v4-flash"}
    reloaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    for provider in reloaded["providers"]:
        for model in provider["models"]:
            assert "tier" not in model
            assert "kind" in model
            assert "capabilities" in model


def test_run_migration_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("WORKAGENT_LLM__TIER1_API_KEY=sk-a\n", encoding="utf-8")
    report = run_migration(
        env_path=env,
        providers_path=tmp_path / "missing.yaml",
        migrate_providers=False,
        dry_run=True,
    )
    assert report.env_changed is True
    assert "WORKAGENT_LLM__TIER1_API_KEY" in report.env_removed_keys
    assert "TIER1_API_KEY" in env.read_text()
