"""Context management for the agent runtime.

Typed sources, cost-function budgeting, and attachments-first rendering.
The :class:`ContextManager` is the single entry point for per-turn
context assembly.
"""

from leagent.context.artifact_error_tracker import ArtifactErrorTracker
from leagent.context.budget import MinimiseResult, minimise
from leagent.context.cache import SourceCache
from leagent.context.file_state import FileState
from leagent.context.ledger import ContextLedger, LedgerRow
from leagent.context.manager import ContextManager
from leagent.context.recipe import ContextRecipe, RecipeEntry, get_recipe
from leagent.context.sources.base import ContextSource, ResolveContext
from leagent.context.types import (
    AttachmentKind,
    ContextBlock,
    ContextScope,
    EnvironmentSnapshot,
    FileReadRecord,
    ProjectMemoryOrigin,
    ProjectMemorySource,
    RenderTarget,
    TurnContext,
    WorkingSetEntry,
)
from leagent.context.working_set import WorkingSet

__all__ = [
    "ArtifactErrorTracker",
    "AttachmentKind",
    "ContextBlock",
    "ContextLedger",
    "ContextManager",
    "ContextRecipe",
    "ContextScope",
    "ContextSource",
    "EnvironmentSnapshot",
    "FileReadRecord",
    "FileState",
    "LedgerRow",
    "MinimiseResult",
    "ProjectMemoryOrigin",
    "ProjectMemorySource",
    "RecipeEntry",
    "RenderTarget",
    "ResolveContext",
    "SourceCache",
    "TurnContext",
    "WorkingSet",
    "WorkingSetEntry",
    "get_recipe",
    "minimise",
]
