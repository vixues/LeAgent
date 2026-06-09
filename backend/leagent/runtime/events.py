"""Unified runtime event + result types.

**Canonical home:** :mod:`leagent.sdk.events`.

This module re-exports the SDK event types so existing ``from
leagent.runtime.events import ...`` statements keep working during the
migration window.  New code should import directly from
:mod:`leagent.sdk`.
"""

from leagent.sdk.events import AgentEvent, AgentEventType, AgentResult  # noqa: F401

__all__ = ["AgentEvent", "AgentEventType", "AgentResult"]
