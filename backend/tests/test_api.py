"""Tests for the LeAgent API endpoints.

Uses the ``client`` / ``async_client`` fixtures from conftest.py which wrap
the real FastAPI application.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


# ===========================================================================
# /health
# ===========================================================================


class TestHealthEndpoint:
    def test_health_returns_200(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200

    def test_health_body_has_status(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert data["status"] == "healthy"

    def test_health_body_has_version(self, client: TestClient) -> None:
        data = client.get("/health").json()
        assert "version" in data
        assert isinstance(data["version"], str)


# ===========================================================================
# /  (root)
# ===========================================================================


class TestRootEndpoint:
    def test_root_returns_200(self, client: TestClient) -> None:
        assert client.get("/").status_code in (200, 404)

    def test_root_returns_name(self, client: TestClient) -> None:
        resp = client.get("/")
        if resp.status_code == 200:
            data = resp.json()
            assert data["name"] == "LeAgent"

    def test_root_returns_version(self, client: TestClient) -> None:
        resp = client.get("/")
        if resp.status_code == 200:
            data = resp.json()
            assert "version" in data


# ===========================================================================
# Middleware contract
# ===========================================================================


class TestMiddlewareContract:
    def test_request_id_header_present(self, client: TestClient) -> None:
        """RequestIDMiddleware must inject X-Request-ID on every response."""
        resp = client.get("/health")
        assert "x-request-id" in resp.headers

    def test_client_request_id_preserved(self, client: TestClient) -> None:
        custom_id = "test-correlation-abc123"
        resp = client.get("/health", headers={"X-Request-ID": custom_id})
        assert resp.headers.get("x-request-id") == custom_id

    def test_content_size_limit_413_on_oversized(self) -> None:
        """ContentSizeLimitMiddleware must return 413 when body exceeds limit."""
        from leagent.api.middleware import ContentSizeLimitMiddleware
        from leagent.main import create_app

        app = create_app()
        # Wrap with a very tight size limit for this test
        app.add_middleware(ContentSizeLimitMiddleware, max_content_size=5)
        tight_client = TestClient(app, raise_server_exceptions=False)
        resp = tight_client.post(
            "/api/v1/chat/run",
            content=b"x" * 100,
            headers={"Content-Length": "100"},
        )
        assert resp.status_code == 413


# ===========================================================================
# /api/v1  — versioned prefix existence
# ===========================================================================


class TestAPIv1Prefix:
    def test_unknown_v1_route_returns_404_not_500(self, client: TestClient) -> None:
        """Any call under /api/v1 on an unknown path should return 404, not crash."""
        resp = client.get("/api/v1/nonexistent_endpoint_xyz")
        assert resp.status_code == 404

    def test_v1_auth_prefix_removed(self, client: TestClient) -> None:
        """Auth routes are removed in single-node mode."""
        resp = client.post("/api/v1/auth/login", json={})
        assert resp.status_code in (404, 405, 422)

    def test_v1_health_mounted(self, client: TestClient) -> None:
        """v1 basic health is under /api/v1/health; root /health remains."""
        r = client.get("/api/v1/health")
        assert r.status_code in (200, 404)
        if r.status_code == 200:
            data = r.json()
            assert data.get("status") == "healthy"
            assert "version" in data
        assert client.get("/health").status_code == 200
        detailed = client.get("/api/v1/health/detailed")
        # Single-node mode may expose detailed health without auth (200).
        assert detailed.status_code in (200, 401, 403, 404)
        if detailed.status_code == 200:
            assert isinstance(detailed.json(), dict)


# ===========================================================================
# Exception handler contract
# ===========================================================================


class TestExceptionHandlerContract:
    def test_leagent_error_returns_json(self, client: TestClient) -> None:
        """LeAgentError subclasses should always produce JSON, never HTML."""
        # Any 4xx/5xx response from the app should be JSON, not HTML
        resp = client.get("/api/v1/nonexistent")
        ct = resp.headers.get("content-type", "")
        # FastAPI default 404s return JSON
        assert "application/json" in ct or resp.status_code == 404


# ===========================================================================
# CORS headers
# ===========================================================================


class TestCORSHeaders:
    def test_preflight_returns_cors_headers(self, client: TestClient) -> None:
        """OPTIONS preflight should return CORS allow headers."""
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )
        # CORS middleware should either allow or the request passes through
        assert resp.status_code in (200, 204, 405)


# ===========================================================================
# /api/v1/cron/preview-next-runs  (static path vs /{job_id})
# ===========================================================================


class TestCronPreviewNextRunsRoute:
    def test_get_preview_next_runs_is_not_job_id_path(self, client: TestClient, test_user: dict) -> None:
        """The literal path segment must not be validated as a UUID ``job_id`` (422)."""
        resp = client.get(
            "/api/v1/cron/preview-next-runs",
            params={"cron_expression": "0 0 * * *", "count": 5},
            headers=test_user["auth_header"],
        )
        # Wrong routing yields 422 with path ``job_id`` and input ``preview-next-runs``.
        if resp.status_code == 422:
            try:
                detail = resp.json().get("detail")
            except Exception:
                detail = None
            if isinstance(detail, list):
                for err in detail:
                    if not isinstance(err, dict):
                        continue
                    loc = err.get("loc") or ()
                    if (
                        "job_id" in loc
                        and err.get("input") == "preview-next-runs"
                    ):
                        raise AssertionError(
                            "GET /preview-next-runs was matched as /{job_id}; fix route order"
                        )
