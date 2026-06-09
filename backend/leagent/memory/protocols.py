"""Structural interfaces for the memory subsystem.

.. deprecated::
    The canonical protocol home is :mod:`leagent.sdk.protocols`. This module
    re-exports :class:`~leagent.sdk.protocols.RecallProvider` for backwards
    compatibility; new code should import it from ``leagent.sdk.protocols``
    (or the ``leagent.sdk`` public surface).
"""

from __future__ import annotations

from leagent.sdk.protocols import RecallProvider

__all__ = ["RecallProvider"]
