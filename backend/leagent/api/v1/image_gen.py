"""Image-generation configuration API.

Manages the art ``GenerationService`` config persisted in the ``image_gen``
section of ``providers.yaml`` via :class:`ImageGenConfigStore`:

* **presets** — named ``(backend, model, params)`` bundles for quick switching,
* **default preset** — the workflow-level active image model,
* **backend credentials** — API keys / endpoints for the real backends,
* **local diffusion** — model directories + default checkpoint,
* **backends / models** — introspection used to populate workflow dropdowns,
* **test** — a credential-free-safe connectivity probe.

All mutations reset the image-gen config + generation-service singletons so
changes take effect without a restart.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from leagent.llm.generation import (
    BACKEND_MODEL_CATALOG,
    CUSTOM_KINDS,
    CUSTOM_PROTOCOLS,
    CustomProvider,
    ImageGenConfigError,
    ImageGenPreset,
    get_image_gen_config,
    local_models,
    reset_image_gen_config,
)
from leagent.llm.generation.base import GENERATION_KINDS
from leagent.llm.generation.config import _HTTP_BACKENDS, _KEYED_BACKENDS
from leagent.llm.generation.service import (
    build_default_generation_service,
    get_generation_service,
    reset_generation_service,
)
from leagent.services.auth import CurrentUserId

_logger = logging.getLogger(__name__)

router = APIRouter()


def _reload() -> None:
    """Reset the config + generation-service singletons after a config write."""
    reset_image_gen_config()
    reset_generation_service()


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class PresetModel(BaseModel):
    id: str
    label: str = ""
    backend: str = "offline"
    model: str = ""
    kind: str = "image"
    params: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class DefaultPresetModel(BaseModel):
    preset_id: str = ""


class BackendInfo(BaseModel):
    name: str
    kinds: list[str] = Field(default_factory=list)
    available: bool = False
    credential_type: str = "none"  # "api_key" | "http" | "none"
    configured: bool = False


class CredentialUpdate(BaseModel):
    api_key: str | None = None
    base_url: str | None = None
    url: str | None = None
    key: str | None = None


class CredentialStatus(BaseModel):
    name: str
    credential_type: str
    configured: bool
    base_url: str = ""
    url: str = ""


class LocalConfigModel(BaseModel):
    enabled: bool = True
    models_dir: str = ""
    lora_dir: str = ""
    default_model: str = ""


class LocalConfigResponse(LocalConfigModel):
    discovered_models: list[str] = Field(default_factory=list)


class TestRequest(BaseModel):
    backend: str | None = None
    preset_id: str | None = None
    prompt: str = "a small calibration swatch"


class TestResult(BaseModel):
    success: bool
    provider: str = ""
    model: str = ""
    placeholder: bool = False
    error: str = ""


class CustomProviderModel(BaseModel):
    name: str
    kinds: list[str] = Field(default_factory=lambda: ["image"])
    protocol: str = "openai"
    base_url: str = ""
    api_key: str = ""
    models: list[str] = Field(default_factory=list)
    enabled: bool = True


class CustomProviderInfo(BaseModel):
    """Custom-provider view that never leaks the stored secret."""

    name: str
    kinds: list[str] = Field(default_factory=list)
    protocol: str = "openai"
    base_url: str = ""
    models: list[str] = Field(default_factory=list)
    enabled: bool = True
    configured: bool = False


def _custom_info(provider: CustomProvider) -> CustomProviderInfo:
    return CustomProviderInfo(
        name=provider.name,
        kinds=list(provider.kinds),
        protocol=provider.protocol,
        base_url=provider.base_url,
        models=list(provider.models),
        enabled=provider.enabled,
        configured=bool(provider.resolved_api_key()) if provider.protocol == "openai" else bool(provider.resolved_base_url()),
    )


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


@router.get("/presets", response_model=list[PresetModel])
async def list_presets() -> list[PresetModel]:
    store = get_image_gen_config()
    return [PresetModel(**p.to_dict()) for p in store.presets()]


@router.post("/presets", response_model=PresetModel, status_code=status.HTTP_201_CREATED)
async def create_preset(body: PresetModel, _user: CurrentUserId) -> PresetModel:
    store = get_image_gen_config()
    if store.get_preset(body.id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"preset '{body.id}' already exists")
    try:
        store.upsert_preset(ImageGenPreset.from_dict(body.model_dump()))
    except ImageGenConfigError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    _reload()
    return body


@router.put("/presets/{preset_id}", response_model=PresetModel)
async def update_preset(preset_id: str, body: PresetModel, _user: CurrentUserId) -> PresetModel:
    store = get_image_gen_config()
    if store.get_preset(preset_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"preset '{preset_id}' not found")
    data = body.model_dump()
    data["id"] = preset_id
    store.upsert_preset(ImageGenPreset.from_dict(data))
    _reload()
    return PresetModel(**data)


@router.delete("/presets/{preset_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_preset(preset_id: str, _user: CurrentUserId) -> None:
    store = get_image_gen_config()
    if not store.delete_preset(preset_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"preset '{preset_id}' not found")
    _reload()


@router.get("/default", response_model=DefaultPresetModel)
async def get_default_preset() -> DefaultPresetModel:
    return DefaultPresetModel(preset_id=get_image_gen_config().default_preset_id())


@router.put("/default", response_model=DefaultPresetModel)
async def set_default_preset(body: DefaultPresetModel, _user: CurrentUserId) -> DefaultPresetModel:
    store = get_image_gen_config()
    try:
        store.set_default_preset(body.preset_id)
    except ImageGenConfigError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    _reload()
    return body


# ---------------------------------------------------------------------------
# Backends + models (introspection for workflow dropdowns)
# ---------------------------------------------------------------------------


@router.get("/backends", response_model=list[BackendInfo])
async def list_backends() -> list[BackendInfo]:
    """List every generation backend with availability + credential type.

    Enumerated dynamically from the freshly-built generation service (covering
    every media kind, concrete starters, and custom providers) so the admin UI
    and workflow palette stay in sync with what is actually registered.
    """
    svc = build_default_generation_service()
    store = get_image_gen_config()
    custom_names = {p.name for p in store.custom_providers()}

    invokers: dict[str, Any] = {}
    for kind in GENERATION_KINDS:
        for backend in svc.backends_for(kind):
            invokers.setdefault(backend.name, backend)
    # The offline floor is registered implicitly; surface it explicitly.
    if "offline" not in invokers:
        invokers["offline"] = svc._offline  # noqa: SLF001 - internal floor reference

    out: list[BackendInfo] = []
    for name, backend in invokers.items():
        if name in custom_names:
            cred_type = "custom"
            configured = _custom_info(store.get_custom_provider(name)).configured
        elif name in _KEYED_BACKENDS:
            cred_type = "api_key"
            configured = bool(store.backend_credentials(name).get("api_key"))
        elif name in _HTTP_BACKENDS:
            cred_type = "http"
            configured = bool(store.backend_credentials(name).get("url"))
        else:
            cred_type = "none"
            configured = True
        try:
            available = backend.available() if backend is not None else (name == "offline")
        except Exception:  # noqa: BLE001
            available = False
        out.append(
            BackendInfo(
                name=name,
                kinds=list(getattr(backend, "kinds", ["image"])),
                available=bool(available) or name == "offline",
                credential_type=cred_type,
                configured=configured,
            )
        )
    return out


@router.get("/models", response_model=list[str])
async def list_models(backend: str = Query(...)) -> list[str]:
    """List selectable model ids for a backend (catalog, local, or custom)."""
    if backend == "local":
        return local_models()
    custom = get_image_gen_config().get_custom_provider(backend)
    if custom is not None:
        return list(custom.models)
    return list(BACKEND_MODEL_CATALOG.get(backend, []))


# ---------------------------------------------------------------------------
# Credentials
# ---------------------------------------------------------------------------


@router.get("/credentials", response_model=list[CredentialStatus])
async def list_credentials() -> list[CredentialStatus]:
    """Credential *status* (never the secret) for each configurable backend."""
    store = get_image_gen_config()
    out: list[CredentialStatus] = []
    for name in _KEYED_BACKENDS:
        creds = store.backend_credentials(name)
        out.append(CredentialStatus(
            name=name, credential_type="api_key",
            configured=bool(creds.get("api_key")), base_url=creds.get("base_url", ""),
        ))
    for name in _HTTP_BACKENDS:
        creds = store.backend_credentials(name)
        out.append(CredentialStatus(
            name=name, credential_type="http",
            configured=bool(creds.get("url")), url=creds.get("url", ""),
        ))
    return out


@router.put("/credentials/{backend}", response_model=CredentialStatus)
async def set_credentials(
    backend: str, body: CredentialUpdate, _user: CurrentUserId
) -> CredentialStatus:
    if backend not in (*_KEYED_BACKENDS, *_HTTP_BACKENDS):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"unknown backend '{backend}'")
    store = get_image_gen_config()
    existing = store.backend_credentials_raw(backend)
    payload = body.model_dump(exclude_none=True)
    # Blank api_key/key preserves the existing secret (write-once UX).
    for secret in ("api_key", "key"):
        if secret in payload and not str(payload[secret]).strip():
            payload.pop(secret)
    existing.update(payload)
    store.set_backend_credentials(backend, existing)
    _reload()
    creds = get_image_gen_config().backend_credentials(backend)
    if backend in _KEYED_BACKENDS:
        return CredentialStatus(
            name=backend, credential_type="api_key",
            configured=bool(creds.get("api_key")), base_url=creds.get("base_url", ""),
        )
    return CredentialStatus(
        name=backend, credential_type="http",
        configured=bool(creds.get("url")), url=creds.get("url", ""),
    )


# ---------------------------------------------------------------------------
# Custom providers (generic admin-registerable backends)
# ---------------------------------------------------------------------------


@router.get("/providers", response_model=list[CustomProviderInfo])
async def list_custom_providers() -> list[CustomProviderInfo]:
    """List admin-registered generic providers (secrets never returned)."""
    return [_custom_info(p) for p in get_image_gen_config().custom_providers()]


@router.post("/providers", response_model=CustomProviderInfo, status_code=status.HTTP_201_CREATED)
async def create_custom_provider(body: CustomProviderModel, _user: CurrentUserId) -> CustomProviderInfo:
    store = get_image_gen_config()
    if store.get_custom_provider(body.name) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"provider '{body.name}' already exists")
    if body.protocol not in CUSTOM_PROTOCOLS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"unsupported protocol '{body.protocol}'")
    if any(k not in CUSTOM_KINDS for k in body.kinds):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unsupported media kind")
    try:
        provider = store.upsert_custom_provider(CustomProvider.from_dict(body.model_dump()))
    except ImageGenConfigError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    _reload()
    return _custom_info(provider)


@router.put("/providers/{name}", response_model=CustomProviderInfo)
async def update_custom_provider(
    name: str, body: CustomProviderModel, _user: CurrentUserId
) -> CustomProviderInfo:
    store = get_image_gen_config()
    existing = store.get_custom_provider(name)
    if existing is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"provider '{name}' not found")
    data = body.model_dump()
    data["name"] = name
    # Blank api_key preserves the existing secret (write-once UX).
    if not str(data.get("api_key") or "").strip():
        data["api_key"] = existing.api_key
    try:
        provider = store.upsert_custom_provider(CustomProvider.from_dict(data))
    except ImageGenConfigError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    _reload()
    return _custom_info(provider)


@router.delete("/providers/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_provider(name: str, _user: CurrentUserId) -> None:
    if not get_image_gen_config().delete_custom_provider(name):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"provider '{name}' not found")
    _reload()


# ---------------------------------------------------------------------------
# Local diffusion
# ---------------------------------------------------------------------------


@router.get("/local", response_model=LocalConfigResponse)
async def get_local_config() -> LocalConfigResponse:
    cfg = get_image_gen_config().local_config()
    return LocalConfigResponse(**cfg, discovered_models=local_models())


@router.put("/local", response_model=LocalConfigResponse)
async def set_local_config(body: LocalConfigModel, _user: CurrentUserId) -> LocalConfigResponse:
    store = get_image_gen_config()
    store.set_local_config(body.model_dump())
    _reload()
    cfg = get_image_gen_config().local_config()
    return LocalConfigResponse(**cfg, discovered_models=local_models())


# ---------------------------------------------------------------------------
# Connectivity test
# ---------------------------------------------------------------------------


@router.post("/test", response_model=TestResult)
async def test_backend(body: TestRequest, _user: CurrentUserId) -> TestResult:
    """Probe a backend/preset with a tiny generation; reports the outcome."""
    store = get_image_gen_config()
    provider = body.backend
    kind = "image"
    params: dict[str, Any] = {}
    model: str | None = None
    if body.preset_id:
        preset = store.get_preset(body.preset_id)
        if preset is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"preset '{body.preset_id}' not found")
        provider = preset.backend
        kind = preset.kind or "image"
        model = preset.model or None
        params.update(preset.params)
    if kind == "image":
        params["width"], params["height"] = 256, 256
    elif kind in ("video", "audio"):
        params.setdefault("duration", 1)
    provider_arg = None if provider in (None, "", "auto") else provider
    if model:
        params["model"] = model
    try:
        out = await get_generation_service().generate(
            kind=kind, prompt=body.prompt, provider=provider_arg,
            max_retries=0, **params,
        )
    except Exception as exc:  # noqa: BLE001
        return TestResult(success=False, error=str(exc))
    return TestResult(
        success=out.success, provider=out.provider, model=out.model,
        placeholder=bool(out.meta.get("placeholder")), error=out.error or "",
    )
