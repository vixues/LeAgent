"""DashScope TTS (qwen-tts) and ASR (qwen-audio-asr) adapters."""

from __future__ import annotations

import base64
from typing import Any

from leagent.llm.domain_registry import (
    DomainModelResult,
    DomainModelSpec,
    DomainParam,
)
from leagent.llm.transport import HttpTransport, TransportConfig

_BASE_URL = "https://dashscope.aliyuncs.com/api/v1"

_TTS_VOICES = ("Cherry", "Serena", "Ethan", "Chelsie")


class DashScopeTTSAdapter:
    """Text-to-speech via DashScope ``qwen-tts``."""

    spec = DomainModelSpec(
        task="tts",
        provider="dashscope",
        model="qwen-tts",
        display_name="Text to Speech (DashScope)",
        description="Synthesise speech audio from text via DashScope qwen-tts.",
        params=(
            DomainParam(id="text", io_type="STRING", required=True, multiline=True,
                        tooltip="Text to synthesise"),
            DomainParam(id="voice", io_type="COMBO", choices=_TTS_VOICES,
                        default="Cherry", tooltip="Speaker voice"),
            DomainParam(id="model", io_type="STRING", default="qwen-tts",
                        tooltip="DashScope TTS model name"),
        ),
        output="audio",
    )

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = _BASE_URL,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._transport = HttpTransport(TransportConfig(complete_timeout=timeout))

    async def invoke(self, **params: Any) -> DomainModelResult:
        text = str(params.get("text") or "").strip()
        if not text:
            return DomainModelResult(success=False, error="Missing 'text' parameter")
        model = str(params.get("model") or self.spec.model)
        voice = str(params.get("voice") or "Cherry")

        headers = self._transport.request_headers({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })
        payload = {
            "model": model,
            "input": {"text": text, "voice": voice},
        }
        client = self._transport.complete_client
        with self._transport.request_span("tts", model=model, provider="dashscope"):
            resp = await client.post(
                f"{self.base_url}/services/aigc/multimodal-generation/generation",
                headers=headers,
                json=payload,
            )
        resp.raise_for_status()
        body = resp.json()
        audio = (body.get("output") or {}).get("audio") or {}
        url = str(audio.get("url") or "")
        b64 = audio.get("data")
        result = DomainModelResult(
            model=model,
            provider="dashscope",
            mime="audio/wav",
            url=url or None,
            metadata={"voice": voice, "usage": body.get("usage") or {}},
        )
        if b64:
            result.b64_data = str(b64)
        elif url:
            dl = await client.get(url)
            dl.raise_for_status()
            result.b64_data = base64.b64encode(dl.content).decode()
        else:
            result.success = False
            result.error = f"DashScope TTS returned no audio: {body}"
        return result

    async def aclose(self) -> None:
        await self._transport.aclose()


class DashScopeASRAdapter:
    """Speech-to-text via DashScope ``qwen-audio-asr``."""

    spec = DomainModelSpec(
        task="asr",
        provider="dashscope",
        model="qwen-audio-asr",
        display_name="Speech to Text (DashScope)",
        description="Transcribe an audio file (URL) via DashScope qwen-audio-asr.",
        params=(
            DomainParam(id="audio_url", io_type="STRING", required=True,
                        tooltip="Public URL of the audio file to transcribe"),
            DomainParam(id="model", io_type="STRING", default="qwen-audio-asr",
                        tooltip="DashScope ASR model name"),
        ),
        output="text",
    )

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = _BASE_URL,
        timeout: float = 120.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._transport = HttpTransport(TransportConfig(complete_timeout=timeout))

    async def invoke(self, **params: Any) -> DomainModelResult:
        audio_url = str(params.get("audio_url") or "").strip()
        if not audio_url:
            return DomainModelResult(success=False, error="Missing 'audio_url' parameter")
        model = str(params.get("model") or self.spec.model)

        headers = self._transport.request_headers({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })
        payload = {
            "model": model,
            "input": {
                "messages": [
                    {"role": "user", "content": [{"audio": audio_url}]},
                ]
            },
        }
        client = self._transport.complete_client
        with self._transport.request_span("asr", model=model, provider="dashscope"):
            resp = await client.post(
                f"{self.base_url}/services/aigc/multimodal-generation/generation",
                headers=headers,
                json=payload,
            )
        resp.raise_for_status()
        body = resp.json()
        text = _extract_asr_text(body)
        if text is None:
            return DomainModelResult(
                success=False,
                error=f"DashScope ASR returned no transcript: {body}",
                model=model,
                provider="dashscope",
            )
        return DomainModelResult(
            text=text,
            model=model,
            provider="dashscope",
            metadata={"usage": body.get("usage") or {}},
        )

    async def aclose(self) -> None:
        await self._transport.aclose()


def _extract_asr_text(body: dict[str, Any]) -> str | None:
    choices = (body.get("output") or {}).get("choices") or []
    for choice in choices:
        content = (choice.get("message") or {}).get("content")
        if isinstance(content, str) and content.strip():
            return content
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    return block["text"]
    return None
