"""Cron scheduling tools for the agent."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from leagent.cron.base import CronJob, CronJobStatus, CronJobType
from leagent.services.service_manager import get_service_manager
from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


def _job_summary(job: CronJob) -> dict[str, Any]:
    return {
        "id": str(job.id),
        "name": job.name,
        "description": job.description,
        "schedule": job.schedule,
        "target_type": job.target_type.value,
        "target_id": job.target_id,
        "workflow_id": job.workflow_id,
        "enabled": job.enabled,
        "status": job.status.value,
        "payload": job.payload,
        "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
        "next_run_at": job.next_run_at.isoformat() if job.next_run_at else None,
        "run_count": job.run_count,
        "user_id": job.user_id,
    }


class CronCreateTool(BaseTool):
    name = "cron_create"
    description = (
        "Create a scheduled cron job with a cron expression, target type, and optional payload."
    )
    category = ToolCategory.UTIL
    is_read_only = False
    is_concurrency_safe = False
    aliases = ["schedule", "create_cron", "add_cron"]
    search_hint = "cron schedule create job task timer recurring"
    interrupt_behavior = "block"
    max_result_size_chars = 50_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Creating cron job"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Display name for the job"},
                "schedule": {
                    "type": "string",
                    "description": "Cron expression (5 or 6 fields)",
                },
                "target_type": {
                    "type": "string",
                    "enum": ["workflow", "task", "webhook", "script"],
                    "description": "What the schedule invokes",
                },
                "target_id": {
                    "type": "string",
                    "description": "Target identifier (workflow id, task id, URL, script id, etc.)",
                },
                "description": {"type": "string", "description": "Optional longer description"},
                "payload": {"type": "object", "description": "Optional JSON payload for the target"},
                "enabled": {
                    "type": "boolean",
                    "default": True,
                    "description": "Whether the job is enabled when created",
                },
            },
            "required": ["name", "schedule", "target_type"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        try:
            sm = get_service_manager()
            cron = sm.cron
            if cron is None:
                return {"error": "Cron service unavailable"}

            target_type = CronJobType(params["target_type"])
            payload = params.get("payload")
            if payload is not None and not isinstance(payload, dict):
                return {"error": "payload must be an object"}
            payload = payload or {}

            enabled = params.get("enabled", True)
            status = CronJobStatus.ACTIVE if enabled else CronJobStatus.DISABLED

            job = CronJob(
                name=params["name"],
                schedule=params["schedule"],
                target_type=target_type,
                target_id=params.get("target_id"),
                description=params.get("description") or "",
                payload=payload,
                enabled=enabled,
                status=status,
                user_id=context.user_id or None,
            )

            added = await cron.add_job(job)
            logger.info("cron_tool_create", job_id=str(added.id), name=added.name)
            return {"job": added.to_dict()}
        except Exception as e:
            logger.error("cron_create_failed", error=str(e))
            return {"error": str(e)}


class CronDeleteTool(BaseTool):
    name = "cron_delete"
    description = "Remove a cron job by its UUID."
    category = ToolCategory.UTIL
    is_read_only = False
    is_destructive = True
    is_concurrency_safe = False
    aliases = ["remove_cron", "delete_cron", "unschedule"]
    search_hint = "cron delete remove job unschedule"
    interrupt_behavior = "block"
    max_result_size_chars = 50_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Deleting cron job"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "job_id": {
                    "type": "string",
                    "description": "UUID of the cron job to remove",
                },
            },
            "required": ["job_id"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        try:
            sm = get_service_manager()
            cron = sm.cron
            if cron is None:
                return {"error": "Cron service unavailable"}

            try:
                job_uuid = UUID(params["job_id"])
            except ValueError:
                return {"error": "job_id must be a valid UUID"}

            removed = await cron.remove_job(job_uuid)
            logger.info("cron_tool_delete", job_id=params["job_id"], removed=removed)
            return {"removed": removed, "job_id": params["job_id"]}
        except Exception as e:
            logger.error("cron_delete_failed", error=str(e))
            return {"error": str(e)}


class CronListTool(BaseTool):
    name = "cron_list"
    description = "List cron jobs, optionally filtered by status and enabled flag."
    category = ToolCategory.UTIL
    is_read_only = True
    is_concurrency_safe = True
    aliases = ["list_crons", "show_crons"]
    search_hint = "cron list show jobs scheduled tasks"
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Listing cron jobs"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["active", "paused", "running", "failed", "disabled"],
                    "description": "Filter by job status",
                },
                "enabled": {
                    "type": "boolean",
                    "description": "Filter by enabled flag",
                },
            },
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        try:
            sm = get_service_manager()
            cron = sm.cron
            if cron is None:
                return {"error": "Cron service unavailable"}

            status_raw = params.get("status")
            status_filter: CronJobStatus | None = None
            if status_raw is not None:
                status_filter = CronJobStatus(status_raw)

            enabled_filter = params.get("enabled")
            if enabled_filter is not None and not isinstance(enabled_filter, bool):
                return {"error": "enabled must be a boolean when provided"}

            jobs = cron.list_jobs(status_filter, enabled_filter)
            return {"jobs": [_job_summary(j) for j in jobs], "count": len(jobs)}
        except Exception as e:
            logger.error("cron_list_failed", error=str(e))
            return {"error": str(e)}
