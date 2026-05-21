"""Tests for GET /api/v1/canvas/preview/screenshot (Playwright render → PNG/JPEG)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from leagent.api.v1 import canvas as canvas_api
from leagent.api.v1.canvas import _content_disposition
from leagent.services.database.models.canvas import CanvasContentType, CanvasDocument


@pytest.fixture
def canvas_screenshot_stub(app):  # type: ignore[no-untyped-def]
    """Stub canvas dependency: skip JWT/DB; still exercises Playwright in the route."""
    cid = uuid4()
    doc = CanvasDocument(
        id=uuid4(),
        canvas_id=cid,
        revision=1,
        session_id=uuid4(),
        user_id=uuid4(),
        title="ScreenshotTest",
        content_type=CanvasContentType.HTML.value,
        html_body=(
            '<main class="p-6"><h1 class="text-xl font-semibold text-slate-800">'
            "Canvas Screenshot</h1>"
            '<p class="text-slate-600">playwright-ok</p></main>'
        ),
    )
    mock = MagicMock()
    mock.load_verified_from_token = AsyncMock(return_value=doc)
    app.dependency_overrides[canvas_api._canvas_dep] = lambda: mock
    yield
    app.dependency_overrides.pop(canvas_api._canvas_dep, None)


def test_canvas_preview_screenshot_returns_png(
    client: TestClient,
    app,
    canvas_screenshot_stub,
) -> None:
    resp = client.get(
        "/api/v1/canvas/preview/screenshot",
        params={"token": "dummy-token-value-32chars!!", "format": "png", "width": 640, "height": 480},
    )
    if resp.status_code == 503:
        pytest.skip("Playwright/Chromium unavailable: " + resp.text[:200])
    assert resp.status_code == 200, resp.text
    ct = resp.headers.get("content-type", "")
    assert "image/png" in ct
    body = resp.content
    assert len(body) > 200, "PNG should have non-trivial payload"
    assert body.startswith(b"\x89PNG\r\n\x1a\n")


def test_content_disposition_unicode_title_is_latin1_safe() -> None:
    header = _content_disposition("inline", "LeAgent vs OpenClaw — 表格对比.png")
    header.encode("latin-1")
    assert "filename*=" in header
    assert "表格对比" in header


def test_canvas_preview_screenshot_unicode_title(
    client: TestClient,
    app,
) -> None:
    cid = uuid4()
    doc = CanvasDocument(
        id=uuid4(),
        canvas_id=cid,
        revision=1,
        session_id=uuid4(),
        user_id=uuid4(),
        title="LeAgent vs OpenClaw — 表格对比",
        content_type=CanvasContentType.HTML.value,
        html_body='<main class="p-6"><h1>表格</h1></main>',
    )
    mock = MagicMock()
    mock.load_verified_from_token = AsyncMock(return_value=doc)
    app.dependency_overrides[canvas_api._canvas_dep] = lambda: mock
    try:
        resp = client.get(
            "/api/v1/canvas/preview/screenshot",
            params={"token": "dummy-token-value-32chars!!", "format": "png"},
        )
        if resp.status_code == 503:
            pytest.skip("Playwright/Chromium unavailable: " + resp.text[:200])
        assert resp.status_code == 200, resp.text
        disp = resp.headers.get("content-disposition", "")
        disp.encode("latin-1")
        assert resp.content.startswith(b"\x89PNG\r\n\x1a\n")
    finally:
        app.dependency_overrides.pop(canvas_api._canvas_dep, None)


def test_canvas_preview_screenshot_invalid_token_403(client: TestClient, app) -> None:
    mock = MagicMock()
    mock.load_verified_from_token = AsyncMock(return_value=None)
    app.dependency_overrides[canvas_api._canvas_dep] = lambda: mock
    try:
        resp = client.get(
            "/api/v1/canvas/preview/screenshot",
            params={"token": "expired-or-bad-token-32chars!!"},
        )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(canvas_api._canvas_dep, None)
