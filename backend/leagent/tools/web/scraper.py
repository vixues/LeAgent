"""Web scraper tool for fetching and parsing web pages.

This module provides a tool for extracting content from web pages
using CSS or XPath selectors, with support for both text and
structured data extraction.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext
from leagent.tools.web.browser_pool import BrowserPool
from leagent.tools.web.robots_policy import assert_fetch_allowed

logger = structlog.get_logger(__name__)


class WebScraperTool(BaseTool):
    """Tool for scraping content from web pages.

    Fetches web pages and extracts content using CSS or XPath selectors.
    Supports both simple text extraction and structured data parsing.

    Example:
        >>> tool = WebScraperTool()
        >>> result = await tool.run({
        ...     "url": "https://example.com",
        ...     "selectors": {"title": "h1", "links": "a[href]"},
        ...     "extract_text": True
        ... }, context)
    """

    name = "web_scraper"
    description = (
        "Fetch and parse web pages, extracting content using CSS or XPath selectors. "
        "Respects optional robots.txt checks and a short pre-navigation delay to reduce "
        "accidental rate limits on single-machine installs."
    )
    category = ToolCategory.WEB
    version = "1.0.0"
    timeout_sec = 60
    aliases = ["scrape", "web_extract", "fetch_page"]
    search_hint = "scrape fetch web page extract content CSS XPath selector parse"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000

    @property
    def parameters(self) -> dict[str, Any]:
        """Define the JSON schema for tool parameters."""
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "The URL of the web page to scrape",
                },
                "selectors": {
                    "type": "object",
                    "additionalProperties": {"type": "string"},
                    "description": "Named selectors for data extraction. Keys are field names, values are CSS/XPath selectors",
                },
                "selector": {
                    "type": "string",
                    "description": "Single selector for simple extraction (alternative to selectors object)",
                },
                "selector_type": {
                    "type": "string",
                    "enum": ["css", "xpath"],
                    "default": "css",
                    "description": "Type of selector: 'css' or 'xpath'",
                },
                "extract_text": {
                    "type": "boolean",
                    "default": True,
                    "description": "Extract text content (True) or HTML (False)",
                },
                "extract_attributes": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of attributes to extract from elements",
                },
                "multiple": {
                    "type": "boolean",
                    "default": False,
                    "description": "Extract all matching elements (True) or first only (False)",
                },
                "wait_for_selector": {
                    "type": "string",
                    "description": "Wait for this selector to appear before scraping",
                },
                "wait_timeout_ms": {
                    "type": "integer",
                    "default": 10000,
                    "description": "Timeout for wait_for_selector in milliseconds",
                },
                "javascript_enabled": {
                    "type": "boolean",
                    "default": True,
                    "description": "Enable JavaScript execution on the page",
                },
                "scroll_to_bottom": {
                    "type": "boolean",
                    "default": False,
                    "description": "Scroll to bottom before scraping (for infinite scroll pages)",
                },
            },
            "required": ["url"],
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        url = (params or {}).get("url", "")
        return f"Scraping{f' {url}' if url else ' web page'}"

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute web scraping on the specified URL.

        Args:
            params: Scraping parameters including URL and selectors.
            context: Tool execution context.

        Returns:
            Dictionary containing extracted data and metadata.
        """
        url = params["url"]
        selectors = params.get("selectors", {})
        single_selector = params.get("selector")
        selector_type = params.get("selector_type", "css")
        extract_text = params.get("extract_text", True)
        extract_attributes = params.get("extract_attributes", [])
        multiple = params.get("multiple", False)
        wait_for_selector = params.get("wait_for_selector")
        wait_timeout_ms = params.get("wait_timeout_ms", 10000)
        scroll_to_bottom = params.get("scroll_to_bottom", False)

        from leagent.config.settings import get_settings

        wf = get_settings().web_fetch
        async with httpx.AsyncClient(trust_env=True, timeout=25.0) as rclient:
            await assert_fetch_allowed(rclient, url)
        delay_s = max(0.0, float(wf.pre_navigation_delay_ms) / 1000.0)
        if delay_s > 0:
            await asyncio.sleep(delay_s)

        logger.info("Starting web scrape", url=url, selector_count=len(selectors) or 1)

        pool = await BrowserPool.get_instance()

        async with pool.get_page() as page:
            response = await page.goto(url, wait_until="domcontentloaded")

            if response is None or not response.ok:
                status = response.status if response else "no response"
                raise RuntimeError(f"Failed to load page: {url} (status: {status})")

            if wait_for_selector:
                await page.wait_for_selector(wait_for_selector, timeout=wait_timeout_ms)

            if scroll_to_bottom:
                await self._scroll_to_bottom(page)

            result: dict[str, Any] = {
                "url": url,
                "title": await page.title(),
                "status": response.status,
            }

            if single_selector:
                result["data"] = await self._extract_selector(
                    page,
                    single_selector,
                    selector_type,
                    extract_text,
                    extract_attributes,
                    multiple,
                )
            elif selectors:
                result["data"] = {}
                for field_name, sel in selectors.items():
                    result["data"][field_name] = await self._extract_selector(
                        page,
                        sel,
                        selector_type,
                        extract_text,
                        extract_attributes,
                        multiple,
                    )
            else:
                if extract_text:
                    result["data"] = await page.inner_text("body")
                else:
                    result["data"] = await page.content()

        logger.info("Web scrape completed", url=url)
        return result

    async def _extract_selector(
        self,
        page,
        selector: str,
        selector_type: str,
        extract_text: bool,
        extract_attributes: list[str],
        multiple: bool,
    ) -> Any:
        """Extract content from page using a selector.

        Args:
            page: Playwright page object.
            selector: CSS or XPath selector.
            selector_type: Type of selector ('css' or 'xpath').
            extract_text: Whether to extract text content.
            extract_attributes: List of attributes to extract.
            multiple: Whether to extract all matches.

        Returns:
            Extracted content (string, dict, or list).
        """
        if selector_type == "xpath":
            locator = page.locator(f"xpath={selector}")
        else:
            locator = page.locator(selector)

        count = await locator.count()
        if count == 0:
            return [] if multiple else None

        async def extract_element(element_locator):
            result = {}

            if extract_text:
                try:
                    result["text"] = await element_locator.inner_text()
                except Exception:
                    result["text"] = ""

            if extract_attributes:
                for attr in extract_attributes:
                    try:
                        result[attr] = await element_locator.get_attribute(attr)
                    except Exception:
                        result[attr] = None

            if extract_text and not extract_attributes:
                return result.get("text", "")

            return result

        if multiple:
            results = []
            for i in range(count):
                element = locator.nth(i)
                data = await extract_element(element)
                results.append(data)
            return results
        else:
            return await extract_element(locator.first)

    async def _scroll_to_bottom(self, page, max_scrolls: int = 10) -> None:
        """Scroll to the bottom of the page for infinite scroll pages.

        Args:
            page: Playwright page object.
            max_scrolls: Maximum number of scroll iterations.
        """
        previous_height = 0
        for _ in range(max_scrolls):
            current_height = await page.evaluate("document.body.scrollHeight")
            if current_height == previous_height:
                break

            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(1000)
            previous_height = current_height
