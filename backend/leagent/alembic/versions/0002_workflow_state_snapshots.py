"""create workflow_state_snapshots table

Revision ID: 0002_workflow_state_snapshots
Revises: 0001_agent_checkpoints
Create Date: 2026-06-12

Durable workflow run snapshots backing :class:`leagent.workflow.state_store.SQLWorkflowStateStore`.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "0002_workflow_state_snapshots"
down_revision: Union[str, None] = "0001_agent_checkpoints"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "workflow_state_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("state_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=True),
        sa.Column("prompt_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_workflow_state_snapshots_state_id"),
        "workflow_state_snapshots",
        ["state_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_workflow_state_snapshots_execution_id"),
        "workflow_state_snapshots",
        ["execution_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workflow_state_snapshots_prompt_id"),
        "workflow_state_snapshots",
        ["prompt_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_workflow_state_snapshots_prompt_id"),
        table_name="workflow_state_snapshots",
    )
    op.drop_index(
        op.f("ix_workflow_state_snapshots_execution_id"),
        table_name="workflow_state_snapshots",
    )
    op.drop_index(
        op.f("ix_workflow_state_snapshots_state_id"),
        table_name="workflow_state_snapshots",
    )
    op.drop_table("workflow_state_snapshots")
