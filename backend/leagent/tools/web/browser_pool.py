"""Browser pool for managing Playwright browser instances.

This module provides connection pooling and lifecycle management for
Playwright browser instances, enabling efficient resource usage across
multiple web automation tools.

Playwright is imported lazily on first ``initialize()`` so installing the
``browser`` extra at runtime (without restarting the process) can succeed.
"""

from __future__ import annotations

import asyncio
import atexit
import importlib
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, AsyncIterator

import structlog

if TYPE_CHECKING:
    from collections.abc import Callable

logger = structlog.get_logger(__name__)


def _lazy_playwright() -> tuple[Any, Any, Any, Any, Any]:
    """Import Playwright API objects; raises ImportError if the package is missing."""
    mod = importlib.import_module("playwright.async_api")
    async_playwright = mod.async_playwright
    Browser = mod.Browser
    BrowserContext = mod.BrowserContext
    Page = mod.Page
    Playwright = mod.Playwright
    return Browser, BrowserContext, Page, Playwright, async_playwright


def _browser_config_from_settings() -> BrowserConfig:
    from leagent.config.settings import get_settings

    wb = get_settings().web_browser
    return BrowserConfig(
        headless=wb.headless,
        locale=wb.locale,
        timezone=wb.timezone,
        user_agent=(wb.user_agent or None) or None,
        ignore_https_errors=wb.ignore_https_errors,
    )


@dataclass
class BrowserConfig:
    """Configuration for browser instances."""

    headless: bool = True
    slow_mo: int = 0
    timeout_ms: int = 30000
    viewport_width: int = 1920
    viewport_height: int = 1080
    user_agent: str | None = None
    locale: str = "en-US"
    timezone: str = "America/New_York"
    ignore_https_errors: bool = False
    proxy: dict[str, str] | None = None
    extra_http_headers: dict[str, str] = field(default_factory=dict)


