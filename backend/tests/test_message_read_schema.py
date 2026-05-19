from __future__ import annotations

import json
from datetime import datetime
from uuid import uuid4

from leagent.services.database.models.message import Message, MessageRead, MessageRole


def test_message_read_parses_json_text_fields() -> None:
    message = Message(
        id=uuid4(),
        session_id=uuid4(),
        user_id=uuid4(),
        role=MessageRole.ASSISTANT,
        content="Done",
        tool_calls=json.dumps(
            [
                {
                    "id": "call-1",
                    "name": "excel_generator",
                    "arguments": {"sheet_name": "contacts"},
                    "status": "success",
                },
            ],
        ),
        attachments=json.dumps(
            [
                {
                    "id": "att-1",
                    "filename": "contacts.pdf",
                    "content_type": "application/pdf",
                    "size": 1234,
                },
            ],
        ),
        extensions=json.dumps({"chat_workflow_digest": "abc123"}),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    read = MessageRead.model_validate(message)

    assert read.tool_calls == [
        {
            "id": "call-1",
            "name": "excel_generator",
            "arguments": {"sheet_name": "contacts"},
            "status": "success",
        },
    ]
    assert read.attachments == [
        {
            "id": "att-1",
            "filename": "contacts.pdf",
            "content_type": "application/pdf",
            "size": 1234,
        },
    ]
    assert read.extensions == {"chat_workflow_digest": "abc123"}
