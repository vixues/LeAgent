"""Gateway stack bootstrap stub — no-op for local deployment."""

from __future__ import annotations

from typing import Any


class GatewayStack:
    """No-op gateway stack for local deployment."""

    def __init__(self) -> None:
        self.auth = None


def build_gateway_stack(**_kw: Any) -> GatewayStack:
    return GatewayStack()
