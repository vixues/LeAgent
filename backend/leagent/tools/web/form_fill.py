"""Web form filling tool for automated form interactions.

This module provides a tool for filling web forms by selector,
handling various input types including text, checkboxes, selects,
and file uploads.
"""

from __future__ import annotations

from typing import Any

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.web.browser_pool import BrowserPool

logger = structlog.get_logger(__name__)


class WebFormFillTool(BaseTool):
    """Tool for filling web forms programmatically.

    Supports various input types including text fields, textareas,
    checkboxes, radio buttons, select dropdowns, and file uploads.

    Example:
        >>> tool = WebFormFillTool()
        >>> result = await tool.run({
        ...     "url": "https://example.com/form",
        ...     "fields": [
        ...         {"selector": "#username", "value": "testuser"},
        ...         {"selector": "#email", "value": "test@example.com"},
        ...         {"selector": "#country", "value": "US", "type": "select"}
        ...     ]
        ... }, context)
    """

    name = "web_form_fill"
    description = (
        "Fill web forms by specifying selectors and values for each field. "
        "Supports text inputs, checkboxes, radio buttons, selects, and file uploads."
    )
    category = ToolCategory.WEB
    version = "1.0.0"
    timeout_sec = 60
    aliases = ["form", "fill_form", "web_input"]
    search_hint = "form fill input text checkbox radio select file upload web"
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
                    "description": "The URL of the page containing the form",
                },
                "fields": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "selector": {
                                "type": "string",
                                "description": "CSS selector for the form field",
                            },
                            "value": {
                                "description": "Value to fill (string, boolean for checkbox, or array for multi-select)",
                            },
                            "type": {
                                "type": "string",
                                "enum": ["text", "checkbox", "radio", "select", "file", "date", "clear_then_fill"],
                                "default": "text",
                                "description": "Type of input field",
                            },
                            "delay_ms": {
                                "type": "integer",
                                "default": 0,
                                "description": "Delay between keystrokes for text input (ms)",
                            },
                        },
                        "required": ["selector", "value"],
                    },
                    "description": "List of form fields to fill",
                },
                "submit_selector": {
                    "type": "string",
                    "description": "Selector for submit button to click after filling",
                },
                "wait_after_submit_ms": {
                    "type": "integer",
                    "default": 2000,
                    "description": "Time to wait after clicking submit (ms)",
                },
                "wait_for_navigation": {
                    "type": "boolean",
                    "default": True,
                    "description": "Wait for page navigation after submit",
                },
                "storage_state": {
                    "type": "string",
                    "description": "Path to storage state file for session persistence",
                },
                "return_page_content": {
                    "type": "boolean",
                    "default": False,
                    "description": "Return page HTML content after form submission",
                },
            },
            "required": ["url", "fields"],
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Filling web form"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute form filling on the specified page.

        Args:
            params: Form filling parameters.
            context: Tool execution context.

        Returns:
            Dictionary containing fill results and optional page content.
        """
        url = params["url"]
        fields = params["fields"]
        submit_selector = params.get("submit_selector")
        wait_after_submit_ms = params.get("wait_after_submit_ms", 2000)
        wait_for_navigation = params.get("wait_for_navigation", True)
        storage_state = params.get("storage_state")
        return_page_content = params.get("return_page_content", False)

        logger.info("Starting form fill", url=url, field_count=len(fields))

        pool = await BrowserPool.get_instance()

        async with pool.get_page(storage_state=storage_state) as page:
            response = await page.goto(url, wait_until="domcontentloaded")

            if response is None or not response.ok:
                status = response.status if response else "no response"
                raise RuntimeError(f"Failed to load page: {url} (status: {status})")

            filled_fields = []
            for field in fields:
                selector = field["selector"]
                value = field["value"]
                field_type = field.get("type", "text")
                delay_ms = field.get("delay_ms", 0)

                try:
                    await self._fill_field(page, selector, value, field_type, delay_ms)
                    filled_fields.append({"selector": selector, "success": True})
                    logger.debug("Field filled", selector=selector, type=field_type)
                except Exception as e:
                    filled_fields.append({"selector": selector, "success": False, "error": str(e)})
                    logger.warning("Failed to fill field", selector=selector, error=str(e))

            result: dict[str, Any] = {
                "url": url,
                "fields_filled": filled_fields,
                "submitted": False,
            }

            if submit_selector:
                try:
                    if wait_for_navigation:
                        async with page.expect_navigation(timeout=30000):
                            await page.click(submit_selector)
                    else:
                        await page.click(submit_selector)
                        await page.wait_for_timeout(wait_after_submit_ms)

                    result["submitted"] = True
                    result["final_url"] = page.url
                    logger.info("Form submitted", final_url=page.url)
                except Exception as e:
                    result["submit_error"] = str(e)
                    logger.warning("Form submission failed", error=str(e))

            if return_page_content:
                result["page_content"] = await page.content()
                result["page_title"] = await page.title()

        return result

    async def _fill_field(
        self,
        page,
        selector: str,
        value: Any,
        field_type: str,
        delay_ms: int,
    ) -> None:
        """Fill a single form field.

        Args:
            page: Playwright page object.
            selector: CSS selector for the field.
            value: Value to fill.
            field_type: Type of input field.
            delay_ms: Delay between keystrokes.
        """
        await page.wait_for_selector(selector, state="visible", timeout=10000)

        if field_type == "text":
            await page.fill(selector, str(value))

        elif field_type == "clear_then_fill":
            await page.click(selector, click_count=3)
            await page.keyboard.press("Backspace")
            if delay_ms > 0:
                await page.type(selector, str(value), delay=delay_ms)
            else:
                await page.fill(selector, str(value))

        elif field_type == "checkbox":
            is_checked = await page.is_checked(selector)
            if value and not is_checked:
                await page.check(selector)
            elif not value and is_checked:
                await page.uncheck(selector)

        elif field_type == "radio":
            await page.check(selector)

        elif field_type == "select":
            if isinstance(value, list):
                await page.select_option(selector, value)
            else:
                await page.select_option(selector, str(value))

        elif field_type == "file":
            if isinstance(value, list):
                await page.set_input_files(selector, value)
            else:
                await page.set_input_files(selector, str(value))

        elif field_type == "date":
            await page.fill(selector, str(value))

        else:
            await page.fill(selector, str(value))
