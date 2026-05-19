"""Heavy v1/v2 API routers mounted after the first HTTP readiness yield.

Importing workflow/canvas/extensions/… pulls large dependency graphs. These
routes are registered from :func:`mount_deferred_routers` during post-startup
warmup (see ``leagent.main``).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import APIRouter

logger = logging.getLogger(__name__)


def mount_v1_deferred_routes(v1_router: APIRouter) -> None:
    """Mount non-critical v1 routers (canvas, workflow, documents, …)."""
    # Idempotent per router instance — do not use a process-global flag or a
    # second ``APIRouter(prefix="/api/v1")`` (e.g. in tests) would stay empty.
    if getattr(v1_router, "_leagent_deferred_v1_mounted", False):
        return
    setattr(v1_router, "_leagent_deferred_v1_mounted", True)

    # Canvas (hosted HTML / gen-ui preview)
    try:
        from leagent.api.v1 import canvas as v1_canvas

        v1_router.include_router(v1_canvas.router, prefix="/canvas", tags=["v1-canvas"])
    except ImportError:
        pass

    # Tasks
    try:
        from leagent.api.v1 import tasks as v1_tasks

        v1_router.include_router(v1_tasks.router, prefix="/tasks", tags=["v1-tasks"])
    except ImportError:
        pass

    # Workflow engine
    try:
        from leagent.workflow.server import router as workflow_router

        v1_router.include_router(workflow_router, tags=["v1-workflow"])
    except ImportError:
        pass

    # Documents
    try:
        from leagent.api.v1 import documents as v1_documents

        v1_router.include_router(v1_documents.router, prefix="/documents", tags=["v1-documents"])
    except ImportError:
        pass

    # Admin: task monitoring
    try:
        from leagent.api.v1.admin import tasks as v1_admin_tasks

        v1_router.include_router(
            v1_admin_tasks.router,
            prefix="/admin/tasks",
            tags=["v1-admin-tasks"],
        )
    except ImportError:
        pass

    # Files
    try:
        from leagent.api.v1 import files as v1_files

        v1_router.include_router(v1_files.router, prefix="/files", tags=["v1-files"])
    except ImportError:
        pass

    # Streams
    try:
        from leagent.api.v1 import streams as v1_streams

        v1_router.include_router(v1_streams.router, prefix="/streams", tags=["v1-streams"])
    except ImportError:
        pass

    # Folders
    try:
        from leagent.api.v1 import folders as v1_folders

        v1_router.include_router(v1_folders.router, prefix="/folders", tags=["v1-folders"])
    except ImportError:
        pass

    # Coding projects
    try:
        from leagent.api.v1 import coding_projects as v1_coding_projects

        v1_router.include_router(
            v1_coding_projects.router,
            prefix="/coding-projects",
            tags=["v1-coding-projects"],
        )
    except ImportError:
        pass

    # Pet Space
    try:
        from leagent.api.v1 import pet_space as v1_pet_space

        v1_router.include_router(
            v1_pet_space.router, prefix="/pet-space", tags=["v1-pet-space"]
        )
    except ImportError:
        pass

    # Folder Items
    try:
        from leagent.api.v1 import folder_items as v1_folder_items

        v1_router.include_router(
            v1_folder_items.router, prefix="/folder-items", tags=["v1-folder-items"]
        )
    except ImportError:
        pass

    # MCP
    try:
        from leagent.api.v1 import mcp as v1_mcp

        v1_router.include_router(v1_mcp.router, prefix="/mcp", tags=["v1-mcp"])
    except ImportError:
        pass

    # Extensions
    try:
        from leagent.api.v1 import extensions as v1_extensions

        v1_router.include_router(
            v1_extensions.router, prefix="/extensions", tags=["v1-extensions"]
        )
    except ImportError:
        pass

    # Python environment (pip / uv)
    try:
        from leagent.api.v1 import python_env as v1_python_env

        v1_router.include_router(
            v1_python_env.router, prefix="/python-env", tags=["v1-python-env"]
        )
    except ImportError:
        pass

    # ~/.leagent/.env token keys (GitHub, LLM env aliases)
    try:
        from leagent.api.v1 import settings_tokens as v1_settings_tokens

        v1_router.include_router(
            v1_settings_tokens.router, prefix="/settings", tags=["v1-settings-tokens"]
        )
    except ImportError:
        pass

    try:
        from leagent.api.v1 import settings_mail as v1_settings_mail

        v1_router.include_router(
            v1_settings_mail.router, prefix="/settings", tags=["v1-settings-mail"]
        )
    except ImportError:
        pass

    # Skills HTTP
    try:
        from leagent.api.v1 import skills as v1_skills

        v1_router.include_router(v1_skills.router, prefix="/skills", tags=["v1-skills"])
    except ImportError:
        pass

    # Channels
    try:
        from leagent.api.v1 import channels as v1_channels

        v1_router.include_router(v1_channels.router, prefix="/channels", tags=["v1-channels"])
    except ImportError:
        pass

    # Templates
    try:
        from leagent.api.v1 import templates as v1_templates

        v1_router.include_router(v1_templates.router, prefix="/templates", tags=["v1-templates"])
    except ImportError:
        pass

    # Cron
    try:
        from leagent.api.v1 import cron as v1_cron

        v1_router.include_router(v1_cron.router, prefix="/cron", tags=["v1-cron"])
    except ImportError:
        pass

    # Webhooks
    try:
        from leagent.api.v1 import webhooks as v1_webhooks

        v1_router.include_router(v1_webhooks.router, prefix="/webhooks", tags=["v1-webhooks"])
    except ImportError:
        pass

    # Metrics
    try:
        from leagent.api.v1 import metrics as v1_metrics

        v1_router.include_router(v1_metrics.router, prefix="/metrics", tags=["v1-metrics"])
    except ImportError:
        pass

    # Stats
    try:
        from leagent.api.v1 import stats as v1_stats

        v1_router.include_router(v1_stats.router, prefix="/stats", tags=["v1-stats"])
    except ImportError:
        pass

    # Activities
    try:
        from leagent.api.v1 import activities as v1_activities

        v1_router.include_router(
            v1_activities.router, prefix="/activities", tags=["v1-activities"]
        )
    except ImportError:
        pass

    logger.info("Deferred v1 API routers mounted")


def mount_v2_deferred_routes(v2_router: APIRouter) -> None:
    """Mount v2 routers (chat, agents)."""
    if getattr(v2_router, "_leagent_deferred_v2_mounted", False):
        return
    setattr(v2_router, "_leagent_deferred_v2_mounted", True)

    try:
        from leagent.api.v2 import chat as v2_chat

        v2_router.include_router(v2_chat.router, prefix="/chat", tags=["v2-chat"])
    except ImportError:
        pass

    try:
        from leagent.api.v2 import agents as v2_agents

        v2_router.include_router(v2_agents.router, prefix="/agents", tags=["v2-agents"])
    except ImportError:
        pass

    logger.info("Deferred v2 API routers mounted")
