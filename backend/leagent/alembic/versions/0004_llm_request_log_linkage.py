"""llm_request_log linkage columns

Revision ID: 0004_llm_request_log_linkage
Revises: 0003_chat_projects
Create Date: 2026-06-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "0004_llm_request_log_linkage"
down_revision: Union[str, None] = "0003_chat_projects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return table_name in inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(c["name"] == column_name for c in inspect(op.get_bind()).get_columns(table_name))


def _has_index(table_name: str, index_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(i["name"] == index_name for i in inspect(op.get_bind()).get_indexes(table_name))


def upgrade() -> None:
    if not _has_table("llm_request_logs"):
        op.create_table(
            "llm_request_logs",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("provider_name", sa.String(length=100), nullable=False),
            sa.Column("model", sa.String(length=200), nullable=False),
            sa.Column("request_model", sa.String(length=200), nullable=False),
            sa.Column("input_tokens", sa.Integer(), nullable=False),
            sa.Column("output_tokens", sa.Integer(), nullable=False),
            sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
            sa.Column("cache_miss_tokens", sa.Integer(), nullable=False),
            sa.Column("total_cost_usd", sa.Float(), nullable=False),
            sa.Column("latency_ms", sa.Float(), nullable=False),
            sa.Column("ttfb_ms", sa.Float(), nullable=False),
            sa.Column("status_code", sa.Integer(), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("session_id", sa.String(length=100), nullable=True),
            sa.Column("user_id", sa.String(length=100), nullable=True),
            sa.Column("user_message_id", sa.String(length=100), nullable=True),
            sa.Column("call_index", sa.Integer(), nullable=False),
            sa.Column("call_kind", sa.String(length=32), nullable=False),
            sa.Column("is_streaming", sa.Boolean(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        for col in ("provider_name", "model", "status_code", "session_id", "user_id", "user_message_id", "call_kind"):
            op.create_index(op.f(f"ix_llm_request_logs_{col}"), "llm_request_logs", [col], unique=False)
        return

    if _has_column("llm_request_logs", "cache_write_tokens") and not _has_column(
        "llm_request_logs", "cache_miss_tokens"
    ):
        op.alter_column(
            "llm_request_logs",
            "cache_write_tokens",
            new_column_name="cache_miss_tokens",
        )
    elif not _has_column("llm_request_logs", "cache_miss_tokens"):
        op.add_column(
            "llm_request_logs",
            sa.Column("cache_miss_tokens", sa.Integer(), nullable=False, server_default="0"),
        )

    if not _has_column("llm_request_logs", "user_id"):
        op.add_column(
            "llm_request_logs",
            sa.Column("user_id", sa.String(length=100), nullable=True),
        )
    if not _has_column("llm_request_logs", "user_message_id"):
        op.add_column(
            "llm_request_logs",
            sa.Column("user_message_id", sa.String(length=100), nullable=True),
        )
    if not _has_column("llm_request_logs", "call_index"):
        op.add_column(
            "llm_request_logs",
            sa.Column("call_index", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _has_column("llm_request_logs", "call_kind"):
        op.add_column(
            "llm_request_logs",
            sa.Column("call_kind", sa.String(length=32), nullable=False, server_default="chat"),
        )

    for col in ("user_id", "user_message_id", "call_kind"):
        idx = op.f(f"ix_llm_request_logs_{col}")
        if not _has_index("llm_request_logs", idx):
            op.create_index(idx, "llm_request_logs", [col], unique=False)


def downgrade() -> None:
    if not _has_table("llm_request_logs"):
        return
    for col in ("call_kind", "call_index", "user_message_id", "user_id"):
        if _has_column("llm_request_logs", col):
            idx = op.f(f"ix_llm_request_logs_{col}")
            if _has_index("llm_request_logs", idx):
                op.drop_index(idx, table_name="llm_request_logs")
            op.drop_column("llm_request_logs", col)
    if _has_column("llm_request_logs", "cache_miss_tokens") and not _has_column(
        "llm_request_logs", "cache_write_tokens"
    ):
        op.alter_column(
            "llm_request_logs",
            "cache_miss_tokens",
            new_column_name="cache_write_tokens",
        )
