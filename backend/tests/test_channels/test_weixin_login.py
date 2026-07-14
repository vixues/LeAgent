"""Tests for Weixin QR login helpers (API-facing)."""

from __future__ import annotations

from leagent.channels.weixin.login import (
    normalize_qr_status,
    parse_login_result,
    render_qr_data_url,
)


def test_normalize_qr_status() -> None:
    assert normalize_qr_status({"status": "wait"}) == "wait"
    assert normalize_qr_status({"status": "scaned"}) == "scanned"
    assert normalize_qr_status({"qrcode_status": "confirmed"}) == "confirmed"
    assert normalize_qr_status({"status": "expired"}) == "expired"


def test_parse_login_result() -> None:
    result = parse_login_result(
        {
            "bot_token": "tok-abc",
            "account_id": "acc-1",
            "baseurl": "https://ilinkai.weixin.qq.com",
        }
    )
    assert result.token == "tok-abc"
    assert result.account_id == "acc-1"


def test_render_qr_data_url_png() -> None:
    data_url = render_qr_data_url("weixin-login-payload-abc123")
    assert data_url.startswith("data:image/png;base64,")
    assert len(data_url) > 100


def test_render_qr_encodes_https_liteapp_url() -> None:
    """liteapp URLs must be encoded into the QR — they are not image srcs."""
    url = "https://liteapp.weixin.qq.com/q/7GiQu1?qrcode=abc&bot_type=3"
    data_url = render_qr_data_url(url)
    assert data_url.startswith("data:image/png;base64,")


def test_extract_prefers_liteapp_payload() -> None:
    from leagent.channels.weixin.login import _extract_qr_fields

    token, payload = _extract_qr_fields(
        {
            "qrcode": "349ce75ceb5f4e6dd72a0a6ad3c35afa",
            "qrcode_img_content": (
                "https://liteapp.weixin.qq.com/q/7GiQu1"
                "?qrcode=349ce75ceb5f4e6dd72a0a6ad3c35afa&bot_type=3"
            ),
            "ret": 0,
        }
    )
    assert token == "349ce75ceb5f4e6dd72a0a6ad3c35afa"
    assert payload.startswith("https://liteapp.weixin.qq.com/")
