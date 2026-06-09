"""Tests for GET /api/v1/canvas/preview/screenshot (Playwright render → PNG/JPEG)."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from urllib.parse import quote, unquote
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from leagent.api.v1 import canvas as canvas_api
from leagent.api.v1.canvas import (
    _ascii_filename_fallback,
    _content_disposition,
)
from leagent.db.models.canvas import CanvasContentType, CanvasDocument

SCREENSHOT_PATH = "/api/v1/canvas/preview/screenshot"
VALID_TOKEN = "dummy-token-value-32chars!!"

# Generic non-ASCII fixtures (no product-specific copy).
_UNICODE_TITLE = "Sample Report — 示例"
_UNICODE_FILENAME = f"{_UNICODE_TITLE}.png"
_UNICODE_FILENAME_ENCODED = quote(_UNICODE_FILENAME, safe="")

# Minimal image signatures returned by stubbed Playwright (not full decodable images).
_STUB_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128
_STUB_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 128


def _make_canvas_document(
    *,
    title: str = "ScreenshotTest",
    html_body: str | None = None,
) -> CanvasDocument:
    return CanvasDocument(
        id=uuid4(),
        canvas_id=uuid4(),
        revision=1,
        session_id=uuid4(),
        user_id=uuid4(),
        title=title,
        content_type=CanvasContentType.HTML.value,
        html_body=html_body
        or (
            '<main class="p-6"><h1 class="text-xl font-semibold text-slate-800">'
            "Canvas Screenshot</h1>"
            '<p class="text-slate-600">playwright-ok</p></main>'
        ),
    )


def _skip_if_playwright_unavailable(response: Any) -> None:
    if response.status_code == 503:
        pytest.skip(f"Playwright/Chromium unavailable: {response.text[:200]}")


@pytest.fixture
def override_canvas_service(app: Any) -> Callable[[CanvasDocument | None], MagicMock]:
    """Inject a CanvasService mock for ``_canvas_dep``; always restored after the test."""

    def _apply(doc: CanvasDocument | None) -> MagicMock:
        mock = MagicMock()
        mock.load_verified_from_token = AsyncMock(return_value=doc)
        app.dependency_overrides[canvas_api._canvas_dep] = lambda: mock
        return mock

    yield _apply
    app.dependency_overrides.pop(canvas_api._canvas_dep, None)


@pytest.fixture
def stub_playwright_browser(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Avoid launching Chromium; return deterministic PNG/JPEG bytes per format."""

    captures: dict[str, Any] = {"fmt": "png"}

    async def _screenshot(*, type: str, **_kwargs: Any) -> bytes:
        captures["fmt"] = type
        return _STUB_JPEG if type == "jpeg" else _STUB_PNG

    page = MagicMock()
    page.goto = AsyncMock()
    page.set_content = AsyncMock()
    page.evaluate = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.screenshot = AsyncMock(side_effect=_screenshot)
    page.close = AsyncMock()

    browser = MagicMock()
    browser.new_page = AsyncMock(return_value=page)

    async def _get_pw_browser() -> MagicMock:
        return browser

    monkeypatch.setattr(canvas_api, "_get_pw_browser", _get_pw_browser)
    return {"browser": browser, "page": page, "captures": captures}


class TestAsciiFilenameFallback:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("report.png", "report.png"),
            ("  spaced  ", "spaced"),
            ("", "download"),
            ("___", "download"),
        ],
    )
    def test_ascii_passthrough_and_defaults(self, raw: str, expected: str) -> None:
        assert _ascii_filename_fallback(raw) == expected

    def test_non_ascii_replaced_with_underscores(self) -> None:
        # Keep an ASCII prefix so strip() does not remove the whole stem.
        assert _ascii_filename_fallback("report-示例.png") == "report-__.png"

    def test_truncates_to_180_chars(self) -> None:
        long_name = "a" * 250 + ".png"
        assert len(_ascii_filename_fallback(long_name)) == 180


class TestContentDisposition:
    def test_header_is_latin1_encodable(self) -> None:
        header = _content_disposition("inline", _UNICODE_FILENAME)
        header.encode("latin-1")

    def test_includes_rfc5987_filename_star(self) -> None:
        header = _content_disposition("inline", _UNICODE_FILENAME)
        assert 'filename="' in header
        assert "filename*=UTF-8''" in header
        star = header.split("filename*=UTF-8''", 1)[1]
        assert unquote(star) == _UNICODE_FILENAME

    @pytest.mark.parametrize(
        ("disposition", "expected_prefix"),
        [
            ("inline", "inline;"),
            ("attachment", "attachment;"),
            ("invalid", "inline;"),
        ],
    )
    def test_disposition_type(self, disposition: str, expected_prefix: str) -> None:
        header = _content_disposition(disposition, "out.png")
        assert header.startswith(expected_prefix)


class TestCanvasPreviewScreenshotValidation:
    def test_rejects_short_token(self, client: TestClient) -> None:
        resp = client.get(SCREENSHOT_PATH, params={"token": "short"})
        assert resp.status_code == 422

    @pytest.mark.parametrize("fmt", ["gif", "webp", ""])
    def test_rejects_unsupported_format(self, client: TestClient, fmt: str) -> None:
        resp = client.get(
            SCREENSHOT_PATH,
            params={"token": VALID_TOKEN, "format": fmt},
        )
        assert resp.status_code == 422


