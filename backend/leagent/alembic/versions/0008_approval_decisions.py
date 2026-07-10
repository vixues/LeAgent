"""approval_decisions audit table

Revision ID: 0008_approval_decisions
Revises: 0007_coding_project_kind
Create Date: 2026-07-10

Phase 2 of the Codex-style approval flow: every user Allow/Deny decision
on a gated tool call is audited durably.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0008_approval_decisions"
down_revision: Union[str, None] = "0007_coding_project_kind"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return table_name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("approval_decisions"):
        return
    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("session_id", sa.String(length=100), nullable=True),
        sa.Column("user_id", sa.String(length=100), nullable=True),
        sa.Column("tool_call_id", sa.String(length=100), nullable=False),
        sa.Column("tool_name", sa.String(length=200), nullable=False),
        sa.Column("params_digest", sa.String(length=32), nullable=False),
        sa.Column("params_summary", sa.String(length=2000), nullable=True),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("decided_by", sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("session_id", "user_id", "tool_name", "decision"):
        op.create_index(
            op.f(f"ix_approval_decisions_{col}"), "approval_decisions", [col], unique=False,
        )


def downgrade() -> None:
    if not _has_table("approval_decisions"):
        return
    for col in ("decision", "tool_name", "user_id", "session_id"):
        op.drop_index(op.f(f"ix_approval_decisions_{col}"), table_name="approval_decisions")
    op.drop_table("approval_decisions")
