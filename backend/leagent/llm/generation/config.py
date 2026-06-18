"""Persistent configuration for the art image-generation stack.

The hand-authored art pipeline (``Art.ImageGen`` etc.) is driven by the
:class:`~leagent.llm.generation.service.GenerationService`, whose backends
historically read credentials/endpoints straight from ``os.environ``. This
module makes that stack **configurable and reloadable** by persisting an
``image_gen`` section inside the unified ``~/.leagent/providers.yaml`` v2
document, alongside the chat-provider registry.

Three things are managed here:

* **Backend credentials / endpoints** — API keys + base URLs for the real
  backends (``siliconflow`` / ``openai`` / ``dashscope`` / ``http_*``) and the
  local-diffusion model directories. Values may be literal or ``${ENV_VAR}``
  references (resolved lazily, env wins only when the YAML value is a ref).
* **Presets** — ComfyUI-style named bundles of *(backend, model, params)* so a
  workflow node can switch the active image model in one click.
* **Default preset** — the workflow-level "active image model" applied to art
  nodes left on ``provider: auto``.

Both this store and :class:`~leagent.llm.provider_config.ProviderConfigService`
round-trip the same YAML file; :func:`leagent.llm.providers_schema.validate_v2_config`
preserves the ``image_gen`` key so neither surface clobbers the other.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from leagent.config.constants import PROVIDERS_PATH
from leagent.utils.logging import get_logger

logger = get_logger(__name__)

#: Backends that accept an API key + optional base URL.
_KEYED_BACKENDS = ("siliconflow", "openai", "dashscope", "replicate", "elevenlabs")
#: Backends that are external HTTP services (url + key).
_HTTP_BACKENDS = ("http_upscale", "http_video", "http_mesh3d", "http_vfx")

#: Default credential templates (``${ENV}`` refs preserve prior env behaviour).
_DEFAULT_BACKENDS: dict[str, dict[str, str]] = {
    "siliconflow": {"api_key": "${SILICONFLOW_API_KEY}", "base_url": ""},
    "openai": {"api_key": "${OPENAI_API_KEY}", "base_url": ""},
    "dashscope": {"api_key": "${DASHSCOPE_API_KEY}", "base_url": ""},
    "replicate": {"api_key": "${REPLICATE_API_TOKEN}", "base_url": ""},
    "elevenlabs": {"api_key": "${ELEVENLABS_API_KEY}", "base_url": ""},
    "http_upscale": {"url": "${LEAGENT_UPSCALE_URL}", "key": "${LEAGENT_UPSCALE_KEY}"},
    "http_video": {"url": "${LEAGENT_VIDEO_GEN_URL}", "key": "${LEAGENT_VIDEO_GEN_KEY}"},
    "http_mesh3d": {"url": "${LEAGENT_MESH3D_GEN_URL}", "key": "${LEAGENT_MESH3D_GEN_KEY}"},
    "http_vfx": {"url": "${LEAGENT_VFX_GEN_URL}", "key": "${LEAGENT_VFX_GEN_KEY}"},
}

#: Known model ids per backend for the workflow model-picker dropdowns. Local
#: diffusion models are discovered from disk instead (see :func:`local_models`).
BACKEND_MODEL_CATALOG: dict[str, list[str]] = {
    "siliconflow": [
        "Kwai-Kolors/Kolors",
        "black-forest-labs/FLUX.1-schnell",
        "black-forest-labs/FLUX.1-dev",
        "stabilityai/stable-diffusion-3-5-large",
    ],
    "openai": ["dall-e-3", "dall-e-2", "gpt-image-1"],
    "dashscope": ["wanx2.1-t2i-turbo", "wanx2.1-t2i-plus", "wanx-v1"],
    "replicate": [
        "black-forest-labs/flux-schnell",
        "black-forest-labs/flux-dev",
        "stability-ai/stable-diffusion-3.5-large",
        "minimax/video-01",
        "tencent/hunyuan-video",
    ],
    "elevenlabs": [
        "eleven_multilingual_v2",
        "eleven_turbo_v2_5",
        "eleven_monolingual_v1",
    ],
    "offline": ["offline-solid"],
}

#: Default starter presets so a fresh install has something to pick.
_DEFAULT_PRESETS: list[dict[str, Any]] = [
    {
        "id": "offline",
        "label": "Offline (placeholder)",
        "backend": "offline",
        "model": "",
        "kind": "image",
        "params": {"width": 1024, "height": 1024},
        "enabled": True,
    },
    {
        "id": "kolors",
        "label": "SiliconFlow · Kolors",
        "backend": "siliconflow",
        "model": "Kwai-Kolors/Kolors",
        "kind": "image",
        "params": {
            "width": 1024,
            "height": 1024,
            "num_inference_steps": 20,
            "guidance_scale": 7.5,
        },
        "enabled": True,
    },
    {
        "id": "flux-schnell",
        "label": "SiliconFlow · FLUX.1-schnell",
        "backend": "siliconflow",
        "model": "black-forest-labs/FLUX.1-schnell",
        "kind": "image",
        "params": {"width": 1024, "height": 1024, "num_inference_steps": 4},
        "enabled": True,
    },
    {
        "id": "replicate-video",
        "label": "Replicate · Video",
        "backend": "replicate",
        "model": "minimax/video-01",
        "kind": "video",
        "params": {"duration": 4},
        "enabled": True,
    },
    {
        "id": "elevenlabs-tts",
        "label": "ElevenLabs · Text-to-Speech",
        "backend": "elevenlabs",
        "model": "eleven_multilingual_v2",
        "kind": "audio",
        "params": {},
        "enabled": True,
    },
]

_DEFAULT_LOCAL: dict[str, Any] = {
    "enabled": True,
    "models_dir": "",
    "lora_dir": "",
    "default_model": "",
}


def resolve_ref(raw: str) -> str:
    """Resolve a ``${ENV_VAR}`` reference; literals pass through unchanged."""
    if isinstance(raw, str) and raw.startswith("${") and raw.endswith("}"):
        return os.getenv(raw[2:-1], "").strip()
    return (raw or "").strip() if isinstance(raw, str) else ""


@dataclass
class ImageGenPreset:
    """A named *(backend, model, params)* bundle for quick model switching."""

    id: str
    label: str
    backend: str
    model: str = ""
    kind: str = "image"
    params: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "backend": self.backend,
            "model": self.model,
            "kind": self.kind,
            "params": dict(self.params),
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ImageGenPreset:
        return cls(
            id=str(data.get("id") or "").strip(),
            label=str(data.get("label") or data.get("id") or "").strip(),
            backend=str(data.get("backend") or "offline").strip(),
            model=str(data.get("model") or "").strip(),
            kind=str(data.get("kind") or "image").strip(),
            params=dict(data.get("params") or {}),
            enabled=data.get("enabled", True) is not False,
        )


#: Protocols a generic admin-registered provider can speak.
CUSTOM_PROTOCOLS = ("openai", "http")
#: Media kinds a custom provider may declare.
CUSTOM_KINDS = ("image", "video", "model3d", "vfx", "audio")


@dataclass
class CustomProvider:
    """A generic, admin-registerable media-generation provider.

    Dispatches either as OpenAI-compatible (``/images/generations`` for image,
    ``/audio/speech`` for audio) or as the generic LeAgent ``http_*`` JSON
    contract, depending on ``protocol``.
    """

    name: str
    kinds: list[str] = field(default_factory=lambda: ["image"])
    protocol: str = "openai"
    base_url: str = ""
    api_key: str = ""
    models: list[str] = field(default_factory=list)
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kinds": list(self.kinds),
            "protocol": self.protocol,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "models": list(self.models),
            "enabled": self.enabled,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CustomProvider:
        kinds = [str(k).strip() for k in (data.get("kinds") or ["image"]) if str(k).strip()]
        protocol = str(data.get("protocol") or "openai").strip().lower()
        return cls(
            name=str(data.get("name") or "").strip(),
            kinds=[k for k in kinds if k in CUSTOM_KINDS] or ["image"],
            protocol=protocol if protocol in CUSTOM_PROTOCOLS else "openai",
            base_url=str(data.get("base_url") or "").strip(),
            api_key=str(data.get("api_key") or "").strip(),
            models=[str(m).strip() for m in (data.get("models") or []) if str(m).strip()],
            enabled=data.get("enabled", True) is not False,
        )

    def resolved_api_key(self) -> str:
        return resolve_ref(self.api_key)

    def resolved_base_url(self) -> str:
        return resolve_ref(self.base_url)


class ImageGenConfigError(ValueError):
    """Invalid image-generation configuration (bad preset id, etc.)."""


class ImageGenConfigStore:
    """Read/write the ``image_gen`` section of ``providers.yaml``.

    Only the ``image_gen`` key is mutated; every other top-level key (providers,
    routing, pricing, …) is preserved so this store and
    :class:`ProviderConfigService` coexist on one file.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or PROVIDERS_PATH

    # -- raw file I/O ----------------------------------------------------

    def _load_raw(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        try:
            with open(self._path, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
        except (OSError, yaml.YAMLError):
            logger.warning("image_gen_config_read_failed", path=str(self._path))
            return {}
        return data if isinstance(data, dict) else {}

    def _section(self) -> dict[str, Any]:
        section = self._load_raw().get("image_gen")
        return section if isinstance(section, dict) else {}

    def _write_section(self, section: dict[str, Any]) -> None:
        raw = self._load_raw()
        raw["image_gen"] = section
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as fh:
            yaml.dump(raw, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)

    # -- presets ---------------------------------------------------------

    def presets(self) -> list[ImageGenPreset]:
        raw = self._section().get("presets")
        if not isinstance(raw, list) or not raw:
            return [ImageGenPreset.from_dict(p) for p in _DEFAULT_PRESETS]
        return [ImageGenPreset.from_dict(p) for p in raw if isinstance(p, dict)]

    def get_preset(self, preset_id: str) -> ImageGenPreset | None:
        for preset in self.presets():
            if preset.id == preset_id:
                return preset
        return None

    def upsert_preset(self, preset: ImageGenPreset) -> ImageGenPreset:
        if not preset.id:
            raise ImageGenConfigError("preset id cannot be empty")
        section = self._section()
        presets = [ImageGenPreset.from_dict(p) for p in (section.get("presets") or _DEFAULT_PRESETS)]
        replaced = False
        out: list[dict[str, Any]] = []
        for existing in presets:
            if existing.id == preset.id:
                out.append(preset.to_dict())
                replaced = True
            else:
                out.append(existing.to_dict())
        if not replaced:
            out.append(preset.to_dict())
        section["presets"] = out
        self._write_section(section)
        return preset

    def delete_preset(self, preset_id: str) -> bool:
        section = self._section()
        presets = section.get("presets")
        if not isinstance(presets, list):
            presets = _DEFAULT_PRESETS
        remaining = [p for p in presets if isinstance(p, dict) and p.get("id") != preset_id]
        if len(remaining) == len(presets):
            return False
        section["presets"] = remaining
        if section.get("default_preset") == preset_id:
            section["default_preset"] = remaining[0]["id"] if remaining else ""
        self._write_section(section)
        return True

    def default_preset_id(self) -> str:
        section = self._section()
        configured = str(section.get("default_preset") or "").strip()
        if configured and self.get_preset(configured) is not None:
            return configured
        return ""

    def default_preset(self) -> ImageGenPreset | None:
        pid = self.default_preset_id()
        return self.get_preset(pid) if pid else None

    def set_default_preset(self, preset_id: str) -> None:
        if preset_id and self.get_preset(preset_id) is None:
            raise ImageGenConfigError(f"unknown preset '{preset_id}'")
        section = self._section()
        section["default_preset"] = preset_id
        self._write_section(section)

    # -- backend credentials --------------------------------------------

    def _backends(self) -> dict[str, dict[str, str]]:
        configured = self._section().get("backends")
        merged = {k: dict(v) for k, v in _DEFAULT_BACKENDS.items()}
        if isinstance(configured, dict):
            for name, creds in configured.items():
                if isinstance(creds, dict):
                    merged.setdefault(name, {}).update({k: str(v) for k, v in creds.items()})
        return merged

    def backend_credentials(self, name: str) -> dict[str, str]:
        """Return resolved (``${ENV}``-substituted) credentials for *name*."""
        raw = self._backends().get(name, {})
        return {k: resolve_ref(v) for k, v in raw.items()}

    def backend_credentials_raw(self, name: str) -> dict[str, str]:
        """Return the stored (unresolved) credential values for editing."""
        return dict(self._backends().get(name, {}))

    def set_backend_credentials(self, name: str, creds: dict[str, str]) -> None:
        section = self._section()
        backends = section.get("backends")
        if not isinstance(backends, dict):
            backends = {}
        backends[name] = {k: str(v) for k, v in creds.items() if v is not None}
        section["backends"] = backends
        self._write_section(section)

    # -- custom providers ------------------------------------------------

    def custom_providers(self) -> list[CustomProvider]:
        raw = self._section().get("custom_providers")
        if not isinstance(raw, list):
            return []
        return [
            CustomProvider.from_dict(p)
            for p in raw
            if isinstance(p, dict) and str(p.get("name") or "").strip()
        ]

    def get_custom_provider(self, name: str) -> CustomProvider | None:
        for provider in self.custom_providers():
            if provider.name == name:
                return provider
        return None

    def upsert_custom_provider(self, provider: CustomProvider) -> CustomProvider:
        if not provider.name:
            raise ImageGenConfigError("custom provider name cannot be empty")
        if provider.name in _DEFAULT_BACKENDS or provider.name in (
            "offline",
            "local",
        ):
            raise ImageGenConfigError(f"'{provider.name}' is a reserved backend name")
        section = self._section()
        existing = [
            CustomProvider.from_dict(p)
            for p in (section.get("custom_providers") or [])
            if isinstance(p, dict)
        ]
        out: list[dict[str, Any]] = []
        replaced = False
        for entry in existing:
            if entry.name == provider.name:
                out.append(provider.to_dict())
                replaced = True
            else:
                out.append(entry.to_dict())
        if not replaced:
            out.append(provider.to_dict())
        section["custom_providers"] = out
        self._write_section(section)
        return provider

    def delete_custom_provider(self, name: str) -> bool:
        section = self._section()
        providers = section.get("custom_providers")
        if not isinstance(providers, list):
            return False
        remaining = [
            p for p in providers if not (isinstance(p, dict) and p.get("name") == name)
        ]
        if len(remaining) == len(providers):
            return False
        section["custom_providers"] = remaining
        self._write_section(section)
        return True

    # -- local diffusion -------------------------------------------------

    def local_config(self) -> dict[str, Any]:
        configured = self._section().get("local")
        merged = dict(_DEFAULT_LOCAL)
        if isinstance(configured, dict):
            merged.update(configured)
        merged["models_dir"] = resolve_ref(str(merged.get("models_dir") or ""))
        merged["lora_dir"] = resolve_ref(str(merged.get("lora_dir") or ""))
        merged["default_model"] = resolve_ref(str(merged.get("default_model") or ""))
        merged["enabled"] = merged.get("enabled", True) is not False
        return merged

    def set_local_config(self, cfg: dict[str, Any]) -> None:
        section = self._section()
        current = section.get("local")
        if not isinstance(current, dict):
            current = dict(_DEFAULT_LOCAL)
        for key in ("enabled", "models_dir", "lora_dir", "default_model"):
            if key in cfg:
                current[key] = cfg[key]
        section["local"] = current
        self._write_section(section)


_CHECKPOINT_SUFFIXES = (".safetensors", ".ckpt")


def _resolved_models_dir() -> Path:
    """Configured local-diffusion model dir, falling back to env/default."""
    configured = get_image_gen_config().local_config().get("models_dir") or ""
    if configured:
        return Path(configured).expanduser()
    env = os.environ.get("LEAGENT_DIFFUSION_MODELS_DIR", "").strip()
    if env:
        return Path(env).expanduser()
    return Path.home() / ".leagent" / "models" / "diffusion"


def local_models() -> list[str]:
    """Discover selectable local-diffusion checkpoints + the default model id."""
    found: list[str] = []
    root = _resolved_models_dir()
    try:
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.suffix.lower() in _CHECKPOINT_SUFFIXES and path.is_file():
                    found.append(str(path.relative_to(root)))
    except OSError:
        pass
    cfg = get_image_gen_config().local_config()
    fallback = (
        cfg.get("default_model")
        or os.environ.get("LEAGENT_DIFFUSION_DEFAULT_MODEL", "").strip()
        or "stabilityai/stable-diffusion-xl-base-1.0"
    )
    if fallback and fallback not in found:
        found.append(fallback)
    return found


# ---------------------------------------------------------------------------
# Module-level singleton (mirrors ProviderConfigService)
# ---------------------------------------------------------------------------

_STORE: ImageGenConfigStore | None = None


def get_image_gen_config() -> ImageGenConfigStore:
    """Return (or create) the process-wide image-gen config store."""
    global _STORE
    if _STORE is None:
        _STORE = ImageGenConfigStore()
    return _STORE


def reset_image_gen_config() -> None:
    """Invalidate the singleton so the next access re-reads YAML."""
    global _STORE  # noqa: PLW0603
    _STORE = None


__all__ = [
    "BACKEND_MODEL_CATALOG",
    "CUSTOM_KINDS",
    "CUSTOM_PROTOCOLS",
    "CustomProvider",
    "ImageGenConfigError",
    "ImageGenConfigStore",
    "ImageGenPreset",
    "get_image_gen_config",
    "local_models",
    "reset_image_gen_config",
    "resolve_ref",
]
