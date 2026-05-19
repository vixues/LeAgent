"""Pydantic schemas shared by every service.

Today the authoritative models live under :mod:`leagent.schema`. This
package re-exports them so services can depend on ``leagent_core`` without
pulling in FastAPI / SQLAlchemy. Once the monolith is fully split, these
definitions will move here directly.
"""

from __future__ import annotations

try:
    from leagent.schema import *  # noqa: F401,F403
except ImportError:
    # ``leagent_core`` is installable without the monolith.
    pass

__all__: list[str] = []
