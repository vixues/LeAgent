"""HTTP client for the WeChat iLink Bot API."""

from __future__ import annotations

import asyncio
import base64
import json
import secrets
import struct
from typing import Any
from urllib.parse import quote

import structlog

logger = structlog.get_logger(__name__)

ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
WEIXIN_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"
ILINK_APP_ID = "bot"
CHANNEL_VERSION = "2.2.0"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0

EP_GET_UPDATES = "ilink/bot/getupdates"
EP_SEND_MESSAGE = "ilink/bot/sendmessage"
EP_SEND_TYPING = "ilink/bot/sendtyping"
EP_GET_CONFIG = "ilink/bot/getconfig"
EP_GET_UPLOAD_URL = "ilink/bot/getuploadurl"
EP_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"

LONG_POLL_TIMEOUT_MS = 35_000
API_TIMEOUT_MS = 15_000
CONFIG_TIMEOUT_MS = 10_000
QR_TIMEOUT_MS = 35_000

SESSION_EXPIRED_ERRCODE = -14
RATE_LIMIT_ERRCODE = -2

ITEM_TEXT = 1
ITEM_IMAGE = 2
ITEM_VOICE = 3
ITEM_FILE = 4
ITEM_VIDEO = 5

MSG_TYPE_USER = 1
MSG_TYPE_BOT = 2
MSG_STATE_FINISH = 2

TYPING_START = 1
TYPING_STOP = 2

MEDIA_IMAGE = 1
MEDIA_VIDEO = 2
MEDIA_FILE = 3
MEDIA_VOICE = 4


class SessionExpiredError(RuntimeError):
    """Raised when iLink returns errcode=-14 (or stale-session equivalent)."""


