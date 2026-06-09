"""Health check API endpoints.

Public: ``GET /health`` (and ``/live``, ``/ready``, ``/startup``) for probes.
Admin-gated: ``/detailed``, ``/version``, ``/metrics`` — use
``PermissionChecker("admin:panel")``; not listed in ``PUBLIC_ROUTES`` in
``audit_router_auth.py`` (auth is detected on the route).
"""

from __future__ import annotations

import platform
import time
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from prometheus_client import REGISTRY
from pydantic import BaseModel, Field

from leagent import __version__ as leagent_version
from leagent.api.deps import get_service_manager
from leagent.config.settings import get_settings
from leagent.services.auth import PermissionChecker
from leagent.services.service_manager import ServiceManager
from leagent.utils.metrics import get_metrics

router = APIRouter()

_start_time = time.time()

_admin_panel = [Depends(PermissionChecker("admin:panel"))]


class HealthStatus(BaseModel):
    """Health status response."""

    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    uptime_seconds: int = 0


class DetailedHealthStatus(BaseModel):
    """Detailed health status with component checks."""

    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    uptime_seconds: int = 0
    components: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ReadinessStatus(BaseModel):
    """Readiness probe response."""

    ready: bool = True
    checks: dict[str, bool] = Field(default_factory=dict)


class LivenessStatus(BaseModel):
    """Liveness probe response."""

    alive: bool = True
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StartupStatus(BaseModel):
    """Application has finished lifespan startup (services initialised)."""

    started: bool = True


def _uptime_seconds() -> int:
    return int(time.time() - _start_time)


def _norm_component_status(svc: Any) -> str:
    if not isinstance(svc, dict):
        return "degraded"
    st = str(svc.get("status", "")).lower()
    if st in ("ok", "healthy", "running", "runnable"):
        return "healthy"
    if st in ("error", "unhealthy", "failed", "unavailable"):
        return "unhealthy"
    if st == "not_initialized":
        return "degraded"
    if "error" in svc and svc.get("error"):
        return "unhealthy"
    if svc.get("healthy") is False:
        return "unhealthy"
    if svc.get("healthy") is True:
        return "healthy"
    if st in ("degraded", "unknown"):
        return "degraded"
    if st:
        return "degraded"
    return "degraded"


def _overall_status(components: dict[str, dict[str, Any]]) -> str:
    norms = [_norm_component_status(c) for c in components.values()]
    if not norms:
        return "healthy"
    if all(n == "healthy" for n in norms):
        return "healthy"
    if all(n == "unhealthy" for n in norms):
        return "unhealthy"
    return "degraded"


def _prune_for_components(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    services = raw.get("services") or {}
    for name, svc in services.items():
        if not isinstance(svc, dict):
            out[name] = {"status": "degraded", "detail": str(svc)}
            continue
        comp = dict(svc)
        comp["status"] = _norm_component_status(svc)
        out[str(name)] = comp
    return out


def _registry_numeric_snapshot() -> dict[str, Any]:
    out: dict[str, Any] = {"uptime_seconds": _uptime_seconds()}
    try:
        get_metrics()  # ensure LeAgent metrics singleton is initialised
    except Exception:  # noqa: BLE001
        pass
    try:
        for family in REGISTRY.collect():
            if family.name == "leagent_http_request_total":
                out["http_requests_total"] = int(
                    sum(s.value for s in family.samples)
                )
            elif family.name == "leagent_active_chat_connections":
                out["active_chat_connections"] = int(
                    max((s.value for s in family.samples), default=0)
                )
    except Exception:  # noqa: BLE001
        pass
    if "http_requests_total" not in out:
        out["http_requests_total"] = 0
    if "active_chat_connections" not in out:
        out["active_chat_connections"] = 0
    return out


def _process_rss_mb() -> float:
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        ru = usage.ru_maxrss
        if ru <= 0:
            return 0.0
        # macOS: bytes; Linux: kilobytes
        if platform.system() == "Darwin":
            return round(ru / (1024 * 1024), 2)
        return round(ru / 1024, 2)
    except Exception:  # noqa: BLE001
        return 0.0


@router.get("", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """Basic health check endpoint (public)."""
    return HealthStatus(
        status="healthy",
        version=leagent_version,
        timestamp=datetime.utcnow(),
        uptime_seconds=_uptime_seconds(),
    )


@router.get(
    "/detailed",
    response_model=DetailedHealthStatus,
    dependencies=_admin_panel,
)
async def detailed_health_check(
    sm: Annotated[ServiceManager, Depends(get_service_manager)],
) -> DetailedHealthStatus:
    """Aggregated service health (admin)."""
    raw = await sm.health_check()
    components = _prune_for_components(raw)
    overall = _overall_status(components)
    if not components and not raw.get("healthy", True):
        overall = "unhealthy"
    return DetailedHealthStatus(
        status=overall,
        version=leagent_version,
        timestamp=datetime.utcnow(),
        uptime_seconds=_uptime_seconds(),
        components=components,
    )


@router.get("/ready", response_model=ReadinessStatus)
async def readiness_check(
    sm: Annotated[ServiceManager, Depends(get_service_manager)],
) -> ReadinessStatus:
    """Kubernetes readiness probe (public)."""
    checks: dict[str, bool] = {
        "database": sm.db is not None,
        "cache": sm.cache is not None,
        "services_started": sm.is_started,
        "migrations": sm.db is not None,
    }
    # Primary signal: startup completed. Individual checks are informational (optional subsystems).
    return ReadinessStatus(ready=sm.is_started, checks=checks)


@router.get("/live", response_model=LivenessStatus)
async def liveness_check() -> LivenessStatus:
    """Kubernetes liveness probe (public)."""
    return LivenessStatus(alive=True, timestamp=datetime.utcnow())


@router.get("/startup", response_model=StartupStatus)
async def startup_check(
    sm: Annotated[ServiceManager, Depends(get_service_manager)],
) -> StartupStatus:
    """Whether lifespan startup completed (public)."""
    return StartupStatus(started=sm.is_started)


@router.get("/version", dependencies=_admin_panel)
async def get_version() -> dict[str, str]:
    """Build and runtime version (admin)."""
    settings = get_settings()
    return {
        "version": leagent_version,
        "api_version": "v1",
        "build": settings.environment,
        "python_version": platform.python_version(),
    }


@router.get("/metrics", dependencies=_admin_panel)
async def get_health_metrics() -> dict[str, Any]:
    """Lightweight app metrics (admin); distinct from ``GET /api/v1/metrics`` (Prometheus)."""
    out = _registry_numeric_snapshot()
    out["process_rss_mb"] = _process_rss_mb()
    return out


@router.get("/memory", dependencies=_admin_panel)
async def memory_write_health(
    sm: Annotated[ServiceManager, Depends(get_service_manager)],
) -> dict[str, Any]:
    """Agent memory write path status (episode / fact / procedure)."""
    am = getattr(sm, "agent_memory", None)
    if am is None:
        return {"status": "not_initialized"}
    return {"status": "ok", **am.memory_write_status()}
