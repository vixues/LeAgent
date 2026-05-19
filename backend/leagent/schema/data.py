"""Core data models used across the agent pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class Data(BaseModel):
    """Generic data envelope used by tools and the agent pipeline."""

    id: UUID = Field(default_factory=uuid4)
    data: dict[str, Any] = Field(default_factory=dict)
    text: str = ""
    source: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value


class DataFrame(BaseModel):
    """Tabular data representation compatible with pandas conversion."""

    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    dtypes: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def col_count(self) -> int:
        return len(self.columns)

    def to_records(self) -> list[dict[str, Any]]:
        return [dict(zip(self.columns, row)) for row in self.rows]

    @classmethod
    def from_records(cls, records: list[dict[str, Any]]) -> DataFrame:
        if not records:
            return cls()
        columns = list(records[0].keys())
        rows = [[r.get(c) for c in columns] for r in records]
        return cls(columns=columns, rows=rows)


class Message(BaseModel):
    """Internal message representation for agent communication."""

    id: UUID = Field(default_factory=uuid4)
    role: str = "user"
    content: str = ""
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None
    files: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @property
    def token_estimate(self) -> int:
        """Rough token estimate (4 chars ≈ 1 token for CJK-heavy text)."""
        return max(1, len(self.content) // 3)
