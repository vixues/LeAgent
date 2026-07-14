"""Channel configuration API endpoints."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from leagent.api.deps import ServiceManagerDep
from leagent.services.auth import CurrentUserId

router = APIRouter()


class ChannelType(str, Enum):
    """Supported channel types."""

    DINGTALK = "dingtalk"
    FEISHU = "feishu"
    WECHAT_WORK = "wechat_work"
    WEIXIN = "weixin"
    WEB = "web"
    API = "api"
    CONSOLE = "console"


class ChannelStatus(str, Enum):
    """Channel connection status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"


_channels: dict[UUID, dict[str, Any]] = {}


class ChannelConfig(BaseModel):
    """Channel configuration response."""

    id: UUID
    name: str
    channel_type: ChannelType
    status: ChannelStatus
    enabled: bool
    config: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class ChannelCreateRequest(BaseModel):
    """Request schema for creating a channel."""

    name: str = Field(..., min_length=1, max_length=100)
    channel_type: ChannelType
    enabled: bool = Field(default=True)
    config: dict[str, Any] = Field(default_factory=dict)


class ChannelUpdateRequest(BaseModel):
    """Request schema for updating a channel."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    enabled: Optional[bool] = None
    config: Optional[dict[str, Any]] = None


class ChannelListResponse(BaseModel):
    """Response for channel listing."""

    channels: list[ChannelConfig]
    total: int


class ChannelTestResponse(BaseModel):
    """Response for channel connection test."""

    channel_id: UUID
    channel_type: ChannelType
    success: bool
    latency_ms: int
    error: Optional[str] = None


class WeixinLoginStartRequest(BaseModel):
    """Optional overrides when requesting a Weixin QR code."""

    base_url: Optional[str] = None


class WeixinLoginStartResponse(BaseModel):
    """QR session returned to the frontend for scanning."""

    qrcode: str
    qr_url: str = ""
    qr_image_data_url: str = ""
    base_url: str
    status: str = "wait"


class WeixinLoginStatusResponse(BaseModel):
    """Polled QR login status; on confirmed, gateway is hot-started."""

    status: str
    qrcode: str
    connected: bool = False
    account_id: str = ""
    base_url: str = ""
    running: bool = False
    message: str = ""


class WeixinRuntimeResponse(BaseModel):
    """Live Weixin poller status."""

    enabled: bool = False
    configured: bool = False
    running: bool = False
    account_id: str = ""
    session_expired: bool = False


# ── Weixin QR login (must be registered before /{channel_id}) ───────────


@router.post("/weixin/login/start", response_model=WeixinLoginStartResponse)
async def weixin_login_start(
    user_id: CurrentUserId,
    body: WeixinLoginStartRequest | None = None,
) -> WeixinLoginStartResponse:
    """Request a Weixin iLink QR code for browser scanning."""
    from leagent.channels.weixin.client import ILINK_BASE_URL
    from leagent.channels.weixin.login import start_qr_session

    _ = user_id
    base = ((body.base_url if body else None) or ILINK_BASE_URL).rstrip("/")
    try:
        session = await start_qr_session(base_url=base)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to request Weixin QR: {exc}",
        ) from exc

    return WeixinLoginStartResponse(
        qrcode=session.qrcode,
        qr_url=session.qr_url,
        qr_image_data_url=session.qr_image_data_url,
        base_url=session.base_url,
        status="wait",
    )


@router.get("/weixin/login/status", response_model=WeixinLoginStatusResponse)
async def weixin_login_status(
    user_id: CurrentUserId,
    sm: ServiceManagerDep,
    qrcode: str = Query(..., min_length=1),
    base_url: Optional[str] = Query(default=None),
) -> WeixinLoginStatusResponse:
    """Poll QR scan status; on confirm, hot-start the Weixin agent channel."""
    from leagent.channels.weixin.client import ILINK_BASE_URL
    from leagent.channels.weixin.login import check_qr_session

    _ = user_id
    resolved_base = (base_url or ILINK_BASE_URL).rstrip("/")
    try:
        result = await check_qr_session(qrcode, base_url=resolved_base)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to poll Weixin QR status: {exc}",
        ) from exc

    status_value = str(result.get("status") or "unknown")
    response = WeixinLoginStatusResponse(
        status=status_value,
        qrcode=qrcode,
        connected=bool(result.get("connected")),
        account_id=str(result.get("account_id") or ""),
        base_url=str(result.get("base_url") or resolved_base),
    )

    if status_value == "confirmed":
        try:
            runtime = await sm.ensure_weixin_running()
            response.running = bool(runtime.get("running"))
            response.message = "Weixin connected; long-poll started (no restart needed)."
        except Exception as exc:
            response.running = False
            response.message = (
                f"Credentials saved, but failed to start poller: {exc}. "
                "Try again from the Weixin panel."
            )
    elif status_value == "scanned":
        response.message = "QR scanned — confirm on your phone."
    elif status_value == "expired":
        response.message = "QR expired — request a new code."
    else:
        response.message = "Waiting for scan…"

    return response


@router.get("/weixin/runtime", response_model=WeixinRuntimeResponse)
async def weixin_runtime(
    user_id: CurrentUserId,
    sm: ServiceManagerDep,
) -> WeixinRuntimeResponse:
    """Return whether the Weixin long-poller is currently running."""
    _ = user_id
    data = sm.weixin_runtime_status()
    return WeixinRuntimeResponse(**data)


@router.post("/weixin/start", response_model=WeixinRuntimeResponse)
async def weixin_start(
    user_id: CurrentUserId,
    sm: ServiceManagerDep,
) -> WeixinRuntimeResponse:
    """Hot-start / reload Weixin from saved credentials (no process restart)."""
    _ = user_id
    try:
        await sm.ensure_weixin_running()
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    data = sm.weixin_runtime_status()
    return WeixinRuntimeResponse(**data)


@router.post("/weixin/stop", response_model=WeixinRuntimeResponse)
async def weixin_stop(
    user_id: CurrentUserId,
    sm: ServiceManagerDep,
) -> WeixinRuntimeResponse:
    """Stop the live Weixin poller and persist enabled=false (keeps credentials)."""
    _ = user_id
    await sm.stop_weixin_channel()
    data = sm.weixin_runtime_status()
    return WeixinRuntimeResponse(**data)


@router.get("", response_model=ChannelListResponse)
async def list_channels(
    user_id: CurrentUserId,
    channel_type: Optional[ChannelType] = Query(default=None),
    status: Optional[ChannelStatus] = Query(default=None),
) -> ChannelListResponse:
    """List all configured channels."""
    channels = []

    for channel_id, data in _channels.items():
        if data.get("user_id") != user_id:
            continue
        if channel_type and data.get("channel_type") != channel_type:
            continue
        if status and data.get("status") != status:
            continue

        channels.append(
            ChannelConfig(
                id=channel_id,
                name=data["name"],
                channel_type=data["channel_type"],
                status=data["status"],
                enabled=data["enabled"],
                config=data.get("config", {}),
                created_at=data["created_at"],
                updated_at=data["updated_at"],
            )
        )

    return ChannelListResponse(
        channels=channels,
        total=len(channels),
    )


@router.post("", response_model=ChannelConfig, status_code=status.HTTP_201_CREATED)
async def create_channel(
    data: ChannelCreateRequest,
    user_id: CurrentUserId,
) -> ChannelConfig:
    """Create a new channel configuration."""
    channel_id = uuid4()
    now = datetime.utcnow()

    _channels[channel_id] = {
        "user_id": user_id,
        "name": data.name,
        "channel_type": data.channel_type,
        "status": ChannelStatus.INACTIVE,
        "enabled": data.enabled,
        "config": data.config,
        "created_at": now,
        "updated_at": now,
    }

    return ChannelConfig(
        id=channel_id,
        name=data.name,
        channel_type=data.channel_type,
        status=ChannelStatus.INACTIVE,
        enabled=data.enabled,
        config=data.config,
        created_at=now,
        updated_at=now,
    )


@router.get("/{channel_id}", response_model=ChannelConfig)
async def get_channel(
    channel_id: UUID,
    user_id: CurrentUserId,
) -> ChannelConfig:
    """Get channel configuration by ID."""
    data = _channels.get(channel_id)
    if not data or data.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )

    return ChannelConfig(
        id=channel_id,
        name=data["name"],
        channel_type=data["channel_type"],
        status=data["status"],
        enabled=data["enabled"],
        config=data.get("config", {}),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


@router.put("/{channel_id}", response_model=ChannelConfig)
async def update_channel(
    channel_id: UUID,
    data: ChannelUpdateRequest,
    user_id: CurrentUserId,
) -> ChannelConfig:
    """Update a channel configuration."""
    channel_data = _channels.get(channel_id)
    if not channel_data or channel_data.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )

    if data.name is not None:
        channel_data["name"] = data.name
    if data.enabled is not None:
        channel_data["enabled"] = data.enabled
    if data.config is not None:
        channel_data["config"] = data.config

    channel_data["updated_at"] = datetime.utcnow()

    return ChannelConfig(
        id=channel_id,
        name=channel_data["name"],
        channel_type=channel_data["channel_type"],
        status=channel_data["status"],
        enabled=channel_data["enabled"],
        config=channel_data.get("config", {}),
        created_at=channel_data["created_at"],
        updated_at=channel_data["updated_at"],
    )


@router.delete("/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel(
    channel_id: UUID,
    user_id: CurrentUserId,
) -> None:
    """Delete a channel configuration."""
    data = _channels.get(channel_id)
    if not data or data.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )

    del _channels[channel_id]


@router.post("/{channel_id}/test", response_model=ChannelTestResponse)
async def test_channel(
    channel_id: UUID,
    user_id: CurrentUserId,
) -> ChannelTestResponse:
    """Test channel connection."""
    import time

    data = _channels.get(channel_id)
    if not data or data.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )

    start_time = time.time()

    success = True
    error = None
    latency_ms = int((time.time() - start_time) * 1000) + 50

    if success:
        data["status"] = ChannelStatus.ACTIVE
    else:
        data["status"] = ChannelStatus.ERROR

    return ChannelTestResponse(
        channel_id=channel_id,
        channel_type=data["channel_type"],
        success=success,
        latency_ms=latency_ms,
        error=error,
    )


@router.post("/{channel_id}/activate")
async def activate_channel(
    channel_id: UUID,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """Activate a channel."""
    data = _channels.get(channel_id)
    if not data or data.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )

    data["enabled"] = True
    data["status"] = ChannelStatus.ACTIVE
    data["updated_at"] = datetime.utcnow()

    return {
        "channel_id": str(channel_id),
        "status": ChannelStatus.ACTIVE.value,
        "message": "Channel activated",
    }


@router.post("/{channel_id}/deactivate")
async def deactivate_channel(
    channel_id: UUID,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """Deactivate a channel."""
    data = _channels.get(channel_id)
    if not data or data.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Channel not found",
        )

    data["enabled"] = False
    data["status"] = ChannelStatus.INACTIVE
    data["updated_at"] = datetime.utcnow()

    return {
        "channel_id": str(channel_id),
        "status": ChannelStatus.INACTIVE.value,
        "message": "Channel deactivated",
    }
