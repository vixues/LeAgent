"""Agent tool: inspect then apply settings (env secrets, MCP, channels)."""

from __future__ import annotations

from typing import Any

import structlog

from leagent.services.settings_configure import apply_changes, inspect_changes
from leagent.services.settings_plan import get_settings_plan_registry, hash_changes
from leagent.tools.base import BaseTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class ConfigureSettingsTool(BaseTool):
    """Propose and apply allowlisted settings after user confirmation."""

    name = "configure_settings"
    description = (
        "Inspect or apply LeAgent settings from structured changes: env secrets "
        "(~/.leagent/.env allowlist), MCP servers, and outbound channels (config.yaml). "
        "ALWAYS call action=inspect first; show the redacted summary to the user via "
        "ask_user (permission UI); only after they allow, call action=apply with the "
        "returned plan_id. Never echo full secrets. Do not use config_file on .env."
    )
    category = ToolCategory.INTEGRATION
    version = "1.0.0"
    timeout_sec = 30
    is_read_only = False
    is_concurrency_safe = False
    interrupt_behavior = "block"
    search_hint = (
        "configure settings api key secret smtp mcp channel dingtalk feishu "
        "webhook env WEB_SEARCH Bing DeepSeek setup"
    )
    aliases = ["settings_configure", "setup_settings"]

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "required": ["action"],
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["inspect", "apply"],
                    "description": "inspect: validate + redacted plan; apply: write using plan_id.",
                },
                "plan_id": {
                    "type": "string",
                    "description": "Required for apply; returned by a prior inspect in this session.",
                },
                "changes": {
                    "type": "array",
                    "description": (
                        "Required for inspect. Items: "
                        "{kind:env, key, value} | "
                        "{kind:mcp, name, transport, command?, args?, url?, env?, remove?} | "
                        "{kind:channel, name, enabled?, config:{endpoint?,token?,webhook_url?}}"
                    ),
                    "items": {"type": "object"},
                },
            },
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        action = (params or {}).get("action") or "inspect"
        return f"Configuring settings ({action})"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> Any:
        action = str(params.get("action") or "").strip().lower()
        if action not in ("inspect", "apply"):
            return {"ok": False, "error": "action must be inspect|apply"}

        session_id = str(getattr(context, "session_id", "") or "")
        registry = get_settings_plan_registry()

        if action == "inspect":
            raw_changes = params.get("changes")
            if not isinstance(raw_changes, list) or not raw_changes:
                return {"ok": False, "error": "inspect requires a non-empty changes array"}

            insp = inspect_changes(raw_changes)
            if not insp.ok:
                return {
                    "ok": False,
                    "errors": insp.errors,
                    "summary": [],
                    "next_step": "Fix the listed errors and call inspect again.",
                }

            plan = registry.create(session_id=session_id, changes=insp.normalized_changes)
            summary = [
                {
                    "kind": s.kind,
                    "target": s.target,
                    "action": s.action,
                    "preview": s.preview,
                    **({"detail": s.detail} if s.detail else {}),
                }
                for s in insp.summary
            ]
            logger.info(
                "configure_settings_inspect",
                plan_id=plan.plan_id,
                count=len(summary),
                kinds=[s.kind for s in insp.summary],
            )
            return {
                "ok": True,
                "plan_id": plan.plan_id,
                "summary": summary,
                "warnings": insp.warnings,
                "already_set": insp.already_set,
                "verify_next": insp.verify_next,
                "next_step": (
                    "Show the summary to the user with ask_user "
                    "(ui_variant=permission, permission_kind=tool_run). "
                    "If they allow, call configure_settings with action=apply and this plan_id "
                    "(do not re-send secret values)."
                ),
            }

        # apply
        plan_id = str(params.get("plan_id") or "").strip()
        if not plan_id:
            return {
                "ok": False,
                "error": "apply requires plan_id from a prior inspect",
                "next_step": "Call action=inspect first, then ask_user, then apply.",
            }

        plan = registry.get(plan_id)
        if plan is None:
            return {
                "ok": False,
                "error": "plan_id not found or expired (TTL ~10 minutes)",
                "next_step": "Re-run action=inspect with the same changes, then ask_user again.",
            }

        if plan.session_id and session_id and plan.session_id != session_id:
            return {
                "ok": False,
                "error": "plan_id belongs to a different session",
                "next_step": "Re-run inspect in this chat session.",
            }

        # Optional: if caller re-sends changes, they must match the plan hash.
        extra = params.get("changes")
        if isinstance(extra, list) and extra:
            insp2 = inspect_changes(extra)
            candidate = insp2.normalized_changes if insp2.ok else extra
            if hash_changes(candidate) != plan.changes_hash:
                return {
                    "ok": False,
                    "error": "changes do not match the inspected plan; refuse apply to prevent tampering",
                    "next_step": "Call inspect again and use the new plan_id after user confirmation.",
                }

        plan = registry.consume(plan_id)
        if plan is None:
            return {"ok": False, "error": "plan_id not found or expired"}

        applied = await apply_changes(plan.changes)
        if not applied.ok:
            logger.warning("configure_settings_apply_failed", errors=applied.errors)
            return {
                "ok": False,
                "errors": applied.errors,
                "next_step": "Fix errors and run inspect → ask_user → apply again.",
            }

        logger.info(
            "configure_settings_applied",
            plan_id=plan_id,
            updated=applied.updated,
            targets=applied.applied,
        )
        return {
            "ok": True,
            "updated": applied.updated,
            "applied": applied.applied,
            "verify_next": applied.verify_next,
            "next_step": (
                "Confirm success to the user without repeating secret values. "
                "Optionally follow verify_next hints."
            ),
        }
