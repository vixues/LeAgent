"""Model provider management API endpoints.

Provides CRUD for provider configurations persisted in ``providers.yaml``,
a default-model endpoint, connection testing, and preset discovery.
"""

from __future__ import annotations

import logging
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import func, select

from leagent.llm.provider_config import (
    DefaultModelConfig,
    ProviderConfig,
    ProviderConfigService,
    ProviderConfigValidationError,
    get_provider_config_service,
)
from leagent.services.auth import CurrentUserId
from leagent.db import DatabaseService, get_database_service
from leagent.db.models import LLMRequestLog, Message

_logger = logging.getLogger(__name__)

router = APIRouter()


async def _trigger_llm_reload() -> None:
    """Ask the running ServiceManager to hot-reload LLMService."""
    try:
        from leagent.services.service_manager import get_service_manager
        sm = get_service_manager()
        await sm.reload_llm_service()
    except Exception:
        _logger.warning("LLM reload after provider change failed", exc_info=True)


def _get_service() -> ProviderConfigService:
    return get_provider_config_service()


def _as_json_utc(dt: datetime) -> datetime:
    """Attach UTC tz so JSON encodes with ``Z`` (naive DB timestamps are UTC wall)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _as_json_utc_opt(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return _as_json_utc(dt)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class ProviderModelInfo(BaseModel):
    name: str
    kind: str = "chat"
    capabilities: dict[str, Any] = Field(default_factory=dict)
    context_window: int = 0
    enabled: bool = True
    description: str = ""
    pricing: dict[str, float] = Field(default_factory=dict)


class ProviderResponse(BaseModel):
    name: str
    type: str
    label: str = ""
    enabled: bool = True
    base_url: str = ""
    requires_api_key: bool = True
    api_key_set: bool = False
    models: list[ProviderModelInfo] = Field(default_factory=list)
    supports_streaming: bool = False
    supports_tools: bool = False
    supports_embeddings: bool = False
    is_healthy: bool | None = None
    timeout: int = 120
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(default="openai")
    api_key: Optional[str] = Field(default=None, max_length=500)
    base_url: Optional[str] = Field(default=None, max_length=500)
    models: Optional[list[dict[str, Any]]] = None
    enabled: bool = True
    timeout: int = Field(default=120, ge=1, le=600)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderUpdateRequest(BaseModel):
    type: Optional[str] = None
    api_key: Optional[str] = Field(default=None, max_length=500)
    base_url: Optional[str] = Field(default=None, max_length=500)
    models: Optional[list[dict[str, Any]]] = None
    enabled: Optional[bool] = None
    timeout: Optional[int] = Field(default=None, ge=1, le=600)
    metadata: Optional[dict[str, Any]] = None


class DefaultModelRequest(BaseModel):
    provider: str
    model: str


class DefaultModelResponse(BaseModel):
    provider: str
    model: str


class TestResult(BaseModel):
    provider_name: str
    model: str = ""
    is_healthy: bool
    latency_ms: float = 0.0
    ttfb_ms: float = 0.0
    status: str = "unknown"
    error: Optional[str] = None
    error_category: Optional[str] = None


class DeepSeekBalanceInfo(BaseModel):
    currency: str = ""
    total_balance: str = ""
    granted_balance: str = ""
    topped_up_balance: str = ""


class DeepSeekBalanceResponse(BaseModel):
    provider_name: str
    is_available: bool
    balance_infos: list[DeepSeekBalanceInfo] = Field(default_factory=list)


class BalanceItem(BaseModel):
    label: str
    amount: str = ""
    currency: str = ""
    usage_percent: float | None = None


class ProviderBalanceResponse(BaseModel):
    provider_name: str
    is_available: bool
    balance_items: list[BalanceItem] = Field(default_factory=list)
    balance_infos: list[DeepSeekBalanceInfo] = Field(default_factory=list)
    last_queried: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SpendLimitStatus(BaseModel):
    provider_name: str
    daily_limit_usd: float | None = None
    monthly_limit_usd: float | None = None
    daily_spend_usd: float = 0.0
    monthly_spend_usd: float = 0.0
    daily_exceeded: bool = False
    monthly_exceeded: bool = False


class PresetInfo(BaseModel):
    type: str
    label: str
    default_base_url: str = ""
    requires_api_key: bool = False
    models: list[ProviderModelInfo] = Field(default_factory=list)


class ModelUsageRow(BaseModel):
    """Aggregated usage metrics for one (provider-inferred, model) pair."""

    model: str
    request_count: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    avg_latency_ms: float = 0.0
    total_cost_usd: float = 0.0
    last_used_at: Optional[datetime] = None


class DiscoveredModel(BaseModel):
    id: str
    name: str
    owned_by: str = ""
    created: Any | None = None
    already_configured: bool = False
    raw: dict[str, Any] = Field(default_factory=dict)


class UsageSummary(BaseModel):
    days: int
    since: datetime
    total_requests: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    cache_hit_rate: float = 0.0
    avg_latency_ms: float = 0.0
    rows: list[ModelUsageRow] = Field(default_factory=list)


class ProviderUsageRow(BaseModel):
    provider_name: str
    request_count: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0


class RequestLogRow(BaseModel):
    id: str
    provider_name: str
    model: str
    request_model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    total_cost_usd: float = 0.0
    latency_ms: float = 0.0
    ttfb_ms: float = 0.0
    status_code: int = 200
    error: Optional[str] = None
    is_streaming: bool = False
    created_at: datetime


class UsageTrendRow(BaseModel):
    bucket: datetime
    request_count: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0


class PricingEntry(BaseModel):
    model: str
    input_per_1m: float = 0.0
    output_per_1m: float = 0.0
    cache_read_per_1m: float = 0.0
    cache_write_per_1m: float = 0.0


class ConfigImportRequest(BaseModel):
    config: dict[str, Any]
    merge: bool = True


class SpeedTestRequest(BaseModel):
    candidates: list[str] = Field(default_factory=list)


class SpeedTestResult(BaseModel):
    url: str
    ok: bool
    latency_ms: float = 0.0
    error: str = ""


class ProviderHealthEntry(BaseModel):
    provider_name: str
    is_healthy: bool | None = None
    latency_ms: float = 0.0
    ttfb_ms: float = 0.0
    status: str = "unknown"
    error: Optional[str] = None
    error_category: Optional[str] = None
    last_checked: Optional[float] = None
    circuit: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _compute_api_key_set(pc: ProviderConfig, svc: ProviderConfigService) -> bool:
    """Reflect whether a usable API credential exists (YAML, ``${ENV}`` ref, or global LLM env)."""
    resolved = str(svc._resolve_api_key(pc.api_key or "")).strip()
    if resolved:
        return True

    from leagent.config.settings import get_settings

    llm = get_settings().llm
    t = pc.type
    if t in ("openai", "azure"):
        return bool(str(llm.openai_api_key or "").strip())
    if t == "anthropic":
        return bool(str(llm.anthropic_api_key or "").strip())
    if t in ("qwen", "dashscope"):
        return bool(str(llm.dashscope_api_key or "").strip())
    if t == "deepseek":
        return bool(str(llm.deepseek_api_key or "").strip())
    if t == "ollama":
        return False
    if t == "custom":
        return bool(str(llm.openai_api_key or "").strip())
    return False


def _resolve_provider_api_key(pc: ProviderConfig, svc: ProviderConfigService) -> str:
    """Resolve a provider API key from YAML or global LLM environment settings."""
    resolved = str(svc._resolve_api_key(pc.api_key or "")).strip()
    if resolved:
        return resolved

    from leagent.config.settings import get_settings

    llm = get_settings().llm
    if pc.type == "deepseek":
        return str(llm.deepseek_api_key or "").strip()
    return ""


def _provider_display_label(pc: ProviderConfig) -> str:
    """Human-readable provider name for UI (custom YAML names, metadata label, presets)."""
    from leagent.llm.provider_config import PROVIDER_PRESETS

    meta = pc.metadata if isinstance(pc.metadata, dict) else {}
    meta_label = meta.get("label")
    if isinstance(meta_label, str) and meta_label.strip():
        return meta_label.strip()
    if pc.type == "custom":
        return pc.name
    preset = PROVIDER_PRESETS.get(pc.type, {})
    return str(preset.get("label") or pc.type)


def _to_response(pc: ProviderConfig, svc: ProviderConfigService) -> ProviderResponse:
    from leagent.llm.provider_config import PROVIDER_PRESETS

    label = _provider_display_label(pc)
    preset = PROVIDER_PRESETS.get(pc.type, {})
    requires_api_key = bool(preset.get("requires_api_key", True))

    is_healthy: bool | None = None
    supports_streaming = False
    supports_tools = False
    supports_embeddings = False
    metadata = dict(pc.metadata or {})
    if svc.registry.has_provider(pc.name):
        info = svc.registry.get_provider_info(pc.name)
        is_healthy = info.is_healthy
        supports_streaming = info.provider.supports_streaming
        supports_tools = info.provider.supports_tools
        supports_embeddings = info.provider.supports_embeddings
        metadata["circuit"] = info.circuit_breaker.snapshot().__dict__

    api_key_set = _compute_api_key_set(pc, svc) if requires_api_key else False

    return ProviderResponse(
        name=pc.name,
        type=pc.type,
        label=label,
        enabled=pc.enabled,
        base_url=pc.base_url,
        requires_api_key=requires_api_key,
        api_key_set=api_key_set,
        models=[
            ProviderModelInfo(
                name=m.get("name", ""),
                kind=m.get("kind", "chat"),
                capabilities=m.get("capabilities", {}),
                context_window=m.get("context_window", 0),
                enabled=m.get("enabled", True),
                description=m.get("description", ""),
                pricing=m.get("pricing", {}),
            )
            for m in pc.models
        ],
        supports_streaming=supports_streaming,
        supports_tools=supports_tools,
        supports_embeddings=supports_embeddings,
        is_healthy=is_healthy,
        timeout=pc.timeout,
        metadata=metadata,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/providers", response_model=list[ProviderResponse])
async def list_providers(
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> list[ProviderResponse]:
    """List all configured providers."""
    return [_to_response(p, svc) for p in svc.list_providers()]


@router.post("/providers", response_model=ProviderResponse, status_code=status.HTTP_201_CREATED)
async def create_provider(
    data: ProviderCreateRequest,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> ProviderResponse:
    """Add a new model provider (persisted to YAML)."""
    try:
        pc = svc.create_provider(data.model_dump(exclude_none=True))
    except ProviderConfigValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    await _trigger_llm_reload()
    return _to_response(pc, svc)


@router.put("/providers/{provider_name}", response_model=ProviderResponse)
async def update_provider(
    provider_name: str,
    data: ProviderUpdateRequest,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> ProviderResponse:
    """Update an existing provider."""
    try:
        raw = data.model_dump(exclude_none=True)
        # Treat empty api_key as "keep existing" — the frontend sends "" when
        # the user leaves the password field blank during edit.
        if "api_key" in raw and not str(raw["api_key"]).strip():
            del raw["api_key"]
        pc = svc.update_provider(provider_name, raw)
    except ProviderConfigValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    await _trigger_llm_reload()
    return _to_response(pc, svc)


@router.delete("/providers/{provider_name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider(
    provider_name: str,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> None:
    """Remove a provider from YAML config and in-memory registry."""
    if svc.get_provider(provider_name) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_name}' not found",
        )
    svc.delete_provider(provider_name)
    await _trigger_llm_reload()


@router.post("/providers/{provider_name}/test", response_model=TestResult)
async def test_provider(
    provider_name: str,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> TestResult:
    """Test connectivity to a provider by sending a simple prompt."""
    result = await svc.test_provider(provider_name)
    pc = svc.get_provider(provider_name)
    model = result.tested_model or (pc.models[0]["name"] if pc and pc.models else "")
    return TestResult(
        provider_name=result.provider_name,
        model=model,
        is_healthy=result.is_healthy,
        latency_ms=result.latency_ms,
        ttfb_ms=result.ttfb_ms,
        status=result.status,
        error=result.error,
        error_category=result.error_category,
    )


@router.get("/providers/{provider_name}/health", response_model=TestResult)
async def check_provider_health(
    provider_name: str,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> TestResult:
    """Health check for a specific provider."""
    if not svc.registry.has_provider(provider_name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_name}' not found in registry",
        )
    result = await svc.registry.test_connection(provider_name)
    return TestResult(
        provider_name=result.provider_name,
        is_healthy=result.is_healthy,
        latency_ms=result.latency_ms,
        ttfb_ms=result.ttfb_ms,
        status=result.status,
        error=result.error,
        error_category=result.error_category,
    )


@router.post("/health/check-all", response_model=list[TestResult])
async def check_all_providers_health(
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> list[TestResult]:
    """Actively stream-test all enabled providers in parallel."""
    providers = [p for p in svc.list_providers() if p.enabled]
    results = await asyncio.gather(
        *(svc.test_provider(p.name) for p in providers),
        return_exceptions=True,
    )
    out: list[TestResult] = []
    for pc, result in zip(providers, results, strict=False):
        if isinstance(result, Exception):
            out.append(
                TestResult(
                    provider_name=pc.name,
                    model=pc.models[0]["name"] if pc.models else "",
                    is_healthy=False,
                    status="failed",
                    error=str(result),
                )
            )
            continue
        out.append(
            TestResult(
                provider_name=result.provider_name,
                model=pc.models[0]["name"] if pc.models else "",
                is_healthy=result.is_healthy,
                latency_ms=result.latency_ms,
                ttfb_ms=result.ttfb_ms,
                status=result.status,
                error=result.error,
                error_category=result.error_category,
            )
        )
    return out


@router.get("/providers/{provider_name}/balance", response_model=ProviderBalanceResponse)
async def get_deepseek_provider_balance(
    provider_name: str,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> ProviderBalanceResponse:
    """Fetch the current account balance for supported providers."""
    pc = svc.get_provider(provider_name)
    if pc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_name}' not found",
        )
    api_key = _resolve_provider_api_key(pc, svc)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provider API key is not configured",
        )

    from httpx import AsyncClient, HTTPError, HTTPStatusError
    from leagent.llm.providers.deepseek import DeepSeekProvider
    from leagent.llm.providers.deepseek_utils import check_balance

    try:
        if pc.type == "deepseek":
            base_url = pc.base_url or DeepSeekProvider.DEFAULT_BASE_URL
            data = await check_balance(api_key, base_url=base_url, timeout=float(pc.timeout or 15))
            infos = [
                DeepSeekBalanceInfo(
                    currency=str(item.get("currency", "")),
                    total_balance=str(item.get("total_balance", "")),
                    granted_balance=str(item.get("granted_balance", "")),
                    topped_up_balance=str(item.get("topped_up_balance", "")),
                )
                for item in data.get("balance_infos", [])
                if isinstance(item, dict)
            ]
            return ProviderBalanceResponse(
                provider_name=provider_name,
                is_available=bool(data.get("is_available", False)),
                balance_infos=infos,
                balance_items=[
                    BalanceItem(
                        label="balance",
                        amount=i.total_balance,
                        currency=i.currency,
                    )
                    for i in infos
                ],
            )

        base_url = (pc.base_url or "").rstrip("/")
        headers = {"Authorization": f"Bearer {api_key}"}
        async with AsyncClient(timeout=float(pc.timeout or 15)) as client:
            if "openrouter" in base_url:
                resp = await client.get("https://openrouter.ai/api/v1/credits", headers=headers)
                resp.raise_for_status()
                payload = resp.json().get("data", resp.json())
                return ProviderBalanceResponse(
                    provider_name=provider_name,
                    is_available=True,
                    balance_items=[
                        BalanceItem(label="credits", amount=str(payload.get("total_credits", "")), currency="USD"),
                        BalanceItem(label="usage", amount=str(payload.get("total_usage", "")), currency="USD"),
                    ],
                )
            if "siliconflow" in base_url:
                resp = await client.get(f"{base_url}/user/info", headers=headers)
                resp.raise_for_status()
                payload = resp.json()
                data = payload.get("data", payload)
                return ProviderBalanceResponse(
                    provider_name=provider_name,
                    is_available=True,
                    balance_items=[
                        BalanceItem(label="balance", amount=str(data.get("balance", "")), currency=str(data.get("currency", ""))),
                    ],
                )
            if "stepfun" in base_url or "step" in base_url:
                resp = await client.get(f"{base_url}/accounts", headers=headers)
                resp.raise_for_status()
                payload = resp.json()
                return ProviderBalanceResponse(
                    provider_name=provider_name,
                    is_available=True,
                    balance_items=[
                        BalanceItem(label="account", amount=str(payload), currency=""),
                    ],
                )
    except HTTPStatusError as exc:
        detail = exc.response.text or str(exc)
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DeepSeek balance request failed: {exc}",
        ) from exc

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Balance is not supported for this provider type or base URL",
    )


@router.get("/default", response_model=DefaultModelResponse)
async def get_default_model(
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> DefaultModelResponse:
    """Get the current default provider and model."""
    d = svc.get_default()
    return DefaultModelResponse(provider=d.provider, model=d.model)


@router.put("/default", response_model=DefaultModelResponse)
async def set_default_model(
    data: DefaultModelRequest,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> DefaultModelResponse:
    """Set the default provider and model."""
    try:
        d = svc.set_default(data.provider, data.model)
    except ProviderConfigValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    await _trigger_llm_reload()
    return DefaultModelResponse(provider=d.provider, model=d.model)


class TaskBinding(BaseModel):
    provider: str = ""
    model: str = ""


class TaskRoutingResponse(BaseModel):
    tasks: dict[str, TaskBinding] = Field(default_factory=dict)


class TaskRoutingUpdateRequest(BaseModel):
    tasks: dict[str, TaskBinding] = Field(default_factory=dict)


@router.get("/routing/tasks", response_model=TaskRoutingResponse)
async def get_task_routing(
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> TaskRoutingResponse:
    """Return routing.tasks from providers.yaml."""
    raw = svc.get_task_routing()
    tasks: dict[str, TaskBinding] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        tasks[str(key)] = TaskBinding(
            provider=str(value.get("provider") or ""),
            model=str(value.get("model") or ""),
        )
    return TaskRoutingResponse(tasks=tasks)


@router.put("/routing/tasks", response_model=TaskRoutingResponse)
async def set_task_routing(
    data: TaskRoutingUpdateRequest,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> TaskRoutingResponse:
    """Update routing.tasks in providers.yaml."""
    payload = {key: binding.model_dump() for key, binding in data.tasks.items()}
    try:
        svc.set_task_routing(payload)
    except ProviderConfigValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await _trigger_llm_reload()
    return TaskRoutingResponse(tasks=data.tasks)


class AvailableModel(BaseModel):
    """A model available for chat selection, aggregated across all enabled providers."""
    provider_name: str
    provider_type: str
    provider_label: str = ""
    model_name: str
    kind: str = "chat"
    capabilities: dict[str, Any] = Field(default_factory=dict)
    context_window: int = 0
    pricing: dict[str, float] = Field(default_factory=dict)
    description: str = ""
    is_default: bool = False


@router.get("/available", response_model=list[AvailableModel])
async def list_available_models(
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> list[AvailableModel]:
    """Return a flat list of all available models across enabled providers.

    Suitable for populating the chat model selector dropdown.
    """
    default_cfg = svc.get_default()
    result: list[AvailableModel] = []

    for pc in svc.list_providers():
        if not pc.enabled:
            continue
        label = _provider_display_label(pc)
        for m in pc.models:
            if m.get("enabled", True) is False:
                continue
            name = (m.get("name") or "").strip()
            if not name:
                continue
            is_default = (pc.name == default_cfg.provider and name == default_cfg.model)
            result.append(
                AvailableModel(
                    provider_name=pc.name,
                    provider_type=pc.type,
                    provider_label=label,
                    model_name=name,
                    kind=m.get("kind", "chat"),
                    capabilities=m.get("capabilities", {}),
                    context_window=m.get("context_window", 0),
                    pricing=m.get("pricing", {}),
                    description=m.get("description", ""),
                    is_default=is_default,
                )
            )

    return result


@router.get("/presets", response_model=list[PresetInfo])
async def get_presets(
    user_id: CurrentUserId,
) -> list[PresetInfo]:
    """Return available provider type presets for frontend pre-fill."""
    presets = ProviderConfigService.get_presets()
    result = []
    for ptype, info in presets.items():
        result.append(
            PresetInfo(
                type=ptype,
                label=info["label"],
                default_base_url=info.get("default_base_url", ""),
                requires_api_key=info.get("requires_api_key", False),
                models=[
                    ProviderModelInfo(
                        name=m["name"],
                        kind=m.get("kind", "chat"),
                        capabilities=m.get("capabilities", {}),
                        context_window=m.get("context_window", 0),
                        enabled=m.get("enabled", True),
                        description=m.get("description", ""),
                        pricing=m.get("pricing", {}),
                    )
                    for m in info.get("models", [])
                ],
            )
        )
    return result


@router.get("/providers/{provider_name}/discover", response_model=list[DiscoveredModel])
async def discover_provider_models(
    provider_name: str,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> list[DiscoveredModel]:
    """Fetch available models from provider model-list APIs."""
    try:
        return [DiscoveredModel(**item) for item in await svc.discover_models(provider_name)]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Model discovery failed: {exc}",
        ) from exc


@router.get("/usage/summary", response_model=UsageSummary)
async def get_usage_summary(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    days: int = Query(default=30, ge=1, le=365),
) -> UsageSummary:
    """Aggregate LLM usage metrics from the messages table.

    Returns per-model request counts, token totals and average latency for the
    last ``days`` days. Only messages with a non-null ``model`` are counted.
    """
    since = datetime.utcnow() - timedelta(days=days)

    async with db.session() as session:
        log_stmt = (
            select(
                LLMRequestLog.model,
                func.count().label("request_count"),
                func.coalesce(func.sum(LLMRequestLog.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(LLMRequestLog.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(LLMRequestLog.input_tokens + LLMRequestLog.output_tokens), 0).label("total_tokens"),
                func.coalesce(func.sum(LLMRequestLog.total_cost_usd), 0.0).label("total_cost_usd"),
                func.coalesce(func.sum(LLMRequestLog.cache_read_tokens), 0).label("cache_read_tokens"),
                func.coalesce(func.sum(LLMRequestLog.cache_write_tokens), 0).label("cache_write_tokens"),
                func.coalesce(func.avg(LLMRequestLog.latency_ms), 0.0).label("avg_latency_ms"),
                func.max(LLMRequestLog.created_at).label("last_used_at"),
            )
            .where(LLMRequestLog.created_at >= since)
            .group_by(LLMRequestLog.model)
        )
        log_result = await session.exec(log_stmt)
        log_rows = log_result.all()
        if log_rows:
            rows: list[ModelUsageRow] = []
            total_requests = 0
            total_tokens = 0
            total_cost = 0.0
            cache_read = 0
            cache_write = 0
            weighted_latency_sum = 0.0
            for row in log_rows:
                request_count = int(row[1] or 0)
                total_tok = int(row[4] or 0)
                avg_latency = float(row[8] or 0.0)
                cost = float(row[5] or 0.0)
                rows.append(
                    ModelUsageRow(
                        model=row[0] or "unknown",
                        request_count=request_count,
                        total_input_tokens=int(row[2] or 0),
                        total_output_tokens=int(row[3] or 0),
                        total_tokens=total_tok,
                        total_cost_usd=cost,
                        avg_latency_ms=avg_latency,
                        last_used_at=_as_json_utc_opt(row[9]),
                    )
                )
                total_requests += request_count
                total_tokens += total_tok
                total_cost += cost
                cache_read += int(row[6] or 0)
                cache_write += int(row[7] or 0)
                weighted_latency_sum += avg_latency * request_count
            rows.sort(key=lambda r: r.request_count, reverse=True)
            cache_total = cache_read + cache_write
            return UsageSummary(
                days=days,
                since=_as_json_utc(since),
                total_requests=total_requests,
                total_tokens=total_tokens,
                total_cost_usd=total_cost,
                cache_hit_rate=(cache_read / cache_total if cache_total else 0.0),
                avg_latency_ms=(weighted_latency_sum / total_requests if total_requests else 0.0),
                rows=rows,
            )

        stmt = (
            select(
                Message.model,
                func.count().label("request_count"),
                func.coalesce(func.sum(Message.input_tokens), 0).label("input_tokens"),
                func.coalesce(func.sum(Message.output_tokens), 0).label("output_tokens"),
                func.coalesce(func.sum(Message.total_tokens), 0).label("total_tokens"),
                func.coalesce(func.avg(Message.latency_ms), 0.0).label("avg_latency_ms"),
                func.max(Message.created_at).label("last_used_at"),
            )
            .where(Message.model.is_not(None))
            .where(Message.created_at >= since)
            .group_by(Message.model)
        )
        result = await session.exec(stmt)
        raw_rows = result.all()

    rows: list[ModelUsageRow] = []
    total_requests = 0
    total_tokens = 0
    weighted_latency_sum = 0.0
    for row in raw_rows:
        # Row is a sqlmodel Row tuple; access by index for portability.
        model = row[0] or "unknown"
        request_count = int(row[1] or 0)
        input_tokens = int(row[2] or 0)
        output_tokens = int(row[3] or 0)
        total_tok = int(row[4] or 0)
        avg_latency = float(row[5] or 0.0)
        last_used = row[6]

        rows.append(
            ModelUsageRow(
                model=model,
                request_count=request_count,
                total_input_tokens=input_tokens,
                total_output_tokens=output_tokens,
                total_tokens=total_tok,
                avg_latency_ms=avg_latency,
                last_used_at=_as_json_utc_opt(last_used),
            )
        )
        total_requests += request_count
        total_tokens += total_tok
        weighted_latency_sum += avg_latency * request_count

    avg_latency_ms = (
        weighted_latency_sum / total_requests if total_requests > 0 else 0.0
    )

    rows.sort(key=lambda r: r.request_count, reverse=True)

    return UsageSummary(
        days=days,
        since=_as_json_utc(since),
        total_requests=total_requests,
        total_tokens=total_tokens,
        avg_latency_ms=avg_latency_ms,
        rows=rows,
    )


@router.get("/usage/providers", response_model=list[ProviderUsageRow])
async def get_provider_usage(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    days: int = Query(default=30, ge=1, le=365),
) -> list[ProviderUsageRow]:
    """Aggregate usage metrics by provider."""
    since = datetime.utcnow() - timedelta(days=days)
    async with db.session() as session:
        stmt = (
            select(
                LLMRequestLog.provider_name,
                func.count(),
                func.coalesce(func.sum(LLMRequestLog.input_tokens + LLMRequestLog.output_tokens), 0),
                func.coalesce(func.sum(LLMRequestLog.total_cost_usd), 0.0),
                func.coalesce(func.avg(LLMRequestLog.latency_ms), 0.0),
            )
            .where(LLMRequestLog.created_at >= since)
            .group_by(LLMRequestLog.provider_name)
        )
        rows = (await session.exec(stmt)).all()
    return [
        ProviderUsageRow(
            provider_name=row[0] or "unknown",
            request_count=int(row[1] or 0),
            total_tokens=int(row[2] or 0),
            total_cost_usd=float(row[3] or 0.0),
            avg_latency_ms=float(row[4] or 0.0),
        )
        for row in rows
    ]


@router.get("/usage/requests", response_model=list[RequestLogRow])
async def get_request_logs(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    days: int = Query(default=7, ge=1, le=365),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[RequestLogRow]:
    """Return recent request-level model usage logs."""
    since = datetime.utcnow() - timedelta(days=days)
    async with db.session() as session:
        stmt = (
            select(LLMRequestLog)
            .where(LLMRequestLog.created_at >= since)
            .order_by(LLMRequestLog.created_at.desc())
            .limit(limit)
        )
        rows = list((await session.exec(stmt)).all())
    return [
        RequestLogRow(
            id=str(row.id),
            provider_name=row.provider_name,
            model=row.model,
            request_model=row.request_model,
            input_tokens=row.input_tokens,
            output_tokens=row.output_tokens,
            cache_read_tokens=row.cache_read_tokens,
            cache_write_tokens=row.cache_write_tokens,
            total_cost_usd=row.total_cost_usd,
            latency_ms=row.latency_ms,
            ttfb_ms=row.ttfb_ms,
            status_code=row.status_code,
            error=row.error,
            is_streaming=row.is_streaming,
            created_at=_as_json_utc(row.created_at),
        )
        for row in rows
    ]


@router.get("/usage/trends", response_model=list[UsageTrendRow])
async def get_usage_trends(
    user_id: CurrentUserId,
    db: Annotated[DatabaseService, Depends(get_database_service)],
    days: int = Query(default=30, ge=1, le=365),
) -> list[UsageTrendRow]:
    """Return daily usage trend rows."""
    since = datetime.utcnow() - timedelta(days=days)
    async with db.session() as session:
        stmt = select(LLMRequestLog).where(LLMRequestLog.created_at >= since)
        logs = list((await session.exec(stmt)).all())
    buckets: dict[datetime, UsageTrendRow] = {}
    for log in logs:
        bucket = datetime(log.created_at.year, log.created_at.month, log.created_at.day)
        row = buckets.setdefault(bucket, UsageTrendRow(bucket=_as_json_utc(bucket)))
        row.request_count += 1
        row.total_tokens += int(log.input_tokens or 0) + int(log.output_tokens or 0)
        row.total_cost_usd += float(log.total_cost_usd or 0.0)
    return [buckets[k] for k in sorted(buckets)]


@router.get("/providers/{provider_name}/limits", response_model=SpendLimitStatus)
async def get_provider_spend_limits(
    provider_name: str,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
    db: Annotated[DatabaseService, Depends(get_database_service)],
) -> SpendLimitStatus:
    """Return configured daily/monthly spend limits and current usage."""
    pc = svc.get_provider(provider_name)
    if pc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Provider '{provider_name}' not found")
    limits = pc.metadata.get("limits") if isinstance(pc.metadata, dict) else {}
    if not isinstance(limits, dict):
        limits = {}
    daily_limit = limits.get("daily_usd")
    monthly_limit = limits.get("monthly_usd")
    now = datetime.utcnow()
    day_start = datetime(now.year, now.month, now.day)
    month_start = datetime(now.year, now.month, 1)
    async with db.session() as session:
        daily = (
            await session.exec(
                select(func.coalesce(func.sum(LLMRequestLog.total_cost_usd), 0.0))
                .where(LLMRequestLog.provider_name == provider_name)
                .where(LLMRequestLog.created_at >= day_start)
            )
        ).one()
        monthly = (
            await session.exec(
                select(func.coalesce(func.sum(LLMRequestLog.total_cost_usd), 0.0))
                .where(LLMRequestLog.provider_name == provider_name)
                .where(LLMRequestLog.created_at >= month_start)
            )
        ).one()
    daily_spend = float(daily or 0.0)
    monthly_spend = float(monthly or 0.0)
    daily_limit_f = float(daily_limit) if daily_limit not in (None, "") else None
    monthly_limit_f = float(monthly_limit) if monthly_limit not in (None, "") else None
    return SpendLimitStatus(
        provider_name=provider_name,
        daily_limit_usd=daily_limit_f,
        monthly_limit_usd=monthly_limit_f,
        daily_spend_usd=daily_spend,
        monthly_spend_usd=monthly_spend,
        daily_exceeded=daily_limit_f is not None and daily_spend >= daily_limit_f,
        monthly_exceeded=monthly_limit_f is not None and monthly_spend >= monthly_limit_f,
    )


@router.get("/pricing", response_model=list[PricingEntry])
async def list_pricing(
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> list[PricingEntry]:
    """List editable model pricing entries."""
    pricing = svc.get_pricing_config()
    return [
        PricingEntry(
            model=model,
            input_per_1m=float((entry or {}).get("input_per_1m", 0.0) or 0.0),
            output_per_1m=float((entry or {}).get("output_per_1m", 0.0) or 0.0),
            cache_read_per_1m=float((entry or {}).get("cache_read_per_1m", 0.0) or 0.0),
            cache_write_per_1m=float((entry or {}).get("cache_write_per_1m", 0.0) or 0.0),
        )
        for model, entry in pricing.items()
        if isinstance(entry, dict)
    ]


@router.put("/pricing/{model_name}", response_model=PricingEntry)
async def update_pricing(
    model_name: str,
    data: PricingEntry,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> PricingEntry:
    """Create or update pricing for one model."""
    pricing = svc.get_pricing_config()
    pricing[model_name] = {
        "input_per_1m": data.input_per_1m,
        "output_per_1m": data.output_per_1m,
        "cache_read_per_1m": data.cache_read_per_1m,
        "cache_write_per_1m": data.cache_write_per_1m,
    }
    svc.set_pricing_config(pricing)
    return PricingEntry(model=model_name, **pricing[model_name])


@router.get("/config/export", response_model=dict[str, Any])
async def export_provider_config(
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
    include_secrets: bool = Query(default=False),
) -> dict[str, Any]:
    """Export provider configuration; API keys are masked by default."""
    return svc.export_config(include_secrets=include_secrets)


@router.post("/config/import", response_model=dict[str, Any])
async def import_provider_config(
    data: ConfigImportRequest,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> dict[str, Any]:
    """Import provider configuration with optional merge behavior."""
    try:
        imported = svc.import_config(data.config, merge=data.merge)
    except ProviderConfigValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await _trigger_llm_reload()
    return imported


@router.post("/config/backup", response_model=dict[str, str])
async def backup_provider_config(
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> dict[str, str]:
    """Create a timestamped providers.yaml backup."""
    return {"backup_id": svc.create_backup()}


@router.get("/config/backups", response_model=list[str])
async def list_provider_config_backups(
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> list[str]:
    """List providers.yaml backups."""
    return svc.list_backups()


@router.post("/config/restore/{backup_id}", response_model=dict[str, Any])
async def restore_provider_config_backup(
    backup_id: str,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> dict[str, Any]:
    """Restore providers.yaml from a backup."""
    try:
        restored = svc.restore_backup(backup_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found") from exc
    await _trigger_llm_reload()
    return restored


@router.post("/providers/{provider_name}/speed-test", response_model=list[SpeedTestResult])
async def speed_test_provider_endpoints(
    provider_name: str,
    data: SpeedTestRequest,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> list[SpeedTestResult]:
    """Measure latency for candidate provider base URLs."""
    try:
        return [SpeedTestResult(**item) for item in await svc.speed_test_endpoints(provider_name, data.candidates)]
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/health", response_model=list[ProviderHealthEntry])
async def get_all_providers_health(
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> list[ProviderHealthEntry]:
    """Return last-known health status for every registered provider.

    Does not actively re-test providers; it reports the cached state updated by
    explicit ``POST /providers/{name}/test`` calls.
    """
    out: list[ProviderHealthEntry] = []
    for pc in svc.list_providers():
        if not svc.registry.has_provider(pc.name):
            out.append(ProviderHealthEntry(provider_name=pc.name, is_healthy=None))
            continue
        info = svc.registry.get_provider_info(pc.name)
        out.append(
            ProviderHealthEntry(
                provider_name=pc.name,
                is_healthy=info.is_healthy,
                last_checked=info.last_health_check or None,
                status=(
                    "operational"
                    if info.is_healthy
                    else ("failed" if info.is_healthy is False else "unknown")
                ),
                circuit=info.circuit_breaker.snapshot().__dict__,
            )
        )
    return out
