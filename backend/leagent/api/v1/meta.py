"""Runtime product metadata for SPA (edition, build, version).

Intentionally public so the login / setup screens can render product chrome
without a session. Sensitive diagnostics live under ``/metrics`` (gated).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from leagent import __version__ as leagent_version
from leagent.config.settings import get_settings

router = APIRouter()


class MetaResponse(BaseModel):
    app_name: str
    edition: str
    version: str
    desktop_mode: bool
    local_mode: bool
    build_git_sha: str
    build_time: str
    offline_registry_configured: bool = False


@router.get("", response_model=MetaResponse)
async def meta() -> MetaResponse:
    s = get_settings()
    return MetaResponse(
        app_name=s.app_name,
        edition=s.edition,
        version=leagent_version,
        desktop_mode=s.desktop_mode,
        local_mode=s.local_mode,
        build_git_sha=(s.build_git_sha or "").strip(),
        build_time=(s.build_time or "").strip(),
        offline_registry_configured=bool((s.license_offline_registry_path or "").strip()),
    )
