"""Shared pytest fixtures for the LeAgent test suite.

Intentional skips elsewhere (do not remove without product scope):

- ``test_path_sandbox.py``: strict sandbox mode; desktop builds use unrestricted
  paths — see ``test_path_sandbox_desktop.py``.
- ``test_doc_tools.py``: ``skipif`` when PyMuPDF/pandas stacks are missing (install
  ``uv sync --extra dev``, which includes the doc-tool wheels).
- ``test_code_execution.py``: unrestricted subprocess workspace boundaries (policy).

"""

from __future__ import annotations

import os
from pathlib import Path

# Before any ``import leagent.*``: ``leagent.config.constants`` snapshots
# ``LEAGENT_HOME`` at import time; default ``~/.leagent`` breaks CI / parallel
# runs and can hit permission / lock issues on Windows.
_backend_root = Path(__file__).resolve().parent.parent
_wa_pytest = _backend_root / ".pytest_leagent_home"
_wa_pytest.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("LEAGENT_HOME", str(_wa_pytest.resolve()))
# Force skip duplicate deferred mounts in lifespan (``setdefault`` would not override a user shell env).
os.environ["LEAGENT_SKIP_LIFESPAN_DEFERRED_ROUTES"] = "1"
# Deterministic routing: a developer ``LEAGENT_FRONTEND_DIST`` would mount StaticFiles
# before deferred routes (405/404). Tests mount SPA last via ``mount_frontend_spa_if_configured``.
os.environ.pop("LEAGENT_FRONTEND_DIST", None)

pytest_plugins = [
    "tests.fixtures.sample_files",
    "tests.fixtures.excel_analysis",
]

import asyncio
import tempfile
import uuid
from typing import Any, AsyncIterator, Iterator
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from leagent.services.auth.service import LOCAL_USER_ID
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from leagent.agent.base import AgentConfig, AgentContext, AgentMode, AgentState
from leagent.config.settings import Settings, get_settings
from leagent.main import create_app, mount_frontend_spa_if_configured

# Force-import every model module so SQLModel.metadata sees the full schema
# (the test DB is created via ``SQLModel.metadata.create_all``). Forgetting a
# model here leads to confusing "no such table" failures in tests that only
# indirectly touch the missing entity — explicit is better than implicit.
import leagent.services.database.models  # noqa: F401
from leagent.tools.base import ToolCategory, ToolContext
from leagent.tools.registry import ToolRegistry


def pytest_configure(config: pytest.Config) -> None:
    """Register warning filters early (belt-and-suspenders with ``pyproject.toml``).

    Ensures teardown noise from asyncio subprocess ``__del__`` and aiosqlite worker
    threads does not appear when pytest discovers config from a non-backend CWD.
    """
    import warnings

    warnings.filterwarnings("ignore", category=pytest.PytestUnraisableExceptionWarning)
    warnings.filterwarnings("ignore", category=pytest.PytestUnhandledThreadExceptionWarning)


TEST_DB_URL = "sqlite+aiosqlite:///./test.db"


@pytest.fixture(autouse=True, scope="session")
def _widen_sandbox_for_tests():
    """Allow /tmp and system temp during tests so tmp_path works with the sandbox."""
    from leagent.file.sandbox import reset_roots

    old = os.environ.get("LEAGENT_TOOL_FILE_ROOTS")
    system_tmp = str(Path(tempfile.gettempdir()).resolve())
    os.environ["LEAGENT_TOOL_FILE_ROOTS"] = (
        f"/tmp,/tmp/leagent/files,{system_tmp}"
    )
    reset_roots()
    yield
    if old is None:
        os.environ.pop("LEAGENT_TOOL_FILE_ROOTS", None)
    else:
        os.environ["LEAGENT_TOOL_FILE_ROOTS"] = old
    reset_roots()


@pytest.fixture(scope="session")
def test_settings() -> Settings:
    """Return settings configured for the test environment."""
    settings = get_settings()
    settings.debug = True
    settings.environment = "development"
    settings.database.driver = "sqlite+aiosqlite"
    return settings


