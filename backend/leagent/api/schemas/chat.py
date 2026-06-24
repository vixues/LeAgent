"""Request/response DTOs for the chat API.

These were previously defined inline in ``api/v1/chat.py``; they now live here as
the canonical client contract and are re-exported from the chat router package
for backward compatibility.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from leagent.db.models.message import MessageRole


class ChatCompletionMessage(BaseModel):
    role: MessageRole
    content: str
    name: str | None = None


class ChatCompletionRequest(BaseModel):
    model: str = Field(default="default", description="Model to use for completion")
    messages: list[ChatCompletionMessage]
    session_id: UUID | None = None
    project_id: UUID | None = None
    stream: bool = Field(default=True, description="Whether to stream the response")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1, le=128000)
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    #: Per-app agent customization (used by the non-streaming agent path, e.g.
    #: leagent.js custom chatbots). ``system_prompt`` is appended to the system
    #: prompt; ``agent_variant`` selects the persona/recipe (falls back to
    #: ``default_agent`` when unknown).
    system_prompt: str | None = Field(default=None, max_length=8000)
    agent_variant: str | None = Field(default=None, max_length=64)


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatCompletionMessage
    finish_reason: str | None = None


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage
    #: Session the turn ran in. Lets clients (e.g. leagent.js custom apps)
    #: reuse the session for multi-turn memory when they did not pass one.
    session_id: UUID | None = None


class SessionAttachmentsResponse(BaseModel):
    """Session-scoped files (user uploads and agent-registered outputs)."""

    session_id: UUID
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class AuthorizedPathEntry(BaseModel):
    """One user-granted directory for tool filesystem access in this chat session."""

    path: str
    label: str | None = None


class AuthorizedPathsResponse(BaseModel):
    session_id: UUID
    paths: list[AuthorizedPathEntry] = Field(default_factory=list)


class AuthorizedPathCreateBody(BaseModel):
    path: str = Field(..., min_length=1, max_length=4096)
    label: str | None = Field(default=None, max_length=200)


class ChatCompletionChunk(BaseModel):
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: list[dict[str, Any]]


class SendMessageRequest(BaseModel):
    """User turn: non-empty text and/or persisted attachment ids."""

    content: str = Field(default="", max_length=100000)
    role: MessageRole = MessageRole.USER
    stream: bool = True
    model: str | None = None
    attachments: list[str] | None = None

    @model_validator(mode="after")
    def require_text_or_attachments(self) -> "SendMessageRequest":
        text = (self.content or "").strip()
        has_att = bool(self.attachments)
        if not text and not has_att:
            raise ValueError("content cannot be empty unless attachments are provided")
        return self


class SessionUpdateRequest(BaseModel):
    name: str | None = None
    is_active: bool | None = None
    project_id: UUID | None = None
    metadata_patch: dict[str, Any] | None = Field(
        default=None,
        description="Shallow-merged into chat_sessions.session_metadata (merge_session_metadata).",
    )


class SessionTodoStatusPatchRequest(BaseModel):
    """Patch one session-scoped agent todo status (manual UI updates)."""

    status: Literal["pending", "in_progress", "completed", "cancelled"]


class ChatWorkflowStepRunRequest(BaseModel):
    """Run one step from a persisted chat workflow card."""

    message_id: UUID
    workflow_digest: str = Field(..., min_length=16, max_length=128)
    user_input: str = Field(default="", max_length=50_000)
    parent_run_id: str | None = Field(default=None, max_length=64)


class ChatWorkflowStepRunResponse(BaseModel):
    """HTTP response for a chat workflow step run."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: int | None = None
    prompt_id: str | None = None
    run_id: str | None = None


class ChatWorkflowEmbedRunRequest(BaseModel):
    """Run a persisted chat workflow DAG embed (whole graph) in-chat."""

    message_id: UUID
    workflow_digest: str = Field(..., min_length=16, max_length=128)
    user_input: str = Field(default="", max_length=50_000)
    # Structured run inputs from the generated GenUI operation panel, keyed by
    # the workflow's declared input names (resolve as ``${input.<name>}``).
    inputs: dict[str, Any] | None = Field(default=None)
    parent_run_id: str | None = Field(default=None, max_length=64)


class ChatWorkflowEmbedRunResponse(BaseModel):
    """HTTP response for starting a chat workflow embed (DAG) run.

    The run executes in the background; ``status`` is ``running`` once started
    and the terminal status is persisted to message extensions on completion.
    """

    success: bool
    status: str | None = None
    error: str | None = None
    prompt_id: str | None = None
    run_id: str | None = None


class ChatWorkflowTemplateRead(BaseModel):
    """Built-in chat workflow card for demos and regression testing."""

    id: str
    title: str
    description: str = ""
    spec: dict[str, Any]
    digest: str
    category: str = "demo"
    playbook_id: str | None = None


class SessionExecutionRead(BaseModel):
    """Active or recent execution run for a chat session."""

    run_id: str
    scope: str
    parent_run_id: str | None = None
    prompt_id: str | None = None
    status: str = "running"
    pause_token: dict[str, Any] | None = None


