"""Web screenshot tool for capturing page and element images.

This module provides a tool for taking screenshots of web pages,
supporting full page captures, element-specific screenshots,
and various output formats.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any
from uuid import uuid4

import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.web.browser_pool import BrowserPool

logger = structlog.get_logger(__name__)


class WebScreenshotTool(BaseTool):
    """Tool for taking screenshots of web pages.

    Supports full page screenshots, viewport captures, and
    element-specific screenshots with various output options.

    Example:
        >>> tool = WebScreenshotTool()
        >>> result = await tool.run({
        ...     "url": "https://example.com",
        ...     "full_page": True,
        ...     "output_format": "file"
        ... }, context)
    """

    name = "web_screenshot"
    description = (
        "Take screenshots of web pages or specific elements. "
        "By default saves PNG/JPEG to the session workspace and returns preview URLs "
        "(use output_format 'base64' only when you need inline image data)."
    )
    category = ToolCategory.WEB
    version = "1.0.0"
    timeout_sec = 60
    aliases = ["screenshot", "capture", "web_capture"]
    search_hint = "screenshot capture web page element full viewport PNG JPEG image"
    is_concurrency_safe = True
    is_read_only = False
    interrupt_behavior = "cancel"
    max_result_size_chars = 50_000
    output_path_params = ("file_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        """Define the JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL of the page to screenshot",
                },
                "selector": {
                    "type": "string",
                    "description": "CSS selector for element to screenshot (if not specified, captures viewport/page)",
                },
                "full_page": {
                    "type": "boolean",
                    "default": False,
                    "description": "Capture full scrollable page (ignored if selector specified)",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["base64", "file"],
                    "default": "file",
                    "description": (
                        "'file' (default): write image under session uploads when session_id is set, "
                        "register as attachment and return preview URLs; otherwise a temp path. "
                        "'base64': inline image_base64 (large; avoid for full-page captures)."
                    ),
                },
                "file_path": {
                    "type": "string",
                    "description": "Optional path for file output; if omitted with output_format 'file' and a chat session_id, saves under the session upload directory.",
                },
                "image_type": {
                    "type": "string",
                    "enum": ["png", "jpeg"],
                    "default": "png",
                    "description": "Image format",
                },
                "quality": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 100,
                    "default": 80,
                    "description": "JPEG quality (0-100, only for JPEG)",
                },
                "viewport_width": {
                    "type": "integer",
                    "default": 1920,
                    "description": "Viewport width in pixels",
                },
                "viewport_height": {
                    "type": "integer",
                    "default": 1080,
                    "description": "Viewport height in pixels",
                },
                "scale": {
                    "type": "number",
                    "default": 1.0,
                    "description": "Device scale factor (1.0 = normal, 2.0 = retina)",
                },
                "clip": {
                    "type": "object",
                    "properties": {
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "width": {"type": "number"},
                        "height": {"type": "number"},
                    },
                    "description": "Clip region for screenshot",
                },
                "omit_background": {
                    "type": "boolean",
                    "default": False,
                    "description": "Make background transparent (PNG only)",
                },
                "wait_for_selector": {
                    "type": "string",
                    "description": "Wait for this selector to appear before screenshot",
                },
                "wait_timeout_ms": {
                    "type": "integer",
                    "default": 10000,
                    "description": "Timeout for wait operations (ms)",
                },
                "delay_ms": {
                    "type": "integer",
                    "default": 0,
                    "description": "Delay before taking screenshot (ms)",
                },
                "hide_selectors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "CSS selectors of elements to hide before screenshot",
                },
                "storage_state": {
                    "type": "string",
                    "description": "Path to storage state file for session persistence",
                },
            },
            "required": ["url"],
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        url = (params or {}).get("url", "")
        return f"Taking screenshot{f' of {url}' if url else ''}"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute screenshot capture on the specified page.

        Args:
            params: Screenshot parameters.
            context: Tool execution context.

        Returns:
            Dictionary containing screenshot data or file path.
        """
        url = params["url"]
        selector = params.get("selector")
        full_page = params.get("full_page", False)
        output_format = params.get("output_format", "file")
        file_path = params.get("file_path")
        image_type = params.get("image_type", "png")
        quality = params.get("quality", 80)
        viewport_width = params.get("viewport_width", 1920)
        viewport_height = params.get("viewport_height", 1080)
        scale = params.get("scale", 1.0)
        clip = params.get("clip")
        omit_background = params.get("omit_background", False)
        wait_for_selector = params.get("wait_for_selector")
        wait_timeout_ms = params.get("wait_timeout_ms", 10000)
        delay_ms = params.get("delay_ms", 0)
        hide_selectors = params.get("hide_selectors", [])
        storage_state = params.get("storage_state")

        logger.info("Starting screenshot capture", url=url, full_page=full_page, selector=selector)

        pool = await BrowserPool.get_instance()

        context_options = {
            "viewport": {"width": viewport_width, "height": viewport_height},
            "device_scale_factor": scale,
        }

        async with pool.get_page(storage_state=storage_state, **context_options) as page:
            response = await page.goto(url, wait_until="domcontentloaded")

            if response is None or not response.ok:
                status = response.status if response else "no response"
                raise RuntimeError(f"Failed to load page: {url} (status: {status})")

            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=wait_timeout_ms)

            for hide_selector in hide_selectors:
                try:
                    await page.evaluate(f"""
                        document.querySelectorAll('{hide_selector}').forEach(el => el.style.visibility = 'hidden');
                    """)
                except Exception as e:
                    logger.warning("Failed to hide element", selector=hide_selector, error=str(e))

            if delay_ms > 0:
                await page.wait_for_timeout(delay_ms)

            screenshot_options: dict[str, Any] = {
                "type": image_type,
            }

            if image_type == "jpeg":
                screenshot_options["quality"] = quality

            if omit_background and image_type == "png":
                screenshot_options["omit_background"] = True

            if selector:
                element = page.locator(selector)
                await element.wait_for(state="visible", timeout=wait_timeout_ms)
                screenshot_bytes = await element.screenshot(**screenshot_options)
                element_info = {
                    "selector": selector,
                    "bounding_box": await element.bounding_box(),
                }
            else:
                if full_page:
                    screenshot_options["full_page"] = True
                elif clip:
                    screenshot_options["clip"] = clip

                screenshot_bytes = await page.screenshot(**screenshot_options)
                element_info = None

            result: dict[str, Any] = {
                "url": url,
                "page_title": await page.title(),
                "image_type": image_type,
                "full_page": full_page and not selector,
                "viewport": {"width": viewport_width, "height": viewport_height},
            }

            if element_info:
                result["element"] = element_info

            if output_format == "base64":
                result["image_base64"] = base64.b64encode(screenshot_bytes).decode("utf-8")
                result["size_bytes"] = len(screenshot_bytes)
            else:
                display_name = (
                    Path(file_path).name
                    if file_path
                    else f"screenshot_{uuid4().hex[:8]}.{image_type}"
                )
                result["size_bytes"] = len(screenshot_bytes)
                try:
                    from leagent.file.tool_output import register_tool_artifact

                    reg = await register_tool_artifact(
                        screenshot_bytes,
                        filename=display_name,
                        content_type=f"image/{image_type}",
                        session_id=context.session_id,
                        user_id=context.user_id,
                    )
                except Exception:  # noqa: BLE001
                    logger.warning("web_screenshot_register_failed", exc_info=True)
                    reg = None

                if reg:
                    fid = str(reg.get("id") or "")
                    result["file_id"] = fid
                    if fid:
                        result["preview_path"] = f"/api/v1/files/{fid}/preview"
                    result["preview_url"] = reg.get("preview_url")
                    result["download_url"] = reg.get("download_url")
                    result["file_path"] = reg.get("storage_path")

        logger.info("Screenshot captured", url=url, size_bytes=result.get("size_bytes", 0))
        return result
