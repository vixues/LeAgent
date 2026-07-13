"""Add files.summary for knowledge catalog blurbs

Revision ID: 0015_files_summary
Revises: 0014_agent_traces_nullable_json
Create Date: 2026-07-13

Extractive document summaries are written after chunk indexing so
``knowledge_search`` catalog/read can advertise KB docs without LLM cost.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0015_files_summary"
down_revision: Union[str, None] = "0014_agent_traces_nullable_json"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return table_name in inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(c["name"] == column_name for c in inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if not _has_table("files"):
        return
    if _has_column("files", "summary"):
        return
    op.add_column("files", sa.Column("summary", sa.Text(), nullable=True))


def downgrade() -> None:
    if not _has_table("files"):
        return
    if not _has_column("files", "summary"):
        return
    op.drop_column("files", "summary")
