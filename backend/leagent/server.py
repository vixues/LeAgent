"""Uvicorn / Gunicorn launcher utilities."""

from __future__ import annotations

import multiprocessing
import os
from argparse import ArgumentParser


def run_uvicorn(
    host: str = "0.0.0.0",
    port: int = 7860,
    workers: int = 1,
    reload: bool = False,
    log_level: str = "info",
) -> None:
    """Launch the application with Uvicorn."""
    import uvicorn

    uvicorn.run(
        "leagent.main:app",
        host=host,
        port=port,
        workers=workers,
        reload=reload,
        log_level=log_level,
        timeout_keep_alive=120,
        limit_concurrency=200,
        # Access logging is handled by AccessLogMiddleware (structured, with
        # correlation IDs). Disable uvicorn's duplicate access log.
        access_log=False,
    )


def run_gunicorn(
    host: str = "0.0.0.0",
    port: int = 7860,
    workers: int | None = None,
    log_level: str = "info",
) -> None:
    """Launch the application with Gunicorn + Uvicorn workers (production)."""
    from gunicorn.app.base import BaseApplication

    effective_workers = workers or _default_worker_count()

    class LeAgentApplication(BaseApplication):  # type: ignore[misc]
        def __init__(self, options: dict | None = None) -> None:
            self.options = options or {}
            super().__init__()

        def load_config(self) -> None:
            for key, value in self.options.items():
                if key in self.cfg.settings and value is not None:
                    self.cfg.set(key.lower(), value)

        def load(self):  # type: ignore[override]
            from leagent.main import app

            return app

    options = {
        "bind": f"{host}:{port}",
        "workers": effective_workers,
        "worker_class": "uvicorn.workers.UvicornWorker",
        "loglevel": log_level,
        "timeout": 300,
        "graceful_timeout": 30,
        "keepalive": 120,
        "max_requests": 5000,
        "max_requests_jitter": 500,
        "preload_app": False,
        # Access logging handled by AccessLogMiddleware; keep only error log.
        "errorlog": "-",
    }

    LeAgentApplication(options).run()


def _default_worker_count() -> int:
    cpu_count = multiprocessing.cpu_count()
    env_override = os.getenv("LEAGENT_WORKERS")
    if env_override:
        return int(env_override)
    return min(cpu_count * 2 + 1, 8)


def main() -> None:
    """Command-line entrypoint for ``python -m leagent.server``."""
    parser = ArgumentParser(description="Run the LeAgent FastAPI server.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=7860)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    run_uvicorn(
        host=args.host,
        port=args.port,
        workers=args.workers,
        reload=args.reload,
        log_level=args.log_level,
    )


if __name__ == "__main__":
    main()
