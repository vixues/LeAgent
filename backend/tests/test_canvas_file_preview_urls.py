"""Tests for signing managed file URLs in canvas HTML."""

from __future__ import annotations

from uuid import uuid4

import pytest

from leagent.config.settings import get_settings
from leagent.services.auth.signed_url import (
    sign_managed_file_urls_in_html,
    verify_signed_token,
)
from leagent.services.canvas.service import build_preview_html, playwright_document_base
from leagent.db.models.canvas import CanvasContentType, CanvasDocument


@pytest.fixture()
def signing_settings():
    s = get_settings()
    s.files.signed_url_secret = "canvas-html-sign-test-secret"
    s.files.preview_ttl_seconds = 3600
    return s


class TestSignManagedFileUrlsInHtml:
    def test_signs_unsigned_preview_src(self, signing_settings) -> None:
        fid = uuid4()
        uid = uuid4()
        html = f'<img src="/api/v1/files/{fid}/preview" alt="plot"/>'
        out = sign_managed_file_urls_in_html(html, settings=signing_settings, user_id=uid)
        assert f"/api/v1/files/{fid}/preview?token=" in out
        token = out.split("token=", 1)[1].split('"', 1)[0]
        decoded = verify_signed_token(signing_settings, token)
        assert decoded.attachment_id == fid
        assert decoded.user_id == uid
        assert decoded.scope == "preview"

    def test_refreshes_stale_signed_preview(self, signing_settings) -> None:
        fid = uuid4()
        uid = uuid4()
        html = (
            f'<img src="/api/v1/files/{fid}/preview?token=old.stale" alt="x"/>'
        )
        out = sign_managed_file_urls_in_html(html, settings=signing_settings, user_id=uid)
        assert "token=old.stale" not in out
        assert f"/api/v1/files/{fid}/preview?token=" in out

    def test_signs_absolute_preview_urls(self, signing_settings) -> None:
        fid = uuid4()
        uid = uuid4()
        html = (
            f'<img src="http://localhost:8000/api/v1/files/{fid}/preview" alt="x"/>'
        )
        out = sign_managed_file_urls_in_html(html, settings=signing_settings, user_id=uid)
        assert out.startswith('<img src="/api/v1/files/')
        assert "token=" in out

    def test_public_base_makes_playwright_absolute_urls(self, signing_settings) -> None:
        fid = uuid4()
        uid = uuid4()
        html = f'<img src="/api/v1/files/{fid}/preview" alt="plot"/>'
        out = sign_managed_file_urls_in_html(
            html,
            settings=signing_settings,
            user_id=uid,
            public_base="http://127.0.0.1:7860",
        )
        assert out.startswith('<img src="http://127.0.0.1:7860/api/v1/files/')
        assert "token=" in out

    def test_signs_download_hrefs(self, signing_settings) -> None:
        fid = uuid4()
        uid = uuid4()
        html = f'<a href="/api/v1/files/{fid}/download">save</a>'
        out = sign_managed_file_urls_in_html(html, settings=signing_settings, user_id=uid)
        assert f"/api/v1/files/{fid}/download?token=" in out
        token = out.split("token=", 1)[1].split('"', 1)[0]
        decoded = verify_signed_token(signing_settings, token)
        assert decoded.scope == "download"

    def test_leaves_external_urls_unchanged(self, signing_settings) -> None:
        html = '<img src="https://cdn.example.com/chart.png" alt="x"/>'
        out = sign_managed_file_urls_in_html(html, settings=uuid4(), user_id=uuid4())
        assert out == html

    def test_noop_without_user_id(self, signing_settings) -> None:
        fid = uuid4()
        html = f'<img src="/api/v1/files/{fid}/preview"/>'
        out = sign_managed_file_urls_in_html(html, settings=signing_settings, user_id=None)
        assert out == html


class TestBuildPreviewHtmlSigning:
    def test_build_preview_html_signs_embedded_images(self, signing_settings) -> None:
        fid = uuid4()
        uid = uuid4()
        doc = CanvasDocument(
            canvas_id=uuid4(),
            revision=1,
            session_id=uuid4(),
            user_id=uid,
            title="t",
            content_type=CanvasContentType.HTML.value,
            html_body=f'<div><img src="/api/v1/files/{fid}/preview" alt="plot"/></div>',
        )
        html, mime = build_preview_html(doc, signing_settings)
        assert mime.startswith("text/html")
        assert f"/api/v1/files/{fid}/preview?token=" in html

    def test_build_preview_html_playwright_uses_absolute_signed_urls(
        self,
        signing_settings,
    ) -> None:
        fid = uuid4()
        uid = uuid4()
        doc = CanvasDocument(
            canvas_id=uuid4(),
            revision=1,
            session_id=uuid4(),
            user_id=uid,
            title="t",
            content_type=CanvasContentType.HTML.value,
            html_body=f'<img src="/api/v1/files/{fid}/preview" alt="plot"/>',
        )
        base = playwright_document_base(signing_settings)
        html, _mime = build_preview_html(doc, signing_settings, public_base=base)
        assert f'{base}/api/v1/files/{fid}/preview?token=' in html
