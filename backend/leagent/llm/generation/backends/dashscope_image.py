"""DashScope Wanx image generation backend."""

from __future__ import annotations

from typing import Any

from leagent.utils.logging import get_logger

from leagent.llm.generation.adapter import provider_result_to_output
from leagent.llm.generation.base import GenerationOutput
from leagent.llm.generation.config import get_image_gen_config
from leagent.llm.generation.providers.dashscope import DashScopeWanxProvider

logger = get_logger(__name__)


class DashScopeImageBackend:
    """Text-to-image via Alibaba DashScope Wanx API."""

    name = "dashscope"
    kinds = ("image",)

    def _credentials(self) -> dict[str, str]:
        return get_image_gen_config().backend_credentials("dashscope")

    def available(self) -> bool:
        return bool(self._credentials().get("api_key", "").strip())

    def _make_provider(self) -> DashScopeWanxProvider:
        creds = self._credentials()
        kwargs: dict[str, Any] = {"api_key": creds.get("api_key", "").strip()}
        if base_url := creds.get("base_url", "").strip():
            kwargs["base_url"] = base_url
        return DashScopeWanxProvider(**kwargs)

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        if kind != "image":
            return GenerationOutput.failure(kind, f"{self.name} produces only images")
        provider = self._make_provider()
        try:
            model = str(params.get("model") or "wanx2.1-t2i-turbo")
            gen_kwargs: dict[str, Any] = {}
            if size := params.get("size"):
                gen_kwargs["size"] = size
            result = await provider.generate(model=model, prompt=prompt, **gen_kwargs)
            return provider_result_to_output(
                result, kind="image", provider=self.name, model=model,
            )
        finally:
            aclose = getattr(provider, "aclose", None)
            if aclose is not None:
                try:
                    await aclose()
                except Exception:  # noqa: BLE001
                    logger.debug("image_provider_aclose_failed", provider=self.name)


__all__ = ["DashScopeImageBackend"]
