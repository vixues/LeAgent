"""Phase 3 — multimodal generation depth + standardized contract.

Covers the offline-deterministic floor for the new VFX modality, the typed
``GenerationRequest`` contract, img2img/ControlNet conditioning influence, the
dedicated upscale hook, and per-modality backend availability gating. All
assertions run credential-free against the always-registered offline backend.
"""

from __future__ import annotations

import os

import pytest

from leagent.llm.capabilities import Modality, TaskType, kind_to_output, kind_to_task
from leagent.llm.generation import (
    GENERATION_KINDS,
    GenerationRequest,
    GenerationService,
    build_default_generation_service,
)
from leagent.llm.generation.backends import (
    HttpUpscaleBackend,
    HttpVfxBackend,
    OfflineGenerationBackend,
)
from leagent.llm.generation.placeholders import sprite_sheet_png


# -- standardized request contract ------------------------------------------


def test_generation_request_validate_rejects_unknown_kind():
    req = GenerationRequest(kind="hologram", prompt="x")
    assert req.validate() is not None


def test_generation_request_requires_prompt_or_image():
    assert GenerationRequest(kind="image", prompt="").validate() is not None
    assert GenerationRequest(kind="image", prompt="", image={"file_id": "f"}).validate() is None
    assert GenerationRequest(kind="image", prompt="hero").validate() is None


def test_generation_request_from_params_round_trips_conditioning():
    req = GenerationRequest.from_params(
        kind="image",
        prompt="knight",
        provider="local",
        model="sdxl",
        image={"file_id": "ref"},
        controlnet={"mode": "openpose", "strength": 0.7},
        width=512,
        height=512,
    )
    assert req.kind == "image"
    assert req.model == "sdxl"
    assert req.controlnet == {"mode": "openpose", "strength": 0.7}
    flat = req.as_params()
    assert flat["model"] == "sdxl"
    assert flat["image"] == {"file_id": "ref"}
    assert flat["controlnet"]["mode"] == "openpose"
    assert flat["width"] == 512


# -- VFX modality ------------------------------------------------------------


def test_vfx_is_a_known_generation_kind():
    assert "vfx" in GENERATION_KINDS
    assert kind_to_task("vfx") == TaskType.VFX_GEN
    assert kind_to_output("vfx") == Modality.VFX


def test_sprite_sheet_png_is_deterministic_and_valid():
    a = sprite_sheet_png("fireball", frames=8, cols=4)
    b = sprite_sheet_png("fireball", frames=8, cols=4)
    assert a == b  # deterministic
    assert a.startswith(b"\x89PNG\r\n\x1a\n")
    # different prompt → different bytes
    assert a != sprite_sheet_png("smoke", frames=8, cols=4)


@pytest.mark.asyncio
async def test_offline_backend_produces_vfx_sprite_sheet():
    backend = OfflineGenerationBackend()
    out = await backend.generate(kind="vfx", prompt="explosion", frames=9, cols=3, fps=15)
    assert out.success
    assert out.kind == "vfx"
    assert out.mime == "image/png"
    assert out.data and out.data.startswith(b"\x89PNG")
    anim = out.meta["animation"]
    assert anim["frames"] == 9
    assert anim["cols"] == 3
    assert anim["rows"] == 3
    assert anim["fps"] == 15


@pytest.mark.asyncio
async def test_service_generates_vfx_offline():
    svc = build_default_generation_service()
    out = await svc.generate(kind="vfx", prompt="magic glow", provider="offline", frames=6, cols=3)
    assert out.success
    assert out.kind == "vfx"
    assert out.meta["animation"]["frames"] == 6


# -- img2img / ControlNet conditioning influence (offline) -------------------


@pytest.mark.asyncio
async def test_img2img_reference_changes_offline_output():
    backend = OfflineGenerationBackend()
    plain = await backend.generate(kind="image", prompt="hero", width=64, height=64)
    conditioned = await backend.generate(
        kind="image", prompt="hero", width=64, height=64, image={"file_id": "ref-a"}
    )
    assert plain.success and conditioned.success
    assert plain.data != conditioned.data  # conditioning visibly changes the asset
    assert conditioned.meta.get("img2img") is True


@pytest.mark.asyncio
async def test_controlnet_conditioning_recorded_in_meta():
    backend = OfflineGenerationBackend()
    out = await backend.generate(
        kind="image", prompt="pose", width=64, height=64,
        controlnet={"mode": "openpose", "strength": 0.9},
    )
    assert out.success
    assert out.meta["controlnet"]["mode"] == "openpose"


# -- backend availability gating ---------------------------------------------


def test_http_backends_unavailable_without_env(monkeypatch):
    for var in ("LEAGENT_VFX_GEN_URL", "LEAGENT_UPSCALE_URL"):
        monkeypatch.delenv(var, raising=False)
    assert HttpVfxBackend().available() is False
    assert HttpUpscaleBackend().available() is False


def test_http_backends_available_with_env(monkeypatch):
    monkeypatch.setenv("LEAGENT_VFX_GEN_URL", "https://vfx.example/api")
    monkeypatch.setenv("LEAGENT_UPSCALE_URL", "https://sr.example/api")
    assert HttpVfxBackend().available() is True
    assert HttpUpscaleBackend().available() is True


def test_vfx_backend_registered_in_default_service():
    svc = build_default_generation_service()
    # offline floor always serves vfx; http_vfx is registered as the real hook.
    palette = svc.palette_providers("vfx")
    assert "offline" in palette
    assert "http_vfx" in palette


@pytest.mark.asyncio
async def test_unsupported_kind_fails_cleanly():
    svc = GenerationService()
    out = await svc.generate(kind="hologram", prompt="x")
    assert out.success is False
    assert "unsupported kind" in (out.error or "")
