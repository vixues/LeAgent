"""Pet Space upload MIME sniffing (SVG / GIF / PNG when Content-Type is weak)."""

from __future__ import annotations

from leagent.api.v1.files import resolve_pet_space_upload_mime_type


def test_declared_image_mime_passthrough() -> None:
    assert resolve_pet_space_upload_mime_type("x.png", "image/png", b"not-a-png") == "image/png"


def test_svg_from_filename_when_octet_stream() -> None:
    svg = b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg"></svg>'
    assert resolve_pet_space_upload_mime_type("mascot.svg", "application/octet-stream", svg) == "image/svg+xml"


def test_svg_sniff_when_no_filename() -> None:
    svg = b"<svg xmlns=\"http://www.w3.org/2000/svg\"></svg>"
    assert resolve_pet_space_upload_mime_type(None, None, svg) == "image/svg+xml"


def test_gif_magic_bytes() -> None:
    blob = b"GIF89a" + b"\x00" * 20
    assert resolve_pet_space_upload_mime_type(None, "application/octet-stream", blob) == "image/gif"
