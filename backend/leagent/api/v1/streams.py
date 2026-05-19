"""Media stream helpers (RTSP preview via server-side ffmpeg)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from leagent.services.auth.tokens import TokenError
from pydantic import BaseModel, Field

from leagent.config.settings import Settings, get_settings
from leagent.services.auth import CurrentUserId
from leagent.services.rtsp_proxy import (
    decode_rtsp_mjpeg_token,
    mint_rtsp_mjpeg_token,
    claims_to_byte_stream,
)

router = APIRouter()


class RtspTokenRequest(BaseModel):
    url: str = Field(..., min_length=1)


class RtspTokenResponse(BaseModel):
    """Short-lived bearer for ``GET …/streams/rtsp/mjpeg`` (usable in ``<img src>``)."""

    token: str


@router.post("/rtsp/token", response_model=RtspTokenResponse)
def create_rtsp_mjpeg_token(
    body: RtspTokenRequest,
    settings: Annotated[Settings, Depends(get_settings)],
    user_id: CurrentUserId,
) -> RtspTokenResponse:
    if not settings.rtsp_stream.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="RTSP stream proxy is disabled (set RTSP_STREAM_ENABLED=true to enable)",
        )
    try:
        token = mint_rtsp_mjpeg_token(settings, user_id=user_id, rtsp_url=body.url)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    return RtspTokenResponse(token=token)


@router.get("/rtsp/mjpeg")
async def rtsp_mjpeg(
    token: Annotated[str, Query(min_length=1)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> StreamingResponse:
    if not settings.rtsp_stream.enabled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="RTSP stream proxy is disabled",
        )
    try:
        claims = decode_rtsp_mjpeg_token(settings, token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired stream token",
        ) from exc

    gen = claims_to_byte_stream(settings, claims)
    try:
        first = await anext(gen)
    except StopAsyncIteration:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="no data from RTSP source",
        ) from None
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    async def body():
        yield first
        async for chunk in gen:
            yield chunk

    return StreamingResponse(
        body(),
        media_type="multipart/x-mixed-replace; boundary=ffmpeg",
    )
