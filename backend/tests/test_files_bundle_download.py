"""Tests for POST /api/v1/files/bundle/download helpers (filename sanitization)."""

from __future__ import annotations

from leagent.api.v1 import files as v1_files


class TestSanitizeBundleFilename:
    def test_defaults_to_zip(self) -> None:
        assert v1_files._sanitize_bundle_download_filename(None) == "workspace-files.zip"
        assert v1_files._sanitize_bundle_download_filename("") == "workspace-files.zip"

    def test_strips_path_segments(self) -> None:
        assert v1_files._sanitize_bundle_download_filename("../../../etc/passwd") == "passwd.zip"

    def test_appends_zip_extension(self) -> None:
        assert v1_files._sanitize_bundle_download_filename("my-export").endswith(".zip")
        assert "my-export" in v1_files._sanitize_bundle_download_filename("my-export")
