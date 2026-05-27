"""LeAgent shared primitives consumed by every runtime service.

`leagent_core` is the lightweight, pure-Python library that the API Gateway,
Agent Runtime, Workflow Runtime, LLM Gateway, and Tool Worker all depend on.

It intentionally has **no** knowledge of FastAPI routers, agent controllers,
workflow engines, or provider SDKs. It only provides cross-cutting building
blocks (cache, queue, events, rate limiting, circuit breaker, telemetry, DB
engine factory, auth, gRPC stubs) so individual services stay thin and
independently deployable.
"""

from __future__ import annotations

__version__ = "1.1.3"

__all__ = ["__version__"]
