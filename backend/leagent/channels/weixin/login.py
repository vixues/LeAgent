"""QR-code login flow for WeChat iLink Bot."""

from __future__ import annotations

import asyncio
import base64
import io
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import structlog

from .client import ILINK_BASE_URL, WeixinClient
from .store import save_account

logger = structlog.get_logger(__name__)

StatusCallback = Callable[[str, dict[str, Any]], None]

CONFIRMED_STATUSES = frozenset({"confirmed", "confirm", "success"})
SCANNED_STATUSES = frozenset({"scaned", "scanned", "scan"})
EXPIRED_STATUSES = frozenset({"expired", "expire", "timeout"})
WAIT_STATUSES = frozenset({"wait", "waiting", ""})


@dataclass
class WeixinLoginResult:
    """Result of a successful QR login."""

    account_id: str
    token: str
    base_url: str
    user_id: str = ""


@dataclass
class WeixinQrSession:
    """Payload for starting a QR login session (API / CLI / UI)."""

    qrcode: str
    qr_url: str
    qr_image_data_url: str
    base_url: str


def _extract_qr_fields(qr_data: dict[str, Any]) -> tuple[str, str]:
    """Split iLink QR response into poll token vs scannable payload.

    iLink returns:
    - ``qrcode``: short hex token — used only for ``get_qrcode_status`` polling
    - ``qrcode_img_content``: full liteapp URL WeChat must scan
      (e.g. ``https://liteapp.weixin.qq.com/q/...?qrcode=...&bot_type=3``)

    Encoding the hex token into a QR makes WeChat show a plain string with
    **no** authorize button. Always encode ``qrcode_img_content`` (or the
    best available scannable payload) into the displayed QR.
    """
    qrcode = str(qr_data.get("qrcode") or qr_data.get("qr_code") or "").strip()
    # Prefer the liteapp / scannable content — NOT a raster image URL.
    scan_payload = str(
        qr_data.get("qrcode_img_content")
        or qr_data.get("qrcode_img_url")
        or qr_data.get("qrcode_url")
        or qr_data.get("url")
        or ""
    ).strip()
    return qrcode, scan_payload


def render_qr_data_url(content: str) -> str:
    """Render *content* (usually a liteapp URL) as a PNG data URL.

    Requires the ``qrcode`` package (and Pillow). Empty string on failure.
    """
    text = (content or "").strip()
    if not text:
        return ""
    if text.startswith("data:image/"):
        return text

    try:
        import qrcode
    except ImportError:
        logger.warning("qrcode package not installed; cannot render Weixin QR PNG")
        return ""

    try:
        qr = qrcode.QRCode(border=2, box_size=6)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except Exception:
        logger.warning("failed to render QR PNG", exc_info=True)
        return ""


def normalize_qr_status(raw: dict[str, Any]) -> str:
    """Normalize iLink QR status strings to wait|scanned|confirmed|expired|unknown."""
    status = str(raw.get("status") or raw.get("qrcode_status") or "").strip().lower()
    if status in CONFIRMED_STATUSES:
        return "confirmed"
    if status in SCANNED_STATUSES or status == "scaned_but_redirect":
        return "scanned"
    if status in EXPIRED_STATUSES:
        return "expired"
    if status in WAIT_STATUSES:
        return "wait"
    return status or "unknown"


def parse_login_result(
    status_data: dict[str, Any],
    *,
    fallback_base_url: str = ILINK_BASE_URL,
) -> WeixinLoginResult:
    """Extract credentials from a confirmed QR status payload."""
    account_id = str(
        status_data.get("account_id")
        or status_data.get("ilink_user_id")
        or status_data.get("bot_id")
        or ""
    ).strip()
    token = str(
        status_data.get("bot_token")
        or status_data.get("token")
        or status_data.get("ilink_bot_token")
        or ""
    ).strip()
    returned_base = str(
        status_data.get("baseurl")
        or status_data.get("base_url")
        or fallback_base_url
    ).strip().rstrip("/")
    user_id = str(status_data.get("user_id") or "").strip()

    if not token:
        raise RuntimeError(f"QR confirmed but no token in response: {status_data}")
    if not account_id:
        account_id = user_id or "default"

    return WeixinLoginResult(
        account_id=account_id,
        token=token,
        base_url=returned_base or fallback_base_url,
        user_id=user_id,
    )


def persist_login_result(result: WeixinLoginResult) -> None:
    """Save account file + enable ``channels.weixin`` in runtime config."""
    from leagent.config.config import ChannelConfig, load_config, save_config

    save_account(
        account_id=result.account_id,
        token=result.token,
        base_url=result.base_url,
        user_id=result.user_id,
    )
    config = load_config()
    if "weixin" not in config.channels:
        config.channels["weixin"] = ChannelConfig()
    wx = config.channels["weixin"]
    wx.enabled = True
    wx.token = result.token
    wx.extra["account_id"] = result.account_id
    wx.extra["base_url"] = result.base_url
    if result.user_id:
        wx.extra["user_id"] = result.user_id
    save_config(config)


