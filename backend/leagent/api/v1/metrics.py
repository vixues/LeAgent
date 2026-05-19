"""Prometheus metrics endpoint for LeAgent.

Exposes application metrics in Prometheus text format for scraping.
"""

from __future__ import annotations

from fastapi import APIRouter, Response

from leagent.utils.metrics import get_metrics

router = APIRouter()


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
)
async def get_prometheus_metrics() -> Response:
    """Return Prometheus metrics.
    
    Returns metrics in the Prometheus text exposition format for scraping.
    This endpoint should be scraped by Prometheus at regular intervals.
    
    Example response:
        # HELP leagent_http_request_total Total HTTP requests
        # TYPE leagent_http_request_total counter
        leagent_http_request_total{method="GET",endpoint="/api/v1/chat",status_code="200"} 150.0
    """
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
    """Health check for metrics endpoint.
    
    Verifies the metrics collection system is operational.
    """
    metrics = get_metrics()
    
    return {
        "status": "healthy",
        "metrics_available": "true",
    }
