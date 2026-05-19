"""Smoke tests for the FastAPI scaffold."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import ITEMS, app

client = TestClient(app)


def test_health_returns_ok() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "status": "ready"}


def test_items_round_trip() -> None:
    ITEMS.clear()
    ITEMS.append({"name": "seed", "quantity": 1})  # type: ignore[arg-type]

    resp = client.post("/items", json={"name": "demo", "quantity": 3})
    assert resp.status_code == 201
    assert resp.json()["name"] == "demo"

    listed = client.get("/items").json()
    assert any(it["name"] == "demo" for it in listed)