def _base_info() -> dict[str, Any]:
    return {"channel_version": CHANNEL_VERSION}


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _random_wechat_uin() -> str:
    value = struct.unpack(">I", secrets.token_bytes(4))[0]
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _headers(token: str | None, body: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Content-Length": str(len(body.encode("utf-8"))),
        "X-WECHAT-UIN": _random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def is_session_expired(
    ret: int | None,
    errcode: int | None,
    errmsg: str | None = None,
) -> bool:
    """True when the response indicates a stale / expired session."""
    if errcode == SESSION_EXPIRED_ERRCODE or ret == SESSION_EXPIRED_ERRCODE:
        return True
    if ret == RATE_LIMIT_ERRCODE or errcode == RATE_LIMIT_ERRCODE:
        return (errmsg or "").lower() == "unknown error"
    return False


def _raise_if_expired(data: dict[str, Any]) -> None:
    ret = data.get("ret")
    errcode = data.get("errcode")
    errmsg = data.get("errmsg")
    try:
        ret_i = int(ret) if ret is not None else None
    except (TypeError, ValueError):
        ret_i = None
    try:
        err_i = int(errcode) if errcode is not None else None
    except (TypeError, ValueError):
        err_i = None
    if is_session_expired(ret_i, err_i, str(errmsg) if errmsg else None):
        raise SessionExpiredError(
            f"iLink session expired (ret={ret}, errcode={errcode}, errmsg={errmsg})"
        )


class WeixinClient:
    """Thin async wrapper around iLink Bot API endpoints."""

    def __init__(
        self,
        *,
        token: str,
        base_url: str = ILINK_BASE_URL,
        cdn_base_url: str = WEIXIN_CDN_BASE_URL,
        session: Any | None = None,
    ) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.cdn_base_url = cdn_base_url.rstrip("/")
        self._session = session
        self._owns_session = session is None

    async def _ensure_session(self) -> Any:
        if self._session is not None and not getattr(self._session, "closed", False):
            return self._session
        import aiohttp

        timeout = aiohttp.ClientTimeout(total=None, connect=None, sock_connect=None, sock_read=None)
        self._session = aiohttp.ClientSession(trust_env=True, timeout=timeout)
        self._owns_session = True
        return self._session

    async def close(self) -> None:
        if self._owns_session and self._session is not None and not self._session.closed:
            await self._session.close()
        self._session = None

    async def api_post(
        self,
        endpoint: str,
        payload: dict[str, Any],
        *,
        timeout_ms: int = API_TIMEOUT_MS,
        token: str | None = None,
    ) -> dict[str, Any]:
        session = await self._ensure_session()
        body = _json_dumps({**payload, "base_info": _base_info()})
        url = f"{self.base_url}/{endpoint}"
        auth_token = token if token is not None else self.token

        async def _do() -> dict[str, Any]:
            async with session.post(url, data=body, headers=_headers(auth_token, body)) as response:
                raw = await response.text()
                if not response.ok:
                    raise RuntimeError(f"iLink POST {endpoint} HTTP {response.status}: {raw[:200]}")
                return json.loads(raw)

        data = await asyncio.wait_for(_do(), timeout=timeout_ms / 1000)
        _raise_if_expired(data)
        return data

    async def api_get(
        self,
        endpoint: str,
        *,
        timeout_ms: int = QR_TIMEOUT_MS,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        session = await self._ensure_session()
        url = f"{self.base_url}/{endpoint}"
        headers = {
            "iLink-App-Id": ILINK_APP_ID,
            "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
        }

        async def _do() -> dict[str, Any]:
            async with session.get(url, headers=headers, params=params) as response:
                raw = await response.text()
                if not response.ok:
                    raise RuntimeError(f"iLink GET {endpoint} HTTP {response.status}: {raw[:200]}")
                return json.loads(raw)

        return await asyncio.wait_for(_do(), timeout=timeout_ms / 1000)

    async def get_updates(self, sync_buf: str) -> dict[str, Any]:
        try:
            return await self.api_post(
                EP_GET_UPDATES,
                {"get_updates_buf": sync_buf},
                timeout_ms=LONG_POLL_TIMEOUT_MS,
            )
        except asyncio.TimeoutError:
            return {"ret": 0, "msgs": [], "get_updates_buf": sync_buf}

    async def send_text(
        self,
        *,
        to: str,
        text: str,
        context_token: str | None,
        client_id: str,
    ) -> dict[str, Any]:
        if not text or not text.strip():
            raise ValueError("send_text: text must not be empty")
        message: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": to,
            "client_id": client_id,
            "message_type": MSG_TYPE_BOT,
            "message_state": MSG_STATE_FINISH,
            "item_list": [{"type": ITEM_TEXT, "text_item": {"text": text}}],
        }
        if context_token:
            message["context_token"] = context_token
        return await self.api_post(EP_SEND_MESSAGE, {"msg": message})

    async def send_media_message(
        self,
        *,
        to: str,
        item: dict[str, Any],
        context_token: str | None,
        client_id: str,
    ) -> dict[str, Any]:
        message: dict[str, Any] = {
            "from_user_id": "",
            "to_user_id": to,
            "client_id": client_id,
            "message_type": MSG_TYPE_BOT,
            "message_state": MSG_STATE_FINISH,
            "item_list": [item],
        }
        if context_token:
            message["context_token"] = context_token
        return await self.api_post(EP_SEND_MESSAGE, {"msg": message})

    async def send_typing(
        self,
        *,
        to_user_id: str,
        typing_ticket: str,
        status: int,
    ) -> None:
        await self.api_post(
            EP_SEND_TYPING,
            {
                "ilink_user_id": to_user_id,
                "typing_ticket": typing_ticket,
                "status": status,
            },
            timeout_ms=CONFIG_TIMEOUT_MS,
        )

    async def get_config(
        self,
        *,
        user_id: str,
        context_token: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"ilink_user_id": user_id}
        if context_token:
            payload["context_token"] = context_token
        return await self.api_post(EP_GET_CONFIG, payload, timeout_ms=CONFIG_TIMEOUT_MS)

    async def get_upload_url(
        self,
        *,
        to_user_id: str,
        media_type: int,
        filekey: str,
        rawsize: int,
        rawfilemd5: str,
        filesize: int,
        aeskey_hex: str,
    ) -> dict[str, Any]:
        return await self.api_post(
            EP_GET_UPLOAD_URL,
            {
                "filekey": filekey,
                "media_type": media_type,
                "to_user_id": to_user_id,
                "rawsize": rawsize,
                "rawfilemd5": rawfilemd5,
                "filesize": filesize,
                "no_need_thumb": True,
                "aeskey": aeskey_hex,
            },
        )

    async def get_bot_qrcode(self, bot_type: int = 3) -> dict[str, Any]:
        return await self.api_get(
            EP_GET_BOT_QR,
            params={"bot_type": str(bot_type)},
            timeout_ms=QR_TIMEOUT_MS,
        )

    async def get_qrcode_status(self, qrcode: str) -> dict[str, Any]:
        return await self.api_get(
            EP_GET_QR_STATUS,
            params={"qrcode": qrcode},
            timeout_ms=QR_TIMEOUT_MS,
        )

    def cdn_download_url(self, encrypted_query_param: str) -> str:
        return (
            f"{self.cdn_base_url}/download"
            f"?encrypted_query_param={quote(encrypted_query_param, safe='')}"
        )

    def cdn_upload_url(self, upload_param: str, filekey: str) -> str:
        return (
            f"{self.cdn_base_url}/upload"
            f"?encrypted_query_param={quote(upload_param, safe='')}"
            f"&filekey={quote(filekey, safe='')}"
        )