class TestCanvasPreviewScreenshotAuth:
    def test_invalid_token_returns_403(
        self,
        client: TestClient,
        override_canvas_service: Callable[[CanvasDocument | None], MagicMock],
    ) -> None:
        override_canvas_service(None)
        resp = client.get(SCREENSHOT_PATH, params={"token": "expired-or-bad-token-32chars!!"})
        assert resp.status_code == 403
        assert "Invalid or expired" in resp.text or resp.status_code == 403


class TestCanvasPreviewScreenshotResponse:
    """Route logic with Playwright stubbed (fast, no Chromium required)."""

    @pytest.mark.parametrize(
        ("fmt", "magic", "media_prefix"),
        [
            ("png", _STUB_PNG[:8], "image/png"),
            ("jpeg", _STUB_JPEG[:4], "image/jpeg"),
        ],
    )
    def test_returns_image_for_format(
        self,
        client: TestClient,
        override_canvas_service: Callable[[CanvasDocument | None], MagicMock],
        stub_playwright_browser: dict[str, Any],
        fmt: str,
        magic: bytes,
        media_prefix: str,
    ) -> None:
        override_canvas_service(_make_canvas_document())
        resp = client.get(
            SCREENSHOT_PATH,
            params={"token": VALID_TOKEN, "format": fmt, "width": 640, "height": 480},
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers.get("content-type", "").startswith(media_prefix)
        assert resp.content.startswith(magic)
        assert stub_playwright_browser["captures"]["fmt"] == fmt

    def test_cjk_title_yields_latin1_content_disposition(
        self,
        client: TestClient,
        override_canvas_service: Callable[[CanvasDocument | None], MagicMock],
        stub_playwright_browser: dict[str, Any],
    ) -> None:
        override_canvas_service(_make_canvas_document(title=_UNICODE_TITLE))
        resp = client.get(SCREENSHOT_PATH, params={"token": VALID_TOKEN, "format": "png"})
        assert resp.status_code == 200, resp.text

        disposition = resp.headers.get("content-disposition", "")
        disposition.encode("latin-1")
        assert "filename*=" in disposition
        assert _UNICODE_FILENAME_ENCODED in disposition
        assert resp.content.startswith(_STUB_PNG[:8])

        page = stub_playwright_browser["page"]
        page.goto.assert_awaited_once()
        assert page.goto.await_args.kwargs.get("wait_until") == "load"
        nav_url = page.goto.await_args.args[0] if page.goto.await_args.args else ""
        assert "/api/v1/canvas/preview" in nav_url
        assert "token=" in nav_url

    def test_passes_viewport_to_playwright(
        self,
        client: TestClient,
        override_canvas_service: Callable[[CanvasDocument | None], MagicMock],
        stub_playwright_browser: dict[str, Any],
    ) -> None:
        override_canvas_service(_make_canvas_document())
        client.get(
            SCREENSHOT_PATH,
            params={"token": VALID_TOKEN, "width": 1200, "height": 800},
        )
        stub_playwright_browser["browser"].new_page.assert_awaited_once_with(
            viewport={"width": 1200, "height": 800},
        )


class TestCanvasPreviewScreenshotPlaywrightIntegration:
    """Optional end-to-end render against real Chromium (skipped when unavailable)."""

    pytestmark = pytest.mark.skipif(
        os.getenv("LEAGENT_RUN_PLAYWRIGHT_E2E") != "1",
        reason="Set LEAGENT_RUN_PLAYWRIGHT_E2E=1 to run real Chromium screenshot tests.",
    )

    @pytest.fixture
    def live_canvas_doc(
        self,
        override_canvas_service: Callable[[CanvasDocument | None], MagicMock],
    ) -> CanvasDocument:
        doc = _make_canvas_document()
        override_canvas_service(doc)
        return doc

    def test_renders_non_trivial_png(
        self,
        client: TestClient,
        live_canvas_doc: CanvasDocument,
    ) -> None:
        resp = client.get(
            SCREENSHOT_PATH,
            params={"token": VALID_TOKEN, "format": "png", "width": 640, "height": 480},
        )
        _skip_if_playwright_unavailable(resp)
        assert resp.status_code == 200, resp.text
        assert "image/png" in resp.headers.get("content-type", "")
        assert len(resp.content) > 200
        assert resp.content.startswith(b"\x89PNG\r\n\x1a\n")

    def test_unicode_title_does_not_crash_server(
        self,
        client: TestClient,
        override_canvas_service: Callable[[CanvasDocument | None], MagicMock],
    ) -> None:
        override_canvas_service(_make_canvas_document(title=_UNICODE_TITLE))
        resp = client.get(SCREENSHOT_PATH, params={"token": VALID_TOKEN, "format": "png"})
        _skip_if_playwright_unavailable(resp)
        assert resp.status_code == 200, resp.text
        disposition = resp.headers.get("content-disposition", "")
        disposition.encode("latin-1")
