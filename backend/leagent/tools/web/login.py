"""Web login tool for automated authentication.

This module provides a tool for automating login flows on web applications,
with support for session persistence, multi-step authentication,
and credential management.
"""

from __future__ import annotations

import json
import os
from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.web.browser_pool import BrowserPool

logger = structlog.get_logger(__name__)


class WebLoginTool(BaseTool):
    """Tool for automated web login.

    Handles authentication flows including form-based login,
    multi-step verification, and session persistence for
    maintaining authenticated state across requests.

    Example:
        >>> tool = WebLoginTool()
        >>> result = await tool.run({
        ...     "url": "https://example.com/login",
        ...     "username_selector": "#username",
        ...     "username": "user@example.com",
        ...     "password_selector": "#password",
        ...     "password": "secret123",
        ...     "submit_selector": "button[type=submit]",
        ...     "save_session": True
        ... }, context)
    """

    name = "web_login"
    description = (
        "Perform automated login on web applications with credential input "
        "and session persistence for maintaining authenticated state."
    )
    category = ToolCategory.WEB
    version = "1.0.0"
    timeout_sec = 90
    aliases = ["login", "web_auth", "authenticate"]
    search_hint = "login authenticate web credential session username password"
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = False
    interrupt_behavior = "block"
    max_result_size_chars = 50_000
    output_path_params = ("session_file_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        """Define the JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Login page URL",
                },
                "username_selector": {
                    "type": "string",
                    "description": "CSS selector for username/email input",
                },
                "username": {
                    "type": "string",
                    "description": "Username or email to enter",
                },
                "password_selector": {
                    "type": "string",
                    "description": "CSS selector for password input",
                },
                "password": {
                    "type": "string",
                    "description": "Password to enter",
                },
                "submit_selector": {
                    "type": "string",
                    "description": "CSS selector for submit/login button",
                },
                "additional_fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "selector": {"type": "string"},
                            "value": {"type": "string"},
                            "type": {
                                "type": "string",
                                "enum": ["text", "checkbox", "select"],
                                "default": "text",
                            },
                        },
                        "required": ["selector", "value"],
                    },
                    "description": "Additional form fields to fill",
                },
                "pre_login_actions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {
                                "type": "string",
                                "enum": ["click", "wait", "type"],
                            },
                            "selector": {"type": "string"},
                            "value": {"type": "string"},
                            "timeout_ms": {"type": "integer"},
                        },
                        "required": ["action"],
                    },
                    "description": "Actions to perform before login (e.g., dismiss popups)",
                },
                "post_login_verification": {
                    "type": "object",
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["selector", "url_contains", "url_not_contains", "text_present"],
                        },
                        "value": {"type": "string"},
                        "timeout_ms": {"type": "integer", "default": 10000},
                    },
                    "description": "Method to verify successful login",
                },
                "save_session": {
                    "type": "boolean",
                    "default": False,
                    "description": "Save session state for future requests",
                },
                "session_file_path": {
                    "type": "string",
                    "description": "Path to save/load session state",
                },
                "load_existing_session": {
                    "type": "boolean",
                    "default": False,
                    "description": "Try to load existing session before login",
                },
                "wait_after_submit_ms": {
                    "type": "integer",
                    "default": 3000,
                    "description": "Time to wait after clicking submit (ms)",
                },
                "two_factor": {
                    "type": "object",
                    "properties": {
                        "expected": {"type": "boolean", "default": False},
                        "code_selector": {"type": "string"},
                        "submit_selector": {"type": "string"},
                    },
                    "description": "Two-factor authentication configuration",
                },
            },
            "required": ["url", "username_selector", "username", "password_selector", "password", "submit_selector"],
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        url = (params or {}).get("url", "")
        return f"Logging in{f' to {url}' if url else ''}"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute login flow on the specified page.

        Args:
            params: Login parameters.
            context: Tool execution context.

        Returns:
            Dictionary containing login results and session state.
        """
        url = params["url"]
        username_selector = params["username_selector"]
        username = params["username"]
        password_selector = params["password_selector"]
        password = params["password"]
        submit_selector = params["submit_selector"]
        additional_fields = params.get("additional_fields", [])
        pre_login_actions = params.get("pre_login_actions", [])
        post_login_verification = params.get("post_login_verification")
        save_session = params.get("save_session", False)
        session_file_path = params.get("session_file_path")
        load_existing_session = params.get("load_existing_session", False)
        wait_after_submit_ms = params.get("wait_after_submit_ms", 3000)
        two_factor = params.get("two_factor", {})

        logger.info("Starting login flow", url=url, username=username[:3] + "***")

        storage_state = None
        if load_existing_session and session_file_path and os.path.exists(session_file_path):
            try:
                storage_state = session_file_path
                logger.info("Loaded existing session", path=session_file_path)
            except Exception as e:
                logger.warning("Failed to load session", error=str(e))

        pool = await BrowserPool.get_instance()

        async with pool.get_context(storage_state=storage_state) as browser_context:
            page = await browser_context.new_page()

            try:
                response = await page.goto(url, wait_until="domcontentloaded")

                if response is None or not response.ok:
                    status = response.status if response else "no response"
                    raise RuntimeError(f"Failed to load login page: {url} (status: {status})")

                if load_existing_session and storage_state:
                    is_logged_in = await self._verify_login(page, post_login_verification)
                    if is_logged_in:
                        logger.info("Already logged in from existing session")
                        return {
                            "success": True,
                            "url": url,
                            "final_url": page.url,
                            "already_logged_in": True,
                            "session_restored": True,
                        }

                for action in pre_login_actions:
                    await self._execute_pre_action(page, action)

                await page.wait_for_selector(username_selector, state="visible", timeout=10000)
                await page.fill(username_selector, username)

                await page.wait_for_selector(password_selector, state="visible", timeout=10000)
                await page.fill(password_selector, password)

                for field in additional_fields:
                    await self._fill_additional_field(page, field)

                try:
                    async with page.expect_navigation(timeout=30000):
                        await page.click(submit_selector)
                except Exception:
                    await page.click(submit_selector)
                    await page.wait_for_timeout(wait_after_submit_ms)

                if two_factor.get("expected"):
                    result = await self._handle_two_factor(page, two_factor)
                    if not result["success"]:
                        return result

                login_success = await self._verify_login(page, post_login_verification)

                result: dict[str, Any] = {
                    "success": login_success,
                    "url": url,
                    "final_url": page.url,
                    "page_title": await page.title(),
                }

                if not login_success:
                    error_text = await self._get_error_message(page)
                    result["error"] = error_text or "Login verification failed"
                    logger.warning("Login failed", url=url, error=result.get("error"))
                else:
                    logger.info("Login successful", url=url, final_url=page.url)

                if save_session and login_success:
                    session_path = session_file_path
                    if not session_path:
                        temp_dir = context.temp_dir or "/tmp"
                        session_path = os.path.join(
                            temp_dir, f"session_{context.user_id}_{context.session_id}.json"
                        )

                    os.makedirs(os.path.dirname(session_path), exist_ok=True)
                    state = await browser_context.storage_state()

                    with open(session_path, "w") as f:
                        json.dump(state, f)

                    result["session_file"] = session_path
                    logger.info("Session saved", path=session_path)

                return result

            finally:
                await page.close()

    async def _execute_pre_action(self, page, action: dict) -> None:
        """Execute a pre-login action.

        Args:
            page: Playwright page object.
            action: Action configuration.
        """
        action_type = action["action"]
        selector = action.get("selector")
        value = action.get("value")
        timeout_ms = action.get("timeout_ms", 5000)

        if action_type == "click" and selector:
            try:
                await page.wait_for_selector(selector, state="visible", timeout=timeout_ms)
                await page.click(selector)
            except Exception as e:
                logger.debug("Pre-action click skipped", selector=selector, error=str(e))

        elif action_type == "wait":
            if selector:
                await page.wait_for_selector(selector, timeout=timeout_ms)
            elif value:
                await page.wait_for_timeout(int(value))

        elif action_type == "type" and selector and value:
            await page.fill(selector, value)

    async def _fill_additional_field(self, page, field: dict) -> None:
        """Fill an additional form field.

        Args:
            page: Playwright page object.
            field: Field configuration.
        """
        selector = field["selector"]
        value = field["value"]
        field_type = field.get("type", "text")

        await page.wait_for_selector(selector, state="visible", timeout=5000)

        if field_type == "text":
            await page.fill(selector, value)
        elif field_type == "checkbox":
            if value.lower() in ("true", "1", "yes"):
                await page.check(selector)
            else:
                await page.uncheck(selector)
        elif field_type == "select":
            await page.select_option(selector, value)

    async def _verify_login(self, page, verification: dict | None) -> bool:
        """Verify login was successful.

        Args:
            page: Playwright page object.
            verification: Verification configuration.

        Returns:
            True if login verified, False otherwise.
        """
        if not verification:
            return True

        verify_type = verification.get("type")
        value = verification.get("value", "")
        timeout_ms = verification.get("timeout_ms", 10000)

        try:
            if verify_type == "selector":
                await page.wait_for_selector(value, state="visible", timeout=timeout_ms)
                return True

            elif verify_type == "url_contains":
                for _ in range(timeout_ms // 500):
                    if value in page.url:
                        return True
                    await page.wait_for_timeout(500)
                return False

            elif verify_type == "url_not_contains":
                for _ in range(timeout_ms // 500):
                    if value not in page.url:
                        return True
                    await page.wait_for_timeout(500)
                return False

            elif verify_type == "text_present":
                locator = page.locator(f"text={value}")
                await locator.wait_for(state="visible", timeout=timeout_ms)
                return True

        except Exception as e:
            logger.debug("Login verification failed", type=verify_type, error=str(e))
            return False

        return True

    async def _handle_two_factor(self, page, two_factor: dict) -> dict[str, Any]:
        """Handle two-factor authentication.

        This is a placeholder that returns information about 2FA requirement.
        Actual 2FA code entry would need external input.

        Args:
            page: Playwright page object.
            two_factor: Two-factor configuration.

        Returns:
            Result dictionary indicating 2FA state.
        """
        code_selector = two_factor.get("code_selector")

        if code_selector:
            try:
                await page.wait_for_selector(code_selector, state="visible", timeout=5000)
                return {
                    "success": False,
                    "requires_2fa": True,
                    "code_selector": code_selector,
                    "message": "Two-factor authentication required. Please provide the verification code.",
                }
            except Exception:
                pass

        return {"success": True}

    async def _get_error_message(self, page) -> str | None:
        """Try to extract error message from page.

        Args:
            page: Playwright page object.

        Returns:
            Error message if found, None otherwise.
        """
        error_selectors = [
            ".error",
            ".error-message",
            ".alert-danger",
            ".alert-error",
            "[role='alert']",
            ".login-error",
            "#error",
            ".form-error",
        ]

        for selector in error_selectors:
            try:
                element = page.locator(selector).first
                if await element.is_visible():
                    text = await element.inner_text()
                    if text and text.strip():
                        return text.strip()
            except Exception:
                continue

        return None
