"""Filesystem watcher that reloads custom node packs on change.

Uses ``watchdog`` when available; degrades to a no-op with a warning if
the dependency is not installed. Changes are debounced to avoid flapping
during bulk edits.
"""

from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import structlog

from .loader import load_directory
from .registry import NodeRegistry, get_registry

logger = structlog.get_logger(__name__)


class HotReloader:
    """Debounced filesystem watcher for a custom-nodes directory."""

    def __init__(
        self,
        path: str | Path,
        *,
        registry: NodeRegistry | None = None,
        debounce_sec: float = 0.5,
    ) -> None:
        self.path = Path(path)
        self.registry = registry or get_registry()
        self.debounce_sec = debounce_sec
        self._observer: object | None = None
        self._pending: dict[str, float] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        try:
            self._loop = loop or asyncio.get_event_loop()
        except RuntimeError:
            self._loop = None
        try:
            from watchdog.events import FileSystemEventHandler
            from watchdog.observers import Observer
        except ImportError:
            logger.warning("hot_reload_disabled_no_watchdog")
            return

        class _Handler(FileSystemEventHandler):
            def __init__(self, parent: "HotReloader") -> None:
                super().__init__()
                self._parent = parent

            def on_any_event(self, event) -> None:  # type: ignore[no-untyped-def]
                if event.is_directory:
                    return
                self._parent._schedule(event.src_path)

        observer = Observer()
        observer.schedule(_Handler(self), str(self.path), recursive=True)
        observer.start()
        self._observer = observer
        logger.info("hot_reload_started", path=str(self.path))

    def stop(self) -> None:
        if self._observer is None:
            return
        self._observer.stop()  # type: ignore[attr-defined]
        self._observer.join()  # type: ignore[attr-defined]
        self._observer = None

    def _schedule(self, src_path: str) -> None:
        with self._lock:
            self._pending[src_path] = time.monotonic()
        if self._loop is None:
            return
        self._loop.call_later(
            self.debounce_sec,
            lambda: asyncio.run_coroutine_threadsafe(self._maybe_fire(src_path), self._loop)  # type: ignore[arg-type]
            if self._loop else None,
        )

    async def _maybe_fire(self, src_path: str) -> None:
        with self._lock:
            first_seen = self._pending.get(src_path)
        if first_seen is None:
            return
        if time.monotonic() - first_seen < self.debounce_sec:
            return
        with self._lock:
            self._pending.pop(src_path, None)
        try:
            await load_directory(self.path, self.registry, run_prestartup=False)
            logger.info("hot_reload_applied", src_path=src_path)
        except Exception:  # noqa: BLE001
            logger.error("hot_reload_failed", src_path=src_path, exc_info=True)

    async def reload_all(self) -> None:
        """Manual reload trigger used by the admin API endpoint."""
        await load_directory(self.path, self.registry, run_prestartup=False)
