"""CDN media upload/download with AES-128-ECB for Weixin iLink."""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from typing import Any
from urllib.parse import urlparse

import structlog

from .client import (
    MEDIA_FILE,
    MEDIA_IMAGE,
    MEDIA_VIDEO,
    MEDIA_VOICE,
    ITEM_FILE,
    ITEM_IMAGE,
    ITEM_VIDEO,
    WeixinClient,
)
from .crypto import aes128_ecb_decrypt, aes128_ecb_encrypt, aes_padded_size, parse_aes_key

logger = structlog.get_logger(__name__)

_WEIXIN_CDN_ALLOWLIST: frozenset[str] = frozenset(
    {
        "novac2c.cdn.weixin.qq.com",
        "ilinkai.weixin.qq.com",
        "wx.qlogo.cn",
        "thirdwx.qlogo.cn",
        "res.wx.qq.com",
        "mmbiz.qpic.cn",
        "mmbiz.qlogo.cn",
    }
)


def assert_weixin_cdn_url(url: str) -> None:
    """Raise ValueError if *url* is not on the WeChat CDN allowlist (SSRF guard)."""
    try:
        parsed = urlparse(url)
        scheme = (parsed.scheme or "").lower()
        host = parsed.hostname or ""
    except Exception as exc:
        raise ValueError(f"Unparseable media URL: {url!r}") from exc

    if scheme not in {"http", "https"}:
        raise ValueError(f"Media URL has disallowed scheme {scheme!r}")
    if host not in _WEIXIN_CDN_ALLOWLIST:
        raise ValueError(f"Media URL host {host!r} is not in the WeChat CDN allowlist")


def _media_ref(item: dict[str, Any], key: str) -> dict[str, Any]:
    return (item.get(key) or {}).get("media") or {}


async def _download_bytes(session: Any, url: str, timeout_seconds: float = 60.0) -> bytes:
    async def _do() -> bytes:
        async with session.get(url) as response:
            response.raise_for_status()
            return await response.read()

    return await asyncio.wait_for(_do(), timeout=timeout_seconds)


async def download_and_decrypt_media(
    client: WeixinClient,
    *,
    encrypted_query_param: str | None = None,
    aes_key: str | None = None,
    full_url: str | None = None,
    timeout_seconds: float = 60.0,
) -> bytes:
    """Download CDN ciphertext and optionally decrypt with AES-128-ECB."""
    session = await client._ensure_session()
    if encrypted_query_param:
        url = client.cdn_download_url(encrypted_query_param)
        raw = await _download_bytes(session, url, timeout_seconds)
    elif full_url:
        assert_weixin_cdn_url(full_url)
        raw = await _download_bytes(session, full_url, timeout_seconds)
    else:
        raise RuntimeError("media item had neither encrypt_query_param nor full_url")

    if aes_key:
        raw = aes128_ecb_decrypt(raw, parse_aes_key(aes_key))
    return raw


async def extract_inbound_media(
    client: WeixinClient,
    item: dict[str, Any],
) -> tuple[str, bytes, str] | None:
    """Extract inbound media from an iLink item.

    Returns ``(kind, plaintext_bytes, filename)`` or ``None``.
    """
    item_type = int(item.get("type") or 0)
    ref: dict[str, Any] = {}
    kind = ""
    filename = "file.bin"

    if item_type == ITEM_IMAGE:
        ref = _media_ref(item, "image_item") or item.get("image_item") or {}
        media = ref.get("media") or ref
        kind = "image"
        filename = "image.jpg"
    elif item_type == ITEM_VIDEO:
        ref = _media_ref(item, "video_item") or item.get("video_item") or {}
        media = ref.get("media") or ref
        kind = "video"
        filename = "video.mp4"
    elif item_type == ITEM_FILE:
        file_item = item.get("file_item") or {}
        media = file_item.get("media") or file_item
        kind = "file"
        filename = str(file_item.get("file_name") or file_item.get("filename") or "file.bin")
    elif item_type == 3:  # ITEM_VOICE
        voice_item = item.get("voice_item") or {}
        transcript = voice_item.get("text") or voice_item.get("recognition")
        if transcript:
            return ("voice_text", str(transcript).encode("utf-8"), "voice.txt")
        media = voice_item.get("media") or voice_item
        kind = "voice"
        filename = "voice.silk"
    else:
        return None

    encrypted_param = (
        media.get("encrypt_query_param")
        or media.get("encrypted_query_param")
        or media.get("encrypt_query")
    )
    aes_key = media.get("aes_key") or media.get("aeskey")
    full_url = media.get("full_url") or media.get("url")

    try:
        data = await download_and_decrypt_media(
            client,
            encrypted_query_param=str(encrypted_param) if encrypted_param else None,
            aes_key=str(aes_key) if aes_key else None,
            full_url=str(full_url) if full_url else None,
        )
    except Exception:
        logger.exception("weixin: failed to download inbound media", kind=kind)
        return None
    return (kind, data, filename)


