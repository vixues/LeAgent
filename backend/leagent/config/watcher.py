"""File-based configuration watcher with callback support."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from leagent.config.config import Config, load_config
from leagent.config.constants import CONFIG_PATH

logger = logging.getLogger(__name__)

CallbackFn = Callable[[str, Any, Any], Awaitable[None]]


class ConfigWatcher:
    """Polls a YAML config file for changes and triggers section-specific callbacks."""

    def __init__(
        self,
        config_path: Path | str | None = None,
        poll_interval: float = 5.0,
    ) -> None:
        self._config_path = Path(config_path) if config_path else CONFIG_PATH
        self.poll_interval = poll_interval
        self._callbacks: dict[str, list[CallbackFn]] = {}
        self._current_config: Config | None = None
        self._task: asyncio.Task[None] | None = None
        self._running = False

    def on_change(self, section: str, callback: CallbackFn) -> None:
        """Register a callback for changes in a specific config section."""
        self._callbacks.setdefault(section, []).append(callback)

    async def start(self) -> None:
        """Start the background polling loop."""
        if self._running:
            return
        self._current_config = load_config(self._config_path)
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        logger.info("ConfigWatcher started (poll_interval=%.1fs)", self.poll_interval)

    async def stop(self) -> None:
        """Stop the background polling loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("ConfigWatcher stopped")

    async def _watch_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self.poll_interval)
                await self._check_for_changes()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in config watch loop")

    async def _check_for_changes(self) -> None:
        if not self._config_path.exists():
            return

        new_config = load_config(self._config_path)
        if self._current_config is None:
            self._current_config = new_config
            return

        diffs = self._diff_configs(self._current_config, new_config)
        if diffs:
            logger.info("Config changes detected in sections: %s", list(diffs.keys()))
            self._current_config = new_config
            await self._trigger_callbacks(diffs, new_config)

    def _diff_configs(self, old: Config, new: Config) -> dict[str, tuple[Any, Any]]:
        """Compare two configs and return a dict of changed sections."""
        old_dict = old.model_dump(mode="json")
        new_dict = new.model_dump(mode="json")
        diffs: dict[str, tuple[Any, Any]] = {}

        for key in set(old_dict.keys()) | set(new_dict.keys()):
            old_val = old_dict.get(key)
            new_val = new_dict.get(key)
            if old_val != new_val:
                diffs[key] = (old_val, new_val)

        return diffs

    async def _trigger_callbacks(
        self,
        diffs: dict[str, tuple[Any, Any]],
        new_config: Config,
    ) -> None:
        for section, (old_val, new_val) in diffs.items():
            callbacks = self._callbacks.get(section, [])
            for cb in callbacks:
                try:
                    await cb(section, old_val, new_val)
                except Exception:
                    logger.exception("Error in config callback for section '%s'", section)

            wildcard_callbacks = self._callbacks.get("*", [])
            for cb in wildcard_callbacks:
                try:
                    await cb(section, old_val, new_val)
                except Exception:
                    logger.exception("Error in wildcard config callback for section '%s'", section)
