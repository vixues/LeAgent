"""Real dev-server integration tests for the coding-project supervisor.

Two flows are exercised:

* ``vanilla-html`` boots ``python -m http.server``; the supervisor's
  reverse proxy is bypassed and we hit the bound port directly with
  :class:`httpx.AsyncClient` so we don't depend on the FastAPI app
  fixture.
* ``fastapi`` boots ``uvicorn`` against the scaffold and asserts the
  ``/health`` route returns ``{"ok": true}``.

The Vite template is intentionally **not** booted here — it requires
``npm install`` which is too heavy for unit tests. ``test_coding_projects_manager.py``
covers its template metadata.
"""

from __future__ import annotations

import asyncio
import shutil
import socket
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from tests.test_coding_projects_manager import FakeDB  # type: ignore[no-redef]

from leagent.config.settings import Settings, get_settings
from leagent.services.coding_projects.manager import CodingProjectManager
from leagent.services.coding_projects.runtime import DevServerSupervisor


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest_asyncio.fixture()
async def fake_db() -> FakeDB:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    yield FakeDB(factory)
    await engine.dispose()


@pytest.fixture()
def settings_with_root(tmp_path: Path) -> Settings:
    settings = get_settings()
    settings.coding_projects.root = str(tmp_path / "scratch")
    settings.coding_projects.bind_host = "127.0.0.1"
    settings.coding_projects.port_range_min = 49700
    settings.coding_projects.port_range_max = 49799
    settings.coding_projects.dev_server_startup_timeout_sec = 30
    return settings


@pytest.mark.asyncio
async def test_vanilla_html_dev_server_boots(
    fake_db: FakeDB, settings_with_root: Settings
) -> None:
    if shutil.which("python") is None and shutil.which("python3") is None:
        pytest.skip("python interpreter not on PATH")

    manager = CodingProjectManager(settings_with_root, fake_db)  # type: ignore[arg-type]
    project = await manager.scaffold(
        user_id=uuid4(),
        name="vanilla-test",
        template="vanilla-html",
    )

    server = manager.supervisor
    # Port allocation runs through the manager.start path, which also
    # constructs the argv from the template metadata.
    project_obj, running, token = await manager.start(
        project_id=project.id, user_id=project.user_id
    )
    try:
        assert running.host == "127.0.0.1"
        # Hit the bound port directly so we don't depend on a FastAPI
        # app being mounted in this test. ``trust_env=False`` keeps any
        # corporate HTTP proxy on the developer machine out of the loop.
        async with httpx.AsyncClient(
            timeout=5.0,
            trust_env=False,
            mounts={"all://": httpx.AsyncHTTPTransport(retries=0)},
        ) as client:
            for attempt in range(60):
                try:
                    resp = await client.get(
                        f"http://127.0.0.1:{running.port}/index.html"
                    )
                    if resp.status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                await asyncio.sleep(0.5)
            else:
                logs = manager.snapshot_logs(project.id, max_lines=50)
                pretty = "\n".join(
                    f"[{l.stream}] {l.text}" for l in logs
                ) or "(no log lines captured)"
                pytest.fail(
                    f"vanilla-html server never answered on port "
                    f"{running.port}; supervisor running={server.is_running(project.id)}\n"
                    f"---logs---\n{pretty}"
                )
        assert "Hello from LeAgent" in resp.text
    finally:
        await manager.stop(project_id=project.id, user_id=project.user_id)
    assert not server.is_running(project.id)
    assert token  # token was minted


@pytest.mark.asyncio
async def test_supervisor_force_kill_cleans_up(
    settings_with_root: Settings,
) -> None:
    """Even an uncooperative child gets reaped within graceful_timeout."""
    sup = DevServerSupervisor(
        log_buffer_lines=128,
        startup_timeout_sec=10,
    )
    project_id = uuid4()
    py = shutil.which("python") or shutil.which("python3")
    if not py:
        pytest.skip("python interpreter not on PATH")

    # A loop that ignores SIGTERM so we exercise the kill path.
    script = (
        "import signal, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "print('READY', flush=True)\n"
        "time.sleep(60)\n"
    )
    server = await sup.start(
        project_id=project_id,
        cwd=Path("."),
        argv=("python", "-c", script) if sys.platform.startswith("win") else (py, "-c", script),
        host="127.0.0.1",
        port=_free_port(),
        ready_regex=r"READY",
        startup_timeout_sec=10,
    )
    assert server.pid > 0
    await sup.stop(project_id, graceful_timeout=1.0)
    assert not sup.is_running(project_id)


@pytest.mark.asyncio
async def test_fastapi_template_health_check(
    fake_db: FakeDB, settings_with_root: Settings, tmp_path: Path
) -> None:
    if shutil.which("uvicorn") is None:
        pytest.skip("uvicorn binary not available; pip install uvicorn")
    # Make sure FastAPI itself is importable in this interpreter.
    try:
        import fastapi  # noqa: F401
    except ImportError:
        pytest.skip("fastapi not installed in test interpreter")

    settings_with_root.coding_projects.dev_server_startup_timeout_sec = 60
    manager = CodingProjectManager(settings_with_root, fake_db)  # type: ignore[arg-type]
    project = await manager.scaffold(
        user_id=uuid4(),
        name="fastapi-test",
        template="fastapi",
    )
    # The fastapi template lists ``needs_install``; in CI the test
    # interpreter already has fastapi+uvicorn so we skip the install
    # step by writing the marker file ourselves.
    template = manager.get_template(project.template)
    marker = Path(project.root_path) / template.install_marker_relpath
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("ok")

    project_obj, running, _token = await manager.start(
        project_id=project.id, user_id=project.user_id
    )
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            for _ in range(60):
                try:
                    resp = await client.get(
                        f"http://127.0.0.1:{running.port}/health"
                    )
                    if resp.status_code == 200:
                        break
                except httpx.RequestError:
                    pass
                await asyncio.sleep(0.5)
            else:
                pytest.fail("uvicorn never answered /health")
        body = resp.json()
        assert body["ok"] is True
    finally:
        await manager.stop(project_id=project.id, user_id=project.user_id)
