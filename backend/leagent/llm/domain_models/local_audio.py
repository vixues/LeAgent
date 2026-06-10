"""Self-hosted audio adapters speaking the OpenAI-compatible audio API.

Most local audio servers expose OpenAI-shaped endpoints, so these adapters
re-use :class:`OpenAITTSAdapter` / :class:`OpenAIASRAdapter` with a local
base URL and their own specs:

* **ASR** — faster-whisper-server / whisper.cpp / Speaches
  (``POST /v1/audio/transcriptions``), configured by ``LEAGENT_LOCAL_ASR_URL``
  (+ optional ``LEAGENT_LOCAL_ASR_MODEL``, ``LEAGENT_LOCAL_AUDIO_API_KEY``).
* **TTS** — openedai-speech / Kokoro-FastAPI
  (``POST /v1/audio/speech``), configured by ``LEAGENT_LOCAL_TTS_URL``
  (+ optional ``LEAGENT_LOCAL_TTS_MODEL``, ``LEAGENT_LOCAL_AUDIO_API_KEY``).

URLs may point at the server root (``http://host:8000``) or include the
``/v1`` suffix — both are accepted.
"""

from __future__ import annotations

import os
from typing import Any

from leagent.llm.domain_models.openai_audio import OpenAIASRAdapter, OpenAITTSAdapter
from leagent.llm.domain_registry import (
    DomainModelResult,
    DomainModelSpec,
    DomainParam,
)

ASR_URL_ENV = "LEAGENT_LOCAL_ASR_URL"
ASR_MODEL_ENV = "LEAGENT_LOCAL_ASR_MODEL"
TTS_URL_ENV = "LEAGENT_LOCAL_TTS_URL"
TTS_MODEL_ENV = "LEAGENT_LOCAL_TTS_MODEL"
AUDIO_KEY_ENV = "LEAGENT_LOCAL_AUDIO_API_KEY"


def _normalize_base_url(url: str) -> str:
    """Accept both ``http://host:8000`` and ``http://host:8000/v1`` forms."""
    base = url.strip().rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


class LocalWhisperASRAdapter(OpenAIASRAdapter):
    """Speech-to-text against a self-hosted Whisper-compatible server."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 300.0,
    ) -> None:
        url = base_url or os.environ.get(ASR_URL_ENV, "")
        if not url:
            raise ValueError(f"{ASR_URL_ENV} is not set")
        default_model = model or os.environ.get(ASR_MODEL_ENV, "") or "whisper-1"
        super().__init__(
            api_key=api_key or os.environ.get(AUDIO_KEY_ENV, "") or "local",
            base_url=_normalize_base_url(url),
            timeout=timeout,
        )
        self.spec = DomainModelSpec(
            task="asr",
            provider="local",
            model=default_model,
            display_name="Speech to Text (Local Whisper)",
            description=(
                "Transcribe a local audio file via a self-hosted Whisper server "
                "(faster-whisper / whisper.cpp / Speaches, OpenAI-compatible API)."
            ),
            params=(
                DomainParam(id="audio_path", io_type="STRING", required=True,
                            tooltip="Path to the local audio file to transcribe"),
                DomainParam(id="model", io_type="STRING", default=default_model,
                            tooltip="Model name on the local ASR server"),
                DomainParam(id="language", io_type="STRING", default="",
                            tooltip="Optional ISO-639-1 language hint"),
            ),
            output="text",
        )

    async def invoke(self, **params: Any) -> DomainModelResult:
        result = await super().invoke(**params)
        result.provider = "local"
        return result


class LocalTTSAdapter(OpenAITTSAdapter):
    """Text-to-speech against a self-hosted OpenAI-compatible TTS server."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        url = base_url or os.environ.get(TTS_URL_ENV, "")
        if not url:
            raise ValueError(f"{TTS_URL_ENV} is not set")
        default_model = model or os.environ.get(TTS_MODEL_ENV, "") or "tts-1"
        super().__init__(
            api_key=api_key or os.environ.get(AUDIO_KEY_ENV, "") or "local",
            base_url=_normalize_base_url(url),
            timeout=timeout,
        )
        self.spec = DomainModelSpec(
            task="tts",
            provider="local",
            model=default_model,
            display_name="Text to Speech (Local)",
            description=(
                "Synthesise speech via a self-hosted OpenAI-compatible TTS server "
                "(openedai-speech / Kokoro-FastAPI)."
            ),
            params=(
                DomainParam(id="text", io_type="STRING", required=True, multiline=True,
                            tooltip="Text to synthesise"),
                DomainParam(id="voice", io_type="STRING", default="alloy",
                            tooltip="Voice name on the local TTS server"),
                DomainParam(id="model", io_type="STRING", default=default_model,
                            tooltip="Model name on the local TTS server"),
                DomainParam(id="speed", io_type="FLOAT", default=1.0, min=0.25, max=4.0,
                            tooltip="Speech speed multiplier"),
            ),
            output="audio",
        )

    async def invoke(self, **params: Any) -> DomainModelResult:
        params.setdefault("model", self.spec.model)
        result = await super().invoke(**params)
        result.provider = "local"
        return result


__all__ = [
    "ASR_MODEL_ENV",
    "ASR_URL_ENV",
    "AUDIO_KEY_ENV",
    "TTS_MODEL_ENV",
    "TTS_URL_ENV",
    "LocalTTSAdapter",
    "LocalWhisperASRAdapter",
]
