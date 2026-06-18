"""SiliconFlow image generation provider.

Model-family-aware client for ``/v1/images/generations``. Different SiliconFlow
model families (Kolors, FLUX, Qwen-Image, Qwen-Edit, Z-Image-Turbo) expect
different request fields — this module maps LeAgent preset params to the correct
API contract per family.
"""

from __future__ import annotations

import asyncio
import base64
import os
from enum import Enum
from typing import Any

from leagent.llm.image_gen.base import ImageGenResult
from leagent.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_ENDPOINT = "https://api.siliconflow.cn/v1/images/generations"
DEFAULT_MODEL = "Kwai-Kolors/Kolors"


class SiliconFlowModelFamily(str, Enum):
    """SiliconFlow image model families with distinct API contracts."""

    KOLORS = "kolors"
    FLUX = "flux"
    QWEN_IMAGE = "qwen_image"
    QWEN_EDIT = "qwen_edit"
    Z_IMAGE = "z_image"


# Recommended image_size values from SiliconFlow API documentation.
SILICONFLOW_SIZE_CATALOG: dict[SiliconFlowModelFamily, list[str]] = {
    SiliconFlowModelFamily.KOLORS: [
        "1024x1024",
        "960x1280",
        "768x1024",
        "720x1440",
        "720x1280",
    ],
    SiliconFlowModelFamily.FLUX: [
        "1024x1024",
        "960x1280",
        "768x1024",
        "720x1440",
        "720x1280",
    ],
    SiliconFlowModelFamily.QWEN_IMAGE: [
        "1328x1328",
        "1664x928",
        "928x1664",
        "1472x1140",
        "1140x1472",
        "1584x1056",
        "1056x1584",
    ],
    SiliconFlowModelFamily.Z_IMAGE: [
        "1328x1328",
        "1664x928",
        "928x1664",
        "1472x1140",
        "1140x1472",
        "1584x1056",
        "1056x1584",
    ],
    SiliconFlowModelFamily.QWEN_EDIT: [],
}

_FAMILY_DEFAULTS: dict[SiliconFlowModelFamily, dict[str, Any]] = {
    SiliconFlowModelFamily.KOLORS: {"steps": 20, "guidance_scale": 7.5},
    SiliconFlowModelFamily.FLUX: {"steps": 20, "guidance_scale": None},
    SiliconFlowModelFamily.QWEN_IMAGE: {"steps": 50, "cfg": 4.0},
    SiliconFlowModelFamily.QWEN_EDIT: {"steps": 20, "cfg": 4.0},
    SiliconFlowModelFamily.Z_IMAGE: {"steps": 8, "cfg": 4.0},
}


def match_model_family(model: str) -> SiliconFlowModelFamily:
    """Resolve the API contract family for a SiliconFlow model id."""
    mid = (model or "").strip()
    lower = mid.lower()
    if "qwen-image-edit" in lower or "qwen/qwen-image-edit" in lower:
        return SiliconFlowModelFamily.QWEN_EDIT
    if "qwen-image" in lower or "qwen/qwen-image" in lower:
        return SiliconFlowModelFamily.QWEN_IMAGE
    if mid.startswith("Tongyi-MAI/") or "tongyi-mai" in lower:
        return SiliconFlowModelFamily.Z_IMAGE
    if mid.startswith("Kwai-Kolors/"):
        return SiliconFlowModelFamily.KOLORS
    if mid.startswith("black-forest-labs/") or "flux" in lower:
        return SiliconFlowModelFamily.FLUX
    return SiliconFlowModelFamily.KOLORS


def _parse_wh(size_str: str) -> tuple[int, int]:
    sep = "x" if "x" in size_str else "*"
    w, h = size_str.split(sep, 1)
    return int(w), int(h)


def snap_image_size(family: SiliconFlowModelFamily, width: int, height: int) -> str:
    """Map arbitrary width/height to the nearest family-recommended resolution."""
    catalog = SILICONFLOW_SIZE_CATALOG.get(family) or []
    if not catalog:
        return f"{width}x{height}"
    target_ratio = width / height if height else 1.0
    best = catalog[0]
    best_score = float("inf")
    for size in catalog:
        sw, sh = _parse_wh(size)
        ratio = sw / sh if sh else 1.0
        ratio_diff = abs(ratio - target_ratio)
        pixel_diff = abs(sw - width) + abs(sh - height)
        score = ratio_diff * 1000 + pixel_diff
        if score < best_score:
            best_score = score
            best = size
    return best


def _parse_dimensions(params: dict[str, Any], *, default: tuple[int, int] = (1024, 1024)) -> tuple[int, int]:
    if params.get("width") and params.get("height"):
        return int(params["width"]), int(params["height"])
    size = params.get("size")
    if isinstance(size, str) and ("x" in size or "*" in size):
        return _parse_wh(size.replace("*", "x"))
    if isinstance(size, (int, float)):
        return int(size), int(size)
    return default


def _ref_url(ref: Any) -> str | None:
    if isinstance(ref, str) and ref.strip():
        return ref.strip()
    if isinstance(ref, dict):
        for key in ("preview_url", "src", "url"):
            val = ref.get(key)
            if val:
                return str(val)
    return None


def _default_steps(family: SiliconFlowModelFamily, model: str) -> int:
    defaults = _FAMILY_DEFAULTS[family]
    if family is SiliconFlowModelFamily.FLUX and "schnell" in model.lower():
        return 4
    return int(defaults["steps"])


