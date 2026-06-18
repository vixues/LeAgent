"""Audio kind, custom providers, and ConfiguredGenerationBackend.

All assertions run credential-free against a temp ``providers.yaml`` plus a
stubbed HTTP transport, so the real ``~/.leagent`` file and network are never
touched.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from leagent.llm.generation import config as cfg
from leagent.llm.generation.backends import ConfiguredGenerationBackend, OfflineGenerationBackend
from leagent.llm.generation.config import CustomProvider, ImageGenConfigStore
from leagent.llm.generation.service import build_default_generation_service


@pytest.fixture()
def store(tmp_path, monkeypatch):
    path = tmp_path / "providers.yaml"
    s = ImageGenConfigStore(path=path)
    monkeypatch.setattr(cfg, "_STORE", s)
    return s


# -- audio kind --------------------------------------------------------------


def test_audio_is_a_generation_kind():
    from leagent.llm.generation.base import GENERATION_KINDS

    assert "audio" in GENERATION_KINDS


def test_offline_backend_produces_silent_wav():
    assert "audio" in OfflineGenerationBackend().kinds


@pytest.mark.asyncio
async def test_offline_audio_generation_returns_wav():
    out = await OfflineGenerationBackend().generate(kind="audio", prompt="hello world")
    assert out.success is True
    assert out.mime == "audio/wav"
    assert out.data is not None and out.data[:4] == b"RIFF"
    assert out.meta.get("placeholder") is True


@pytest.mark.asyncio
async def test_service_audio_failover_to_offline(store):
    svc = build_default_generation_service()
    out = await svc.generate(kind="audio", prompt="narration")
    assert out.success is True
    assert out.provider == "offline"


# -- custom providers --------------------------------------------------------


def test_custom_provider_crud_round_trip(store):
    store.upsert_custom_provider(CustomProvider(
        name="my-openai", kinds=["image", "audio"], protocol="openai",
        base_url="https://api.example.com/v1", api_key="sk-x", models=["m1"],
    ))
    got = store.get_custom_provider("my-openai")
    assert got is not None
    assert got.kinds == ["image", "audio"]
    assert got.resolved_api_key() == "sk-x"
    # survives a fresh store on the same file
    reopened = ImageGenConfigStore(path=store._path)
    assert reopened.get_custom_provider("my-openai") is not None
    assert store.delete_custom_provider("my-openai") is True
    assert store.get_custom_provider("my-openai") is None


def test_custom_provider_rejects_reserved_name(store):
    with pytest.raises(cfg.ImageGenConfigError):
        store.upsert_custom_provider(CustomProvider(name="offline", protocol="http"))
    with pytest.raises(cfg.ImageGenConfigError):
        store.upsert_custom_provider(CustomProvider(name="siliconflow", protocol="openai"))


def test_custom_provider_env_ref_resolution(store, monkeypatch):
    monkeypatch.setenv("MY_PROVIDER_KEY", "sk-env")
    store.upsert_custom_provider(CustomProvider(
        name="envp", kinds=["image"], protocol="openai",
        base_url="https://x", api_key="${MY_PROVIDER_KEY}",
    ))
    assert store.get_custom_provider("envp").resolved_api_key() == "sk-env"


def test_custom_providers_registered_in_service(store):
    store.upsert_custom_provider(CustomProvider(
        name="vidcustom", kinds=["video"], protocol="http",
        base_url="https://vid.example", models=["v1"],
    ))
    svc = build_default_generation_service()
    assert "vidcustom" in svc.palette_providers("video")


# -- ConfiguredGenerationBackend ---------------------------------------------


class _FakeResponse:
    def __init__(self, *, json_body=None, content=b"", headers=None):
        self._json = json_body or {}
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._json


class _FakeClient:
    def __init__(self, post_response):
        self._post_response = post_response
        self.calls: list[tuple[str, dict]] = []

    async def post(self, url, headers=None, json=None):
        self.calls.append((url, json or {}))
        return self._post_response

    async def get(self, url, **kwargs):
        return _FakeResponse(content=b"\x89PNG-bytes", headers={"content-type": "image/png"})


class _FakeTransport:
    def __init__(self, post_response):
        self.complete_client = _FakeClient(post_response)

    def request_headers(self, h):
        return dict(h)

    def request_span(self, *a, **k):
        class _Span:
            def __enter__(self_):
                return self_

            def __exit__(self_, *exc):
                return False

        return _Span()

    async def aclose(self):
        return None


def _patch_transport(monkeypatch, post_response):
    import leagent.llm.transport as transport_mod

    fake = _FakeTransport(post_response)
    monkeypatch.setattr(transport_mod, "HttpTransport", lambda *a, **k: fake)
    return fake


@pytest.mark.asyncio
async def test_configured_openai_image_b64(store, monkeypatch):
    import base64

    png = base64.b64encode(b"img-bytes").decode()
    fake = _patch_transport(monkeypatch, _FakeResponse(json_body={"data": [{"b64_json": png}]}))
    provider = CustomProvider(
        name="oai", kinds=["image"], protocol="openai",
        base_url="https://api.example.com/v1", api_key="sk-x", models=["m1"],
    )
    store.upsert_custom_provider(provider)
    backend = ConfiguredGenerationBackend(provider)
    assert backend.available() is True
    out = await backend.generate(kind="image", prompt="a cat")
    assert out.success is True
    assert out.data == b"img-bytes"
    assert fake.complete_client.calls[0][0].endswith("/images/generations")


@pytest.mark.asyncio
async def test_configured_openai_audio_bytes(store, monkeypatch):
    fake = _patch_transport(
        monkeypatch,
        _FakeResponse(content=b"mp3-bytes", headers={"content-type": "audio/mpeg"}),
    )
    provider = CustomProvider(
        name="oai-tts", kinds=["audio"], protocol="openai",
        base_url="https://api.example.com/v1", api_key="sk-x", models=["tts-1"],
    )
    backend = ConfiguredGenerationBackend(provider)
    out = await backend.generate(kind="audio", prompt="say hi")
    assert out.success is True
    assert out.data == b"mp3-bytes"
    assert out.mime == "audio/mpeg"
    assert fake.complete_client.calls[0][0].endswith("/audio/speech")


@pytest.mark.asyncio
async def test_configured_http_protocol_returns_bytes(store, monkeypatch):
    fake = _patch_transport(
        monkeypatch,
        _FakeResponse(content=b"vid-bytes", headers={"content-type": "video/mp4"}),
    )
    provider = CustomProvider(
        name="httpvid", kinds=["video"], protocol="http",
        base_url="https://vid.example/generate", models=["v1"],
    )
    backend = ConfiguredGenerationBackend(provider)
    assert backend.available() is True
    out = await backend.generate(kind="video", prompt="a clip")
    assert out.success is True
    assert out.data == b"vid-bytes"
    assert out.filename.endswith(".mp4")
    # the generic HTTP contract posts to the base URL directly
    assert fake.complete_client.calls[0][0] == "https://vid.example/generate"


@pytest.mark.asyncio
async def test_configured_backend_rejects_unsupported_kind(store):
    provider = CustomProvider(name="imgonly", kinds=["image"], protocol="openai",
                              base_url="https://x", api_key="k")
    out = await ConfiguredGenerationBackend(provider).generate(kind="audio", prompt="x")
    assert out.success is False
