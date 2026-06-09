"""Tests for flow-related database models and CRUD schemas.

Covers FlowStatus/FlowType enums, FlowBase fields, FlowCreate/FlowUpdate/FlowRead
schemas, and the Flow ORM model's default values.  No database connection is
needed – all tests work with in-memory Python objects.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest

from leagent.db.models.flow import (
    Flow,
    FlowCreate,
    FlowRead,
    FlowStatus,
    FlowType,
    FlowUpdate,
    FlowVersion,
)


# ===========================================================================
# Enums
# ===========================================================================


class TestFlowStatusEnum:
    def test_draft(self) -> None:
        assert FlowStatus.DRAFT.value == "draft"

    def test_published(self) -> None:
        assert FlowStatus.PUBLISHED.value == "published"

    def test_archived(self) -> None:
        assert FlowStatus.ARCHIVED.value == "archived"

    def test_all_values_are_str(self) -> None:
        for member in FlowStatus:
            assert isinstance(member.value, str)


class TestFlowTypeEnum:
    def test_agent(self) -> None:
        assert FlowType.AGENT.value == "agent"

    def test_workflow(self) -> None:
        assert FlowType.WORKFLOW.value == "workflow"

    def test_chat(self) -> None:
        assert FlowType.CHAT.value == "chat"

    def test_tool(self) -> None:
        assert FlowType.TOOL.value == "tool"

    def test_all_values_are_str(self) -> None:
        for member in FlowType:
            assert isinstance(member.value, str)


# ===========================================================================
# FlowCreate (request schema)
# ===========================================================================


class TestFlowCreate:
    def test_minimal_creation(self) -> None:
        fc = FlowCreate(name="my_flow")
        assert fc.name == "my_flow"

    def test_default_status_is_draft(self) -> None:
        assert FlowCreate(name="f").status == FlowStatus.DRAFT

    def test_default_type_is_agent(self) -> None:
        assert FlowCreate(name="f").flow_type == FlowType.AGENT

    def test_default_not_public(self) -> None:
        assert FlowCreate(name="f").is_public is False

    def test_data_optional(self) -> None:
        assert FlowCreate(name="f").data is None

    def test_settings_optional(self) -> None:
        assert FlowCreate(name="f").settings is None

    def test_folder_id_optional(self) -> None:
        assert FlowCreate(name="f").folder_id is None

    def test_custom_values(self) -> None:
        folder_id = uuid4()
        fc = FlowCreate(
            name="custom",
            description="A custom flow",
            status=FlowStatus.PUBLISHED,
            flow_type=FlowType.WORKFLOW,
            is_public=True,
            data='{"nodes": []}',
            folder_id=folder_id,
        )
        assert fc.status == FlowStatus.PUBLISHED
        assert fc.flow_type == FlowType.WORKFLOW
        assert fc.is_public is True
        assert fc.folder_id == folder_id

    def test_icon_default(self) -> None:
        fc = FlowCreate(name="f")
        assert fc.icon is not None  # defaults to "🤖"


# ===========================================================================
# FlowUpdate (PATCH schema – all fields optional)
# ===========================================================================


class TestFlowUpdate:
    def test_all_none_by_default(self) -> None:
        fu = FlowUpdate()
        assert fu.name is None
        assert fu.description is None
        assert fu.status is None
        assert fu.flow_type is None
        assert fu.is_public is None
        assert fu.data is None

    def test_partial_update(self) -> None:
        fu = FlowUpdate(name="updated", status=FlowStatus.ARCHIVED)
        assert fu.name == "updated"
        assert fu.status == FlowStatus.ARCHIVED
        assert fu.description is None


# ===========================================================================
# Flow ORM model
# ===========================================================================


class TestFlowModel:
    def test_uuid_primary_key(self) -> None:
        flow = Flow(name="test_flow")
        assert isinstance(flow.id, UUID)

    def test_timestamps(self) -> None:
        flow = Flow(name="test_flow")
        assert isinstance(flow.created_at, datetime)
        assert isinstance(flow.updated_at, datetime)

    def test_default_status(self) -> None:
        assert Flow(name="f").status == FlowStatus.DRAFT

    def test_default_type(self) -> None:
        assert Flow(name="f").flow_type == FlowType.AGENT

    def test_default_not_public(self) -> None:
        assert Flow(name="f").is_public is False

    def test_soft_delete_defaults(self) -> None:
        flow = Flow(name="f")
        assert flow.is_deleted is False
        assert flow.deleted_at is None

    def test_run_count_starts_at_zero(self) -> None:
        assert Flow(name="f").run_count == 0

    def test_version_starts_at_one(self) -> None:
        assert Flow(name="f").version == 1

    def test_data_and_settings_optional(self) -> None:
        flow = Flow(name="f")
        assert flow.data is None
        assert flow.settings is None

    def test_icon_default(self) -> None:
        flow = Flow(name="f")
        assert flow.icon is not None

    def test_nullable_ids(self) -> None:
        flow = Flow(name="f")
        assert flow.user_id is None
        assert flow.folder_id is None
        assert flow.parent_id is None

    def test_custom_name_and_description(self) -> None:
        flow = Flow(name="Invoice Processing", description="Processes invoices")
        assert flow.name == "Invoice Processing"
        assert flow.description == "Processes invoices"


# ===========================================================================
# FlowVersion snapshot model
# ===========================================================================


class TestFlowVersion:
    def test_creation(self) -> None:
        flow_id = uuid4()
        fv = FlowVersion(flow_id=flow_id, version=1, name="v1 snapshot")
        assert fv.flow_id == flow_id
        assert fv.version == 1
        assert fv.name == "v1 snapshot"

    def test_optional_data(self) -> None:
        fv = FlowVersion(flow_id=uuid4(), version=2, name="v2")
        assert fv.data is None
        assert fv.change_log is None
