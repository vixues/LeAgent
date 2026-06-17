"""Deterministic, stdlib-only placeholder asset encoders.

These build *minimal but structurally valid* media bytes so the offline
generation backend can drive the full game-art pipeline end-to-end with
no external services and no third-party encoders. Determinism (seeded by
the prompt) keeps tests hermetic and digests stable.

- :func:`solid_png` — a real PNG (zlib + CRC) of a solid colour.
- :func:`placeholder_mp4` — a structurally valid MP4 (ftyp + mdat boxes).
- :func:`triangle_glb` — a valid binary glTF (GLB) with a single coloured
  triangle that ``THREE.GLTFLoader`` can parse.
"""

from __future__ import annotations

import hashlib
import json
import struct
import zlib


def color_from_prompt(prompt: str) -> tuple[int, int, int]:
    """Derive a stable RGB triple from a prompt string."""
    digest = hashlib.sha256((prompt or "asset").encode("utf-8")).digest()
    # Bias towards mid-bright colours so previews read well on any theme.
    r = 64 + digest[0] % 160
    g = 64 + digest[1] % 160
    b = 64 + digest[2] % 160
    return r, g, b


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def solid_png(width: int = 512, height: int = 512, rgb: tuple[int, int, int] = (90, 120, 200)) -> bytes:
    """Encode a solid-colour RGB PNG of ``width`` x ``height``."""
    width = max(1, min(int(width), 2048))
    height = max(1, min(int(height), 2048))
    r, g, b = (max(0, min(int(c), 255)) for c in rgb)
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    row = b"\x00" + bytes((r, g, b)) * width  # filter byte 0 + pixels
    raw = row * height
    idat = zlib.compress(raw, 9)
    return (
        signature
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


def _mp4_box(tag: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload) + 8) + tag + payload


def placeholder_mp4(seed: str = "") -> bytes:
    """A minimal structurally valid MP4 (``ftyp`` + ``mdat``).

    Not a playable video stream, but a well-formed container with the
    correct magic so MIME sniffing and download work; the GenUI ``Video``
    player degrades gracefully when the media cannot decode.
    """
    ftyp = _mp4_box(b"ftyp", b"isom" + struct.pack(">I", 0x200) + b"isomiso2mp41")
    payload = hashlib.sha256((seed or "video").encode("utf-8")).digest()
    mdat = _mp4_box(b"mdat", payload)
    return ftyp + mdat


def triangle_glb(rgb: tuple[int, int, int] = (200, 120, 90)) -> bytes:
    """Encode a valid GLB containing a single coloured triangle."""
    r, g, b = (max(0.0, min(c / 255.0, 1.0)) for c in rgb)
    positions = [
        0.0, 0.0, 0.0,
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
    ]
    bin_data = b"".join(struct.pack("<f", v) for v in positions)
    gltf = {
        "asset": {"version": "2.0", "generator": "leagent-offline"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [
            {"primitives": [{"attributes": {"POSITION": 0}, "material": 0}]}
        ],
        "materials": [
            {"pbrMetallicRoughness": {"baseColorFactor": [r, g, b, 1.0]}}
        ],
        "accessors": [
            {
                "bufferView": 0,
                "componentType": 5126,  # FLOAT
                "count": 3,
                "type": "VEC3",
                "min": [0.0, 0.0, 0.0],
                "max": [1.0, 1.0, 0.0],
            }
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": len(bin_data)}
        ],
        "buffers": [{"byteLength": len(bin_data)}],
    }
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_pad = (4 - len(json_bytes) % 4) % 4
    json_bytes += b" " * json_pad
    bin_pad = (4 - len(bin_data) % 4) % 4
    bin_bytes = bin_data + b"\x00" * bin_pad

    json_chunk = struct.pack("<I", len(json_bytes)) + b"JSON" + json_bytes
    bin_chunk = struct.pack("<I", len(bin_bytes)) + b"BIN\x00" + bin_bytes
    total = 12 + len(json_chunk) + len(bin_chunk)
    header = b"glTF" + struct.pack("<II", 2, total)
    return header + json_chunk + bin_chunk


__all__ = [
    "color_from_prompt",
    "placeholder_mp4",
    "solid_png",
    "triangle_glb",
]
