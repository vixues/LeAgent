"""backfill agent_traces.root_span_id

Revision ID: 0012_agent_traces_root_span
Revises: 0011_agent_traces
Create Date: 2026-07-12

``SQLModel.metadata.create_all`` can create ``agent_traces`` before alembic
``0011`` runs; ``0011`` then skips ``CREATE TABLE`` and leaves the schema
without ``root_span_id``. This revision adds the column when missing.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0012_agent_traces_root_span"
down_revision: Union[str, None] = "0011_agent_traces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return table_name in inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(c["name"] == column_name for c in inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if _has_table("agent_traces") and not _has_column("agent_traces", "root_span_id"):
        op.add_column(
            "agent_traces",
            sa.Column("root_span_id", sa.String(length=64), nullable=True),
        )


def downgrade() -> None:
    if _has_table("agent_traces") and _has_column("agent_traces", "root_span_id"):
        if inspect(op.get_bind()).dialect.name == "sqlite":
            with op.batch_alter_table("agent_traces") as batch_op:
                batch_op.drop_column("root_span_id")
        else:
            op.drop_column("agent_traces", "root_span_id")
