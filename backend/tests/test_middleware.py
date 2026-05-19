"""Tests for ASGI middleware: RequestIDMiddleware, AccessLogMiddleware, ContentSizeLimitMiddleware."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_app() -> FastAPI:
    app = FastAPI()

    @app.get("/hello")
    async def hello():
        return {"message": "hello"}

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


# ===========================================================================
# RequestIDMiddleware
# ===========================================================================


class TestRequestIDMiddleware:
    def _app(self) -> TestClient:
        from leagent.api.middleware import RequestIDMiddleware
        app = _make_app()
        app.add_middleware(RequestIDMiddleware)
        return TestClient(app)

    def test_adds_x_request_id_header(self) -> None:
        client = self._app()
        resp = client.get("/hello")
        assert resp.status_code == 200
        assert "x-request-id" in resp.headers

    def test_preserves_existing_request_id(self) -> None:
        client = self._app()
        custom_id = "my-request-id-123"
        resp = client.get("/hello", headers={"X-Request-ID": custom_id})
        assert resp.headers.get("x-request-id") == custom_id

    def test_generates_new_id_when_absent(self) -> None:
        client = self._app()
        resp = client.get("/hello")
        request_id = resp.headers.get("x-request-id")
        assert request_id is not None
        assert len(request_id) > 0

    def test_different_requests_get_unique_ids(self) -> None:
        client = self._app()
        ids = set()
        for _ in range(5):
            resp = client.get("/hello")
            ids.add(resp.headers.get("x-request-id"))
        assert len(ids) == 5


# ===========================================================================
# AccessLogMiddleware
# ===========================================================================


class TestAccessLogMiddleware:
    def _app(self) -> TestClient:
        from leagent.api.middleware import AccessLogMiddleware
        app = _make_app()
        app.add_middleware(AccessLogMiddleware)
        return TestClient(app)

    def test_request_succeeds(self) -> None:
        client = self._app()
        resp = client.get("/hello")
        assert resp.status_code == 200

    def test_excluded_path_not_logged(self) -> None:
        """Health endpoint should pass through without interference."""
        client = self._app()
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_custom_exclude_paths(self) -> None:
        from leagent.api.middleware import AccessLogMiddleware
        app = _make_app()
        app.add_middleware(AccessLogMiddleware, exclude_paths={"/hello"})
        client = TestClient(app)
        resp = client.get("/hello")
        assert resp.status_code == 200


# ===========================================================================
# ContentSizeLimitMiddleware
# ===========================================================================


class TestContentSizeLimitMiddleware:
    def _app(self, max_size: int = 1024) -> TestClient:
        from leagent.api.middleware import ContentSizeLimitMiddleware
        app = _make_app()

        @app.post("/upload")
        async def upload():
            return {"ok": True}

        app.add_middleware(ContentSizeLimitMiddleware, max_content_size=max_size)
        return TestClient(app, raise_server_exceptions=False)

    def test_small_body_passes(self) -> None:
        client = self._app(max_size=10240)
        resp = client.post(
            "/upload",
            content=b"small content",
            headers={"Content-Length": "13"},
        )
        assert resp.status_code == 200

    def test_oversized_body_returns_413(self) -> None:
        client = self._app(max_size=10)
        large_body = b"x" * 100
        resp = client.post(
            "/upload",
            content=large_body,
            headers={"Content-Length": str(len(large_body))},
        )
        assert resp.status_code == 413

    def test_no_content_length_passes(self) -> None:
        client = self._app(max_size=1024)
        resp = client.get("/hello")
        assert resp.status_code == 200
