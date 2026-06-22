"""Central API router that aggregates all versioned sub-routers.

Every router is registered eagerly here (no deferred post-startup mounting).
Imports are performed lazily per-router via :func:`importlib.import_module` so a
single broken optional router cannot block the rest, and any failure is *logged*
(not silently swallowed). Heavy runtime *initialization* still happens in the
app lifespan — only route registration is eager.
"""

from __future__ import annotations

import importlib
import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

api_router = APIRouter()

v1_router = APIRouter(prefix="/v1")


def _include(
    parent: APIRouter,
    import_path: str,
    *,
    attr: str = "router",
    prefix: str | None = None,
    tags: list[str] | None = None,
) -> None:
    """Import *import_path* and mount its router attribute onto *parent*.

    Failures (missing optional deps, import errors) are logged and skipped so
    one bad router never blocks the others.
    """
    try:
        module = importlib.import_module(import_path)
        sub = getattr(module, attr)
    except Exception:  # noqa: BLE001 - log and continue; never break ingress
        logger.warning("Router not mounted: %s", import_path, exc_info=True)
        return
    kwargs: dict[str, object] = {}
    if prefix:
        kwargs["prefix"] = prefix
    if tags:
        kwargs["tags"] = tags
    parent.include_router(sub, **kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# v1 sub-routers (resource-scoped)
# ---------------------------------------------------------------------------

_include(v1_router, "leagent.api.v1.meta", prefix="/meta", tags=["v1-meta"])
_include(v1_router, "leagent.api.v1.health", prefix="/health", tags=["v1-health"])
_include(v1_router, "leagent.api.v1.chat", prefix="/chat", tags=["v1-chat"])
_include(
    v1_router,
    "leagent.api.v1.chat_projects",
    prefix="/chat-projects",
    tags=["v1-chat-projects"],
)
_include(v1_router, "leagent.api.v1.tools", prefix="/tools", tags=["v1-tools"])
_include(v1_router, "leagent.api.v1.rules", prefix="/rules", tags=["v1-rules"])
_include(v1_router, "leagent.api.v1.models", prefix="/models", tags=["v1-models"])
_include(
    v1_router,
    "leagent.api.v1.image_gen",
    prefix="/models/image-gen",
    tags=["v1-image-gen"],
)
_include(v1_router, "leagent.api.v1.canvas", prefix="/canvas", tags=["v1-canvas"])
_include(v1_router, "leagent.api.v1.tasks", prefix="/tasks", tags=["v1-tasks"])
_include(v1_router, "leagent.workflow.server", tags=["v1-workflow"])
_include(v1_router, "leagent.api.v1.documents", prefix="/documents", tags=["v1-documents"])
_include(
    v1_router,
    "leagent.api.v1.admin.tasks",
    prefix="/admin/tasks",
    tags=["v1-admin-tasks"],
)
_include(v1_router, "leagent.api.v1.files", prefix="/files", tags=["v1-files"])
_include(v1_router, "leagent.api.v1.pdf_research", prefix="/pdf", tags=["v1-pdf"])
_include(v1_router, "leagent.api.v1.streams", prefix="/streams", tags=["v1-streams"])
_include(v1_router, "leagent.api.v1.folders", prefix="/folders", tags=["v1-folders"])
_include(
    v1_router,
    "leagent.api.v1.coding_projects",
    prefix="/coding-projects",
    tags=["v1-coding-projects"],
)
_include(v1_router, "leagent.api.v1.pet_space", prefix="/pet-space", tags=["v1-pet-space"])
_include(
    v1_router,
    "leagent.api.v1.folder_items",
    prefix="/folder-items",
    tags=["v1-folder-items"],
)
_include(v1_router, "leagent.api.v1.mcp", prefix="/mcp", tags=["v1-mcp"])
_include(v1_router, "leagent.api.v1.extensions", prefix="/extensions", tags=["v1-extensions"])
_include(
    v1_router,
    "leagent.api.v1.python_env",
    prefix="/python-env",
    tags=["v1-python-env"],
)
_include(
    v1_router,
    "leagent.api.v1.settings_tokens",
    prefix="/settings",
    tags=["v1-settings-tokens"],
)
_include(
    v1_router,
    "leagent.api.v1.settings_mail",
    prefix="/settings",
    tags=["v1-settings-mail"],
)
_include(v1_router, "leagent.api.v1.skills", prefix="/skills", tags=["v1-skills"])
_include(v1_router, "leagent.api.v1.channels", prefix="/channels", tags=["v1-channels"])
_include(v1_router, "leagent.api.v1.templates", prefix="/templates", tags=["v1-templates"])
_include(v1_router, "leagent.api.v1.workflow_assets", prefix="/workflow", tags=["v1-workflow-assets"])
_include(v1_router, "leagent.api.v1.cron", prefix="/cron", tags=["v1-cron"])
_include(v1_router, "leagent.api.v1.webhooks", prefix="/webhooks", tags=["v1-webhooks"])
_include(v1_router, "leagent.api.v1.metrics", prefix="/metrics", tags=["v1-metrics"])
_include(v1_router, "leagent.api.v1.stats", prefix="/stats", tags=["v1-stats"])
_include(v1_router, "leagent.api.v1.activities", prefix="/activities", tags=["v1-activities"])

# ---------------------------------------------------------------------------
# Mount versioned routers. There is no ``v2`` surface — it was nominal (empty)
# so it is intentionally not mounted (see the API-layer review §2.4).
# ---------------------------------------------------------------------------

api_router.include_router(v1_router)
