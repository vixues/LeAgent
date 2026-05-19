"""High-level OA adapter tool.

This tool provides a unified interface for interacting with OA systems
using either REST APIs (via `oa_api`) or browser/RPA automation
(`web_login` + `web_scraper` + `web_form_fill`), depending on configuration.

It is designed to match the `OAAdapter` abstraction described in docs/technical.md:

- Login to OA (API token or browser session)
- Fetch form data
- Submit/update forms
- Import reimbursement packages
- Export data files

The actual low-level operations are delegated to existing tools so that
workflows can call a single `oa_adapter` function instead of wiring
multiple OA tools manually.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from leagent.tools.base import BaseTool, ToolCategory, ToolContext


class OAAdapterMode(str, Enum):
    """Execution mode for OA adapter."""

    API = "api"
    RPA = "rpa"


class OAAdapterAction(str, Enum):
    """High-level OA operations supported by the adapter."""

    LOGIN = "login"
    GET_FORM = "get_form"
    SUBMIT_FORM = "submit_form"
    IMPORT_REIMBURSEMENT = "import_reimbursement"
    EXPORT_DATA = "export_data"


class OAAdapterTool(BaseTool):
    """Unified OA adapter wrapping `oa_api` and web/RPA tools.

    Typical usage from a workflow node:

        - id: import_reimbursement
          type: tool_call
          tool: oa_adapter
          params:
            mode: rpa
            action: import_reimbursement
            base_url: "{{ inputs.oa_base_url }}"
            login:
              credential_key: "oa_system"
            form:
              path: "/reimbursement/new"
              data: "{{ steps.assemble_payload.output }}"
    """

    name = "oa_adapter"
    description = (
        "High-level OA adapter that wraps oa_api and web/RPA tools to "
        "login, fetch forms, submit forms, import reimbursements, and export data."
    )
    category = ToolCategory.INTEGRATION
    version = "1.0.0"
    timeout_sec = 180
    max_retries = 1
    aliases = ["oa", "oa_workflow", "office_automation"]
    search_hint = "OA adapter login fetch forms submit reimbursement export import"
    is_concurrency_safe = False
    is_read_only = False
    interrupt_behavior = "block"
    max_result_size_chars = 100_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        op = (params or {}).get("operation", "")
        return f"OA operation{f': {op}' if op else ''}"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": [m.value for m in OAAdapterMode],
                    "description": "Execution mode: 'api' (REST) or 'rpa' (browser automation).",
                    "default": OAAdapterMode.API.value,
                },
                "action": {
                    "type": "string",
                    "enum": [a.value for a in OAAdapterAction],
                    "description": "High-level OA action to perform.",
                },
                "base_url": {
                    "type": "string",
                    "description": "Base URL of the OA system (both API and web).",
                },
                "login": {
                    "type": "object",
                    "description": "Login configuration (for RPA mode).",
                    "properties": {
                        "credential_key": {
                            "type": "string",
                            "description": "Key in credential vault for OA login.",
                        },
                        "url": {
                            "type": "string",
                            "description": "Login page URL (defaults to base_url + '/login').",
                        },
                        "username_selector": {"type": "string"},
                        "password_selector": {"type": "string"},
                        "submit_selector": {"type": "string"},
                        "success_indicator": {"type": "string"},
                    },
                },
                "form": {
                    "type": "object",
                    "description": "Form-related configuration.",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path to form page (RPA) or API endpoint.",
                        },
                        "data": {
                            "type": "object",
                            "description": "Structured form payload to submit.",
                        },
                    },
                },
                "export": {
                    "type": "object",
                    "description": "Export configuration for EXPORT_DATA action.",
                    "properties": {
                        "data_type": {"type": "string"},
                        "endpoint": {"type": "string"},
                        "query": {"type": "object"},
                    },
                },
                "api": {
                    "type": "object",
                    "description": "Low-level API configuration passed through to oa_api/oa_export.",
                    "properties": {
                        "auth_type": {"type": "string"},
                        "auth_credentials": {"type": "object"},
                        "headers": {"type": "object"},
                    },
                },
            },
            "required": ["mode", "action", "base_url"],
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Dispatch high-level OA actions to underlying tools."""
        mode = OAAdapterMode(params.get("mode", OAAdapterMode.API.value))
        action = OAAdapterAction(params["action"])

        if mode == OAAdapterMode.API:
            return await self._execute_api(action, params, context)
        return await self._execute_rpa(action, params, context)

    async def _execute_api(
        self,
        action: OAAdapterAction,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        """Handle API-mode operations via oa_api / oa_export tools."""
        from leagent.tools.integration.oa_api import OAApiTool
        from leagent.tools.integration.oa_export import OAExportTool

        base_url: str = params["base_url"]
        api_cfg: dict[str, Any] = params.get("api", {})

        if action in (OAAdapterAction.SUBMIT_FORM, OAAdapterAction.IMPORT_REIMBURSEMENT):
            form_cfg = params.get("form") or {}
            data = (form_cfg.get("data") or {}) if form_cfg else {}

            tool = OAApiTool()
            result = await tool.run(
                {
                    "base_url": base_url,
                    "operation": "submit",
                    "data": data,
                    **api_cfg,
                },
                context,
            )
            return {
                "mode": "api",
                "action": action.value,
                "operation": "submit",
                "raw": result,
            }

        if action == OAAdapterAction.EXPORT_DATA:
            export_cfg = params.get("export") or {}
            tool = OAExportTool()
            result = await tool.run(
                {
                    "base_url": base_url,
                    "data_type": export_cfg.get("data_type", "workflow_instance"),
                    "endpoint": export_cfg.get("endpoint"),
                    "records": export_cfg.get("records", []),
                    **api_cfg,
                },
                context,
            )
            return {
                "mode": "api",
                "action": action.value,
                "raw": result,
            }

        if action == OAAdapterAction.GET_FORM:
            # For API mode, GET form metadata via generic QUERY operation.
            tool = OAApiTool()
            form_cfg = params.get("form") or {}
            result = await tool.run(
                {
                    "base_url": base_url,
                    "operation": "query",
                    "endpoint": form_cfg.get("path") or "/forms",
                    **api_cfg,
                },
                context,
            )
            return {
                "mode": "api",
                "action": action.value,
                "raw": result,
            }

        if action == OAAdapterAction.LOGIN:
            # API mode login is just an oa_api call with AUTH configuration.
            return {
                "mode": "api",
                "action": action.value,
                "status": "noop",
                "message": "Login is handled implicitly by oa_api auth configuration in API mode.",
            }

        raise ValueError(f"Unsupported API action for oa_adapter: {action.value}")

    async def _execute_rpa(
        self,
        action: OAAdapterAction,
        params: dict[str, Any],
        context: ToolContext,
    ) -> dict[str, Any]:
        """Handle RPA-mode operations via web_* tools."""
        from leagent.tools.web.login import WebLoginTool
        from leagent.tools.web.scraper import WebScraperTool
        from leagent.tools.web.form_fill import WebFormFillTool

        base_url: str = params["base_url"].rstrip("/")
        login_cfg: dict[str, Any] = params.get("login") or {}
        form_cfg: dict[str, Any] = params.get("form") or {}

        session_cookies: list[dict[str, Any]] | None = None

        # For all actions except LOGIN/GET_FORM on public pages, try to login first.
        if action != OAAdapterAction.LOGIN:
            if login_cfg.get("credential_key"):
                login_tool = WebLoginTool()
                login_result = await login_tool.run(
                    {
                        "url": login_cfg.get("url") or f"{base_url}/login",
                        "credential_key": login_cfg["credential_key"],
                        "username_selector": login_cfg.get("username_selector") or "input[name='username']",
                        "password_selector": login_cfg.get("password_selector") or "input[name='password']",
                        "submit_selector": login_cfg.get("submit_selector") or "button[type='submit']",
                        "success_indicator": login_cfg.get("success_indicator"),
                    },
                    context,
                )
                if not login_result.get("success"):
                    return {
                        "mode": "rpa",
                        "action": action.value,
                        "success": False,
                        "error": login_result.get("error", "OA login failed"),
                    }
                session_cookies = login_result.get("session_cookies")

        if action == OAAdapterAction.LOGIN:
            # Explicit login-only action for workflows that need a reusable session.
            if not login_cfg.get("credential_key"):
                raise ValueError("login.credential_key is required for RPA login")
            login_tool = WebLoginTool()
            login_result = await login_tool.run(
                {
                    "url": login_cfg.get("url") or f"{base_url}/login",
                    "credential_key": login_cfg["credential_key"],
                    "username_selector": login_cfg.get("username_selector") or "input[name='username']",
                    "password_selector": login_cfg.get("password_selector") or "input[name='password']",
                    "submit_selector": login_cfg.get("submit_selector") or "button[type='submit']",
                    "success_indicator": login_cfg.get("success_indicator"),
                },
                context,
            )
            return {
                "mode": "rpa",
                "action": action.value,
                "raw": login_result,
            }

        if action == OAAdapterAction.GET_FORM:
            scraper = WebScraperTool()
            url = f"{base_url}/{(form_cfg.get('path') or '').lstrip('/')}"
            result = await scraper.run(
                {
                    "url": url,
                    "cookies": session_cookies,
                    "extract_mode": "structured",
                },
                context,
            )
            return {
                "mode": "rpa",
                "action": action.value,
                "raw": result,
            }

        if action in (OAAdapterAction.SUBMIT_FORM, OAAdapterAction.IMPORT_REIMBURSEMENT):
            form_data = form_cfg.get("data") or {}
            url = f"{base_url}/{(form_cfg.get('path') or '').lstrip('/')}"
            form_tool = WebFormFillTool()
            result = await form_tool.run(
                {
                    "url": url,
                    "session_cookies": session_cookies,
                    "fields": form_data,
                },
                context,
            )
            return {
                "mode": "rpa",
                "action": action.value,
                "raw": result,
            }

        if action == OAAdapterAction.EXPORT_DATA:
            # For RPA exports, callers should use web_rpa directly; we only provide a thin hook here.
            return {
                "mode": "rpa",
                "action": action.value,
                "status": "noop",
                "message": "For complex export flows in RPA mode, use web_rpa in workflows directly.",
            }

        raise ValueError(f"Unsupported RPA action for oa_adapter: {action.value}")

