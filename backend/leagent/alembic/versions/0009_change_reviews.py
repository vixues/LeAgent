"""change_reviews table (worktree review queue)

Revision ID: 0009_change_reviews
Revises: 0008_approval_decisions
Create Date: 2026-07-10

Phase 5 of the Codex-style upgrade: worktree coding sessions produce
reviewable changesets that a human approves (merge) or rejects.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0009_change_reviews"
down_revision: Union[str, None] = "0008_approval_decisions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return table_name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if _has_table("change_reviews"):
        return
    op.create_table(
        "change_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("session_id", sa.String(length=100), nullable=False),
        sa.Column("user_id", sa.String(length=100), nullable=True),
        sa.Column("run_id", sa.String(length=100), nullable=True),
        sa.Column("workspace_mode", sa.String(length=32), nullable=False),
        sa.Column("project_root", sa.String(length=1024), nullable=False),
        sa.Column("worktree_path", sa.String(length=1024), nullable=True),
        sa.Column("branch", sa.String(length=200), nullable=True),
        sa.Column("base_branch", sa.String(length=200), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.String(length=4000), nullable=True),
        sa.Column("files_changed", sa.Integer(), nullable=False),
        sa.Column("additions", sa.Integer(), nullable=False),
        sa.Column("deletions", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decided_by", sa.String(length=100), nullable=True),
        sa.Column("reject_reason", sa.String(length=1000), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    for col in ("session_id", "user_id", "status"):
        op.create_index(
            op.f(f"ix_change_reviews_{col}"), "change_reviews", [col], unique=False,
        )


def downgrade() -> None:
    if not _has_table("change_reviews"):
        return
    for col in ("status", "user_id", "session_id"):
        op.drop_index(op.f(f"ix_change_reviews_{col}"), table_name="change_reviews")
    op.drop_table("change_reviews")
