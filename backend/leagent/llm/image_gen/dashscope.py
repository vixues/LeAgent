"""DashScope Wanx image generation provider."""

from __future__ import annotations

import base64
from typing import Any

from leagent.llm.image_gen.base import ImageGenResult
from leagent.llm.transport import HttpTransport, TransportConfig

_WANX_MODELS = frozenset({"wanx-v1", "wanx2.1-t2i-turbo", "wanx2.1-t2i-plus"})


class DashScopeWanxProvider:
    """Generate images via Alibaba DashScope Wanx API."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://dashscope.aliyuncs.com/api/v1",
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        # Shared, pooled transport (X-Request-Id + traceparent + OTel span).
        self._transport = HttpTransport(TransportConfig(complete_timeout=timeout))

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        size: str = "1024*1024",
        **kwargs: Any,
    ) -> ImageGenResult:
        wanx_model = model if model in _WANX_MODELS or model.startswith("wanx") else "wanx-v1"
        ds_size = size.replace("x", "*") if "x" in size else size
        headers = self._transport.request_headers({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable",
        })
        payload = {
            "model": wanx_model,
            "input": {"prompt": prompt},
            "parameters": {"size": ds_size, "n": 1},
        }
        client = self._transport.complete_client
        with self._transport.request_span("image_generate", model=wanx_model, provider="dashscope"):
            create_resp = await client.post(
                f"{self.base_url}/services/aigc/text2image/image-synthesis",
                headers=headers,
                json=payload,
            )
        create_resp.raise_for_status()
        task_id = create_resp.json().get("output", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"DashScope Wanx task creation failed: {create_resp.text}")

        poll_headers = self._transport.request_headers({
            "Authorization": f"Bearer {self.api_key}",
        })
        for _ in range(60):
            poll = await client.get(
                f"{self.base_url}/tasks/{task_id}",
                headers=poll_headers,
            )
            poll.raise_for_status()
            body = poll.json()
            status = body.get("output", {}).get("task_status")
            if status == "SUCCEEDED":
                results = body.get("output", {}).get("results") or []
                if not results:
                    raise RuntimeError("DashScope Wanx returned no images")
                url = results[0].get("url", "")
                result = ImageGenResult(model=wanx_model, provider="dashscope")
                if url:
                    img_resp = await client.get(url)
                    img_resp.raise_for_status()
                    result.b64_json = base64.b64encode(img_resp.content).decode()
                return result
            if status in ("FAILED", "CANCELED"):
                raise RuntimeError(f"DashScope Wanx task {status}: {body}")
            import asyncio
            await asyncio.sleep(2)
        raise TimeoutError("DashScope Wanx image generation timed out")

    async def aclose(self) -> None:
        await self._transport.aclose()
