"""Chat-callable media tools route through the offline GenerationService.

Credential-free: forces the deterministic offline backend so image / video /
audio tools produce valid placeholder bytes end to end.
"""

from __future__ import annotations

import pytest

from leagent.llm.generation import config as cfg
from leagent.llm.generation.config import ImageGenConfigStore, ImageGenPreset
from leagent.tools.base import ToolContext
from leagent.tools.media.base import build_media_filename


@pytest.fixture()
def store(tmp_path, monkeypatch):
    path = tmp_path / "providers.yaml"
    s = ImageGenConfigStore(path=path)
    monkeypatch.setattr(cfg, "_STORE", s)
    monkeypatch.setenv("LEAGENT_ART_OFFLINE", "1")
    return s


def _ctx() -> ToolContext:
    return ToolContext(user_id=None, session_id=None)


@pytest.mark.asyncio
async def test_image_generate_tool_offline(store):
    from leagent.tools.image.image_generate import ImageGenerateTool

    res = await ImageGenerateTool().execute({"prompt": "a forest", "size": "256x256"}, _ctx())
    assert res["success"] is True
    assert res["kind"] == "image"
    assert res["provider"] == "offline"
    assert res["placeholder"] is True
    # Prompt-derived name, not the backend placeholder "image.png"
    assert res["filename"] != "image.png"
    assert res["filename"].startswith("a_forest_")
    assert res["filename"].endswith(".png")


@pytest.mark.asyncio
async def test_image_generate_respects_explicit_filename(store):
    from leagent.tools.image.image_generate import ImageGenerateTool

    res = await ImageGenerateTool().execute(
        {"prompt": "a forest", "filename": "sunset_cat.png", "size": "256x256"},
        _ctx(),
    )
    assert res["success"] is True
    assert res["filename"] == "sunset_cat.png"


@pytest.mark.asyncio
async def test_video_generate_tool_offline(store):
    from leagent.tools.media.video_generate import VideoGenerateTool

    res = await VideoGenerateTool().execute({"prompt": "a wave", "duration": 2}, _ctx())
    assert res["success"] is True
    assert res["kind"] == "video"
    assert res["mime"] == "video/mp4"
    assert res["filename"] != "video.mp4"
    assert res["filename"].startswith("a_wave_")
    assert res["filename"].endswith(".mp4")


@pytest.mark.asyncio
async def test_audio_generate_tool_offline(store):
    from leagent.tools.media.audio_generate import AudioGenerateTool

    res = await AudioGenerateTool().execute({"prompt": "hello"}, _ctx())
    assert res["success"] is True
    assert res["kind"] == "audio"
    assert res["mime"] == "audio/wav"
    assert res["filename"].startswith("hello_")


@pytest.mark.asyncio
async def test_audio_tool_uses_default_preset_only_for_matching_kind(store, monkeypatch):
    """A default *image* preset must not hijack an audio generation."""
    store.upsert_preset(ImageGenPreset(id="img-def", label="Img", backend="siliconflow",
                                       model="Kwai-Kolors/Kolors", kind="image"))
    store.set_default_preset("img-def")

    from leagent.tools.media.base import resolve_preset_params

    provider, model, params = resolve_preset_params("audio", preset_id=None, provider=None)
    # the image default is skipped → no provider/model forced for audio
    assert provider is None
    assert model is None
    assert params == {}


def test_build_media_filename_from_prompt():
    name = build_media_filename(
        kind="image",
        prompt="a cute orange cat",
        ext="png",
        backend_filename="image.png",
    )
    assert name != "image.png"
    assert name.startswith("a_cute_orange_cat_")
    assert name.endswith(".png")


def test_build_media_filename_collision_avoidance():
    name = build_media_filename(
        kind="image",
        prompt="logo",
        ext="png",
        preferred="logo.png",
        taken={"logo.png"},
    )
    assert name == "logo_2.png"


def test_build_media_filename_cjk_prompt():
    name = build_media_filename(
        kind="image",
        prompt="一只可爱的猫坐在窗台",
        ext="png",
        backend_filename="image.png",
    )
    assert "可爱的猫" in name or name.startswith("一只")
    assert name.endswith(".png")
    assert name != "image.png"
