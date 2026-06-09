"""OpenAPI contract guard — fails CI if the schema can't be generated.

These assertions are cheap structural guards (not golden-file diffs) so they
stay stable across additive route changes while still catching:
  * a router that raises during schema generation (bad ``response_model`` etc.),
  * accidental re-introduction of the retired ``/api/v2`` surface, and
  * the canonical :class:`ErrorResponse` envelope disappearing from components.
"""

from __future__ import annotations

from fastapi import FastAPI


def test_openapi_schema_generates(app: FastAPI) -> None:
    schema = app.openapi()

    assert schema["openapi"].startswith("3.")
    assert schema["info"]["title"]
    paths = schema.get("paths", {})
    assert paths, "OpenAPI schema exposes no paths"

    # All HTTP routes live under /api/v1 — the nominal v2 surface was removed.
    assert not any(p.startswith("/api/v2") for p in paths), "Unexpected /api/v2 paths"
    assert any(p.startswith("/api/v1") for p in paths), "No /api/v1 paths registered"


def test_openapi_advertises_error_envelope(app: FastAPI) -> None:
    schema = app.openapi()
    components = schema.get("components", {}).get("schemas", {})
    assert "ErrorResponse" in components, "Canonical ErrorResponse missing from OpenAPI components"
