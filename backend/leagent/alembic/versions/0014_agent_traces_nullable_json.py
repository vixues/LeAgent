"""Relax agent_traces.tags / scores NOT NULL

Revision ID: 0014_agent_traces_nullable_json
Revises: 0013_users_auth_fields
Create Date: 2026-07-13

``SQLModel.metadata.create_all`` historically created ``tags`` / ``scores`` as
NOT NULL TEXT. The ORM treats them as optional JSON blobs, so inserts with
NULL (no tags/scores yet) failed with IntegrityError and silent empty traces.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0014_agent_traces_nullable_json"
down_revision: Union[str, None] = "0013_users_auth_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return table_name in inspect(op.get_bind()).get_table_names()


def _column_nullable(table_name: str, column_name: str) -> bool | None:
    if not _has_table(table_name):
        return None
    for col in inspect(op.get_bind()).get_columns(table_name):
        if col["name"] == column_name:
            return bool(col.get("nullable", True))
    return None


def upgrade() -> None:
    if not _has_table("agent_traces"):
        return
    alter_tags = _column_nullable("agent_traces", "tags") is False
    alter_scores = _column_nullable("agent_traces", "scores") is False
    if not alter_tags and not alter_scores:
        return
    with op.batch_alter_table("agent_traces") as batch_op:
        if alter_tags:
            batch_op.alter_column(
                "tags",
                existing_type=sa.Text(),
                nullable=True,
            )
        if alter_scores:
            batch_op.alter_column(
                "scores",
                existing_type=sa.Text(),
                nullable=True,
            )


def downgrade() -> None:
    if not _has_table("agent_traces"):
        return
    # Backfill NULLs before restoring NOT NULL.
    op.execute("UPDATE agent_traces SET tags = '{}' WHERE tags IS NULL")
    op.execute("UPDATE agent_traces SET scores = '{}' WHERE scores IS NULL")
    with op.batch_alter_table("agent_traces") as batch_op:
        batch_op.alter_column(
            "tags",
            existing_type=sa.Text(),
            nullable=False,
        )
        batch_op.alter_column(
            "scores",
            existing_type=sa.Text(),
            nullable=False,
        )
