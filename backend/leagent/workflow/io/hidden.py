"""Hidden inputs auto-injected by the execution engine.

Port of ComfyUI's ``Hidden`` enum. Nodes declare which hidden inputs they
need in their schema; the runner populates them from ``HiddenHolder`` at
execution time without the prompt author having to wire them manually.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Hidden(str, Enum):
    """Well-known hidden input identifiers."""

    UNIQUE_ID = "unique_id"        # current node_id
    PROMPT = "prompt"              # full prompt dict
    DYNPROMPT = "dynprompt"        # DynamicPrompt instance
    EXECUTION_ID = "execution_id"  # workflow execution id (prompt_id)
    USER_ID = "user_id"
    SESSION_ID = "session_id"
    TOOL_CONTEXT = "tool_context"  # integration container w/ tool_executor/llm_service
    LLM_SERVICE = "llm_service"
    REVIEW_SERVICE = "review_service"
    AGENT_RUNTIME = "agent_runtime"  # leagent.runtime.AgentRuntime facade
    WORKFLOW_STATE = "workflow_state"  # mutable state object (legacy bridge)
    LOGGER = "logger"


@dataclass
class HiddenHolder:
    """Per-execution bag of hidden values.

    The engine populates fields that exist; nodes receive whichever
    subset they declared.
    """

    unique_id: str | None = None
    prompt: dict[str, Any] = field(default_factory=dict)
    dynprompt: Any = None
    execution_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None
    tool_context: Any = None
    llm_service: Any = None
    review_service: Any = None
    agent_runtime: Any = None
    workflow_state: Any = None
    logger: Any = None
    #: Per-execution :class:`ProgressRegistry`. Nodes use it to stream
    #: intermediate previews to the canvas via
    #: ``progress.update(preview=..., node_id=unique_id)``.
    progress: Any = None

    def resolve(self, key: Hidden) -> Any:
        return getattr(self, key.value, None)

    def with_unique_id(self, unique_id: str) -> "HiddenHolder":
        """Return a shallow copy with a new ``unique_id`` (per-node scope)."""
        return HiddenHolder(
            unique_id=unique_id,
            prompt=self.prompt,
            dynprompt=self.dynprompt,
            execution_id=self.execution_id,
            user_id=self.user_id,
            session_id=self.session_id,
            tool_context=self.tool_context,
            llm_service=self.llm_service,
            review_service=self.review_service,
            agent_runtime=self.agent_runtime,
            workflow_state=self.workflow_state,
            logger=self.logger,
            progress=self.progress,
        )