async def upload_encrypted_media(
    client: WeixinClient,
    *,
    to_user_id: str,
    data: bytes,
    media_type: int,
    filename: str = "file.bin",
) -> dict[str, Any]:
    """Encrypt *data*, upload to CDN, return media reference fields for sendmessage."""
    session = await client._ensure_session()
    aes_key = secrets.token_bytes(16)
    ciphertext = aes128_ecb_encrypt(data, aes_key)
    filekey = uuid.uuid4().hex
    raw_md5 = hashlib.md5(data).hexdigest()
    aes_hex = aes_key.hex()

    upload_info = await client.get_upload_url(
        to_user_id=to_user_id,
        media_type=media_type,
        filekey=filekey,
        rawsize=len(data),
        rawfilemd5=raw_md5,
        filesize=aes_padded_size(len(data)),
        aeskey_hex=aes_hex,
    )

    # Prefer the direct CDN URL from getuploadurl — constructing from
    # upload_param alone can 404 on some CDN edge nodes.
    upload_full_url = str(upload_info.get("upload_full_url") or "").strip()
    upload_param = str(
        upload_info.get("upload_param") or upload_info.get("encrypted_query_param") or ""
    ).strip()
    if upload_full_url.startswith("http"):
        upload_url = upload_full_url
    elif upload_param.startswith("http"):
        upload_url = upload_param
    elif upload_param:
        upload_url = client.cdn_upload_url(upload_param, filekey)
    else:
        raise RuntimeError(f"getuploadurl missing upload param: {upload_info}")

    async def _do_upload() -> str:
        async with session.post(
            upload_url,
            data=ciphertext,
            headers={"Content-Type": "application/octet-stream"},
        ) as response:
            if response.status == 200:
                encrypted_param = response.headers.get("x-encrypted-param")
                if encrypted_param:
                    await response.read()
                    return encrypted_param
                raw = await response.text()
                raise RuntimeError(f"CDN upload missing x-encrypted-param: {raw[:200]}")
            raw = await response.text()
            raise RuntimeError(f"CDN upload HTTP {response.status}: {raw[:200]}")

    encrypted_param = await asyncio.wait_for(_do_upload(), timeout=120)

    media_payload = {
        "encrypt_query_param": encrypted_param,
        "aes_key": base64_aes_key(aes_key),
        "encrypt_type": 1,
        "filekey": filekey,
        "rawsize": len(data),
        "rawfilemd5": raw_md5,
        "filesize": len(ciphertext),
    }
    return {
        "media_type": media_type,
        "filename": filename,
        "media": media_payload,
        "aes_key_hex": aes_hex,
        "rawsize": len(data),
        "ciphertext_size": len(ciphertext),
    }


def base64_aes_key(key: bytes) -> str:
    """Encode AES key the way WeChat clients expect for CDN media.

    iLink expects ``base64(hex_string)``, not ``base64(raw_16_bytes)``. The
    latter makes attachments arrive as unbroken grey boxes / unopenable files.
    """
    import base64

    return base64.b64encode(key.hex().encode("ascii")).decode("ascii")


def build_image_item(upload: dict[str, Any]) -> dict[str, Any]:
    media = dict(upload["media"])
    media.setdefault("encrypt_type", 1)
    return {
        "type": ITEM_IMAGE,
        "image_item": {
            "media": media,
            "mid_size": upload.get("ciphertext_size") or media.get("filesize") or 0,
        },
    }


def build_file_item(upload: dict[str, Any], filename: str) -> dict[str, Any]:
    media = dict(upload["media"])
    media.setdefault("encrypt_type", 1)
    rawsize = int(upload.get("rawsize") or media.get("rawsize") or 0)
    return {
        "type": ITEM_FILE,
        "file_item": {
            "media": media,
            "file_name": filename,
            "len": str(rawsize),
        },
    }


def build_video_item(upload: dict[str, Any]) -> dict[str, Any]:
    media = dict(upload["media"])
    media.setdefault("encrypt_type", 1)
    return {
        "type": ITEM_VIDEO,
        "video_item": {
            "media": media,
            "video_size": upload.get("ciphertext_size") or media.get("filesize") or 0,
            "play_length": 0,
            "video_md5": media.get("rawfilemd5") or "",
        },
    }


def media_type_for_kind(kind: str) -> int:
    mapping = {
        "image": MEDIA_IMAGE,
        "video": MEDIA_VIDEO,
        "file": MEDIA_FILE,
        "voice": MEDIA_VOICE,
    }
    return mapping.get(kind, MEDIA_FILE)
