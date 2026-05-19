"""HTTP smoke tests for ``/api/v1/coding-projects/...``.

These tests run the FastAPI app via ``TestClient`` with a mocked
manager — we don't want to spawn real dev servers from the API
suite (the dedicated ``test_coding_projects_devserver.py`` covers
that). The goal is to verify routing, schema validation, auth, and
preview-token handling.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from leagent.services.auth.tokens import mint_token

from leagent.config.settings import get_settings
from leagent.services.auth.deps import get_current_user_id
from leagent.services.coding_projects.preview_tokens import (
    PREVIEW_AUDIENCE,
    mint_preview_token,
)
from leagent.services.database.models import (
    CodingProject,
    CodingProjectRuntimeKind,
    CodingProjectStatus,
)


def _project_row(user_id: UUID, **overrides: Any) -> CodingProject:
    base = dict(
        id=uuid4(),
        user_id=user_id,
        folder_id=None,
        name="demo",
        description=None,
        template="vanilla-html",
        runtime_kind=CodingProjectRuntimeKind.FRONTEND,
        root_path="/tmp/demo",
        port=None,
        pid=None,
        status=CodingProjectStatus.IDLE,
        last_started_at=None,
        last_stopped_at=None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        is_deleted=False,
    )
    base.update(overrides)
    return CodingProject(**base)


@pytest.fixture()
def fake_manager(
    monkeypatch: pytest.MonkeyPatch, app, test_user: dict[str, Any]
) -> MagicMock:
    """Patch the API's manager getter and override the auth dep."""
    manager = MagicMock()
    manager.list_for_user = AsyncMock(return_value=[])
    manager.get_for_user = AsyncMock()
    manager.scaffold = AsyncMock()
    manager.start = AsyncMock()
    manager.stop = AsyncMock()
    manager.delete = AsyncMock()
    manager.snapshot_logs = MagicMock(return_value=[])

    sup = MagicMock()
    sup.is_running = MagicMock(return_value=False)
    sup.get = MagicMock(return_value=None)
    manager.supervisor = sup
    manager.build_preview_url = MagicMock(
        side_effect=lambda pid, token, sub_path="": f"/api/v1/coding-projects/{pid}/preview/?token={token}"
    )

    def _get_template(name: str) -> Any:
        m = MagicMock()
        m.health_path = "/"
        return m

    manager.get_template = _get_template

    monkeypatch.setattr(
        "leagent.services.coding_projects.manager.get_coding_projects_service",
        lambda: manager,
    )

    # The conftest test_user JWT doesn't include `exp`, so the regular
    # auth dep rejects it. Override with a constant so the API tests
    # can focus on routing + payload shape.
    user_id = UUID(test_user["user_id"])
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    yield manager
    app.dependency_overrides.pop(get_current_user_id, None)


def test_list_templates_returns_builtins(
    client: TestClient, test_user: dict[str, Any], fake_manager: MagicMock
) -> None:
    resp = client.get(
        "/api/v1/coding-projects/templates",
        headers=test_user["auth_header"],
    )
    assert resp.status_code == 200
    data = resp.json()
    names = {row["name"] for row in data}
    assert {"vanilla-html", "vite-react", "fastapi"}.issubset(names)


