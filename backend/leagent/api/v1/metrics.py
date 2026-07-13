"""Prometheus metrics endpoint for LeAgent.

Exposes application metrics in Prometheus text format for scraping.
When auth is enforced and diagnostic gating is on, requires a bearer token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from leagent.config.settings import get_settings
from leagent.services.auth.policy import effective_enforce_auth
from leagent.utils.metrics import get_metrics

router = APIRouter()


async def _require_metrics_access(request: Request) -> None:
    settings = get_settings()
    if not (effective_enforce_auth(settings) and settings.security.gate_diagnostics):
        return
    header = request.headers.get("authorization") or ""
    if not header.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = header[7:].strip()
    from leagent.services.auth.service import get_auth_service

    if get_auth_service().verify_access_token(token) is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.get(
    "",
    summary="Prometheus Metrics",
    description="Returns application metrics in Prometheus text exposition format.",
    response_class=Response,
    responses={
        200: {
            "description": "Prometheus metrics in text format",
            "content": {"text/plain": {}},
        }
    },
    dependencies=[Depends(_require_metrics_access)],
)
async def get_prometheus_metrics() -> Response:
    """Return Prometheus metrics in text exposition format."""
    metrics = get_metrics()
    content = metrics.generate_metrics()
    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get(
    "/health",
    summary="Metrics Health",
    description="Health check for the metrics subsystem.",
    responses={
        200: {"description": "Metrics subsystem is healthy"},
    },
)
async def metrics_health() -> dict[str, str]:
    """Health check for metrics endpoint."""
    get_metrics()
    return {
        "status": "healthy",
        "metrics_available": "true",
    }
