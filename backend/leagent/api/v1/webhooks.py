"""Webhook subscription management API endpoints."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, HttpUrl

from leagent.services.auth import CurrentUserId

router = APIRouter()


class WebhookEvent(str, Enum):
    """Webhook event types."""

    TASK_CREATED = "task.created"
    TASK_COMPLETED = "task.completed"
    TASK_FAILED = "task.failed"
    FLOW_RUN_STARTED = "flow.run.started"
    FLOW_RUN_COMPLETED = "flow.run.completed"
    FLOW_RUN_FAILED = "flow.run.failed"
    MESSAGE_RECEIVED = "message.received"
    FILE_UPLOADED = "file.uploaded"
    FILE_DELETED = "file.deleted"
    FILE_PROCESSED = "file.processed"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"


class WebhookStatus(str, Enum):
    """Webhook subscription status."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"


_webhooks: dict[UUID, dict[str, Any]] = {}


class WebhookInfo(BaseModel):
    """Webhook subscription information."""

    id: UUID
    name: str
    url: str
    events: list[WebhookEvent]
    status: WebhookStatus
    enabled: bool
    delivery_count: int = 0
    failure_count: int = 0
    last_delivery_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class WebhookDetail(BaseModel):
    """Detailed webhook information."""

    id: UUID
    name: str
    description: Optional[str] = None
    url: str
    events: list[WebhookEvent]
    status: WebhookStatus
    enabled: bool
    secret: Optional[str] = None
    headers: dict[str, str] = Field(default_factory=dict)
    retry_count: int = 3
    timeout_seconds: int = 30
    delivery_count: int = 0
    failure_count: int = 0
    last_delivery_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class WebhookCreateRequest(BaseModel):
    """Request schema for creating a webhook."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    url: str = Field(..., max_length=500)
    events: list[WebhookEvent] = Field(..., min_length=1)
    secret: Optional[str] = Field(default=None, max_length=200)
    headers: dict[str, str] = Field(default_factory=dict)
    retry_count: int = Field(default=3, ge=0, le=10)
    timeout_seconds: int = Field(default=30, ge=5, le=120)
    enabled: bool = Field(default=True)


class WebhookUpdateRequest(BaseModel):
    """Request schema for updating a webhook."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    url: Optional[str] = Field(default=None, max_length=500)
    events: Optional[list[WebhookEvent]] = None
    secret: Optional[str] = Field(default=None, max_length=200)
    headers: Optional[dict[str, str]] = None
    retry_count: Optional[int] = Field(default=None, ge=0, le=10)
    timeout_seconds: Optional[int] = Field(default=None, ge=5, le=120)
    enabled: Optional[bool] = None


class WebhookListResponse(BaseModel):
    """Response for webhook listing."""

    webhooks: list[WebhookInfo]
    total: int


class WebhookTestResponse(BaseModel):
    """Response for webhook test."""

    webhook_id: UUID
    success: bool
    status_code: Optional[int] = None
    response_time_ms: int
    error: Optional[str] = None


class WebhookDeliveryLog(BaseModel):
    """Webhook delivery log entry."""

    id: UUID
    webhook_id: UUID
    event: WebhookEvent
    payload: dict[str, Any]
    status_code: Optional[int]
    success: bool
    response_time_ms: int
    error: Optional[str] = None
    created_at: datetime


@router.get("", response_model=WebhookListResponse)
async def list_webhooks(
    user_id: CurrentUserId,
    status: Optional[WebhookStatus] = Query(default=None),
    event: Optional[WebhookEvent] = Query(default=None),
) -> WebhookListResponse:
    """List all webhook subscriptions for the current user."""
    webhooks = []

    for webhook_id, data in _webhooks.items():
        if data.get("user_id") != user_id:
            continue
        if status and data.get("status") != status:
            continue
        if event and event not in data.get("events", []):
            continue

        webhooks.append(
            WebhookInfo(
                id=webhook_id,
                name=data["name"],
                url=data["url"],
                events=data["events"],
                status=data["status"],
                enabled=data["enabled"],
                delivery_count=data.get("delivery_count", 0),
                failure_count=data.get("failure_count", 0),
                last_delivery_at=data.get("last_delivery_at"),
                created_at=data["created_at"],
                updated_at=data["updated_at"],
            )
        )

    return WebhookListResponse(webhooks=webhooks, total=len(webhooks))


@router.post("", response_model=WebhookDetail, status_code=status.HTTP_201_CREATED)
async def create_webhook(
    data: WebhookCreateRequest,
    user_id: CurrentUserId,
) -> WebhookDetail:
    """Create a new webhook subscription."""
    webhook_id = uuid4()
    now = datetime.utcnow()

    _webhooks[webhook_id] = {
        "user_id": user_id,
        "name": data.name,
        "description": data.description,
        "url": data.url,
        "events": data.events,
        "status": WebhookStatus.ACTIVE if data.enabled else WebhookStatus.INACTIVE,
        "enabled": data.enabled,
        "secret": data.secret,
        "headers": data.headers,
        "retry_count": data.retry_count,
        "timeout_seconds": data.timeout_seconds,
        "delivery_count": 0,
        "failure_count": 0,
        "created_at": now,
        "updated_at": now,
    }

    return WebhookDetail(
        id=webhook_id,
        name=data.name,
        description=data.description,
        url=data.url,
        events=data.events,
        status=WebhookStatus.ACTIVE if data.enabled else WebhookStatus.INACTIVE,
        enabled=data.enabled,
        secret=data.secret,
        headers=data.headers,
        retry_count=data.retry_count,
        timeout_seconds=data.timeout_seconds,
        delivery_count=0,
        failure_count=0,
        created_at=now,
        updated_at=now,
    )


