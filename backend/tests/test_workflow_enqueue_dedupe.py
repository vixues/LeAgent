"""Workflow enqueue idempotency: same prompt + user with an active run returns it."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlmodel import select

from leagent.services.auth.service import LOCAL_USER_ID
from leagent.services.database.models.workflow_execution import WorkflowExecution
from leagent.workflow.services import WorkflowService


@pytest.mark.asyncio
async def test_enqueue_returns_same_row_when_already_queued_or_running(db_session):
    user_id = LOCAL_USER_ID
    prompt_id = "wa-dedupe-prompt"
    flow_id = uuid4()
    existing_id = uuid4()

    db_session.add(
        WorkflowExecution(
            id=existing_id,
            flow_id=flow_id,
            user_id=user_id,
            prompt_id=prompt_id,
            status="queued",
            inputs=json.dumps({}),
        )
    )
    await db_session.commit()

    @asynccontextmanager
    async def _session_cm():
        try:
            yield db_session
            await db_session.commit()
        except Exception:
            await db_session.rollback()
            raise

    class _Db:
        def session(self):
            return _session_cm()

    svc = WorkflowService(_Db(), MagicMock(), MagicMock(), queue=None)
    a = await svc.enqueue(
        prompt_id=prompt_id, flow_id=flow_id, user_id=user_id, inputs={}
    )
    b = await svc.enqueue(
        prompt_id=prompt_id, flow_id=flow_id, user_id=user_id, inputs={}
    )
    assert a.id == existing_id
    assert b.id == existing_id

    res = await db_session.exec(select(WorkflowExecution))
    rows = list(res.all())
    assert len(rows) == 1
