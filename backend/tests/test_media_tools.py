"""Chat-callable media tools route through the offline GenerationService.

Credential-free: forces the deterministic offline backend so image / video /
audio tools produce valid placeholder bytes end to end.
"""

from __future__ import annotations

import pytest

from leagent.llm.generation import config as cfg
from leagent.llm.generation.config import ImageGenConfigStore, ImageGenPreset
from leagent.tools.base import ToolContext


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


@pytest.mark.asyncio
async def test_video_generate_tool_offline(store):
    from leagent.tools.media.video_generate import VideoGenerateTool

    res = await VideoGenerateTool().execute({"prompt": "a wave", "duration": 2}, _ctx())
    assert res["success"] is True
    assert res["kind"] == "video"
    assert res["mime"] == "video/mp4"


@pytest.mark.asyncio
async def test_audio_generate_tool_offline(store):
    from leagent.tools.media.audio_generate import AudioGenerateTool

    res = await AudioGenerateTool().execute({"prompt": "hello"}, _ctx())
    assert res["success"] is True
    assert res["kind"] == "audio"
    assert res["mime"] == "audio/wav"


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
