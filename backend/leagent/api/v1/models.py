"""Model provider management API endpoints.

Provides CRUD for provider configurations persisted in ``providers.yaml``,
a default-model endpoint, connection testing, and preset discovery.
"""

from __future__ import annotations

import logging
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
from leagent.services.database import DatabaseService, get_database_service
from leagent.services.database.models import Message

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
    tier: str = ""
    context_window: int = 0
    enabled: bool = True
    description: str = ""
    price_input_per_1m: float = 0.0
    price_output_per_1m: float = 0.0
    supports_tools: bool | None = None
    supports_vision: bool | None = None


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
    error: Optional[str] = None


class DeepSeekBalanceInfo(BaseModel):
    currency: str = ""
    total_balance: str = ""
    granted_balance: str = ""
    topped_up_balance: str = ""


class DeepSeekBalanceResponse(BaseModel):
    provider_name: str
    is_available: bool
    balance_infos: list[DeepSeekBalanceInfo] = Field(default_factory=list)


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
    last_used_at: Optional[datetime] = None


class UsageSummary(BaseModel):
    days: int
    since: datetime
    total_requests: int = 0
    total_tokens: int = 0
    avg_latency_ms: float = 0.0
    rows: list[ModelUsageRow] = Field(default_factory=list)


class ProviderHealthEntry(BaseModel):
    provider_name: str
    is_healthy: bool | None = None
    latency_ms: float = 0.0
    error: Optional[str] = None
    last_checked: Optional[float] = None


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
    name = (pc.name or "").strip()
    if name == "tier1" and str(llm.tier1_api_key or "").strip():
        return True
    if name == "tier2" and str(llm.tier2_api_key or "").strip():
        return True

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
        return bool(
            str(llm.openai_api_key or "").strip()
            or str(llm.tier1_api_key or "").strip()
            or str(llm.tier2_api_key or "").strip()
        )
    return False


def _resolve_provider_api_key(pc: ProviderConfig, svc: ProviderConfigService) -> str:
    """Resolve a provider API key from YAML or global LLM environment settings."""
    resolved = str(svc._resolve_api_key(pc.api_key or "")).strip()
    if resolved:
        return resolved

    from leagent.config.settings import get_settings

    llm = get_settings().llm
    name = (pc.name or "").strip()
    if name == "tier1" and str(llm.tier1_api_key or "").strip():
        return str(llm.tier1_api_key).strip()
    if name == "tier2" and str(llm.tier2_api_key or "").strip():
        return str(llm.tier2_api_key).strip()

    if pc.type == "deepseek":
        return str(llm.deepseek_api_key or "").strip()
    return ""


def _to_response(pc: ProviderConfig, svc: ProviderConfigService) -> ProviderResponse:
    from leagent.llm.provider_config import PROVIDER_PRESETS

    preset = PROVIDER_PRESETS.get(pc.type, {})
    label = preset.get("label", pc.type)
    requires_api_key = bool(preset.get("requires_api_key", True))

    is_healthy: bool | None = None
    supports_streaming = False
    supports_tools = False
    supports_embeddings = False
    if svc.registry.has_provider(pc.name):
        info = svc.registry.get_provider_info(pc.name)
        is_healthy = info.is_healthy
        supports_streaming = info.provider.supports_streaming
        supports_tools = info.provider.supports_tools
        supports_embeddings = info.provider.supports_embeddings

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
                tier=m.get("tier", ""),
                context_window=m.get("context_window", 0),
                enabled=m.get("enabled", True),
                description=m.get("description", ""),
                price_input_per_1m=float(m.get("price_input_per_1m", 0.0) or 0.0),
                price_output_per_1m=float(m.get("price_output_per_1m", 0.0) or 0.0),
                supports_tools=m.get("supports_tools"),
                supports_vision=m.get("supports_vision"),
            )
            for m in pc.models
        ],
        supports_streaming=supports_streaming,
        supports_tools=supports_tools,
        supports_embeddings=supports_embeddings,
        is_healthy=is_healthy,
        timeout=pc.timeout,
        metadata=pc.metadata,
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
        pc = svc.update_provider(provider_name, data.model_dump(exclude_none=True))
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
    model = pc.models[0]["name"] if pc and pc.models else ""
    return TestResult(
        provider_name=result.provider_name,
        model=model,
        is_healthy=result.is_healthy,
        latency_ms=result.latency_ms,
        error=result.error,
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
        error=result.error,
    )


@router.get("/providers/{provider_name}/balance", response_model=DeepSeekBalanceResponse)
async def get_deepseek_provider_balance(
    provider_name: str,
    user_id: CurrentUserId,
    svc: Annotated[ProviderConfigService, Depends(_get_service)],
) -> DeepSeekBalanceResponse:
    """Fetch the current DeepSeek account balance for a configured provider."""
    pc = svc.get_provider(provider_name)
    if pc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_name}' not found",
        )
    if pc.type != "deepseek":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Balance is only available for DeepSeek providers",
        )

    api_key = _resolve_provider_api_key(pc, svc)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DeepSeek API key is not configured",
        )

    from httpx import HTTPError, HTTPStatusError
    from leagent.llm.providers.deepseek import DeepSeekProvider
    from leagent.llm.providers.deepseek_utils import check_balance

    base_url = pc.base_url or DeepSeekProvider.DEFAULT_BASE_URL
    try:
        data = await check_balance(api_key, base_url=base_url, timeout=float(pc.timeout or 15))
    except HTTPStatusError as exc:
        detail = exc.response.text or str(exc)
        raise HTTPException(status_code=exc.response.status_code, detail=detail) from exc
    except HTTPError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"DeepSeek balance request failed: {exc}",
        ) from exc

    return DeepSeekBalanceResponse(
        provider_name=provider_name,
        is_available=bool(data.get("is_available", False)),
        balance_infos=[
            DeepSeekBalanceInfo(
                currency=str(item.get("currency", "")),
                total_balance=str(item.get("total_balance", "")),
                granted_balance=str(item.get("granted_balance", "")),
                topped_up_balance=str(item.get("topped_up_balance", "")),
            )
            for item in data.get("balance_infos", [])
            if isinstance(item, dict)
        ],
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
                        tier=m.get("tier", ""),
                        context_window=m.get("context_window", 0),
                        enabled=m.get("enabled", True),
                        description=m.get("description", ""),
                        price_input_per_1m=float(m.get("price_input_per_1m", 0.0) or 0.0),
                        price_output_per_1m=float(m.get("price_output_per_1m", 0.0) or 0.0),
                        supports_tools=m.get("supports_tools"),
                        supports_vision=m.get("supports_vision"),
                    )
                    for m in info.get("models", [])
                ],
            )
        )
    return result


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
            )
        )
    return out
