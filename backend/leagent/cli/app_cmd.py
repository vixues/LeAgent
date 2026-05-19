"""CLI commands for the FastAPI ASGI process (``leagent.main:app``)."""

from __future__ import annotations

import click

from leagent.cli.utils import console, print_error, print_info, print_success


@click.group(name="app")
def app_group() -> None:
    """Start or probe the HTTP monolith (REST, SSE, WebSockets, workflows, chat APIs)."""


@app_group.command(name="start")
@click.option(
    "--host",
    "-h",
    default="0.0.0.0",
    help="Host address to bind to.",
    show_default=True,
)
@click.option(
    "--port",
    "-p",
    default=7860,
    type=int,
    help="Port to bind to.",
    show_default=True,
)
@click.option(
    "--workers",
    "-w",
    default=1,
    type=int,
    help="Number of worker processes.",
    show_default=True,
)
@click.option(
    "--reload",
    "-r",
    is_flag=True,
    help="Enable auto-reload for development.",
)
@click.option(
    "--log-level",
    "-l",
    type=click.Choice(["debug", "info", "warning", "error", "critical"]),
    default="info",
    help="Logging level.",
    show_default=True,
)
@click.option(
    "--production",
    is_flag=True,
    help="Run with Gunicorn for production deployment.",
)
@click.option(
    "--ssl-keyfile",
    type=click.Path(exists=True),
    default=None,
    help="Path to SSL key file.",
)
@click.option(
    "--ssl-certfile",
    type=click.Path(exists=True),
    default=None,
    help="Path to SSL certificate file.",
)
def start(
    host: str,
    port: int,
    workers: int,
    reload: bool,
    log_level: str,
    production: bool,
    ssl_keyfile: str | None,
    ssl_certfile: str | None,
) -> None:
    """Start ``leagent.main:app`` (Uvicorn by default, or Gunicorn with ``--production``).

    On startup the app runs ``ServiceManager``, optional Alembic migrations, and
    ``bootstrap_tools()`` so HTTP chat sessions match the same tool surface as the CLI.
    """
    if reload and production:
        print_error("Cannot use --reload with --production mode.")
        raise click.Abort()

    if reload and workers > 1:
        print_info("Auto-reload requires single worker, setting workers=1")
        workers = 1

    console.print()
    console.rule("[bold cyan]LeAgent Server[/]")
    console.print()
    console.print(f"  [dim]Host:[/]       {host}")
    console.print(f"  [dim]Port:[/]       {port}")
    console.print(f"  [dim]Workers:[/]    {workers}")
    console.print(f"  [dim]Log Level:[/]  {log_level}")
    console.print(f"  [dim]Mode:[/]       {'Production (Gunicorn)' if production else 'Development (Uvicorn)'}")
    if reload:
        console.print(f"  [dim]Auto-reload:[/] Enabled")
    if ssl_keyfile:
        console.print(f"  [dim]SSL:[/]        Enabled")
    console.print()

    if production:
        _run_gunicorn(host, port, workers, log_level, ssl_keyfile, ssl_certfile)
    else:
        _run_uvicorn(host, port, workers, reload, log_level, ssl_keyfile, ssl_certfile)


def _run_uvicorn(
    host: str,
    port: int,
    workers: int,
    reload: bool,
    log_level: str,
    ssl_keyfile: str | None,
    ssl_certfile: str | None,
) -> None:
    """Start the server with Uvicorn."""
    try:
        import uvicorn
    except ImportError:
        print_error("uvicorn is not installed. Install it with: pip install uvicorn")
        raise click.Abort()

    print_success(f"Starting Uvicorn server on {host}:{port}")
    console.print("[dim]Press Ctrl+C to stop.[/]\n")

    uvicorn_kwargs: dict = {
        "app": "leagent.main:app",
        "host": host,
        "port": port,
        "workers": workers,
        "reload": reload,
        "log_level": log_level,
        "timeout_keep_alive": 120,
        "limit_concurrency": 200,
        "access_log": True,
    }

    if ssl_keyfile and ssl_certfile:
        uvicorn_kwargs["ssl_keyfile"] = ssl_keyfile
        uvicorn_kwargs["ssl_certfile"] = ssl_certfile

    uvicorn.run(**uvicorn_kwargs)


def _run_gunicorn(
    host: str,
    port: int,
    workers: int,
    log_level: str,
    ssl_keyfile: str | None,
    ssl_certfile: str | None,
) -> None:
    """Start the server with Gunicorn."""
    try:
        from gunicorn.app.base import BaseApplication
    except ImportError:
        print_error("gunicorn is not installed. Install it with: pip install gunicorn")
        raise click.Abort()

    import multiprocessing
    import os

    if workers <= 0:
        cpu_count = multiprocessing.cpu_count()
        env_override = os.getenv("LEAGENT_WORKERS")
        if env_override:
            workers = int(env_override)
        else:
            workers = min(cpu_count * 2 + 1, 8)

    class LeAgentApplication(BaseApplication):
        def __init__(self, options: dict | None = None) -> None:
            self.options = options or {}
            super().__init__()

        def load_config(self) -> None:
            for key, value in self.options.items():
                if key in self.cfg.settings and value is not None:
                    self.cfg.set(key.lower(), value)

        def load(self):
            from leagent.main import app

            return app

    options: dict = {
        "bind": f"{host}:{port}",
        "workers": workers,
        "worker_class": "uvicorn.workers.UvicornWorker",
        "loglevel": log_level,
        "timeout": 300,
        "graceful_timeout": 30,
        "keepalive": 120,
        "max_requests": 5000,
        "max_requests_jitter": 500,
        "preload_app": False,
        "accesslog": "-",
        "errorlog": "-",
    }

    if ssl_keyfile and ssl_certfile:
        options["keyfile"] = ssl_keyfile
        options["certfile"] = ssl_certfile

    print_success(f"Starting Gunicorn server on {host}:{port} with {workers} workers")
    console.print("[dim]Press Ctrl+C to stop.[/]\n")

    LeAgentApplication(options).run()


@app_group.command(name="check")
@click.option(
    "--url",
    default="http://localhost:7860",
    help="Server URL to check.",
    show_default=True,
)
def check(url: str) -> None:
    """Check if the LeAgent server is running and healthy."""
    import httpx

    console.print(f"Checking server at {url}...")

    try:
        response = httpx.get(f"{url}/health", timeout=5.0)
        if response.status_code == 200:
            print_success("Server is healthy and responding.")
            data = response.json()
            if data:
                console.print(f"  [dim]Status:[/] {data.get('status', 'ok')}")
                console.print(f"  [dim]Version:[/] {data.get('version', 'unknown')}")
        else:
            print_error(f"Server returned status {response.status_code}")
    except httpx.ConnectError:
        print_error(f"Cannot connect to server at {url}")
        console.print("[dim]The server may not be running. Start it with: leagent app start[/]")
    except httpx.TimeoutException:
        print_error("Connection timed out")
    except Exception as e:
        print_error(f"Health check failed: {e}")
