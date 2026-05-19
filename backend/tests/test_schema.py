"""Tests for API, data, and graph schema models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError


# ===========================================================================
# API schemas: ChatMessage, RunResponse, PaginatedResponse, ErrorResponse
# ===========================================================================


class TestChatMessage:
    def test_user_message(self) -> None:
        from leagent.schema.api import ChatMessage, MessageRole
        msg = ChatMessage(role=MessageRole.USER, content="Hello!")
        assert msg.role == MessageRole.USER
        assert msg.content == "Hello!"

    def test_assistant_message(self) -> None:
        from leagent.schema.api import ChatMessage, MessageRole
        msg = ChatMessage(role=MessageRole.ASSISTANT, content="Hi there!")
        assert msg.role == MessageRole.ASSISTANT

    def test_tool_message(self) -> None:
        from leagent.schema.api import ChatMessage, MessageRole
        msg = ChatMessage(
            role=MessageRole.TOOL,
            content="Tool output",
            tool_call_id="call-123",
        )
        assert msg.tool_call_id == "call-123"

    def test_invalid_role_raises(self) -> None:
        from leagent.schema.api import ChatMessage
        with pytest.raises(ValidationError):
            ChatMessage(role="invalid_role", content="msg")

    def test_timestamp_default(self) -> None:
        from leagent.schema.api import ChatMessage, MessageRole
        msg = ChatMessage(role=MessageRole.USER, content="test")
        assert isinstance(msg.timestamp, datetime)


class TestRunResponse:
    def test_defaults(self) -> None:
        from leagent.schema.api import RunResponse, TaskStatus
        run = RunResponse(run_id=uuid4(), session_id=uuid4())
        assert run.status == TaskStatus.RUNNING

    def test_uuid_fields(self) -> None:
        from leagent.schema.api import RunResponse
        run_id = uuid4()
        session_id = uuid4()
        run = RunResponse(run_id=run_id, session_id=session_id)
        assert run.run_id == run_id
        assert run.session_id == session_id


class TestPaginatedResponse:
    def test_with_items(self) -> None:
        from leagent.schema.api import PaginatedResponse
        response = PaginatedResponse[str](
            items=["a", "b", "c"],
            total=10,
            page=1,
            page_size=3,
            has_next=True,
            has_prev=False,
        )
        assert len(response.items) == 3
        assert response.total == 10
        assert response.has_next is True

    def test_empty_page(self) -> None:
        from leagent.schema.api import PaginatedResponse
        response = PaginatedResponse[int](
            items=[], total=0, page=1, page_size=20
        )
        assert response.items == []
        assert response.has_next is False


class TestErrorResponse:
    def test_default_error_flag(self) -> None:
        from leagent.schema.api import ErrorResponse
        err = ErrorResponse(error_code="TEST_ERR", message="Something failed")
        assert err.error is True
        assert err.error_code == "TEST_ERR"
        assert err.message == "Something failed"

    def test_with_details(self) -> None:
        from leagent.schema.api import ErrorResponse
        err = ErrorResponse(
            error_code="VALIDATION_ERR",
            message="Invalid input",
            details={"field": "amount", "issue": "must be positive"},
        )
        assert err.details["field"] == "amount"


# ===========================================================================
# Data schemas: Data, DataFrame, Message
# ===========================================================================


class TestData:
    def test_creation_defaults(self) -> None:
        from leagent.schema.data import Data
        d = Data()
        assert d.data == {}
        assert d.text == ""
        assert d.source == ""

    def test_get_and_set(self) -> None:
        from leagent.schema.data import Data
        d = Data()
        d.set("key", "value")
        assert d.get("key") == "value"

    def test_get_missing_with_default(self) -> None:
        from leagent.schema.data import Data
        d = Data()
        assert d.get("nonexistent", "default") == "default"

    def test_with_source(self) -> None:
        from leagent.schema.data import Data
        d = Data(text="extracted text", source="pdf_reader")
        assert d.source == "pdf_reader"
        assert d.text == "extracted text"


class TestDataFrame:
    def test_empty_dataframe(self) -> None:
        from leagent.schema.data import DataFrame
        df = DataFrame()
        assert df.row_count == 0
        assert df.col_count == 0

    def test_from_records(self) -> None:
        from leagent.schema.data import DataFrame
        records = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
        ]
        df = DataFrame.from_records(records)
        assert df.col_count == 2
        assert df.row_count == 2
        assert "name" in df.columns
        assert "age" in df.columns

    def test_to_records_roundtrip(self) -> None:
        from leagent.schema.data import DataFrame
        records = [
            {"x": 1, "y": 2},
            {"x": 3, "y": 4},
        ]
        df = DataFrame.from_records(records)
        reconstructed = df.to_records()
        assert reconstructed == records

    def test_empty_records(self) -> None:
        from leagent.schema.data import DataFrame
        df = DataFrame.from_records([])
        assert df.row_count == 0


class TestMessage:
    def test_defaults(self) -> None:
        from leagent.schema.data import Message
        msg = Message(content="Hello")
        assert msg.content == "Hello"
        assert msg.role == "user"
        assert msg.files == []

    def test_token_estimate(self) -> None:
        from leagent.schema.data import Message
        msg = Message(content="a" * 300)
        assert msg.token_estimate >= 1
        assert msg.token_estimate == 300 // 3

    def test_token_estimate_short_content(self) -> None:
        from leagent.schema.data import Message
        msg = Message(content="hi")
        assert msg.token_estimate >= 1

    def test_tool_message(self) -> None:
        from leagent.schema.data import Message
        msg = Message(role="tool", content="result", tool_call_id="call-1")
        assert msg.tool_call_id == "call-1"


# ===========================================================================
# TaskStatus enum values
# ===========================================================================


class TestTaskStatus:
    def test_enum_values(self) -> None:
        from leagent.schema.api import TaskStatus
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
