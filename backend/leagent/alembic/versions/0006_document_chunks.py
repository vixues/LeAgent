"""document chunks table + SQLite FTS5 index

Revision ID: 0006_document_chunks
Revises: 0005_library_layer
Create Date: 2026-07-08

Chunk store backing knowledge retrieval. On SQLite an FTS5 external-content
index (``document_chunks_fts``) with sync triggers provides BM25 ranking and
snippets; PostgreSQL deployments rely on the lexical fallback instead.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0006_document_chunks"
down_revision: Union[str, None] = "0005_library_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return table_name in inspect(op.get_bind()).get_table_names()


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(i["name"] == index_name for i in inspect(op.get_bind()).get_indexes(table_name))


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def upgrade() -> None:
    if not _has_table("document_chunks"):
        op.create_table(
            "document_chunks",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("file_id", sa.Uuid(), nullable=False),
            sa.Column("user_id", sa.Uuid(), nullable=True),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("start_offset", sa.Integer(), nullable=False),
            sa.Column("end_offset", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["file_id"], ["files.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    for colname in ("file_id", "user_id"):
        idx = op.f(f"ix_document_chunks_{colname}")
        if not _has_index("document_chunks", idx):
            op.create_index(idx, "document_chunks", [colname], unique=False)

    if _dialect_name() == "sqlite":
        from leagent.library.fts import FTS_DDL

        for ddl in FTS_DDL:
            op.execute(sa.text(ddl))


def downgrade() -> None:
    if _dialect_name() == "sqlite":
        from leagent.library.fts import FTS_DROP_DDL

        for ddl in FTS_DROP_DDL:
            op.execute(sa.text(ddl))

    if _has_table("document_chunks"):
        for colname in ("user_id", "file_id"):
            idx = op.f(f"ix_document_chunks_{colname}")
            if _has_index("document_chunks", idx):
                op.drop_index(idx, table_name="document_chunks")
        op.drop_table("document_chunks")
