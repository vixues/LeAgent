"""Tests for /api/v1/settings/tokens."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


def test_get_tokens_status(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEAGENT_GITHUB_TOKEN", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    r = client.get("/api/v1/settings/tokens")
    assert r.status_code == 200
    data = r.json()
    assert "keys" in data
    keys = {x["env_key"]: x["set"] for x in data["keys"]}
    assert "LEAGENT_GITHUB_TOKEN" in keys
    assert keys["LEAGENT_GITHUB_TOKEN"] is False
    assert "LEAGENT_SMTP_HOST" in keys


def test_put_rejects_invalid_smtp_port(client: TestClient) -> None:
    r = client.put(
        "/api/v1/settings/tokens",
        json={"values": {"LEAGENT_SMTP_PORT": "99999"}},
    )
    assert r.status_code == 400


def test_put_rejects_invalid_smtp_use_tls(client: TestClient) -> None:
    r = client.put(
        "/api/v1/settings/tokens",
        json={"values": {"LEAGENT_SMTP_USE_TLS": "maybe"}},
    )
    assert r.status_code == 400


def test_put_token_masked_reload_env(client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.setenv("LEAGENT_HOME", str(tmp_path))
    from leagent.services import settings_configure as sc

    monkeypatch.setattr(sc, "env_path", lambda: tmp_path / ".env")

    r = client.put(
        "/api/v1/settings/tokens",
        json={"values": {"LEAGENT_GITHUB_TOKEN": "ghp_test_fake"}},
    )
    assert r.status_code == 200
    assert os.environ.get("LEAGENT_GITHUB_TOKEN") == "ghp_test_fake"
    env_file = tmp_path / ".env"
    assert env_file.is_file()
    text = env_file.read_text(encoding="utf-8")
    assert "LEAGENT_GITHUB_TOKEN" in text


def test_put_rejects_unknown_key(client: TestClient) -> None:
    r = client.put(
        "/api/v1/settings/tokens",
        json={"values": {"MALICIOUS_KEY": "x"}},
    )
    assert r.status_code == 400


def test_put_rejects_error_payload_for_deepseek_key(client: TestClient) -> None:
    r = client.put(
        "/api/v1/settings/tokens",
        json={
            "values": {
                "DEEPSEEK_API_KEY": "{'finish_reason': 'error', 'error': 'LLM request timed out after 120s'}"
            }
        },
    )
    assert r.status_code == 400


def test_put_rejects_invalid_web_search_provider(client: TestClient) -> None:
    r = client.put(
        "/api/v1/settings/tokens",
        json={"values": {"WEB_SEARCH_PROVIDER": "google"}},
    )
    assert r.status_code == 400


def test_put_rejects_invalid_web_fetch_enabled(client: TestClient) -> None:
    r = client.put(
        "/api/v1/settings/tokens",
        json={"values": {"WEB_FETCH_ENABLED": "maybe"}},
    )
    assert r.status_code == 400


def test_put_accepts_web_search_provider_and_clears_cache(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from leagent.services import settings_configure as sc

    monkeypatch.setattr(sc, "env_path", lambda: tmp_path / ".env")
    cleared: list[bool] = []

    def fake_clear() -> None:
        cleared.append(True)

    monkeypatch.setattr("leagent.config.settings.get_settings.cache_clear", fake_clear)
    r = client.put(
        "/api/v1/settings/tokens",
        json={"values": {"WEB_SEARCH_PROVIDER": "bing"}},
    )
    assert r.status_code == 200
    assert cleared == [True]


def test_put_accepts_brave_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from leagent.services import settings_configure as sc

    monkeypatch.setattr(sc, "env_path", lambda: tmp_path / ".env")
    r = client.put(
        "/api/v1/settings/tokens",
        json={"values": {"WEB_SEARCH_PROVIDER": "brave", "WEB_SEARCH_BRAVE_API_KEY": "test-key"}},
    )
    assert r.status_code == 200
