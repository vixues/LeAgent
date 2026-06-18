"""SiliconFlow image generation backend."""

from __future__ import annotations

import base64
from typing import Any

from leagent.llm.generation.base import GenerationOutput
from leagent.llm.generation.config import get_image_gen_config
from leagent.llm.generation.providers.siliconflow import DEFAULT_MODEL, SiliconFlowImageProvider


class SiliconFlowImageBackend:
    """Credential-gated text-to-image backend for SiliconFlow."""

    name = "siliconflow"
    kinds = ("image",)

    def _credentials(self) -> dict[str, str]:
        return get_image_gen_config().backend_credentials("siliconflow")

    def available(self) -> bool:
        return bool(self._credentials().get("api_key", "").strip())

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        if kind != "image":
            return GenerationOutput.failure(kind, "siliconflow produces only images")
        creds = self._credentials()
        api_key = creds.get("api_key", "").strip()
        if not api_key:
            return GenerationOutput.failure("image", "SiliconFlow API key is not configured")

        provider = SiliconFlowImageProvider.from_env(
            api_key=api_key,
            base_url=creds.get("base_url", ""),
        )
        model = str(params.get("model") or DEFAULT_MODEL)
        call_params = {k: v for k, v in params.items() if k != "model"}
        try:
            result = await provider.generate(
                model=model,
                prompt=prompt,
                timeout=float(call_params.pop("timeout", 300)),
                **call_params,
            )
        except RuntimeError as exc:
            return GenerationOutput.failure("image", str(exc))

        data: bytes | None = None
        if result.b64_json:
            data = base64.b64decode(result.b64_json)
        meta: dict[str, Any] = dict(result.metadata or {})
        if result.url:
            meta.setdefault("url", result.url)
        if data is None and not result.url:
            return GenerationOutput.failure("image", "siliconflow returned no image bytes")
        return GenerationOutput(
            success=True,
            kind="image",
            data=data,
            mime=result.mime or "image/png",
            filename="image.png",
            provider=self.name,
            model=model,
            meta=meta,
        )


__all__ = ["SiliconFlowImageBackend"]
