"""HTTP surface smoke tests for the workflow router.

These tests spin up a minimal FastAPI app, stub auth + DB dependencies,
and assert the canonical workflow endpoints are reachable with expected
shapes. They deliberately avoid ServiceManager startup.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from leagent.workflow.server.router import router as workflow_router


@pytest.fixture
def app_with_stubs():
    from leagent.services.auth.deps import get_current_user_id
    from leagent.services.database import get_database_service

    app = FastAPI()
    app.include_router(workflow_router, prefix="/api/v1")

    user_id = uuid4()

    async def _fake_user() -> str:
        return user_id

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def get(self, _cls, _id):
            return None

        async def exec(self, _q):
            class _Res:
                def all(self):
                    return []

                def one(self):
                    return 0

            return _Res()

    class _FakeDB:
        def session(self):
            return _FakeSession()

    app.dependency_overrides[get_current_user_id] = _fake_user
    app.dependency_overrides[get_database_service] = lambda: _FakeDB()
    yield app
    app.dependency_overrides.clear()


def test_object_info_returns_nodes(app_with_stubs):
    import asyncio

    from leagent.workflow.nodes import bootstrap

    asyncio.run(bootstrap())

    client = TestClient(app_with_stubs)
    resp = client.get("/api/v1/workflow/object_info")
    assert resp.status_code == 200
    data = resp.json()
    assert "nodes" in data
    assert "StartNode" in data["nodes"]


def test_get_flow_returns_404_when_missing(app_with_stubs):
    client = TestClient(app_with_stubs)
    resp = client.get(f"/api/v1/workflow/flows/{uuid4()}")
    assert resp.status_code == 404


def test_list_replacements_returns_list(app_with_stubs):
    client = TestClient(app_with_stubs)
    resp = client.get("/api/v1/workflow/admin/replacements")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
