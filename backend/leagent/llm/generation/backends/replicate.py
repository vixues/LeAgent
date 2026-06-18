"""Replicate image+video generation backend."""

from __future__ import annotations

import asyncio
from typing import Any

from leagent.utils.logging import get_logger

from leagent.llm.generation.backends._utils import parse_size
from leagent.llm.generation.base import GenerationOutput
from leagent.llm.generation.config import get_image_gen_config

logger = get_logger(__name__)


class ReplicateBackend:
    """Credential-gated image+video backend for Replicate."""

    name = "replicate"
    kinds = ("image", "video")

    _DEFAULT_URL = "https://api.replicate.com/v1"
    _DEFAULT_IMAGE_MODEL = "black-forest-labs/flux-schnell"
    _DEFAULT_VIDEO_MODEL = "minimax/video-01"

    def _credentials(self) -> dict[str, str]:
        return get_image_gen_config().backend_credentials("replicate")

    def available(self) -> bool:
        return bool(self._credentials().get("api_key", "").strip())

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        if kind not in self.kinds:
            return GenerationOutput.failure(kind, f"replicate cannot produce '{kind}'")
        creds = self._credentials()
        api_key = creds.get("api_key", "").strip()
        if not api_key:
            return GenerationOutput.failure(kind, "Replicate API token is not configured")
        base_url = (creds.get("base_url", "").strip() or self._DEFAULT_URL).rstrip("/")
        default_model = self._DEFAULT_IMAGE_MODEL if kind == "image" else self._DEFAULT_VIDEO_MODEL
        model = str(params.get("model") or default_model)

        gen_input: dict[str, Any] = {"prompt": prompt}
        if kind == "image":
            w, h = parse_size(params.get("size") or params.get("width"), default=(1024, 1024))
            if params.get("width") and params.get("height"):
                w, h = int(params["width"]), int(params["height"])
            gen_input["aspect_ratio"] = params.get("aspect_ratio") or "1:1"
            gen_input.setdefault("width", w)
            gen_input.setdefault("height", h)
        if (ref := params.get("image")) and isinstance(ref, dict):
            ref_url = ref.get("preview_url") or ref.get("src") or ref.get("url")
            if ref_url:
                gen_input["image"] = str(ref_url)

        from leagent.llm.transport import HttpTransport, TransportConfig

        transport = HttpTransport(TransportConfig(complete_timeout=float(params.get("timeout", 600))))
        try:
            headers = transport.request_headers({
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Prefer": "wait",
            })
            client = transport.complete_client
            create_url = f"{base_url}/models/{model}/predictions"
            with transport.request_span(f"{kind}_generate", model=model, provider=self.name):
                resp = await client.post(create_url, headers=headers, json={"input": gen_input})
            resp.raise_for_status()
            body = resp.json()

            status = body.get("status")
            poll_url = (body.get("urls") or {}).get("get")
            attempts = 0
            while status in ("starting", "processing") and poll_url and attempts < 120:
                await asyncio.sleep(2.0)
                poll = await client.get(poll_url, headers=headers)
                poll.raise_for_status()
                body = poll.json()
                status = body.get("status")
                attempts += 1

            if status != "succeeded":
                return GenerationOutput.failure(kind, f"replicate prediction {status}: {body.get('error')}")

            output = body.get("output")
            url = ""
            if isinstance(output, list) and output:
                url = str(output[0])
            elif isinstance(output, str):
                url = output
            if not url:
                return GenerationOutput.failure(kind, f"replicate returned no output: {output}")

            mime = "image/png" if kind == "image" else "video/mp4"
            filename = "image.png" if kind == "image" else "video.mp4"
            try:
                asset = await client.get(url, follow_redirects=True)
                asset.raise_for_status()
                return GenerationOutput(
                    success=True, kind=kind, data=asset.content,
                    mime=asset.headers.get("content-type", mime),
                    filename=filename, provider=self.name, model=model,
                    meta={"url": url},
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("replicate_download_failed", url=url, error=str(exc))
                return GenerationOutput(
                    success=True, kind=kind, data=None, mime=mime,
                    filename=filename, provider=self.name, model=model, meta={"url": url},
                )
        finally:
            await transport.aclose()


__all__ = ["ReplicateBackend"]
