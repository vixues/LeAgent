"""RTSP preview helpers: URL validation, signed stream tokens, ffmpeg MJPEG."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator
from urllib.parse import urlparse
from uuid import UUID

from leagent.config.settings import Settings
from leagent.services.auth.tokens import mint_token, decode_token, TokenError

logger = logging.getLogger(__name__)

RTSP_MJPEG_AUDIENCE = "leagent-rtsp-mjpeg"


def _signing_secret(settings: Settings) -> str:
    s = (settings.canvas.preview_signing_secret or "").strip()
    if s:
        return s
    return "leagent-local-secret"


def validate_rtsp_url(raw: str, *, max_chars: int) -> str:
    """Return a stripped RTSP URL or raise ValueError."""
    url = (raw or "").strip()
    if not url:
        raise ValueError("empty URL")
    if len(url) > max_chars:
        raise ValueError("URL too long")
    parsed = urlparse(url)
    if parsed.scheme not in ("rtsp", "rtsps"):
        raise ValueError("only rtsp and rtsps URLs are allowed")
    if not parsed.hostname:
        raise ValueError("missing host")
    return url


def mint_rtsp_mjpeg_token(
    settings: Settings,
    *,
    user_id: UUID,
    rtsp_url: str,
    ttl_seconds: int | None = None,
) -> str:
    validate_rtsp_url(rtsp_url, max_chars=settings.rtsp_stream.max_url_chars)
    if ttl_seconds is None:
        ttl_seconds = settings.rtsp_stream.token_ttl_seconds
    ttl_seconds = max(60, int(ttl_seconds))

    now = datetime.now(timezone.utc)
    exp = now + timedelta(seconds=ttl_seconds)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "rtsp": rtsp_url,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "aud": RTSP_MJPEG_AUDIENCE,
    }
    return mint_token(payload, _signing_secret(settings))


def decode_rtsp_mjpeg_token(settings: Settings, token: str) -> dict[str, Any]:
    return decode_token(
        token,
        _signing_secret(settings),
        audience=RTSP_MJPEG_AUDIENCE,
        options={"require_exp": True},
    )


def _ffmpeg_args(settings: Settings, rtsp_url: str) -> list[str]:
    rs = settings.rtsp_stream
    exe = (rs.ffmpeg_path or "ffmpeg").strip() or "ffmpeg"
    vf = []
    if rs.scale_max_width and rs.scale_max_width > 0:
        vf = ["-vf", f"scale={int(rs.scale_max_width)}:-2"]
    q = max(1, min(31, int(rs.jpeg_quality)))
    return [
        exe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        rtsp_url,
        "-an",
        *vf,
        "-f",
        "mpjpeg",
        "-q:v",
        str(q),
        "-",
    ]


async def iter_rtsp_mjpeg_bytes(
    settings: Settings,
    rtsp_url: str,
    *,
    first_chunk_timeout_sec: float = 20.0,
) -> AsyncIterator[bytes]:
    """Yield multipart MJPEG bytes from ffmpeg stdout."""
    url = validate_rtsp_url(rtsp_url, max_chars=settings.rtsp_stream.max_url_chars)
    args = _ffmpeg_args(settings, url)
    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "ffmpeg executable not found; install ffmpeg or set RTSP_STREAM_FFMPEG_PATH"
        ) from exc
    assert proc.stdout is not None
    first = True
    try:
        while True:
            if first:
                chunk = await asyncio.wait_for(
                    proc.stdout.read(65536),
                    timeout=first_chunk_timeout_sec,
                )
                first = False
            else:
                chunk = await proc.stdout.read(65536)
            if not chunk:
                break
            yield chunk
    except TimeoutError:
        logger.warning("RTSP ffmpeg first frame timeout for host=%s", urlparse(url).hostname)
        raise RuntimeError("timed out waiting for video from RTSP source") from None
    finally:
        if proc.returncode is None:
            proc.kill()
        try:
            await asyncio.wait_for(proc.wait(), timeout=5.0)
        except TimeoutError:
            logger.warning("RTSP ffmpeg process did not exit cleanly")


async def claims_to_byte_stream(
    settings: Settings,
    claims: dict[str, Any],
) -> AsyncIterator[bytes]:
    raw = claims.get("rtsp")
    if not isinstance(raw, str):
        raise ValueError("token missing rtsp URL")
    async for chunk in iter_rtsp_mjpeg_bytes(settings, raw):
        yield chunk
