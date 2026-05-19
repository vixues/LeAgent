"""Web click tool for element interactions.

This module provides a tool for clicking web elements by selector,
with support for navigation waiting, multiple click types, and
element state verification.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.web.browser_pool import BrowserPool

logger = structlog.get_logger(__name__)


class WebClickTool(BaseTool):
    """Tool for clicking web elements.

    Supports various click types including single click, double click,
    and right click, with options for waiting for navigation or
    specific page states after clicking.

    Example:
        >>> tool = WebClickTool()
        >>> result = await tool.run({
        ...     "url": "https://example.com",
        ...     "selector": "button.submit",
        ...     "wait_for_navigation": True
        ... }, context)
    """

    name = "web_click"
    description = (
        "Click elements on web pages by selector. "
        "Supports single click, double click, right click, and navigation waiting."
    )
    category = ToolCategory.WEB
    version = "1.0.0"
    timeout_sec = 60
    aliases = ["click", "web_tap", "browser_click"]
    search_hint = "click element web page selector single double right navigate"
    is_concurrency_safe = False
    is_read_only = False
    is_destructive = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000

    @property
    def parameters(self) -> dict[str, Any]:
        """Define the JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL of the page (optional if using existing page state)",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for the element to click",
                },
                "click_type": {
                    "type": "string",
                    "enum": ["click", "dblclick", "right_click"],
                    "default": "click",
                    "description": "Type of click action",
                },
                "click_count": {
                    "type": "integer",
                    "default": 1,
                    "description": "Number of times to click",
                },
                "button": {
                    "type": "string",
                    "enum": ["left", "middle", "right"],
                    "default": "left",
                    "description": "Mouse button to use",
                },
                "modifiers": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["Alt", "Control", "Meta", "Shift"],
                    },
                    "description": "Keyboard modifiers to hold during click",
                },
                "position": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                    },
                    "description": "Position within element to click (relative to top-left)",
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                    "description": "Force click even if element is not visible",
                },
                "wait_for_navigation": {
                    "type": "boolean",
                    "default": False,
                    "description": "Wait for page navigation after click",
                },
                "wait_for_selector": {
                    "type": "string",
                    "description": "Wait for this selector to appear after click",
                },
                "wait_for_selector_state": {
                    "type": "string",
                    "enum": ["attached", "detached", "visible", "hidden"],
                    "default": "visible",
                    "description": "State to wait for when using wait_for_selector",
                },
                "wait_timeout_ms": {
                    "type": "integer",
                    "default": 30000,
                    "description": "Timeout for waiting operations (ms)",
                },
                "delay_before_ms": {
                    "type": "integer",
                    "default": 0,
                    "description": "Delay before clicking (ms)",
                },
                "delay_after_ms": {
                    "type": "integer",
                    "default": 0,
                    "description": "Delay after clicking (ms)",
                },
                "storage_state": {
                    "type": "string",
                    "description": "Path to storage state file for session persistence",
                },
                "return_page_info": {
                    "type": "boolean",
                    "default": True,
                    "description": "Return page URL and title after click",
                },
            },
            "required": ["url", "selector"],
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        selector = (params or {}).get("selector", "")
        return f"Clicking element{f': {selector}' if selector else ''}"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute click action on the specified element.

        Args:
            params: Click parameters.
            context: Tool execution context.

        Returns:
            Dictionary containing click results and page state.
        """
        url = params["url"]
        selector = params["selector"]
        click_type = params.get("click_type", "click")
        click_count = params.get("click_count", 1)
        button = params.get("button", "left")
        modifiers = params.get("modifiers", [])
        position = params.get("position")
        force = params.get("force", False)
        wait_for_navigation = params.get("wait_for_navigation", False)
        wait_for_selector = params.get("wait_for_selector")
        wait_for_selector_state = params.get("wait_for_selector_state", "visible")
        wait_timeout_ms = params.get("wait_timeout_ms", 30000)
        delay_before_ms = params.get("delay_before_ms", 0)
        delay_after_ms = params.get("delay_after_ms", 0)
        storage_state = params.get("storage_state")
        return_page_info = params.get("return_page_info", True)

        logger.info("Starting web click", url=url, selector=selector, click_type=click_type)

        pool = await BrowserPool.get_instance()

        async with pool.get_page(storage_state=storage_state) as page:
            response = await page.goto(url, wait_until="domcontentloaded")

            if response is None or not response.ok:
                status = response.status if response else "no response"
                raise RuntimeError(f"Failed to load page: {url} (status: {status})")

            await page.wait_for_selector(selector, state="visible", timeout=wait_timeout_ms)

            if delay_before_ms > 0:
                await page.wait_for_timeout(delay_before_ms)

            click_options: dict[str, Any] = {
                "force": force,
            }

            if click_count > 1:
                click_options["click_count"] = click_count

            if button != "left":
                click_options["button"] = button

            if modifiers:
                click_options["modifiers"] = modifiers

            if position:
                click_options["position"] = position

            element = page.locator(selector)
            element_info = {
                "selector": selector,
                "was_visible": await element.is_visible(),
                "was_enabled": await element.is_enabled(),
            }

            try:
                element_text = await element.inner_text()
                element_info["text"] = element_text[:100] if element_text else None
            except Exception:
                element_info["text"] = None

            try:
                if click_type == "dblclick":
                    if wait_for_navigation:
                        async with page.expect_navigation(timeout=wait_timeout_ms):
                            await element.dblclick(**click_options)
                    else:
                        await element.dblclick(**click_options)

                elif click_type == "right_click":
                    click_options["button"] = "right"
                    await element.click(**click_options)

                else:
                    if wait_for_navigation:
                        async with page.expect_navigation(timeout=wait_timeout_ms):
                            await element.click(**click_options)
                    else:
                        await element.click(**click_options)

                click_success = True
                click_error = None

            except Exception as e:
                click_success = False
                click_error = str(e)
                logger.warning("Click failed", selector=selector, error=click_error)

            if click_success and wait_for_selector:
                try:
                    await page.wait_for_selector(
                        wait_for_selector,
                        state=wait_for_selector_state,
                        timeout=wait_timeout_ms,
                    )
                except Exception as e:
                    logger.warning("Wait for selector failed", selector=wait_for_selector, error=str(e))

            if delay_after_ms > 0:
                await page.wait_for_timeout(delay_after_ms)

            result: dict[str, Any] = {
                "success": click_success,
                "selector": selector,
                "click_type": click_type,
                "element_info": element_info,
            }

            if click_error:
                result["error"] = click_error

            if return_page_info:
                result["page_url"] = page.url
                result["page_title"] = await page.title()

        logger.info("Web click completed", success=click_success, selector=selector)
        return result
