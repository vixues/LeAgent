"""Lazy :func:`get_service_manager` bridge to avoid API ↔ ``main`` import cycles."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from leagent.services.service_manager import ServiceManager


def get_service_manager() -> "ServiceManager":
    """Return the process-wide :class:`ServiceManager` (initialised in ``main`` lifespan)."""
    from leagent.main import get_service_manager as _from_main

    return _from_main()
