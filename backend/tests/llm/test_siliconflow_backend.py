"""SiliconFlow image-generation backend.

Covers credential gating, registration in the default generation service,
and a mocked end-to-end ``generate`` that downloads the returned image URL
into managed bytes. All assertions run without real credentials.
"""

from __future__ import annotations

import contextlib
from typing import Any

import pytest

from leagent.llm.generation import build_default_generation_service
from leagent.llm.generation.backends import SiliconFlowImageBackend


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


# -- mocked generate ---------------------------------------------------------


class _FakeResponse:
    def __init__(self, *, json_body: Any = None, content: bytes = b"", headers: dict | None = None):
        self._json = json_body
        self.content = content
        self.headers = headers or {}

    def raise_for_status(self) -> None:
        return None

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
    # payload mirrors the SiliconFlow images/generations contract
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
async def test_siliconflow_requires_api_key(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    out = await SiliconFlowImageBackend().generate(kind="image", prompt="hero")
    assert out.success is False
    assert "API key" in (out.error or "")
