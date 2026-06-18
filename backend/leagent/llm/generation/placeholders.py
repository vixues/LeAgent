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


def sprite_sheet_png(
    prompt: str = "",
    *,
    frames: int = 8,
    cols: int = 4,
    tile: int = 96,
) -> bytes:
    """Encode a deterministic VFX flipbook / sprite-sheet PNG.

    Produces a ``cols`` × ``rows`` grid of ``tile``-sized cells, each tinted by
    a per-frame variation of the prompt colour so the sheet reads as an
    animated sequence (particles / explosion / glow ramp). Structurally a valid
    RGB PNG that any engine's sprite importer can slice by the frame grid.
    """
    frames = max(1, min(int(frames), 64))
    cols = max(1, min(int(cols), frames))
    rows = (frames + cols - 1) // cols
    tile = max(8, min(int(tile), 256))
    width = cols * tile
    height = rows * tile

    base = color_from_prompt(prompt or "vfx")
    # Pre-compute each frame's colour (brightness ramp across the sequence).
    frame_rgb: list[tuple[int, int, int]] = []
    for i in range(frames):
        t = i / max(1, frames - 1)
        # Ease from the base colour toward white then back (a glow pulse).
        glow = 1.0 - abs(0.5 - t) * 2.0
        frame_rgb.append(tuple(
            max(0, min(int(base[c] + (255 - base[c]) * glow * 0.7), 255))
            for c in range(3)
        ))

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter byte
        cell_row = y // tile
        for x in range(width):
            cell_col = x // tile
            idx = cell_row * cols + cell_col
            if idx < frames:
                r, g, b = frame_rgb[idx]
            else:
                r, g, b = (24, 24, 24)  # padding cells (transparent-ish dark)
            raw += bytes((r, g, b))
    idat = zlib.compress(bytes(raw), 9)
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


def silent_wav(seed: str = "", *, duration_sec: float = 1.0, sample_rate: int = 16000) -> bytes:
    """Encode a deterministic, structurally valid mono 16-bit PCM WAV.

    Produces a short near-silent tone whose faint per-sample variation is
    seeded by the prompt, so credential-free ``audio`` generation runs end to
    end and any player / MIME sniffer accepts the bytes.
    """
    duration_sec = max(0.1, min(float(duration_sec), 30.0))
    sample_rate = max(8000, min(int(sample_rate), 48000))
    n_samples = int(duration_sec * sample_rate)
    digest = hashlib.sha256((seed or "audio").encode("utf-8")).digest()
    amplitude = 16 + digest[0] % 48  # very quiet, but non-zero
    frames = bytearray()
    for i in range(n_samples):
        # Low-frequency square-ish wobble keeps it deterministic and tiny.
        sign = 1 if (i // 64) % 2 == 0 else -1
        frames += struct.pack("<h", sign * amplitude)

    byte_rate = sample_rate * 2  # mono, 16-bit
    data_size = len(frames)
    header = b"RIFF"
    header += struct.pack("<I", 36 + data_size)
    header += b"WAVE"
    header += b"fmt "
    header += struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, byte_rate, 2, 16)
    header += b"data"
    header += struct.pack("<I", data_size)
    return header + bytes(frames)


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
    "silent_wav",
    "solid_png",
    "sprite_sheet_png",
    "triangle_glb",
]
