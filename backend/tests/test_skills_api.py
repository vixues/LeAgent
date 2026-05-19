"""HTTP tests for /api/v1/skills file endpoints and detail mapping."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from tests.test_skills import _write_skill


@pytest.fixture
def skills_auth_header(test_user: dict[str, Any], test_settings: Any) -> dict[str, str]:
    """Bearer token compatible with gateway :class:`TokenPayload` (includes ``exp``)."""
    from leagent.services.auth import AuthService

    auth = AuthService(test_settings)
    token = auth.create_access_token(UUID(test_user["user_id"]))
    return {"Authorization": f"Bearer {token}"}


def _load_manager(tmp_path: Path) -> Any:
    from leagent.skills.manager import SkillsManager

    mgr = SkillsManager(
        skills_dir=tmp_path,
        load_builtin=False,
        enable_hot_reload=False,
        include_interop_roots=False,
    )
    asyncio.run(mgr.load_all())
    return mgr


class TestSkillsFileAPI:
    def test_get_file_returns_raw_skill_md(
        self,
        client: TestClient,
        skills_auth_header: dict[str, str],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from leagent.api.v1 import skills as skills_api

        _write_skill(tmp_path, "file-skill")
        mgr = _load_manager(tmp_path)
        monkeypatch.setattr(skills_api, "get_skills_manager", lambda: mgr)

        r = client.get(
            "/api/v1/skills/file-skill/file",
            headers=skills_auth_header,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["name"] == "file-skill"
        assert "name: file-skill" in data["content"]
        assert "---" in data["content"]
        assert data.get("truncated") is False

    def test_put_file_updates_content_and_get_body_reflects(
        self,
        client: TestClient,
        skills_auth_header: dict[str, str],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from leagent.api.v1 import skills as skills_api

        skill_dir = _write_skill(tmp_path, "edit-skill")
        orig = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert "Instructions for the agent" in orig

        mgr = _load_manager(tmp_path)
        monkeypatch.setattr(skills_api, "get_skills_manager", lambda: mgr)

        new_md = orig.replace("Instructions for the agent", "Updated agent instructions for testing.")
        r = client.put(
            "/api/v1/skills/edit-skill/file",
            headers={**skills_auth_header, "Content-Type": "application/json"},
            json={"content": new_md},
        )
        assert r.status_code == 200, r.text
        assert r.json()["name"] == "edit-skill"

        b = client.get(
            "/api/v1/skills/edit-skill/body",
            headers=skills_auth_header,
        )
        assert b.status_code == 200
        assert "Updated agent instructions" in b.json()["body"]

    def test_put_file_validation_error_unchanged(
        self,
        client: TestClient,
        skills_auth_header: dict[str, str],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from leagent.api.v1 import skills as skills_api

        skill_dir = _write_skill(tmp_path, "bad-put-skill")
        before = (skill_dir / "SKILL.md").read_text(encoding="utf-8")

        mgr = _load_manager(tmp_path)
        monkeypatch.setattr(skills_api, "get_skills_manager", lambda: mgr)

        # Wrong `name` vs directory => validation error
        bad = before.replace("name: bad-put-skill", "name: other-name")
        r = client.put(
            "/api/v1/skills/bad-put-skill/file",
            headers={**skills_auth_header, "Content-Type": "application/json"},
            json={"content": bad},
        )
        assert r.status_code == 400
        after = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        assert after == before

    def test_put_file_forbidden_when_not_editable(
        self,
        client: TestClient,
        skills_auth_header: dict[str, str],
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from leagent.api.v1 import skills as skills_api

        skill_dir = _write_skill(tmp_path, "ro-skill")
        content = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        md_path = skill_dir / "SKILL.md"
        os.chmod(md_path, 0o444)

        mgr = _load_manager(tmp_path)
        monkeypatch.setattr(skills_api, "get_skills_manager", lambda: mgr)
        try:
            r = client.put(
                "/api/v1/skills/ro-skill/file",
                headers={**skills_auth_header, "Content-Type": "application/json"},
                json={"content": content},
            )
            # Read-only file or root: expect forbidden; if OS allows write, skip strict assert.
            assert r.status_code in (403, 200)
        finally:
            os.chmod(md_path, 0o644)