def build_payload(model: str, prompt: str, params: dict[str, Any]) -> dict[str, Any]:
    """Build a SiliconFlow ``/images/generations`` request body for *model*."""
    family = match_model_family(model)
    width, height = _parse_dimensions(params)
    steps = int(
        params.get("num_inference_steps")
        or params.get("steps")
        or _default_steps(family, model)
    )

    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "num_inference_steps": steps,
    }

    if family is SiliconFlowModelFamily.KOLORS:
        payload["image_size"] = snap_image_size(family, width, height)
        payload["batch_size"] = int(params.get("batch_size") or 1)
        payload["guidance_scale"] = float(
            params.get("guidance_scale") or params.get("cfg_scale") or 7.5
        )
    elif family is SiliconFlowModelFamily.FLUX:
        payload["image_size"] = snap_image_size(family, width, height)
    elif family in (SiliconFlowModelFamily.QWEN_IMAGE, SiliconFlowModelFamily.Z_IMAGE):
        payload["image_size"] = snap_image_size(family, width, height)
        payload["cfg"] = float(
            params.get("cfg")
            or params.get("guidance_scale")
            or params.get("cfg_scale")
            or _FAMILY_DEFAULTS[family].get("cfg", 4.0)
        )
    elif family is SiliconFlowModelFamily.QWEN_EDIT:
        payload["cfg"] = float(
            params.get("cfg")
            or params.get("guidance_scale")
            or params.get("cfg_scale")
            or _FAMILY_DEFAULTS[family].get("cfg", 4.0)
        )

    if negative := params.get("negative_prompt"):
        payload["negative_prompt"] = str(negative)

    if (seed := params.get("seed")) is not None:
        try:
            payload["seed"] = int(seed)
        except (TypeError, ValueError):
            pass

    for field in ("image", "image2", "image3"):
        if field in params:
            url = _ref_url(params[field])
            if url:
                payload[field] = url

    return payload


def _extract_error_message(body: Any, status_code: int) -> str:
    if isinstance(body, dict):
        msg = body.get("message") or body.get("error") or body.get("data")
        if msg:
            return f"siliconflow HTTP {status_code}: {msg}"
    return f"siliconflow HTTP {status_code}: {body}"


class SiliconFlowImageProvider:
    """HTTP client for SiliconFlow image generation."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_ENDPOINT,
        timeout: float = 300.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = (base_url or DEFAULT_ENDPOINT).strip() or DEFAULT_ENDPOINT
        self.timeout = timeout

    @classmethod
    def from_env(cls, *, api_key: str, base_url: str = "") -> SiliconFlowImageProvider:
        resolved_url = (
            base_url.strip()
            or os.environ.get("SILICONFLOW_API_URL", "").strip()
            or DEFAULT_ENDPOINT
        )
        return cls(api_key=api_key, base_url=resolved_url)

    async def generate(
        self,
        *,
        model: str,
        prompt: str,
        **params: Any,
    ) -> ImageGenResult:
        """Call SiliconFlow and return an :class:`ImageGenResult`."""
        payload = build_payload(model, prompt, params)
        family = match_model_family(model)
        width, height = _parse_dimensions(params)

        from leagent.llm.transport import HttpTransport, TransportConfig

        transport = HttpTransport(TransportConfig(complete_timeout=self.timeout))
        try:
            headers = transport.request_headers({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            })
            client = transport.complete_client
            with transport.request_span("image_generate", model=model, provider="siliconflow"):
                resp = await client.post(self.base_url, headers=headers, json=payload)
            if resp.status_code >= 400:
                try:
                    body = resp.json()
                except Exception:  # noqa: BLE001
                    body = resp.text
                raise RuntimeError(_extract_error_message(body, resp.status_code))

            body = resp.json()
            images = body.get("images") or body.get("data") or []
            if not images or not isinstance(images[0], dict):
                raise RuntimeError(f"siliconflow returned no image: {body}")

            item = images[0]
            result = ImageGenResult(
                success=True,
                model=model,
                provider="siliconflow",
                metadata={
                    "seed": body.get("seed"),
                    "family": family.value,
                    "width": width,
                    "height": height,
                    "image_size": payload.get("image_size"),
                },
            )

            if b64 := item.get("b64_json"):
                result.b64_json = str(b64)
                return result

            url = item.get("url")
            if not url:
                raise RuntimeError(f"siliconflow returned no image url: {body}")

            result.url = str(url)
            result.metadata["url"] = result.url
            try:
                img_resp = await self._download_image(client, result.url)
                result.b64_json = base64.b64encode(img_resp.content).decode()
                result.mime = img_resp.headers.get("content-type", "image/png")
            except Exception as exc:  # noqa: BLE001 - URL fallback is valid
                logger.warning("siliconflow_image_download_failed", url=result.url, error=str(exc))
            return result
        finally:
            await transport.aclose()

    async def _download_image(self, client: Any, url: str, *, attempts: int = 3) -> Any:
        """Download a SiliconFlow temporary URL with bounded retries."""
        last_exc: Exception | None = None
        for attempt in range(max(1, attempts)):
            try:
                resp = await client.get(url, follow_redirects=True)
                resp.raise_for_status()
                return resp
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt + 1 < attempts:
                    await asyncio.sleep(0.5 * (attempt + 1))
        raise last_exc or RuntimeError("siliconflow image download failed")

    async def aclose(self) -> None:
        return None


__all__ = [
    "DEFAULT_ENDPOINT",
    "DEFAULT_MODEL",
    "SILICONFLOW_SIZE_CATALOG",
    "SiliconFlowImageProvider",
    "SiliconFlowModelFamily",
    "build_payload",
    "match_model_family",
    "snap_image_size",
]
