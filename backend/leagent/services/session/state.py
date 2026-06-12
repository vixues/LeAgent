"""Dataclasses that describe the durable state of a chat session.

The :class:`SessionState` owned by :class:`SessionManager` is the canonical
representation of everything the agent needs to continue a conversation on
any turn:

* the full message transcript (user / assistant / tool) in chronological
  order;
* the structured list of files the user has attached, each with enough
  metadata to render a preview and pass it into a tool;
* a :class:`FileStateCache` snapshot so the agent can deduplicate repeated
  reads across turns;
* cumulative token usage;
* a fingerprint of the system prompt, so controllers can detect when the
  prompt has changed and therefore the LLM cache should be invalidated;
* the session-scoped agent todo list (``todo_write`` / ``todo_read``).

Every field serialises to JSON via :meth:`SessionState.to_dict` so it can be
stored in Redis (for warm reads) *and* the relational database (for durability).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Literal, Mapping
from uuid import UUID, uuid4

SessionTodoStatus = Literal["pending", "in_progress", "completed", "cancelled"]

SESSION_TODO_STATUSES: frozenset[str] = frozenset(
    {"pending", "in_progress", "completed", "cancelled"}
)

ATTACHMENT_KIND_IMAGE = "image"
ATTACHMENT_KIND_DOCUMENT = "document"
ATTACHMENT_KIND_TEXT = "text"
ATTACHMENT_KIND_OTHER = "other"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return _utc_now()
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return _utc_now()


def _serialise_dt(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


@dataclass(slots=True)
class SessionAttachment:
    """A file the user attached to the session.

    The dataclass is intentionally flat so it can round-trip through JSON
    without custom encoders. The agent never receives raw ``UploadFile``
    objects — it only sees :class:`SessionAttachment` instances produced by
    :class:`SessionManager.attach_files`.
    """

    id: UUID
    session_id: UUID
    filename: str
    storage_path: str
    content_type: str
    kind: str
    size: int
    sha256: str
    created_at: datetime = field(default_factory=_utc_now)
    preview_url: str | None = None
    download_url: str | None = None
    text_excerpt: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "session_id": str(self.session_id),
            "filename": self.filename,
            "storage_path": self.storage_path,
            "content_type": self.content_type,
            "kind": self.kind,
            "size": self.size,
            "sha256": self.sha256,
            "created_at": _serialise_dt(self.created_at),
            "preview_url": self.preview_url,
            "download_url": self.download_url,
            "text_excerpt": self.text_excerpt,
            "extra": dict(self.extra or {}),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SessionAttachment:
        return cls(
            id=UUID(str(data["id"])),
            session_id=UUID(str(data["session_id"])),
            filename=str(data.get("filename") or ""),
            storage_path=str(data.get("storage_path") or ""),
            content_type=str(data.get("content_type") or "application/octet-stream"),
            kind=str(data.get("kind") or ATTACHMENT_KIND_OTHER),
            size=int(data.get("size") or 0),
            sha256=str(data.get("sha256") or ""),
            created_at=_parse_dt(data.get("created_at")),
            preview_url=(
                str(data["preview_url"]) if data.get("preview_url") else None
            ),
            download_url=(
                str(data["download_url"]) if data.get("download_url") else None
            ),
            text_excerpt=(
                str(data["text_excerpt"]) if data.get("text_excerpt") else None
            ),
            extra=dict(data.get("extra") or {}),
        )


@dataclass(slots=True)
class SessionMessage:
    """One message in a session transcript.

    We duplicate ``role`` + ``content`` from the wire format rather than
    reusing the SQLModel :class:`Message` to keep a) ORM coupling low and b)
    the LLM-ready format already resolved — ``tool_calls`` is a list of
    ``{"id", "name", "arguments"}`` dicts and attachments are a list of
    ``UUID`` references to :class:`SessionAttachment`.
    """

    role: str
    content: str
    created_at: datetime = field(default_factory=_utc_now)
    tool_calls: list[dict[str, Any]] | None = None
    tool_call_id: str | None = None
    attachment_ids: list[str] = field(default_factory=list)
    model: str | None = None
    id: UUID = field(default_factory=uuid4)
    reasoning_content: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "role": self.role,
            "content": self.content,
            "created_at": _serialise_dt(self.created_at),
            "tool_calls": self.tool_calls,
            "tool_call_id": self.tool_call_id,
            "attachment_ids": list(self.attachment_ids),
            "model": self.model,
            "reasoning_content": self.reasoning_content,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SessionMessage:
        raw_id = data.get("id")
        return cls(
            id=UUID(str(raw_id)) if raw_id else uuid4(),
            role=str(data.get("role") or "user"),
            content=str(data.get("content") or ""),
            created_at=_parse_dt(data.get("created_at")),
            tool_calls=list(data.get("tool_calls") or []) or None,
            tool_call_id=(
                str(data["tool_call_id"]) if data.get("tool_call_id") else None
            ),
            attachment_ids=[str(a) for a in data.get("attachment_ids") or []],
            model=str(data["model"]) if data.get("model") else None,
            reasoning_content=(
                (s or None)
                if isinstance(data.get("reasoning_content"), str)
                and (s := str(data["reasoning_content"]).strip())
                else None
            ),
        )

    def to_llm_message(self) -> dict[str, Any]:
        """Render the message in the shape the LLM chat API expects."""
        payload: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            payload["tool_calls"] = self.tool_calls
        if self.tool_call_id:
            payload["tool_call_id"] = self.tool_call_id
        if self.reasoning_content:
            payload["reasoning_content"] = self.reasoning_content
        return payload


@dataclass(slots=True)
class SessionTodo:
    """One item in the session-scoped agent todo list."""

    id: str
    content: str
    status: SessionTodoStatus = "pending"
    order: int = 0
    updated_at: datetime = field(default_factory=_utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "status": self.status,
            "order": self.order,
            "updated_at": _serialise_dt(self.updated_at),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SessionTodo:
        raw_status = str(data.get("status") or "pending").strip().lower()
        status: SessionTodoStatus = (
            raw_status if raw_status in SESSION_TODO_STATUSES else "pending"  # type: ignore[assignment]
        )
        return cls(
            id=str(data.get("id") or ""),
            content=str(data.get("content") or ""),
            status=status,
            order=int(data.get("order") or 0),
            updated_at=_parse_dt(data.get("updated_at")),
        )


def session_todos_to_tool_dicts(todos: Iterable[SessionTodo]) -> list[dict[str, Any]]:
    """Render session todos for ``ToolContext.extra['todos']``."""
    return [
        {"id": t.id, "content": t.content, "status": t.status}
        for t in sorted(todos, key=lambda x: (x.order, x.id))
    ]


def session_todos_from_tool_dicts(items: Iterable[Mapping[str, Any]]) -> list[SessionTodo]:
    """Normalise tool-layer todo dicts into :class:`SessionTodo` rows."""
    now = _utc_now()
    out: list[SessionTodo] = []
    for index, raw in enumerate(items):
        todo_id = str(raw.get("id") or "").strip() or f"todo-{index}"
        raw_status = str(raw.get("status") or "pending").strip().lower()
        status: SessionTodoStatus = (
            raw_status if raw_status in SESSION_TODO_STATUSES else "pending"  # type: ignore[assignment]
        )
        out.append(
            SessionTodo(
                id=todo_id,
                content=str(raw.get("content") or todo_id),
                status=status,
                order=int(raw.get("order") if raw.get("order") is not None else index),
                updated_at=now,
            )
        )
    return out


def enforce_single_in_progress_todos(todos: list[SessionTodo]) -> list[SessionTodo]:
    """Keep at most one ``in_progress`` item (Cursor-style convention)."""
    seen_in_progress = False
    normalised: list[SessionTodo] = []
    for todo in todos:
        if todo.status != "in_progress":
            normalised.append(todo)
            continue
        if seen_in_progress:
            normalised.append(
                SessionTodo(
                    id=todo.id,
                    content=todo.content,
                    status="pending",
                    order=todo.order,
                    updated_at=todo.updated_at,
                )
            )
        else:
            seen_in_progress = True
            normalised.append(todo)
    return normalised


@dataclass(slots=True)
class SessionUsage:
    """Cumulative LLM usage counters for the session."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    turns: int = 0

    def add(
        self,
        *,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int | None = None,
    ) -> None:
        self.input_tokens += max(0, input_tokens)
        self.output_tokens += max(0, output_tokens)
        if total_tokens is None:
            total_tokens = input_tokens + output_tokens
        self.total_tokens += max(0, total_tokens)
        self.turns += 1

    def to_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "turns": self.turns,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> SessionUsage:
        if not data:
            return cls()
        return cls(
            input_tokens=int(data.get("input_tokens") or 0),
            output_tokens=int(data.get("output_tokens") or 0),
            total_tokens=int(data.get("total_tokens") or 0),
            turns=int(data.get("turns") or 0),
        )


