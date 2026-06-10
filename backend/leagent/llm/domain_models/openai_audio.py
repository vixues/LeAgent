"""OpenAI TTS (tts-1 / gpt-4o-mini-tts) and ASR (whisper) adapters."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from leagent.llm.domain_registry import (
    DomainModelResult,
    DomainModelSpec,
    DomainParam,
)
from leagent.llm.transport import HttpTransport, TransportConfig

_BASE_URL = "https://api.openai.com/v1"

_TTS_VOICES = ("alloy", "echo", "fable", "onyx", "nova", "shimmer")


class OpenAITTSAdapter:
    """Text-to-speech via the OpenAI audio/speech endpoint."""

    spec = DomainModelSpec(
        task="tts",
        provider="openai",
        model="tts-1",
        display_name="Text to Speech (OpenAI)",
        description="Synthesise speech audio from text via the OpenAI TTS API.",
        params=(
            DomainParam(id="text", io_type="STRING", required=True, multiline=True,
                        tooltip="Text to synthesise"),
            DomainParam(id="voice", io_type="COMBO", choices=_TTS_VOICES,
                        default="alloy", tooltip="Speaker voice"),
            DomainParam(id="model", io_type="STRING", default="tts-1",
                        tooltip="OpenAI TTS model name"),
            DomainParam(id="speed", io_type="FLOAT", default=1.0, min=0.25, max=4.0,
                        tooltip="Speech speed multiplier"),
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
        voice = str(params.get("voice") or "alloy")

        headers = self._transport.request_headers({
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        })
        payload: dict[str, Any] = {
            "model": model,
            "voice": voice,
            "input": text,
            "response_format": "mp3",
        }
        speed = params.get("speed")
        if speed:
            payload["speed"] = float(speed)
        client = self._transport.complete_client
        with self._transport.request_span("tts", model=model, provider="openai"):
            resp = await client.post(
                f"{self.base_url}/audio/speech", headers=headers, json=payload,
            )
        resp.raise_for_status()
        return DomainModelResult(
            b64_data=base64.b64encode(resp.content).decode(),
            mime="audio/mpeg",
            model=model,
            provider="openai",
            metadata={"voice": voice},
        )

    async def aclose(self) -> None:
        await self._transport.aclose()


class OpenAIASRAdapter:
    """Speech-to-text via the OpenAI audio/transcriptions endpoint."""

    spec = DomainModelSpec(
        task="asr",
        provider="openai",
        model="whisper-1",
        display_name="Speech to Text (OpenAI)",
        description="Transcribe a local audio file via the OpenAI Whisper API.",
        params=(
            DomainParam(id="audio_path", io_type="STRING", required=True,
                        tooltip="Path to the local audio file to transcribe"),
            DomainParam(id="model", io_type="STRING", default="whisper-1",
                        tooltip="OpenAI ASR model name"),
            DomainParam(id="language", io_type="STRING", default="",
                        tooltip="Optional ISO-639-1 language hint"),
        ),
        output="text",
    )

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = _BASE_URL,
        timeout: float = 300.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._transport = HttpTransport(TransportConfig(complete_timeout=timeout))

    async def invoke(self, **params: Any) -> DomainModelResult:
        audio_path = str(params.get("audio_path") or "").strip()
        if not audio_path:
            return DomainModelResult(success=False, error="Missing 'audio_path' parameter")
        path = Path(audio_path)
        if not path.is_file():
            return DomainModelResult(
                success=False, error=f"Audio file not found: {audio_path}"
            )
        model = str(params.get("model") or self.spec.model)

        headers = self._transport.request_headers({
            "Authorization": f"Bearer {self.api_key}",
        })
        data: dict[str, Any] = {"model": model}
        language = str(params.get("language") or "").strip()
        if language:
            data["language"] = language
        client = self._transport.complete_client
        with self._transport.request_span("asr", model=model, provider="openai"):
            resp = await client.post(
                f"{self.base_url}/audio/transcriptions",
                headers=headers,
                data=data,
                files={"file": (path.name, path.read_bytes())},
            )
        resp.raise_for_status()
        body = resp.json()
        return DomainModelResult(
            text=str(body.get("text") or ""),
            model=model,
            provider="openai",
            metadata={k: v for k, v in body.items() if k != "text"},
        )

    async def aclose(self) -> None:
        await self._transport.aclose()
