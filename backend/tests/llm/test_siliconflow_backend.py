"""SiliconFlow image-generation backend.

Covers credential gating, registration in the default generation service,
model-family payload building, and mocked end-to-end ``generate`` flows.
All assertions run without real credentials.
"""

from __future__ import annotations

import base64
import contextlib
from typing import Any

import pytest

from leagent.llm.generation import build_default_generation_service
from leagent.llm.generation.backends import SiliconFlowImageBackend
from leagent.llm.image_gen.siliconflow import (
    build_payload,
    match_model_family,
    snap_image_size,
    SiliconFlowImageProvider,
    SiliconFlowModelFamily,
)


# -- availability gating -----------------------------------------------------


def test_siliconflow_unavailable_without_env(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    assert SiliconFlowImageBackend().available() is False


def test_siliconflow_available_with_env(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")
    assert SiliconFlowImageBackend().available() is True


def test_siliconflow_registered_in_default_service():
    svc = build_default_generation_service()
    palette = svc.palette_providers("image")
    assert "siliconflow" in palette
    assert "offline" in palette


# -- model-family payload building -------------------------------------------


def test_kolors_payload_unchanged():
    payload = build_payload(
        "Kwai-Kolors/Kolors",
        "an island near sea",
        {"width": 1024, "height": 1024, "num_inference_steps": 20, "guidance_scale": 7.5},
    )
    assert payload["model"] == "Kwai-Kolors/Kolors"
    assert payload["image_size"] == "1024x1024"
    assert payload["batch_size"] == 1
    assert payload["num_inference_steps"] == 20
    assert payload["guidance_scale"] == 7.5
    assert "cfg" not in payload


def test_z_image_turbo_payload_uses_cfg_not_guidance():
    payload = build_payload(
        "Tongyi-MAI/Z-Image-Turbo",
        "hero portrait",
        {"width": 1024, "height": 1024, "cfg": 4.0, "num_inference_steps": 8},
    )
    assert payload["cfg"] == 4.0
    assert payload["num_inference_steps"] == 8
    assert "guidance_scale" not in payload
    assert "batch_size" not in payload
    assert payload["image_size"] == "1328x1328"


def test_qwen_edit_omits_image_size():
    payload = build_payload(
        "Qwen/Qwen-Image-Edit-2509",
        "edit the scene",
        {
            "width": 1024,
            "height": 1024,
            "cfg": 4.0,
            "image": "https://example.com/a.png",
            "image2": "https://example.com/b.png",
        },
    )
    assert "image_size" not in payload
    assert payload["cfg"] == 4.0
    assert payload["image"] == "https://example.com/a.png"
    assert payload["image2"] == "https://example.com/b.png"
    assert "guidance_scale" not in payload


def test_qwen_image_snaps_to_recommended_size():
    assert snap_image_size(SiliconFlowModelFamily.QWEN_IMAGE, 1024, 1024) == "1328x1328"
    payload = build_payload(
        "Qwen/Qwen-Image",
        "landscape",
        {"width": 1024, "height": 1024, "cfg": 4.0},
    )
    assert payload["image_size"] == "1328x1328"
    assert payload["cfg"] == 4.0
    assert match_model_family("Qwen/Qwen-Image") is SiliconFlowModelFamily.QWEN_IMAGE


def test_flux_omits_guidance_scale():
    payload = build_payload(
        "black-forest-labs/FLUX.1-schnell",
        "fast render",
        {"width": 1024, "height": 1024},
    )
    assert payload["image_size"] == "1024x1024"
    assert payload["num_inference_steps"] == 4
    assert "guidance_scale" not in payload
    assert "batch_size" not in payload


# -- mocked generate ---------------------------------------------------------


class _FakeResponse:
    def __init__(
        self,
        *,
        json_body: Any = None,
        content: bytes = b"",
        headers: dict | None = None,
        status_code: int = 200,
        text: str = "",
    ):
        self._json = json_body
        self.content = content
        self.headers = headers or {}
        self.status_code = status_code
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> Any:
        return self._json


class _FakeClient:
    def __init__(self, post_resp: _FakeResponse, get_resp: _FakeResponse):
        self._post_resp = post_resp
        self._get_resp = get_resp
        self.posted: dict[str, Any] = {}

    async def post(self, url: str, *, headers: dict, json: dict) -> _FakeResponse:
        self.posted = {"url": url, "headers": headers, "json": json}
        return self._post_resp

    async def get(self, url: str, *, follow_redirects: bool = False) -> _FakeResponse:
        return self._get_resp


class _FakeTransport:
    def __init__(self, client: _FakeClient):
        self._client = client
        self.closed = False

    def request_headers(self, extra: dict | None = None) -> dict:
        return dict(extra or {})

    @property
    def complete_client(self) -> _FakeClient:
        return self._client

    @contextlib.contextmanager
    def request_span(self, operation: str, **attrs: Any):
        yield None

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_siliconflow_generate_downloads_image_bytes(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")
    png = b"\x89PNG\r\n\x1a\nfake"
    client = _FakeClient(
        post_resp=_FakeResponse(json_body={"images": [{"url": "https://img/x.png"}], "seed": 42}),
        get_resp=_FakeResponse(content=png, headers={"content-type": "image/png"}),
    )
    transport = _FakeTransport(client)
    monkeypatch.setattr(
        "leagent.llm.transport.HttpTransport", lambda *a, **k: transport
    )

    backend = SiliconFlowImageBackend()
    out = await backend.generate(
        kind="image", prompt="an island near sea", width=1024, height=1024,
        num_inference_steps=20, guidance_scale=7.5,
    )

    assert out.success is True
    assert out.data == png
    assert out.provider == "siliconflow"
    assert out.meta["seed"] == 42
    assert transport.closed is True
    sent = client.posted["json"]
    assert sent["model"] == "Kwai-Kolors/Kolors"
    assert sent["image_size"] == "1024x1024"
    assert sent["batch_size"] == 1
    assert sent["num_inference_steps"] == 20
    assert sent["guidance_scale"] == 7.5
    assert client.posted["headers"]["Authorization"] == "Bearer sk-test"


@pytest.mark.asyncio
async def test_siliconflow_generate_falls_back_to_url_on_download_error(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")

    class _RaisingClient(_FakeClient):
        async def get(self, url: str, *, follow_redirects: bool = False) -> _FakeResponse:
            raise ConnectionError("temporary")

    client = _RaisingClient(
        post_resp=_FakeResponse(json_body={"images": [{"url": "https://img/x.png"}]}),
        get_resp=_FakeResponse(),
    )
    transport = _FakeTransport(client)
    monkeypatch.setattr("leagent.llm.transport.HttpTransport", lambda *a, **k: transport)

    out = await SiliconFlowImageBackend().generate(kind="image", prompt="hero")
    assert out.success is True
    assert out.data is None
    assert out.meta["url"] == "https://img/x.png"


@pytest.mark.asyncio
async def test_response_b64_json_decoded(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")
    png = b"\x89PNG\r\n\x1a\nb64"
    client = _FakeClient(
        post_resp=_FakeResponse(json_body={"images": [{"b64_json": base64.b64encode(png).decode()}]}),
        get_resp=_FakeResponse(),
    )
    transport = _FakeTransport(client)
    monkeypatch.setattr("leagent.llm.transport.HttpTransport", lambda *a, **k: transport)

    out = await SiliconFlowImageBackend().generate(
        kind="image",
        prompt="hero",
        model="Tongyi-MAI/Z-Image-Turbo",
        width=1328,
        height=1328,
        cfg=4.0,
    )
    assert out.success is True
    assert out.data == png
    assert client.posted["json"]["cfg"] == 4.0
    assert "guidance_scale" not in client.posted["json"]


@pytest.mark.asyncio
async def test_siliconflow_error_body_surfaced(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")
    client = _FakeClient(
        post_resp=_FakeResponse(
            status_code=400,
            json_body={"message": "invalid model", "code": 20012},
        ),
        get_resp=_FakeResponse(),
    )
    transport = _FakeTransport(client)
    monkeypatch.setattr("leagent.llm.transport.HttpTransport", lambda *a, **k: transport)

    out = await SiliconFlowImageBackend().generate(kind="image", prompt="hero")
    assert out.success is False
    assert "invalid model" in (out.error or "")


@pytest.mark.asyncio
async def test_siliconflow_requires_api_key(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    out = await SiliconFlowImageBackend().generate(kind="image", prompt="hero")
    assert out.success is False
    assert "API key" in (out.error or "")


@pytest.mark.asyncio
async def test_provider_z_image_payload_via_backend(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")
    client = _FakeClient(
        post_resp=_FakeResponse(json_body={"images": [{"url": "https://img/z.png"}]}),
        get_resp=_FakeResponse(content=b"png", headers={"content-type": "image/png"}),
    )
    transport = _FakeTransport(client)
    monkeypatch.setattr("leagent.llm.transport.HttpTransport", lambda *a, **k: transport)

    out = await SiliconFlowImageBackend().generate(
        kind="image",
        prompt="turbo scene",
        model="Tongyi-MAI/Z-Image-Turbo",
        width=1664,
        height=928,
        num_inference_steps=8,
        cfg=4.0,
    )
    assert out.success is True
    sent = client.posted["json"]
    assert sent["model"] == "Tongyi-MAI/Z-Image-Turbo"
    assert sent["image_size"] == "1664x928"
    assert sent["cfg"] == 4.0
    assert "batch_size" not in sent


@pytest.mark.asyncio
async def test_provider_direct_generate(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-test")
    png = b"\x89PNG"
    client = _FakeClient(
        post_resp=_FakeResponse(json_body={"images": [{"url": "https://img/p.png"}]}),
        get_resp=_FakeResponse(content=png, headers={"content-type": "image/png"}),
    )
    transport = _FakeTransport(client)
    monkeypatch.setattr("leagent.llm.transport.HttpTransport", lambda *a, **k: transport)

    provider = SiliconFlowImageProvider(api_key="sk-test")
    result = await provider.generate(model="Kwai-Kolors/Kolors", prompt="cat")
    assert result.success is True
    assert result.b64_json is not None
    assert base64.b64decode(result.b64_json) == png
