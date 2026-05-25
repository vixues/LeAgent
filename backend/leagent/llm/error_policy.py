"""LLM error classification used by retry and failover paths."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from leagent.exceptions.llm import LLMRateLimitError, LLMServiceError, LLMTimeoutError, ModelNotFoundError


class ErrorCategory(str, Enum):
    """Normalized provider error categories."""

    AUTH = "auth"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    MODEL_NOT_FOUND = "model_not_found"
    QUOTA_EXCEEDED = "quota_exceeded"
    SERVER = "server"
    NETWORK = "network"
    BAD_REQUEST = "bad_request"
    CLIENT = "client"
    CIRCUIT_OPEN = "circuit_open"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ErrorClassification:
    """Routing policy decision for an exception."""

    category: ErrorCategory
    retryable: bool
    counts_against_provider: bool = True


_NON_RETRYABLE_STATUS_MARKERS = ("400", "405", "406", "413", "414", "415", "422", "501")
_AUTH_MARKERS = ("401", "403", "unauthorized", "forbidden", "invalid api key", "authentication")
_QUOTA_MARKERS = ("quota", "insufficient balance", "insufficient credits", "billing", "credit")
_NETWORK_MARKERS = ("connection", "network", "dns", "tls", "ssl", "request failed", "max retries exceeded")
_SERVER_MARKERS = ("500", "502", "503", "504", "server error", "temporarily unavailable", "bad gateway")


def classify_llm_error(exc: Exception) -> ErrorClassification:
    """Classify an exception for retry/failover decisions.

    Bad client requests are not retried and do not count against provider
    health. Timeouts, rate limits, auth/quota failures, and server/network
    failures may be resolved by trying another provider/key, so they are
    retryable for failover.
    """
    if isinstance(exc, LLMTimeoutError):
        return ErrorClassification(ErrorCategory.TIMEOUT, retryable=True)
    if isinstance(exc, LLMRateLimitError):
        return ErrorClassification(ErrorCategory.RATE_LIMIT, retryable=True)
    if isinstance(exc, ModelNotFoundError):
        return ErrorClassification(ErrorCategory.MODEL_NOT_FOUND, retryable=True)

    text = str(exc).lower()
    if "circuit is open" in text:
        return ErrorClassification(ErrorCategory.CIRCUIT_OPEN, retryable=True, counts_against_provider=False)
    if any(marker in text for marker in _NON_RETRYABLE_STATUS_MARKERS):
        return ErrorClassification(ErrorCategory.BAD_REQUEST, retryable=False, counts_against_provider=False)
    if any(marker in text for marker in _AUTH_MARKERS):
        return ErrorClassification(ErrorCategory.AUTH, retryable=True)
    if any(marker in text for marker in _QUOTA_MARKERS):
        return ErrorClassification(ErrorCategory.QUOTA_EXCEEDED, retryable=True)
    if any(marker in text for marker in _SERVER_MARKERS):
        return ErrorClassification(ErrorCategory.SERVER, retryable=True)
    if any(marker in text for marker in _NETWORK_MARKERS):
        return ErrorClassification(ErrorCategory.NETWORK, retryable=True)
    if isinstance(exc, LLMServiceError):
        return ErrorClassification(ErrorCategory.UNKNOWN, retryable=False)
    return ErrorClassification(ErrorCategory.UNKNOWN, retryable=False, counts_against_provider=False)