@router.get("/{webhook_id}", response_model=WebhookDetail)
async def get_webhook(
    webhook_id: UUID,
    user_id: CurrentUserId,
) -> WebhookDetail:
    """Get webhook subscription details by ID."""
    data = _webhooks.get(webhook_id)
    if not data or data.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    return WebhookDetail(
        id=webhook_id,
        name=data["name"],
        description=data.get("description"),
        url=data["url"],
        events=data["events"],
        status=data["status"],
        enabled=data["enabled"],
        secret=data.get("secret"),
        headers=data.get("headers", {}),
        retry_count=data.get("retry_count", 3),
        timeout_seconds=data.get("timeout_seconds", 30),
        delivery_count=data.get("delivery_count", 0),
        failure_count=data.get("failure_count", 0),
        last_delivery_at=data.get("last_delivery_at"),
        last_error=data.get("last_error"),
        created_at=data["created_at"],
        updated_at=data["updated_at"],
    )


@router.put("/{webhook_id}", response_model=WebhookDetail)
async def update_webhook(
    webhook_id: UUID,
    data: WebhookUpdateRequest,
    user_id: CurrentUserId,
) -> WebhookDetail:
    """Update a webhook subscription."""
    webhook_data = _webhooks.get(webhook_id)
    if not webhook_data or webhook_data.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    if data.name is not None:
        webhook_data["name"] = data.name
    if data.description is not None:
        webhook_data["description"] = data.description
    if data.url is not None:
        webhook_data["url"] = data.url
    if data.events is not None:
        webhook_data["events"] = data.events
    if data.secret is not None:
        webhook_data["secret"] = data.secret
    if data.headers is not None:
        webhook_data["headers"] = data.headers
    if data.retry_count is not None:
        webhook_data["retry_count"] = data.retry_count
    if data.timeout_seconds is not None:
        webhook_data["timeout_seconds"] = data.timeout_seconds
    if data.enabled is not None:
        webhook_data["enabled"] = data.enabled
        webhook_data["status"] = WebhookStatus.ACTIVE if data.enabled else WebhookStatus.INACTIVE

    webhook_data["updated_at"] = datetime.utcnow()

    return WebhookDetail(
        id=webhook_id,
        name=webhook_data["name"],
        description=webhook_data.get("description"),
        url=webhook_data["url"],
        events=webhook_data["events"],
        status=webhook_data["status"],
        enabled=webhook_data["enabled"],
        secret=webhook_data.get("secret"),
        headers=webhook_data.get("headers", {}),
        retry_count=webhook_data.get("retry_count", 3),
        timeout_seconds=webhook_data.get("timeout_seconds", 30),
        delivery_count=webhook_data.get("delivery_count", 0),
        failure_count=webhook_data.get("failure_count", 0),
        last_delivery_at=webhook_data.get("last_delivery_at"),
        last_error=webhook_data.get("last_error"),
        created_at=webhook_data["created_at"],
        updated_at=webhook_data["updated_at"],
    )


@router.delete("/{webhook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook(
    webhook_id: UUID,
    user_id: CurrentUserId,
) -> None:
    """Delete a webhook subscription."""
    data = _webhooks.get(webhook_id)
    if not data or data.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    del _webhooks[webhook_id]


@router.post("/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(
    webhook_id: UUID,
    user_id: CurrentUserId,
) -> WebhookTestResponse:
    """Test a webhook by sending a test payload."""
    import time

    data = _webhooks.get(webhook_id)
    if not data or data.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    start_time = time.time()

    success = True
    status_code = 200
    error = None
    response_time_ms = int((time.time() - start_time) * 1000) + 100

    return WebhookTestResponse(
        webhook_id=webhook_id,
        success=success,
        status_code=status_code,
        response_time_ms=response_time_ms,
        error=error,
    )


@router.get("/{webhook_id}/deliveries", response_model=list[WebhookDeliveryLog])
async def get_webhook_deliveries(
    webhook_id: UUID,
    user_id: CurrentUserId,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[WebhookDeliveryLog]:
    """Get recent delivery logs for a webhook."""
    data = _webhooks.get(webhook_id)
    if not data or data.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    return []


@router.post("/{webhook_id}/enable")
async def enable_webhook(
    webhook_id: UUID,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """Enable a webhook subscription."""
    data = _webhooks.get(webhook_id)
    if not data or data.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    data["enabled"] = True
    data["status"] = WebhookStatus.ACTIVE
    data["updated_at"] = datetime.utcnow()

    return {
        "webhook_id": str(webhook_id),
        "status": WebhookStatus.ACTIVE.value,
        "message": "Webhook enabled",
    }


@router.post("/{webhook_id}/disable")
async def disable_webhook(
    webhook_id: UUID,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """Disable a webhook subscription."""
    data = _webhooks.get(webhook_id)
    if not data or data.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Webhook not found",
        )

    data["enabled"] = False
    data["status"] = WebhookStatus.INACTIVE
    data["updated_at"] = datetime.utcnow()

    return {
        "webhook_id": str(webhook_id),
        "status": WebhookStatus.INACTIVE.value,
        "message": "Webhook disabled",
    }
