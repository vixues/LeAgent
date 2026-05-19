"""Web automation tools package.

This module provides Playwright-based tools for web automation including
scraping, form filling, clicking, screenshots, and authentication.

Example:
    >>> from leagent.tools.web import (
    ...     BrowserPool,
    ...     WebScraperTool,
    ...     WebFormFillTool,
    ...     WebClickTool,
    ...     WebScreenshotTool,
    ...     WebLoginTool,
    ... )
    >>>
    >>> # Get browser pool instance
    >>> pool = await BrowserPool.get_instance()
    >>>
    >>> # Use tools
    >>> scraper = WebScraperTool()
    >>> result = await scraper.run({"url": "https://example.com"}, context)
"""

from leagent.tools.web.browser_pool import (
    BrowserConfig,
    BrowserPool,
    cleanup_browser_pool,
    get_browser_pool,
)
from leagent.tools.web.click import WebClickTool
from leagent.tools.web.form_fill import WebFormFillTool
from leagent.tools.web.login import WebLoginTool
from leagent.tools.web.scraper import WebScraperTool
from leagent.tools.web.screenshot import WebScreenshotTool

__all__ = [
    # Browser pool management
    "BrowserConfig",
    "BrowserPool",
    "get_browser_pool",
    "cleanup_browser_pool",
    # Web automation tools
    "WebScraperTool",
    "WebFormFillTool",
    "WebClickTool",
    "WebScreenshotTool",
    "WebLoginTool",
]
