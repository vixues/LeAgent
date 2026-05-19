"""Tests for GenUi print HTML and POST /api/v1/canvas/genui/export/pdf."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from leagent.api.v1 import canvas as canvas_api
from leagent.config.settings import Settings
from leagent.services.gen_ui.print_renderer import render_print_document_html
from leagent.services.gen_ui.schema import validate_ui_tree


@pytest.fixture
def genui_pdf_auth_header(test_user: dict[str, Any], test_settings: Settings) -> dict[str, str]:
    """Bearer token compatible with gateway TokenPayload (includes exp)."""
    from leagent.services.auth import AuthService

    auth = AuthService(test_settings)
    token = auth.create_access_token(UUID(test_user["user_id"]))
    return {"Authorization": f"Bearer {token}"}


def test_render_print_document_html_includes_feature_grid_items() -> None:
    html = render_print_document_html(
        {
            "schemaVersion": "1",
            "root": {
                "nodeId": "r",
                "kind": "FeatureGrid",
                "props": {
                    "items": [
                        {"title": "Alpha", "description": "First"},
                        {"title": "Beta", "description": "Second"},
                    ],
                },
            },
        },
        mode="document",
    )
    assert "featgrid" in html
    assert "Alpha" in html and "Beta" in html


def test_render_print_document_html_stat_and_icon() -> None:
    html = render_print_document_html(
        {
            "schemaVersion": "1",
            "root": {
                "nodeId": "r",
                "kind": "Stack",
                "children": [
                    {
                        "nodeId": "s1",
                        "kind": "Stat",
                        "props": {"label": "Users", "value": "42", "delta": "+3"},
                    },
                    {"nodeId": "i1", "kind": "Icon", "props": {"name": "sparkles"}},
                ],
            },
        },
        mode="document",
    )
    assert "Users" in html and "42" in html
    assert "sparkles" in html


def test_render_print_document_html_geek_design_surface() -> None:
    html = render_print_document_html(
        {
            "schemaVersion": "1",
            "root": {
                "nodeId": "r",
                "kind": "DesignSurface",
                "props": {"preset": "geek"},
                "children": [
                    {"nodeId": "h", "kind": "Heading", "props": {"level": 2, "value": "Ops Console"}},
                ],
            },
        },
        mode="document",
    )
    assert "designsurface-geek" in html
    assert "Ops Console" in html


def test_slide_deck_slides_prop_normalizes_to_print_html() -> None:
    raw = {
        "schemaVersion": "1",
        "root": {
            "nodeId": "deck",
            "kind": "SlideDeck",
            "props": {
                "slides": [{"title": "Hello", "content": "World slide"}],
            },
            "children": [],
        },
    }
    normalized = validate_ui_tree(raw, max_depth=64, max_nodes=500)
    html_deck = render_print_document_html(normalized, mode="deck", page_size="Slide16x9")
    assert "Hello" in html_deck and "World slide" in html_deck
    assert "@page { margin: 0; }" in html_deck or "margin: 0" in html_deck


def test_genui_export_pdf_invalid_kind_400(client: TestClient, genui_pdf_auth_header: dict[str, str]) -> None:
    resp = client.post(
        "/api/v1/canvas/genui/export/pdf",
        json={
            "tree": {
                "schemaVersion": "1",
                "root": {"nodeId": "1", "kind": "NotARealKind", "children": []},
            },
            "mode": "document",
        },
        headers=genui_pdf_auth_header,
    )
    assert resp.status_code == 400


def test_genui_export_pdf_returns_pdf_bytes(
    client: TestClient,
    genui_pdf_auth_header: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mock_browser = MagicMock()
    mock_page = MagicMock()
    mock_page.pdf = AsyncMock(return_value=b"%PDF-1.4\nfake")
    mock_page.set_content = AsyncMock()
    mock_page.evaluate = AsyncMock(return_value=None)
    mock_page.emulate_media = AsyncMock()
    mock_page.set_viewport_size = AsyncMock()
    mock_page.wait_for_timeout = AsyncMock()
    mock_page.close = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)

    async def _fake_browser() -> MagicMock:
        return mock_browser

    monkeypatch.setattr(canvas_api, "_get_pw_browser", _fake_browser)

    resp = client.post(
        "/api/v1/canvas/genui/export/pdf",
        json={
            "tree": {
                "schemaVersion": "1",
                "root": {"nodeId": "1", "kind": "Stack", "children": []},
            },
            "mode": "document",
            "page_size": "A4",
            "orientation": "portrait",
        },
        headers=genui_pdf_auth_header,
    )
    assert resp.status_code == 200, resp.text
    assert "application/pdf" in (resp.headers.get("content-type") or "")
    assert resp.content.startswith(b"%PDF")
    mock_page.close.assert_called_once()
