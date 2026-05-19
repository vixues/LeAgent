"""Tests for :mod:`leagent.utils.httpx_proxy`."""

from __future__ import annotations

import logging
import os

import pytest

from leagent.utils import httpx_proxy


@pytest.fixture(autouse=True)
def reset_socks_log_flag():
    httpx_proxy._logged_socks_disable = False  # type: ignore[attr-defined]
    httpx_proxy._logged_socks_enable = False  # type: ignore[attr-defined]
    httpx_proxy._logged_trust_override = False  # type: ignore[attr-defined]
    httpx_proxy._logged_proxy_scheme_normalization.clear()  # type: ignore[attr-defined]
    yield


def test_httpx_trust_env_true_without_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_HTTPX_TRUST_ENV", raising=False)
    monkeypatch.delenv("LEAGENT_HTTPX_TRUST_ENV", raising=False)
    for key in (
        "ALL_PROXY",
        "all_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "HTTPS_PROXY",
        "https_proxy",
    ):
        monkeypatch.delenv(key, raising=False)
    assert httpx_proxy.httpx_trust_env() is True


def test_httpx_trust_env_false_for_socks5(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.delenv("LLM_HTTPX_TRUST_ENV", raising=False)
    monkeypatch.delenv("LEAGENT_HTTPX_TRUST_ENV", raising=False)
    monkeypatch.setenv("HTTP_PROXY", "socks5://127.0.0.1:9")
    # When socks support is installed (socksio), we should keep trust_env=True so the
    # backend can work behind macOS proxy apps. Otherwise we fall back to trust_env=False.
    try:
        import socksio  # noqa: F401
    except Exception:
        caplog.set_level(logging.WARNING, logger="leagent.utils.httpx_proxy")
        assert httpx_proxy.httpx_trust_env() is False
        assert "SOCKS" in caplog.text
    else:
        caplog.set_level(logging.INFO, logger="leagent.utils.httpx_proxy")
        assert httpx_proxy.httpx_trust_env() is True
        assert "SOCKS" in caplog.text


def test_httpx_trust_env_override_never(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_HTTPX_TRUST_ENV", "never")
    monkeypatch.setenv("HTTP_PROXY", "socks5://127.0.0.1:9")
    assert httpx_proxy.httpx_trust_env() is False


def test_httpx_trust_env_override_always(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_HTTPX_TRUST_ENV", "always")
    monkeypatch.setenv("HTTP_PROXY", "socks5://127.0.0.1:9")
    assert httpx_proxy.httpx_trust_env() is True


def test_bare_socks_scheme_normalized_for_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clash / some macOS apps set socks://; httpx only accepts socks5/socks5h."""
    monkeypatch.delenv("LLM_HTTPX_TRUST_ENV", raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "socks://127.0.0.1:7897")
    httpx_proxy.httpx_trust_env()
    assert os.environ["HTTPS_PROXY"] == "socks5://127.0.0.1:7897"
