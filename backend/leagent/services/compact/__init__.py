"""Three-layer context compression service.

Implements the autoCompact + snipCompact + contextCollapse pattern from
the reference architecture to keep the context window within budget.
"""

from leagent.services.compact.service import CompactService

__all__ = ["CompactService"]
