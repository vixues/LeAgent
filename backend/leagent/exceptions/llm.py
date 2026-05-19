"""LLM service exceptions."""

from __future__ import annotations

from typing import Any

from leagent.exceptions.base import LeAgentError


class LLMServiceError(LeAgentError):
    """Generic LLM service failure."""

    error_code = "LLM_SERVICE_ERROR"
    status_code = 502

    def __init__(
        self,
        message: str = "LLM service error",
        *,
        model: str = "",
        endpoint: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        merged = {**(details or {}), "model": model, "endpoint": endpoint}
        super().__init__(message, details=merged)
        self.model = model
        self.endpoint = endpoint


class LLMTimeoutError(LLMServiceError):
    """LLM request exceeded the allowed timeout."""

    error_code = "LLM_TIMEOUT"
    status_code = 504

    def __init__(
        self,
        model: str = "",
        timeout_sec: int = 0,
    ) -> None:
        super().__init__(
            f"LLM request timed out after {timeout_sec}s",
            model=model,
            details={"timeout_sec": timeout_sec},
        )


class LLMRateLimitError(LLMServiceError):
    """LLM provider returned a rate-limit response."""

    error_code = "LLM_RATE_LIMIT"
    status_code = 429

    def __init__(
        self,
        model: str = "",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(
            "LLM rate limit exceeded",
            model=model,
            details={"retry_after": retry_after},
        )
        self.retry_after = retry_after


class ModelNotFoundError(LLMServiceError):
    """Requested model is not available."""

    error_code = "MODEL_NOT_FOUND"
    status_code = 404

    def __init__(self, model: str) -> None:
        super().__init__(
            f"Model '{model}' not found or not loaded",
            model=model,
        )
