"""RTSP MJPEG stream API (token mint + proxy)."""

from __future__ import annotations

import uuid
from urllib.parse import quote

import pytest

from leagent.config.settings import Settings, get_settings
from leagent.services.auth.service import AuthService
from leagent.services.rtsp_proxy import (
    decode_rtsp_mjpeg_token,
    mint_rtsp_mjpeg_token,
    validate_rtsp_url,
)


def _bearer(test_settings: Settings) -> dict[str, str]:
    token = AuthService(test_settings).create_access_token(uuid.uuid4())
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def rtsp_enabled():
    settings = get_settings()
    prev = settings.rtsp_stream.enabled
    settings.rtsp_stream.enabled = True
    yield settings
    settings.rtsp_stream.enabled = prev


def test_validate_rtsp_url_ok() -> None:
    u = validate_rtsp_url("rtsp://192.168.1.10:554/stream", max_chars=2048)
    assert u.startswith("rtsp://")


def test_validate_rtsp_url_rejects_http() -> None:
    with pytest.raises(ValueError):
        validate_rtsp_url("http://192.168.1.1/x", max_chars=2048)


def test_mint_token_roundtrip(rtsp_enabled: Settings) -> None:
    settings = get_settings()
    uid = uuid.uuid4()
    url = "rtsp://example.invalid/live"
    tok = mint_rtsp_mjpeg_token(settings, user_id=uid, rtsp_url=url)
    assert isinstance(tok, str) and len(tok) > 20
    claims = decode_rtsp_mjpeg_token(settings, tok)
    assert claims["sub"] == str(uid)
    assert claims["rtsp"] == url


def test_post_token_disabled(client) -> None:
    settings = get_settings()
    prev = settings.rtsp_stream.enabled
    settings.rtsp_stream.enabled = False
    try:
        r = client.post(
            "/api/v1/streams/rtsp/token",
            json={"url": "rtsp://127.0.0.1/stream"},
            headers=_bearer(settings),
        )
        assert r.status_code == 403
    finally:
        settings.rtsp_stream.enabled = prev


def test_post_token_bad_scheme(client, rtsp_enabled: Settings, test_settings: Settings) -> None:
    r = client.post(
        "/api/v1/streams/rtsp/token",
        json={"url": "http://evil.test/x"},
        headers=_bearer(test_settings),
    )
    assert r.status_code == 422


def test_post_token_ok(client, rtsp_enabled: Settings, test_settings: Settings) -> None:
    r = client.post(
        "/api/v1/streams/rtsp/token",
        json={"url": "rtsp://127.0.0.1:554/live"},
        headers=_bearer(test_settings),
    )
    assert r.status_code == 200
    body = r.json()
    assert "token" in body and body["token"]


def test_mjpeg_invalid_token(client, rtsp_enabled: Settings) -> None:
    r = client.get("/api/v1/streams/rtsp/mjpeg?token=not-a-jwt")
    assert r.status_code == 401


def test_mjpeg_mock_ffmpeg(client, rtsp_enabled: Settings, test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    from leagent.services import rtsp_proxy

    async def _fake_iter(_settings: Settings, _rtsp_url: str, **_kw):
        yield b"--ffmpeg\r\nContent-Type: image/jpeg\r\n\r\n\xff\xd8\xff\xd9\r\n"

    monkeypatch.setattr(rtsp_proxy, "iter_rtsp_mjpeg_bytes", _fake_iter)

    tok_resp = client.post(
        "/api/v1/streams/rtsp/token",
        json={"url": "rtsp://127.0.0.1/x"},
        headers=_bearer(test_settings),
    )
    token = tok_resp.json()["token"]
    r = client.get(f"/api/v1/streams/rtsp/mjpeg?token={quote(token, safe='')}")
    assert r.status_code == 200
    assert "multipart" in (r.headers.get("content-type") or "").lower()
    assert len(r.content) > 0