class BrowserPool:
    """Manages a pool of Playwright browser instances.

    Provides connection pooling, context management, and cleanup
    for efficient browser resource management across web automation tools.

    Example:
        >>> pool = BrowserPool()
        >>> await pool.initialize()
        >>> async with pool.get_page() as page:
        ...     await page.goto("https://example.com")
        >>> await pool.cleanup()
    """

    _instance: BrowserPool | None = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(
        self,
        max_browsers: int = 3,
        max_contexts_per_browser: int = 5,
        config: BrowserConfig | None = None,
    ) -> None:
        """Initialize the browser pool.

        Args:
            max_browsers: Maximum number of browser instances.
            max_contexts_per_browser: Maximum contexts per browser.
            config: Browser configuration options.
        """
        self.max_browsers = max_browsers
        self.max_contexts_per_browser = max_contexts_per_browser
        self.config = config or _browser_config_from_settings()

        self._playwright: Any = None
        self._browsers: list[Any] = []
        self._context_counts: dict[Any, int] = {}
        self._initialized = False
        self._cleanup_registered = False
        self._pw_types: tuple[Any, Any, Any, Any, Any] | None = None

    @classmethod
    async def get_instance(cls, **kwargs) -> BrowserPool:
        """Get or create the singleton browser pool instance.

        Args:
            **kwargs: Arguments passed to BrowserPool constructor.

        Returns:
            The singleton BrowserPool instance.
        """
        async with cls._lock:
            if cls._instance is None:
                inst = cls(**kwargs)
                await inst.initialize()
                cls._instance = inst
            return cls._instance

    @classmethod
    async def reset_instance(cls) -> None:
        """Reset the singleton instance, cleaning up resources."""
        async with cls._lock:
            if cls._instance is not None:
                await cls._instance.cleanup()
                cls._instance = None

    async def initialize(self) -> None:
        """Initialize Playwright and create initial browser instance."""
        if self._initialized:
            return

        try:
            self._pw_types = _lazy_playwright()
        except ImportError as e:
            raise RuntimeError(
                "Playwright is not installed. Install the browser pack: "
                "cd backend && uv sync --extra browser && uv run playwright install chromium "
                "(or pip install 'leagent[browser]' then playwright install chromium)"
            ) from e

        # Prefer full Chromium over chromium-headless-shell — the latter is easy to
        # partially install and breaks zero-config bing_playwright / scraper tools.
        import os

        os.environ.setdefault("PLAYWRIGHT_CHROMIUM_USE_HEADLESS_SHELL", "0")

        _, _, _, _, async_playwright = self._pw_types

        logger.info("Initializing browser pool")
        self._playwright = await async_playwright().start()

        browser = await self._create_browser()
        self._browsers.append(browser)
        self._context_counts[browser] = 0
        self._initialized = True

        if not self._cleanup_registered:
            atexit.register(self._sync_cleanup)
            self._cleanup_registered = True

        logger.info("Browser pool initialized", browser_count=len(self._browsers))

    async def _create_browser(self) -> Any:
        """Create a new browser instance with configured options."""
        if self._playwright is None:
            raise RuntimeError("Playwright not initialized")

        launch_options: dict = {
            "headless": self.config.headless,
            "slow_mo": self.config.slow_mo,
        }

        if self.config.proxy:
            launch_options["proxy"] = self.config.proxy

        return await self._playwright.chromium.launch(**launch_options)

    async def _get_browser(self) -> Any:
        """Get an available browser with capacity for new contexts."""
        for browser in self._browsers:
            if browser.is_connected() and self._context_counts.get(browser, 0) < self.max_contexts_per_browser:
                return browser

        if len(self._browsers) < self.max_browsers:
            browser = await self._create_browser()
            self._browsers.append(browser)
            self._context_counts[browser] = 0
            logger.info("Created new browser", browser_count=len(self._browsers))
            return browser

        min_browser = min(
            (b for b in self._browsers if b.is_connected()),
            key=lambda b: self._context_counts.get(b, 0),
        )
        return min_browser

    @asynccontextmanager
    async def get_context(
        self,
        storage_state: str | dict | None = None,
        **context_options: Any,
    ) -> AsyncIterator[Any]:
        """Get a browser context from the pool.

        Args:
            storage_state: Path or dict for session state persistence.
            **context_options: Additional context options.

        Yields:
            A browser context for web automation.
        """
        if not self._initialized:
            await self.initialize()

        browser = await self._get_browser()
        self._context_counts[browser] = self._context_counts.get(browser, 0) + 1

        options: dict = {
            "viewport": {
                "width": self.config.viewport_width,
                "height": self.config.viewport_height,
            },
            "locale": self.config.locale,
            "timezone_id": self.config.timezone,
            "ignore_https_errors": self.config.ignore_https_errors,
        }

        if self.config.user_agent:
            options["user_agent"] = self.config.user_agent

        if self.config.extra_http_headers:
            options["extra_http_headers"] = self.config.extra_http_headers

        if storage_state:
            options["storage_state"] = storage_state

        options.update(context_options)

        context = await browser.new_context(**options)
        context.set_default_timeout(self.config.timeout_ms)

        try:
            yield context
        finally:
            await context.close()
            self._context_counts[browser] = max(0, self._context_counts.get(browser, 0) - 1)

    @asynccontextmanager
    async def get_page(
        self,
        storage_state: str | dict | None = None,
        **context_options: Any,
    ) -> AsyncIterator[Any]:
        """Get a page from the pool.

        This is a convenience method that creates a context and page.

        Args:
            storage_state: Path or dict for session state persistence.
            **context_options: Additional context options.

        Yields:
            A page for web automation.
        """
        async with self.get_context(storage_state=storage_state, **context_options) as context:
            page = await context.new_page()
            try:
                yield page
            finally:
                await page.close()

    async def cleanup(self) -> None:
        """Clean up all browser instances and Playwright."""
        if not self._initialized:
            return

        logger.info("Cleaning up browser pool")

        for browser in self._browsers:
            try:
                if browser.is_connected():
                    await browser.close()
            except Exception as e:
                logger.warning("Error closing browser", error=str(e))

        self._browsers.clear()
        self._context_counts.clear()

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None

        self._initialized = False
        self._pw_types = None
        logger.info("Browser pool cleaned up")

    def _sync_cleanup(self) -> None:
        """Synchronous cleanup for atexit handler."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.cleanup())
            else:
                loop.run_until_complete(self.cleanup())
        except Exception as e:
            logger.warning("Error in sync cleanup", error=str(e))

    @property
    def browser_count(self) -> int:
        """Return the number of active browsers."""
        return len([b for b in self._browsers if b.is_connected()])

    @property
    def total_context_count(self) -> int:
        """Return the total number of active contexts."""
        return sum(self._context_counts.values())

    def get_stats(self) -> dict[str, Any]:
        """Get pool statistics."""
        return {
            "initialized": self._initialized,
            "browser_count": self.browser_count,
            "max_browsers": self.max_browsers,
            "total_contexts": self.total_context_count,
            "max_contexts_per_browser": self.max_contexts_per_browser,
            "context_distribution": {
                i: self._context_counts.get(b, 0) for i, b in enumerate(self._browsers) if b.is_connected()
            },
        }


async def get_browser_pool(**kwargs: Any) -> BrowserPool:
    """Get the global browser pool instance.

    Args:
        **kwargs: Arguments passed to BrowserPool constructor.

    Returns:
        The singleton BrowserPool instance.
    """
    return await BrowserPool.get_instance(**kwargs)


async def cleanup_browser_pool() -> None:
    """Clean up the global browser pool."""
    await BrowserPool.reset_instance()