async def start_qr_session(
    *,
    base_url: str = ILINK_BASE_URL,
    bot_type: int = 3,
) -> WeixinQrSession:
    """Request a QR code and render a PNG of the **scannable liteapp URL**."""
    client = WeixinClient(token="", base_url=base_url)
    try:
        qr_data = await client.get_bot_qrcode(bot_type=bot_type)
    finally:
        await client.close()

    qrcode_token, scan_payload = _extract_qr_fields(qr_data)
    if not qrcode_token and not scan_payload:
        raise RuntimeError(f"get_bot_qrcode returned no qrcode: {qr_data}")

    # WeChat must scan the liteapp URL, not the hex poll token.
    qr_scan_data = scan_payload or qrcode_token
    image_data_url = render_qr_data_url(qr_scan_data)
    if not image_data_url:
        logger.warning(
            "weixin QR PNG render failed; UI will fall back to showing the URL text",
            payload_prefix=qr_scan_data[:48],
        )

    return WeixinQrSession(
        # Poll status with the hex token when available.
        qrcode=qrcode_token or scan_payload,
        qr_url=scan_payload,
        qr_image_data_url=image_data_url,
        base_url=base_url.rstrip("/"),
    )


async def check_qr_session(
    qrcode: str,
    *,
    base_url: str = ILINK_BASE_URL,
) -> dict[str, Any]:
    """Poll QR status and, on confirmed, persist credentials.

    Supports ``scaned_but_redirect`` by switching to the returned host for
    subsequent polls (caller should pass the updated ``base_url`` back).
    """
    resolved_base = base_url.rstrip("/")
    raw = await poll_qrcode_status(qrcode, base_url=resolved_base)
    status_raw = str(raw.get("status") or raw.get("qrcode_status") or "").strip().lower()

    # iLink may ask us to follow a redirect host mid-login.
    if status_raw == "scaned_but_redirect":
        redirect_host = str(raw.get("redirect_host") or "").strip()
        if redirect_host:
            resolved_base = f"https://{redirect_host}".rstrip("/")
            raw = await poll_qrcode_status(qrcode, base_url=resolved_base)
            status_raw = str(raw.get("status") or "").strip().lower()

    status = normalize_qr_status(raw)
    out: dict[str, Any] = {
        "status": status,
        "qrcode": qrcode,
        "base_url": resolved_base,
    }

    if status == "confirmed":
        result = parse_login_result(raw, fallback_base_url=resolved_base)
        persist_login_result(result)
        out.update(
            {
                "account_id": result.account_id,
                "base_url": result.base_url,
                "user_id": result.user_id,
                "connected": True,
            }
        )
        logger.info("weixin login succeeded", account_id=result.account_id[:12])
    return out


async def request_qrcode(
    *,
    base_url: str = ILINK_BASE_URL,
    bot_type: int = 3,
) -> dict[str, Any]:
    """Request a login QR code from iLink."""
    client = WeixinClient(token="", base_url=base_url)
    try:
        data = await client.get_bot_qrcode(bot_type=bot_type)
    finally:
        await client.close()
    return data


async def poll_qrcode_status(
    qrcode: str,
    *,
    base_url: str = ILINK_BASE_URL,
) -> dict[str, Any]:
    """Poll scan/confirm status for *qrcode*."""
    client = WeixinClient(token="", base_url=base_url)
    try:
        return await client.get_qrcode_status(qrcode)
    finally:
        await client.close()


async def run_qr_login(
    *,
    base_url: str = ILINK_BASE_URL,
    bot_type: int = 3,
    max_qr_refreshes: int = 3,
    poll_interval_sec: float = 1.5,
    on_status: StatusCallback | None = None,
    print_qr_url: Callable[[str], None] | None = None,
) -> WeixinLoginResult:
    """Run the full QR scan-and-confirm login, persisting credentials on success."""
    refreshes = 0

    while refreshes <= max_qr_refreshes:
        session = await start_qr_session(base_url=base_url, bot_type=bot_type)
        display = session.qr_url or session.qrcode
        if print_qr_url:
            print_qr_url(display)
        if on_status:
            on_status("wait", {"qrcode": session.qrcode, "qr_url": session.qr_url})

        while True:
            raw = await poll_qrcode_status(session.qrcode, base_url=session.base_url)
            status = normalize_qr_status(raw)
            if on_status:
                on_status(status, raw)

            if status == "confirmed":
                result = parse_login_result(raw, fallback_base_url=session.base_url)
                persist_login_result(result)
                logger.info(
                    "weixin login succeeded",
                    account_id=result.account_id[:12],
                    base_url=result.base_url,
                )
                return result

            if status == "expired":
                refreshes += 1
                logger.info("weixin QR expired, refreshing", attempt=refreshes)
                break

            await asyncio.sleep(poll_interval_sec)

    raise TimeoutError(
        f"Weixin QR login failed after {max_qr_refreshes} QR refreshes"
    )
