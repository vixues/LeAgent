"""create agent_checkpoints table

Revision ID: 0001_agent_checkpoints
Revises:
Create Date: 2026-06-09

Durable agent-run checkpoints (Codex RolloutRecorder / Claude SessionStore
analogue) backing :class:`leagent.sdk.kernel.checkpoint.SQLCheckpointStore`.
For the zero-config SQLite default this table is also created by
``DatabaseService.create_tables`` (``SQLModel.metadata.create_all``); this
revision exists for PostgreSQL / explicit-migration deployments.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel

revision: str = "0001_agent_checkpoints"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_checkpoints",
        sa.Column("id", sqlmodel.sql.sqltypes.GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("checkpoint_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("agent_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("turn", sa.Integer(), nullable=False),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_agent_checkpoints_checkpoint_id"),
        "agent_checkpoints",
        ["checkpoint_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_agent_checkpoints_session_id"),
        "agent_checkpoints",
        ["session_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_agent_checkpoints_session_id"),
        table_name="agent_checkpoints",
    )
    op.drop_index(
        op.f("ix_agent_checkpoints_checkpoint_id"),
        table_name="agent_checkpoints",
    )
    op.drop_table("agent_checkpoints")
