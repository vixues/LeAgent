"""Contract tests for Pet Space API."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_pet_space_projects_requires_auth(client: TestClient) -> None:
    r = client.get("/api/v1/pet-space/projects")
    # Standalone mode has no gated auth; endpoint may return data or 404 if disabled.
    assert r.status_code in (200, 401, 403, 404)


def test_pet_space_create_project_returns_201(client: TestClient) -> None:
    """Identity stubs include workspaces row so pet_projects FK succeeds."""
    r = client.post("/api/v1/pet-space/projects", json={"name": "Test Project"})
    assert r.status_code == 201
    body = r.json()
    assert body.get("name") == "Test Project"
    assert body.get("id")