@dataclass(slots=True)
class SessionState:
    """Canonical snapshot of a chat session.

    This dataclass is the I/O boundary between :class:`SessionManager` and the
    agent runtime. The ``version`` field lets future payload shape changes be
    migrated forward without silently breaking older stored rows.
    """

    session_id: UUID
    user_id: UUID | None = None
    workspace_id: UUID | None = None
    flow_id: UUID | None = None
    messages: list[SessionMessage] = field(default_factory=list)
    attachments: list[SessionAttachment] = field(default_factory=list)
    file_state: list[dict[str, Any]] = field(default_factory=list)
    usage: SessionUsage = field(default_factory=SessionUsage)
    system_prompt_fingerprint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    todos: list[SessionTodo] = field(default_factory=list)
    created_at: datetime = field(default_factory=_utc_now)
    updated_at: datetime = field(default_factory=_utc_now)
    version: int = 1

    # -- transcript helpers ---------------------------------------------

    def append_message(self, message: SessionMessage) -> None:
        self.messages.append(message)
        self.updated_at = _utc_now()

    def attachment_by_id(self, attachment_id: UUID | str) -> SessionAttachment | None:
        target = str(attachment_id)
        for att in self.attachments:
            if str(att.id) == target:
                return att
        return None

    def attachments_for_message(
        self, message: SessionMessage
    ) -> list[SessionAttachment]:
        if not message.attachment_ids:
            return []
        index = {str(a.id): a for a in self.attachments}
        return [index[a] for a in message.attachment_ids if a in index]

    def upsert_attachment(self, attachment: SessionAttachment) -> None:
        attachment.session_id = self.session_id
        target = str(attachment.id)
        for idx, existing in enumerate(self.attachments):
            if str(existing.id) == target:
                self.attachments[idx] = attachment
                self.updated_at = _utc_now()
                return
        self.attachments.append(attachment)
        self.updated_at = _utc_now()

    def llm_messages(self) -> list[dict[str, Any]]:
        """Render all messages in the shape expected by the LLM chat API."""
        return [m.to_llm_message() for m in self.messages]

    # -- serialisation --------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": str(self.session_id),
            "user_id": str(self.user_id) if self.user_id else None,
            "workspace_id": str(self.workspace_id) if self.workspace_id else None,
            "flow_id": str(self.flow_id) if self.flow_id else None,
            "messages": [m.to_dict() for m in self.messages],
            "attachments": [a.to_dict() for a in self.attachments],
            "file_state": list(self.file_state or []),
            "usage": self.usage.to_dict(),
            "system_prompt_fingerprint": self.system_prompt_fingerprint,
            "metadata": dict(self.metadata or {}),
            "todos": [t.to_dict() for t in self.todos],
            "created_at": _serialise_dt(self.created_at),
            "updated_at": _serialise_dt(self.updated_at),
            "version": self.version,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SessionState:
        session_id_raw = data.get("session_id")
        if not session_id_raw:
            raise ValueError("SessionState.from_dict requires 'session_id'")
        return cls(
            session_id=UUID(str(session_id_raw)),
            user_id=UUID(str(data["user_id"])) if data.get("user_id") else None,
            workspace_id=(
                UUID(str(data["workspace_id"])) if data.get("workspace_id") else None
            ),
            flow_id=UUID(str(data["flow_id"])) if data.get("flow_id") else None,
            messages=[SessionMessage.from_dict(m) for m in data.get("messages") or []],
            attachments=[
                SessionAttachment.from_dict(a) for a in data.get("attachments") or []
            ],
            file_state=list(data.get("file_state") or []),
            usage=SessionUsage.from_dict(data.get("usage")),
            system_prompt_fingerprint=(
                str(data["system_prompt_fingerprint"])
                if data.get("system_prompt_fingerprint")
                else None
            ),
            metadata=dict(data.get("metadata") or {}),
            todos=[SessionTodo.from_dict(t) for t in data.get("todos") or []],
            created_at=_parse_dt(data.get("created_at")),
            updated_at=_parse_dt(data.get("updated_at")),
            version=int(data.get("version") or 1),
        )

    @classmethod
    def from_json(cls, blob: str) -> SessionState:
        return cls.from_dict(json.loads(blob))

    # -- fingerprinting -------------------------------------------------

    @staticmethod
    def fingerprint_system_prompt(prompt: str) -> str:
        """Stable SHA-256 digest of the system prompt."""
        return hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    def replace_messages(self, messages: Iterable[SessionMessage]) -> None:
        """Used by auto-compaction: swap the transcript wholesale."""
        self.messages = list(messages)
        self.updated_at = _utc_now()
