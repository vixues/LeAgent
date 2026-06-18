"""ElevenLabs text-to-speech generation backend."""

from __future__ import annotations

from typing import Any

from leagent.llm.generation.base import GenerationOutput
from leagent.llm.generation.config import get_image_gen_config


class ElevenLabsBackend:
    """Credential-gated text-to-speech (audio) backend for ElevenLabs."""

    name = "elevenlabs"
    kinds = ("audio",)

    _DEFAULT_URL = "https://api.elevenlabs.io/v1"
    _DEFAULT_MODEL = "eleven_multilingual_v2"
    _DEFAULT_VOICE = "21m00Tcm4TlvDq8ikWAM"

    def _credentials(self) -> dict[str, str]:
        return get_image_gen_config().backend_credentials("elevenlabs")

    def available(self) -> bool:
        return bool(self._credentials().get("api_key", "").strip())

    async def generate(self, *, kind: str, prompt: str, **params: Any) -> GenerationOutput:
        if kind != "audio":
            return GenerationOutput.failure(kind, "elevenlabs produces only audio")
        creds = self._credentials()
        api_key = creds.get("api_key", "").strip()
        if not api_key:
            return GenerationOutput.failure("audio", "ElevenLabs API key is not configured")
        base_url = (creds.get("base_url", "").strip() or self._DEFAULT_URL).rstrip("/")
        model = str(params.get("model") or self._DEFAULT_MODEL)
        voice = str(params.get("voice") or params.get("voice_id") or self._DEFAULT_VOICE)

        from leagent.llm.transport import HttpTransport, TransportConfig

        transport = HttpTransport(TransportConfig(complete_timeout=float(params.get("timeout", 180))))
        try:
            headers = transport.request_headers({
                "xi-api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            })
            payload: dict[str, Any] = {"text": prompt, "model_id": model}
            if isinstance(params.get("voice_settings"), dict):
                payload["voice_settings"] = params["voice_settings"]
            with transport.request_span("audio_generate", model=model, provider=self.name):
                resp = await transport.complete_client.post(
                    f"{base_url}/text-to-speech/{voice}", headers=headers, json=payload,
                )
            resp.raise_for_status()
            return GenerationOutput(
                success=True, kind="audio", data=resp.content,
                mime=resp.headers.get("content-type", "audio/mpeg"),
                filename="audio.mp3", provider=self.name, model=model,
                meta={"voice": voice},
            )
        finally:
            await transport.aclose()


__all__ = ["ElevenLabsBackend"]
