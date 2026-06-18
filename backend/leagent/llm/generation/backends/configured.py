"""Admin-configured custom generation backends."""

from __future__ import annotations

import base64
from typing import Any

from leagent.llm.generation.backends._utils import parse_size
from leagent.llm.generation.base import GenerationOutput
from leagent.llm.generation.config import CustomProvider, get_image_gen_config


class ConfiguredGenerationBackend:
    """Generic backend driven by a :class:`CustomProvider` from admin config."""

    def __init__(self, provider: CustomProvider) -> None:
        self._provider = provider
        self.name = provider.name
        self.kinds = tuple(provider.kinds)

    def _provider_config(self) -> CustomProvider:
        return get_image_gen_config().get_custom_provider(self.name) or self._provider

    def available(self) -> bool:
        provider = self._provider_config()
        if not provider.enabled:
            return False
        if not provider.resolved_base_url():
            return False
        if provider.protocol == "openai":
            return bool(provider.resolved_api_key())
        return True

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        provider = self._provider_config()
        if kind not in provider.kinds:
            return GenerationOutput.failure(kind, f"{self.name} cannot produce '{kind}'")
        base_url = provider.resolved_base_url().rstrip("/")
        if not base_url:
            return GenerationOutput.failure(kind, f"{self.name} has no base URL configured")
        api_key = provider.resolved_api_key()
        model = str(params.get("model") or (provider.models[0] if provider.models else ""))

        if provider.protocol == "openai":
            return await self._generate_openai(kind, prompt, base_url, api_key, model, params)
        return await self._generate_http(kind, prompt, base_url, api_key, model, params)

    async def _generate_openai(
        self, kind: str, prompt: str, base_url: str, api_key: str, model: str, params: dict[str, Any]
    ) -> GenerationOutput:
        from leagent.llm.transport import HttpTransport, TransportConfig

        transport = HttpTransport(TransportConfig(complete_timeout=float(params.get("timeout", 300))))
        try:
            headers = transport.request_headers({
                "Authorization": f"Bearer {api_key}" if api_key else "",
                "Content-Type": "application/json",
            })
            client = transport.complete_client
            if kind == "image":
                w, h = parse_size(params.get("size") or params.get("width"), default=(1024, 1024))
                if params.get("width") and params.get("height"):
                    w, h = int(params["width"]), int(params["height"])
                payload: dict[str, Any] = {
                    "model": model or "dall-e-3",
                    "prompt": prompt,
                    "size": params.get("size") or f"{w}x{h}",
                    "n": 1,
                }
                resp = await client.post(f"{base_url}/images/generations", headers=headers, json=payload)
                resp.raise_for_status()
                body = resp.json()
                items = body.get("data") or []
                if items and isinstance(items[0], dict):
                    if items[0].get("b64_json"):
                        return GenerationOutput(
                            success=True, kind="image", data=base64.b64decode(items[0]["b64_json"]),
                            mime="image/png", filename="image.png", provider=self.name, model=model,
                        )
                    if items[0].get("url"):
                        url = str(items[0]["url"])
                        try:
                            asset = await client.get(url, follow_redirects=True)
                            asset.raise_for_status()
                            return GenerationOutput(
                                success=True, kind="image", data=asset.content,
                                mime=asset.headers.get("content-type", "image/png"),
                                filename="image.png", provider=self.name, model=model, meta={"url": url},
                            )
                        except Exception:  # noqa: BLE001
                            return GenerationOutput(
                                success=True, kind="image", data=None, mime="image/png",
                                filename="image.png", provider=self.name, model=model, meta={"url": url},
                            )
                return GenerationOutput.failure("image", f"{self.name} returned no image: {body}")
            if kind == "audio":
                payload = {
                    "model": model or "tts-1",
                    "input": prompt,
                    "voice": params.get("voice") or "alloy",
                }
                if params.get("response_format"):
                    payload["response_format"] = params["response_format"]
                resp = await client.post(f"{base_url}/audio/speech", headers=headers, json=payload)
                resp.raise_for_status()
                return GenerationOutput(
                    success=True, kind="audio", data=resp.content,
                    mime=resp.headers.get("content-type", "audio/mpeg"),
                    filename="audio.mp3", provider=self.name, model=model,
                )
            return GenerationOutput.failure(kind, f"{self.name} openai protocol cannot produce '{kind}'")
        finally:
            await transport.aclose()

    async def _generate_http(
        self, kind: str, prompt: str, base_url: str, api_key: str, model: str, params: dict[str, Any]
    ) -> GenerationOutput:
        from leagent.llm.transport import HttpTransport, TransportConfig

        transport = HttpTransport(TransportConfig(complete_timeout=float(params.get("timeout", 300))))
        try:
            headers = transport.request_headers(
                {"Authorization": f"Bearer {api_key}"} if api_key else {}
            )
            resp = await transport.complete_client.post(
                base_url,
                headers=headers,
                json={
                    "kind": kind,
                    "prompt": prompt,
                    "model": model,
                    "params": {k: v for k, v in params.items() if k != "timeout"},
                },
            )
            resp.raise_for_status()
            mime = resp.headers.get("content-type", "application/octet-stream")
            ext = {"image": "png", "video": "mp4", "audio": "mp3", "model3d": "glb", "vfx": "png"}.get(kind, "bin")
            return GenerationOutput(
                success=True, kind=kind, data=resp.content, mime=mime,
                filename=f"{kind}.{ext}", provider=self.name, model=model,
            )
        finally:
            await transport.aclose()


__all__ = ["ConfiguredGenerationBackend"]
