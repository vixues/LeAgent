"""Request-level LLM usage logs."""

from __future__ import annotations

from typing import Optional

from sqlmodel import Field

from leagent.services.database.models.base import BaseModel


class LLMRequestLog(BaseModel, table=True):
    """Per-request provider usage and cost telemetry."""

    __tablename__ = "llm_request_logs"

    provider_name: str = Field(default="", index=True, max_length=100)
    model: str = Field(default="", index=True, max_length=200)
    request_model: str = Field(default="", max_length=200)
    input_tokens: int = Field(default=0)
    output_tokens: int = Field(default=0)
    cache_read_tokens: int = Field(default=0)
    cache_write_tokens: int = Field(default=0)
    total_cost_usd: float = Field(default=0.0)
    latency_ms: float = Field(default=0.0)
    ttfb_ms: float = Field(default=0.0)
    status_code: int = Field(default=200, index=True)
    error: Optional[str] = Field(default=None)
    session_id: Optional[str] = Field(default=None, index=True, max_length=100)
    is_streaming: bool = Field(default=False)