@pytest.fixture(scope="session")
def app(test_settings: Settings):  # type: ignore[no-untyped-def]
    """Create a FastAPI application instance for testing.

    The production ``create_app()`` registers deferred routers inside
    ``main._post_startup_warmup``. ``TestClient`` runs lifespan; we still mount
    deferred routes here when ``LEAGENT_SKIP_LIFESPAN_DEFERRED_ROUTES=1`` so
    warmup does not double-register paths (405). SPA static files mount last via
    ``mount_frontend_spa_if_configured`` so they cannot shadow API routes.
    """
    from fastapi import APIRouter

    application = create_app()

    from leagent.api.router_deferred import (
        mount_v1_deferred_routes,
        mount_v2_deferred_routes,
    )

    deferred_v1 = APIRouter(prefix="/api/v1")
    deferred_v2 = APIRouter(prefix="/api/v2")
    mount_v1_deferred_routes(deferred_v1)
    mount_v2_deferred_routes(deferred_v2)
    application.include_router(deferred_v1)
    application.include_router(deferred_v2)
    mount_frontend_spa_if_configured(application)

    ev = asyncio.Event()
    ev.set()
    application.state.post_startup_warmup = ev

    return application


@pytest.fixture()
def client(app) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    """Synchronous test client."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest_asyncio.fixture()
async def async_client(app) -> AsyncIterator[AsyncClient]:  # type: ignore[no-untyped-def]
    """Async test client using httpx."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture()
async def db_session() -> AsyncIterator[AsyncSession]:
    """Create a temporary in-memory database session for a single test."""
    engine = create_async_engine(TEST_DB_URL, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

    await engine.dispose()


@pytest.fixture()
def test_user(test_settings: Settings) -> dict[str, Any]:
    """Return a dict representing the implicit local user."""
    user_id = str(LOCAL_USER_ID)
    return {
        "user_id": user_id,
        "username": "local",
        "role": "admin",
        "department": "engineering",
        "token": "local-token",
        "auth_header": {},
    }


@pytest.fixture()
def test_viewer_user(test_settings: Settings) -> dict[str, Any]:
    user_id = str(LOCAL_USER_ID)
    return {
        "user_id": user_id,
        "username": "local",
        "role": "admin",
        "department": "general",
        "token": "local-token",
        "auth_header": {},
    }


# ---------------------------------------------------------------------------
# Tool-layer fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tool_context() -> ToolContext:
    """Minimal ToolContext sufficient for unit-testing tools."""
    return ToolContext(
        user_id="test-user-id",
        session_id="test-session-id",
    )


@pytest.fixture()
def tool_registry() -> ToolRegistry:
    """Fresh ToolRegistry instance per test."""
    return ToolRegistry()


# ---------------------------------------------------------------------------
# Agent-layer fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def agent_config() -> AgentConfig:
    """Default agent config for tests."""
    return AgentConfig(
        max_iterations=5,
        default_timeout_sec=30,
        mode=AgentMode.REACT,
        enable_planning=False,
        enable_memory=False,
        enable_streaming=False,
        verbose=False,
    )


@pytest.fixture()
def agent_context(agent_config: AgentConfig) -> AgentContext:
    """Minimal AgentContext with mocked services."""
    ctx = AgentContext(
        task_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        config=agent_config,
        state=AgentState.IDLE,
    )
    ctx.tools = MagicMock()
    ctx.llm = MagicMock()
    ctx.agent_memory = None
    return ctx


@pytest.fixture()
def mock_llm_service() -> MagicMock:
    """Mock LLMService that returns canned responses."""
    svc = MagicMock()
    svc.complete = AsyncMock(return_value=MagicMock(
        content="mock response",
        tool_calls=None,
        usage=MagicMock(prompt_tokens=10, completion_tokens=20, total_tokens=30),
    ))
    svc.stream = AsyncMock(return_value=iter([]))
    return svc


@pytest.fixture()
def mock_registry() -> MagicMock:
    """Mock ToolRegistry."""
    reg = MagicMock(spec=ToolRegistry)
    reg.get = MagicMock(return_value=None)
    reg.list_all = MagicMock(return_value=[])
    return reg
