"""Tests for leagent.file.primitives — the shared file-management utilities."""

from __future__ import annotations

from pathlib import Path

import pytest

from leagent.file.primitives import (
    FileKind,
    FileScope,
    classify_file_kind,
    detect_mime,
    is_path_inside,
    sanitize_filename,
)


# ── sanitize_filename ────────────────────────────────────────────────

class TestSanitizeFilename:
    def test_strips_directory_components(self):
        assert sanitize_filename("../../etc/passwd") == "passwd"

    def test_replaces_spaces(self):
        assert sanitize_filename("my file.txt") == "my_file.txt"

    def test_removes_special_chars(self):
        assert sanitize_filename("file<>|?.txt") == "file.txt"

    def test_falls_back_to_default(self):
        assert sanitize_filename("   ") == "file"
        assert sanitize_filename("", default="attachment") == "attachment"

    def test_truncates(self):
        long_name = "a" * 300 + ".txt"
        assert len(sanitize_filename(long_name)) == 180

    def test_preserves_alnum_dot_dash_underscore(self):
        assert sanitize_filename("valid-file_name.2024.pdf") == "valid-file_name.2024.pdf"


# ── detect_mime ──────────────────────────────────────────────────────

class TestDetectMime:
    def test_known_extension(self):
        assert detect_mime("report.pdf") == "application/pdf"

    def test_hint_fallback(self):
        assert detect_mime("noext", content_type_hint="image/png") == "image/png"

    def test_octet_stream_default(self):
        assert detect_mime("unknown") == "application/octet-stream"


# ── classify_file_kind ───────────────────────────────────────────────

class TestClassifyFileKind:
    @pytest.mark.parametrize("ext, expected", [
        ("photo.png", FileKind.IMAGE),
        ("doc.pdf", FileKind.DOCUMENT),
        ("data.csv", FileKind.DATA),
        ("music.mp3", FileKind.AUDIO),
        ("clip.mp4", FileKind.VIDEO),
        ("archive.zip", FileKind.ARCHIVE),
        ("script.py", FileKind.CODE),
        ("notes.txt", FileKind.TEXT),
    ])
    def test_by_extension(self, ext: str, expected: FileKind):
        assert classify_file_kind(ext) == expected

    def test_by_mime_when_no_ext(self):
        assert classify_file_kind("noext", "application/pdf") == FileKind.DOCUMENT

    def test_other_fallback(self):
        assert classify_file_kind("weirdfile", "application/x-custom") == FileKind.OTHER


# ── is_path_inside ───────────────────────────────────────────────────

class TestIsPathInside:
    def test_child(self, tmp_path: Path):
        child = tmp_path / "sub" / "file.txt"
        assert is_path_inside(child, (tmp_path,)) is True

    def test_equal(self, tmp_path: Path):
        assert is_path_inside(tmp_path, (tmp_path,)) is True

    def test_outside(self, tmp_path: Path):
        other = tmp_path.parent / "other"
        assert is_path_inside(other, (tmp_path,)) is False

    def test_single_root_auto_wrap(self, tmp_path: Path):
        child = tmp_path / "file"
        assert is_path_inside(child, tmp_path) is True


# ── FileScope enum ───────────────────────────────────────────────────

class TestFileScope:
    def test_values(self):
        assert set(FileScope) == {
            FileScope.SESSION,
            FileScope.KNOWLEDGE,
            FileScope.OUTPUT,
            FileScope.ASSET,
            FileScope.TEMP,
        }
