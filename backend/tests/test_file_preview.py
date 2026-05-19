"""Tests for HMAC-signed attachment URLs.

The preview + download endpoints in :mod:`leagent.api.v1.files` rely on
:mod:`leagent.services.auth.signed_url` for auth so the browser can
embed ``<img src="/api/v1/files/.../preview?token=...">`` without
shipping a JWT. We test the token primitives directly here; the HTTP
endpoint wiring is covered by the API layer tests.
"""

from __future__ import annotations

import time
from uuid import uuid4

import pytest

from leagent.config.settings import get_settings
from leagent.services.auth.signed_url import (
    SignedUrlError,
    build_download_url,
    build_preview_url,
    create_signed_token,
    verify_signed_token,
)


@pytest.fixture()
def signing_settings():
    s = get_settings()
    s.files.signed_url_secret = "unit-test-secret-do-not-use-in-prod"
    s.files.preview_ttl_seconds = 60
    return s


class TestSignedTokenRoundTrip:
    def test_preview_token_round_trips(self, signing_settings) -> None:
        attachment_id = uuid4()
        user_id = uuid4()
        token = create_signed_token(
            signing_settings,
            attachment_id=attachment_id,
            user_id=user_id,
            scope="preview",
        )
        decoded = verify_signed_token(signing_settings, token)
        assert decoded.attachment_id == attachment_id
        assert decoded.user_id == user_id
        assert decoded.scope == "preview"
        assert decoded.expires_at > int(time.time())

    def test_download_token_encodes_scope(self, signing_settings) -> None:
        token = create_signed_token(
            signing_settings,
            attachment_id=uuid4(),
            user_id=uuid4(),
            scope="download",
        )
        decoded = verify_signed_token(signing_settings, token)
        assert decoded.scope == "download"

    def test_build_preview_url_uses_attachment_id(self, signing_settings) -> None:
        attachment_id = uuid4()
        url = build_preview_url(
            signing_settings,
            attachment_id=attachment_id,
            user_id=uuid4(),
        )
        assert url.startswith("/api/v1/files/")
        assert str(attachment_id) in url
        assert "token=" in url
        assert url.endswith(url.split("token=", 1)[-1])  # trailing token body

    def test_build_download_url_has_different_scope(self, signing_settings) -> None:
        attachment_id = uuid4()
        preview = build_preview_url(
            signing_settings,
            attachment_id=attachment_id,
            user_id=None,
        )
        download = build_download_url(
            signing_settings,
            attachment_id=attachment_id,
            user_id=None,
        )
        assert "/preview" in preview
        assert "/download" in download
        assert preview != download


class TestSignedTokenFailures:
    def test_tampered_body_is_rejected(self, signing_settings) -> None:
        token = create_signed_token(
            signing_settings,
            attachment_id=uuid4(),
            user_id=None,
            scope="preview",
        )
        body, mac = token.split(".", 1)
        # Flip the last byte of the body and keep the original MAC.
        tampered = f"{body[:-1]}{'A' if body[-1] != 'A' else 'B'}.{mac}"
        with pytest.raises(SignedUrlError):
            verify_signed_token(signing_settings, tampered)

    def test_expired_token_is_rejected(self, signing_settings) -> None:
        token = create_signed_token(
            signing_settings,
            attachment_id=uuid4(),
            user_id=None,
            scope="preview",
            ttl_seconds=-10,
        )
        with pytest.raises(SignedUrlError):
            verify_signed_token(signing_settings, token)

    def test_malformed_token_is_rejected(self, signing_settings) -> None:
        with pytest.raises(SignedUrlError):
            verify_signed_token(signing_settings, "not-a-real-token")

    def test_cross_secret_rejection(self, signing_settings) -> None:
        token = create_signed_token(
            signing_settings,
            attachment_id=uuid4(),
            user_id=None,
            scope="preview",
        )
        # Flip the secret — verification must now fail.
        signing_settings.files.signed_url_secret = "a-different-secret"
        with pytest.raises(SignedUrlError):
            verify_signed_token(signing_settings, token)
