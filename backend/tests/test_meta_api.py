"""GET /api/v1/meta — product edition and build metadata."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_meta_returns_standalone_edition(client: TestClient) -> None:
    r = client.get("/api/v1/meta")
    assert r.status_code == 200
    body = r.json()
    assert body["edition"] == "standalone"
    assert "app_name" in body and "version" in body
    assert "desktop_mode" in body and "local_mode" in body


def test_v1_responses_advertise_version_policy(client: TestClient) -> None:
    r = client.get("/api/v1/meta")

    assert r.headers["API-Version"] == "1"
    assert r.headers["Deprecation"] == "false"
    assert "rel=\"deprecation\"" in r.headers["Link"]
