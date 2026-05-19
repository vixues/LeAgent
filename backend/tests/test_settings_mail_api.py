"""Tests for GET/POST /api/v1/settings/mail."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from leagent.config.settings import get_settings


def test_get_mail_status(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEAGENT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("LEAGENT_SMTP_PORT", "587")
    monkeypatch.setenv("LEAGENT_SMTP_FROM_EMAIL", "from@example.com")
    monkeypatch.setenv("LEAGENT_SMTP_FROM_NAME", "Tests")
    monkeypatch.setenv("LEAGENT_SMTP_USE_TLS", "true")
    monkeypatch.setenv("LEAGENT_SMTP_USE_SSL", "false")
    monkeypatch.delenv("LEAGENT_SMTP_USERNAME", raising=False)
    monkeypatch.delenv("LEAGENT_SMTP_PASSWORD", raising=False)
    get_settings.cache_clear()

    r = client.get("/api/v1/settings/mail")
    assert r.status_code == 200
    data = r.json()
    assert data["host"] == "smtp.example.com"
    assert data["port"] == 587
    assert data["from_email"] == "from@example.com"
    assert data["from_name"] == "Tests"
    assert data["use_tls"] is True
    assert data["use_ssl"] is False
    assert data["username_set"] is False
    assert data["password_set"] is False


def test_post_mail_test_connection_mocked(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEAGENT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("LEAGENT_SMTP_PORT", "587")
    get_settings.cache_clear()

    async def _noop(merged: dict[str, Any]) -> None:
        return None

    monkeypatch.setattr(
        "leagent.api.v1.settings_mail.check_smtp_connection",
        _noop,
    )

    r = client.post("/api/v1/settings/mail/test", json={})
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True


def test_post_mail_test_send_mocked(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEAGENT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("LEAGENT_SMTP_FROM_EMAIL", "from@example.com")
    get_settings.cache_clear()

    async def _noop_send(merged: dict[str, Any], to_addr: str) -> None:
        assert to_addr == "to@example.com"

    monkeypatch.setattr(
        "leagent.api.v1.settings_mail.send_smtp_test_message",
        _noop_send,
    )

    r = client.post("/api/v1/settings/mail/test", json={"to": "to@example.com"})
    assert r.status_code == 200


def test_post_mail_test_requires_host(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LEAGENT_SMTP_HOST", raising=False)
    get_settings.cache_clear()

    r = client.post("/api/v1/settings/mail/test", json={})
    assert r.status_code == 400


def test_post_mail_test_requires_from_when_sending(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LEAGENT_SMTP_HOST", "smtp.example.com")
    monkeypatch.delenv("LEAGENT_SMTP_FROM_EMAIL", raising=False)
    get_settings.cache_clear()

    r = client.post("/api/v1/settings/mail/test", json={"to": "to@example.com"})
    assert r.status_code == 400
