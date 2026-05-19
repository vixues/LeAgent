"""Unit tests for SMTP default merging."""

from __future__ import annotations

import pytest

from leagent.config.settings import get_settings
from leagent.services.smtp_defaults import merge_smtp_defaults


def test_merge_smtp_defaults_fills_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEAGENT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("LEAGENT_SMTP_PORT", "465")
    monkeypatch.setenv("LEAGENT_SMTP_USERNAME", "u")
    monkeypatch.setenv("LEAGENT_SMTP_PASSWORD", "p")
    monkeypatch.setenv("LEAGENT_SMTP_USE_TLS", "false")
    monkeypatch.setenv("LEAGENT_SMTP_USE_SSL", "true")
    monkeypatch.setenv("LEAGENT_SMTP_FROM_EMAIL", "from@example.com")
    monkeypatch.setenv("LEAGENT_SMTP_FROM_NAME", "FN")
    get_settings.cache_clear()

    out = merge_smtp_defaults({"to": ["a@b.com"], "subject": "Hi"})
    assert out["smtp_host"] == "smtp.example.com"
    assert out["smtp_port"] == 465
    assert out["username"] == "u"
    assert out["password"] == "p"
    assert out["use_ssl"] is True
    assert out["use_tls"] is False
    assert out["from_email"] == "from@example.com"
    assert out["from_name"] == "FN"


def test_merge_preserves_explicit_tool_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEAGENT_SMTP_HOST", "smtp.env.com")
    monkeypatch.setenv("LEAGENT_SMTP_FROM_EMAIL", "env@example.com")
    get_settings.cache_clear()

    out = merge_smtp_defaults(
        {
            "smtp_host": "smtp.override.com",
            "from_email": "override@example.com",
            "to": ["x@y.com"],
            "subject": "S",
        }
    )
    assert out["smtp_host"] == "smtp.override.com"
    assert out["from_email"] == "override@example.com"
