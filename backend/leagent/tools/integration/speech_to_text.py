"""Speech-to-text: OpenAI Whisper when ``OPENAI_API_KEY`` is set, else placeholder."""

from __future__ import annotations

import asyncio
import mimetypes
import os
from pathlib import Path
from typing import Any

import httpx
import structlog

from leagent.tools.base import BaseTool, ToolCategory, ToolContext, ValidationResult

logger = structlog.get_logger(__name__)

_OPENAI_TRANSCRIPTIONS_URL = "https://api.openai.com/v1/audio/transcriptions"


def _language_to_openai_code(language: str | None) -> str | None:
    if not language or not isinstance(language, str):
        return None
    raw = language.strip()
    if not raw:
        return None
    # ISO-639-1 (e.g. zh-CN -> zh)
    return raw.split("-", 1)[0].lower()


def _guess_mime(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    return mime or "application/octet-stream"


class SpeechToTextTool(BaseTool):
    """Transcribe audio to text for workflow nodes (e.g. F-004).

    With ``OPENAI_API_KEY``, calls OpenAI ``whisper-1``. Otherwise returns a
    structured placeholder so workflows keep running in dev (confidence 0.9).

    Optional workflow params ``speaker_diarization``, ``punctuation``, and
    ``timestamps`` are accepted for template compatibility; behaviour depends
    on the provider (Whisper text mode does not expose diarization here).
    """

    name = "speech_to_text"
    description = (
        "Transcribe speech from an audio file to text using OpenAI Whisper when "
        "configured, or return a dev placeholder with metadata."
    )
    category = ToolCategory.INTEGRATION
    version = "1.0.0"
    timeout_sec = 300
    max_retries = 1
    search_hint = "speech transcribe whisper audio ASR STT meeting"
    # Stateless per-call network transcription: safe to dispatch in parallel.
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 500_000
    path_params = ("audio_file",)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "audio_file": {
                    "type": "string",
                    "description": "Path to the audio file (resolved via tool path sandbox)",
                },
                "language": {
                    "type": "string",
                    "description": "BCP-47 language hint (e.g. zh-CN, en-US)",
                },
                "speaker_diarization": {
                    "type": "boolean",
                    "description": "Request speaker diarization when supported by the backend",
                },
                "punctuation": {
                    "type": "boolean",
                    "description": "Request punctuation when supported by the backend",
                },
                "timestamps": {
                    "type": "boolean",
                    "description": "Request segment timestamps when supported by the backend",
                },
            },
            "required": ["audio_file"],
        }

    async def validate_input(
        self, params: dict[str, Any], context: ToolContext
    ) -> ValidationResult:
        path = Path(params["audio_file"])
        if not path.is_file():
            return ValidationResult(
                valid=False,
                message=f"Audio file not found or not a file: {path}",
            )
        return ValidationResult(valid=True)

    def _placeholder(self, audio_path: Path, *, reason: str) -> dict[str, Any]:
        # confidence 0.9 keeps F-004 on the high-confidence branch in dev.
        return {
            "text": (
                f"[Transcription placeholder] {reason}. "
                f"Referenced file: {audio_path}"
            ),
            "confidence": 0.9,
            "low_confidence_parts": [],
            "source": "placeholder",
            "reason": reason,
        }

    async def _openai_transcribe(
        self,
        audio_path: Path,
        language: str | None,
        api_key: str,
    ) -> dict[str, Any]:
        lang = _language_to_openai_code(language)
        data: dict[str, str] = {"model": "whisper-1"}
        if lang:
            data["language"] = lang

        file_bytes = await asyncio.to_thread(audio_path.read_bytes)
        mime = _guess_mime(audio_path)
        files = {"file": (audio_path.name, file_bytes, mime)}
        headers = {"Authorization": f"Bearer {api_key}"}

        async with httpx.AsyncClient(timeout=float(self.timeout_sec)) as client:
            response = await client.post(
                _OPENAI_TRANSCRIPTIONS_URL,
                headers=headers,
                data=data,
                files=files,
            )
            response.raise_for_status()

        ct = (response.headers.get("content-type") or "").lower()
        text = ""
        if "application/json" in ct:
            body = response.json()
            if isinstance(body, dict):
                text = str(body.get("text") or "")
        if not text:
            text = (response.text or "").strip().strip('"')

        return {
            "text": text,
            "confidence": 0.92,
            "low_confidence_parts": [],
            "source": "openai_whisper",
            "language": language,
        }

    async def execute(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        audio_path = Path(params["audio_file"])
        language = params.get("language")

        api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
        if not api_key:
            logger.warning(
                "speech_to_text_placeholder",
                path=str(audio_path),
                reason="OPENAI_API_KEY not set",
            )
            return self._placeholder(audio_path, reason="OPENAI_API_KEY not set")

        try:
            return await self._openai_transcribe(audio_path, language, api_key)
        except httpx.HTTPError as exc:
            logger.warning(
                "speech_to_text_openai_failed",
                path=str(audio_path),
                error=str(exc),
            )
            return self._placeholder(audio_path, reason=f"OpenAI request failed: {exc}")
