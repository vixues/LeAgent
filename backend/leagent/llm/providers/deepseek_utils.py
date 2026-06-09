"""DeepSeek API utility functions (balance check, model listing, etc.)."""

from __future__ import annotations

import logging
from typing import Any

from leagent.llm.providers.deepseek import DeepSeekProvider
from leagent.llm.transport import get_default_transport

logger = logging.getLogger(__name__)


def normalize_deepseek_base_url(raw: str) -> str:
    """Strip trailing ``/v1`` from DeepSeek base URLs.

    The canonical DeepSeek base URL is ``https://api.deepseek.com``
    (no ``/v1`` suffix).  Older configs may have the ``/v1`` form which
    still works but is no longer canonical.
    """
    normalized = raw.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return normalized


async def check_balance(
    api_key: str,
    base_url: str = DeepSeekProvider.DEFAULT_BASE_URL,
    *,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Query the DeepSeek account balance.

    Returns the parsed JSON response::

        {
            "is_available": True,
            "balance_infos": [
                {
                    "currency": "CNY",
                    "total_balance": "10.00",
                    "granted_balance": "0.00",
                    "topped_up_balance": "10.00",
                }
            ],
        }

    Raises :class:`httpx.HTTPStatusError` on non-200 responses.
    """
    normalized_base_url = normalize_deepseek_base_url(base_url)
    url = f"{normalized_base_url}/user/balance"
    transport = get_default_transport()
    headers = transport.request_headers({
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    with transport.request_span("balance", provider="deepseek"):
        response = await transport.complete_client.get(
            url, headers=headers, timeout=timeout
        )
    response.raise_for_status()
    return response.json()


async def list_models(
    api_key: str,
    base_url: str = DeepSeekProvider.DEFAULT_BASE_URL,
    *,
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    """List available DeepSeek models.

    Returns the ``data`` array from ``GET /models``.
    """
    url = f"{normalize_deepseek_base_url(base_url)}/models"
    transport = get_default_transport()
    headers = transport.request_headers({
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    with transport.request_span("list_models", provider="deepseek"):
        response = await transport.complete_client.get(
            url, headers=headers, timeout=timeout
        )
    response.raise_for_status()
    return response.json().get("data", [])
