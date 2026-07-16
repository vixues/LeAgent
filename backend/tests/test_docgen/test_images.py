"""Tests for docgen image resolution (path / file_id / preview URL / base64)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from leagent.docgen.images import extract_file_id, resolve_image
from leagent.docgen.markdown import parse_markdown_blocks
from leagent.docgen.model import ImageBlock

if TYPE_CHECKING:
    pass

# 1x1 transparent PNG.
_PX = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
_FID = "e5551d5e-68cf-4736-9416-92a841e67396"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (_FID, _FID),
        (f"/api/v1/files/{_FID}/preview", _FID),
        (f"/api/v1/files/{_FID}/preview?token=abc", _FID),
        (f"https://host/api/v1/files/{_FID}/download", _FID),
        (f"{_FID}_embed_cover_bg.png", _FID),
        (f"/tmp/uploads/sess/{_FID}_cover.png", _FID),
        ("not-a-uuid", None),
        (None, None),
    ],
)
def test_extract_file_id(value: str | None, expected: str | None) -> None:
    assert extract_file_id(value) == expected


def test_resolve_image_base64() -> None:
    resolved = resolve_image(base64_data=_PX)
    assert resolved is not None
    assert resolved.data[:8] == b"\x89PNG\r\n\x1a\n"
    assert resolved.source_desc == "base64"


def test_resolve_image_path(tmp_path: Path) -> None:
    import base64

    path = tmp_path / "cover.png"
    path.write_bytes(base64.b64decode(_PX))
    resolved = resolve_image(path=str(path))
    assert resolved is not None
    assert resolved.source_desc == "cover.png"


def test_resolve_image_file_id_from_uploads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import base64

    from leagent.config import constants

    upload_root = tmp_path / "uploads"
    session_dir = upload_root / "sess-1"
    session_dir.mkdir(parents=True)
    blob = session_dir / f"{_FID}_embed_cover_bg.png"
    blob.write_bytes(base64.b64decode(_PX))

    monkeypatch.setattr(constants, "UPLOAD_DIR", upload_root)

    by_id = resolve_image(file_id=_FID)
    assert by_id is not None
    assert _FID in by_id.source_desc

    by_preview = resolve_image(url=f"/api/v1/files/{_FID}/preview")
    assert by_preview is not None

    by_storage_name = resolve_image(path=f"{_FID}_embed_cover_bg.png")
    assert by_storage_name is not None


def test_markdown_image_preview_url_becomes_file_id() -> None:
    blocks = parse_markdown_blocks(f"![cover](/api/v1/files/{_FID}/preview)\n")
    assert len(blocks) == 1
    assert isinstance(blocks[0], ImageBlock)
    assert blocks[0].file_id == _FID
    assert blocks[0].path is None