def test_create_project_calls_manager(
    client: TestClient, test_user: dict[str, Any], fake_manager: MagicMock
) -> None:
    user_id = UUID(test_user["user_id"])
    fake_manager.scaffold.return_value = _project_row(user_id, name="hi")

    resp = client.post(
        "/api/v1/coding-projects",
        json={"name": "hi", "template": "vanilla-html"},
        headers=test_user["auth_header"],
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "hi"
    fake_manager.scaffold.assert_awaited_once()


def test_run_returns_preview_url(
    client: TestClient, test_user: dict[str, Any], fake_manager: MagicMock
) -> None:
    user_id = UUID(test_user["user_id"])
    project = _project_row(user_id, status=CodingProjectStatus.RUNNING, port=39999)
    running = MagicMock(host="127.0.0.1", port=39999, pid=4242, run_seq=1)
    fake_manager.start.return_value = (project, running, "tok-123")

    resp = client.post(
        f"/api/v1/coding-projects/{project.id}/run",
        headers=test_user["auth_header"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["preview_url"].startswith(
        f"/api/v1/coding-projects/{project.id}/preview"
    )
    assert body["preview_token"] == "tok-123"
    assert body["port"] == 39999


def test_preview_proxy_rejects_invalid_token(
    client: TestClient, test_user: dict[str, Any], fake_manager: MagicMock
) -> None:
    project_id = uuid4()
    user_id = UUID(test_user["user_id"])
    fake_manager.get_for_user.return_value = _project_row(user_id, id=project_id)

    resp = client.get(
        f"/api/v1/coding-projects/{project_id}/preview/index.html?token=garbage",
        headers=test_user["auth_header"],
    )
    assert resp.status_code == 401


def test_preview_proxy_rejects_token_for_different_project(
    client: TestClient, test_user: dict[str, Any], fake_manager: MagicMock
) -> None:
    settings = get_settings()
    other_project = uuid4()
    user_id = UUID(test_user["user_id"])
    token = mint_preview_token(
        settings,
        project_id=other_project,
        run_seq=1,
        user_id=user_id,
    )
    target_project = uuid4()
    resp = client.get(
        f"/api/v1/coding-projects/{target_project}/preview/?token={token}",
        headers=test_user["auth_header"],
    )
    assert resp.status_code == 403


def test_preview_proxy_rejects_when_audience_wrong(
    client: TestClient, test_user: dict[str, Any], fake_manager: MagicMock
) -> None:
    settings = get_settings()
    project_id = uuid4()
    user_id = UUID(test_user["user_id"])
    payload = {
        "cpid": str(project_id),
        "run": 1,
        "sub": str(user_id),
        "iat": 0,
        "exp": 9_999_999_999,
        "aud": "not-our-audience",
    }
    secret = settings.canvas.preview_signing_secret or "leagent-local-secret"
    bogus = mint_token(payload, secret)
    resp = client.get(
        f"/api/v1/coding-projects/{project_id}/preview/?token={bogus}",
        headers=test_user["auth_header"],
    )
    assert resp.status_code == 401


def test_preview_audience_constant_is_unique() -> None:
    assert PREVIEW_AUDIENCE == "leagent-coding-preview"


def test_workspace_file_reads_text(
    tmp_path: Path,
    client: TestClient,
    test_user: dict[str, Any],
    fake_manager: MagicMock,
) -> None:
    user_id = UUID(test_user["user_id"])
    (tmp_path / "readme.txt").write_text("hello", encoding="utf-8")
    proj = _project_row(user_id, root_path=str(tmp_path))
    fake_manager.get_for_user.return_value = proj

    resp = client.get(
        f"/api/v1/coding-projects/{proj.id}/workspace/file",
        params={"path": "readme.txt"},
        headers=test_user["auth_header"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["content"] == "hello"
    assert body["truncated"] is False


def test_workspace_file_rejects_path_traversal(
    tmp_path: Path,
    client: TestClient,
    test_user: dict[str, Any],
    fake_manager: MagicMock,
) -> None:
    user_id = UUID(test_user["user_id"])
    proj = _project_row(user_id, root_path=str(tmp_path))
    fake_manager.get_for_user.return_value = proj

    resp = client.get(
        f"/api/v1/coding-projects/{proj.id}/workspace/file",
        params={"path": "../../etc/passwd"},
        headers=test_user["auth_header"],
    )
    assert resp.status_code == 400


def test_workspace_tree_lists_files(
    tmp_path: Path,
    client: TestClient,
    test_user: dict[str, Any],
    fake_manager: MagicMock,
) -> None:
    user_id = UUID(test_user["user_id"])
    (tmp_path / "alpha.txt").write_text("a")
    proj = _project_row(user_id, root_path=str(tmp_path))
    fake_manager.get_for_user.return_value = proj

    resp = client.get(
        f"/api/v1/coding-projects/{proj.id}/workspace/tree",
        headers=test_user["auth_header"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["root"]["type"] == "dir"
    names = {
        ch["name"]
        for ch in body["root"].get("children", [])
        if ch["type"] == "file"
    }
    assert "alpha.txt" in names


def test_workspace_git_smoke(
    tmp_path: Path,
    client: TestClient,
    test_user: dict[str, Any],
    fake_manager: MagicMock,
) -> None:
    user_id = UUID(test_user["user_id"])
    proj = _project_row(user_id, root_path=str(tmp_path))
    fake_manager.get_for_user.return_value = proj

    resp = client.get(
        f"/api/v1/coding-projects/{proj.id}/workspace/git",
        headers=test_user["auth_header"],
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "is_git" in body
    assert "git_available" in body