class MaterializedTemplateRow(BaseModel):
    template_id: str
    message_id: UUID


class MaterializeWorkflowTemplatesResponse(BaseModel):
    session_id: UUID
    templates: list[MaterializedTemplateRow]


class AgentMemoryEpisodeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    session_id: str
    user_id: str | None = None
    summary: str
    tags: list[str] = Field(default_factory=list)
    importance: float = 0.0
    token_count: int | None = None
    recall_count: int = 0
    last_recalled_at: datetime | None = None
    created_at: datetime | None = None


class AgentMemoryFactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    key: str
    value: str
    confidence: float = 0.8
    source: str | None = None
    workspace_id: str | None = None
    created_at: datetime | None = None


class AgentMemoryProcedureRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    signature: str
    description: str
    run_count: int = 0
    success_count: int = 0
    success_rate: float = 0.0
    last_outcome: str | None = None
    last_run_at: datetime | None = None
    created_at: datetime | None = None


class AgentMemorySnapshotRead(BaseModel):
    enabled: bool
    episodes: list[AgentMemoryEpisodeRead]
    facts: list[AgentMemoryFactRead]
    procedures: list[AgentMemoryProcedureRead]


class PromptLayerRead(BaseModel):
    name: str
    body: str
    tokens: int = 0
    truncated: bool = False


class PromptPreviewRead(BaseModel):
    """On-demand assembled system prompt (debug / inspector)."""

    query_used: str
    system_text: str
    total_chars: int
    stable_hash: str
    full_hash: str
    variant_key: str
    layers: list[PromptLayerRead]
    approx_transcript_tokens: int = 0
    approx_context_tokens: int = 0


class StreamEvent(BaseModel):
    event: str
    data: dict[str, Any]


class SessionCancelResponse(BaseModel):
    session_id: str
    cancelled: bool
    processes_killed: int = 0
    message: str


class ResumeCheckpointRequest(BaseModel):
    checkpoint_id: str
    prompt: str = ""


class ResumeCheckpointResponse(BaseModel):
    session_id: str
    checkpoint_id: str
    accepted: bool
    message: str


class AgentTaskItem(BaseModel):
    task_id: str
    session_id: str
    started_at: str
    updated_at: str
    phase: str
    tool_name: str | None = None
    status: str = "running"


class AgentTasksListResponse(BaseModel):
    session_id: str
    tasks: list[AgentTaskItem]
    scope_note: str = (
        "This process only. Multiple gateway workers each maintain an independent task list."
    )


class CompactContextRequest(BaseModel):
    force_llm: bool = False


class CompactContextResponse(BaseModel):
    applied: bool
    approx_tokens_before: int
    approx_tokens_after: int
    stages_applied: list[str]
    #: Hypothetical row reduction if the same compression were written to the transcript.
    removed_messages: int
    llm_autocompact_applied: bool


class MessageFeedbackBody(BaseModel):
    """Thumbs feedback: ``5`` = like, ``1`` = dislike, ``null`` = clear."""

    model_config = ConfigDict(extra="forbid")
    rating: int | None


class DirEntry(BaseModel):
    name: str
    path: str
    is_dir: bool


class BrowseResponse(BaseModel):
    path: str
    parent: str | None
    entries: list[DirEntry]
    quick_access: list[DirEntry]


class DailyGreetingsResponse(BaseModel):
    """Ten rotating welcome lines for the empty chat hero + pet bubble acknowledgments."""

    date: str = Field(..., description="UTC calendar day (YYYY-MM-DD) this set is valid for")
    greetings: list[str] = Field(..., min_length=1, max_length=16)
    pet_bubbles: list[str] = Field(
        default_factory=list,
        min_length=0,
        max_length=16,
        description="Short post-reply pet speech-bubble lines (refreshed daily).",
    )


__all__ = [
    "ChatCompletionMessage",
    "ChatCompletionRequest",
    "ChatCompletionChoice",
    "ChatCompletionUsage",
    "ChatCompletionResponse",
    "SessionAttachmentsResponse",
    "AuthorizedPathEntry",
    "AuthorizedPathsResponse",
    "AuthorizedPathCreateBody",
    "ChatCompletionChunk",
    "SendMessageRequest",
    "SessionUpdateRequest",
    "ChatWorkflowStepRunRequest",
    "ChatWorkflowStepRunResponse",
    "ChatWorkflowTemplateRead",
    "SessionExecutionRead",
    "MaterializedTemplateRow",
    "MaterializeWorkflowTemplatesResponse",
    "AgentMemoryEpisodeRead",
    "AgentMemoryFactRead",
    "AgentMemoryProcedureRead",
    "AgentMemorySnapshotRead",
    "PromptLayerRead",
    "PromptPreviewRead",
    "StreamEvent",
    "SessionCancelResponse",
    "AgentTaskItem",
    "AgentTasksListResponse",
    "CompactContextRequest",
    "CompactContextResponse",
    "MessageFeedbackBody",
    "DirEntry",
    "BrowseResponse",
    "DailyGreetingsResponse",
]
