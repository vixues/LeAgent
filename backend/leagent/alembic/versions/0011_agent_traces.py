"""agent running traces + llm_request_logs.run_id

Revision ID: 0011_agent_traces
Revises: 0010_chat_project_folder
Create Date: 2026-07-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0011_agent_traces"
down_revision: Union[str, None] = "0010_chat_project_folder"
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
    if not _has_table("agent_traces"):
        op.create_table(
            "agent_traces",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("trace_id", sa.String(length=64), nullable=False),
            sa.Column("parent_trace_id", sa.String(length=64), nullable=True),
            sa.Column("session_id", sa.String(length=100), nullable=True),
            sa.Column("user_id", sa.String(length=100), nullable=True),
            sa.Column("scope", sa.String(length=32), nullable=False),
            sa.Column("agent_name", sa.String(length=200), nullable=False),
            sa.Column("model", sa.String(length=200), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("terminal_reason", sa.String(length=64), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("latency_ms", sa.Float(), nullable=False),
            sa.Column("input_tokens", sa.Integer(), nullable=False),
            sa.Column("output_tokens", sa.Integer(), nullable=False),
            sa.Column("cache_read_tokens", sa.Integer(), nullable=False),
            sa.Column("cache_miss_tokens", sa.Integer(), nullable=False),
            sa.Column("total_cost_usd", sa.Float(), nullable=False),
            sa.Column("tool_call_count", sa.Integer(), nullable=False),
            sa.Column("llm_call_count", sa.Integer(), nullable=False),
            sa.Column("experiment_id", sa.String(length=64), nullable=True),
            sa.Column("prompt_hash", sa.String(length=64), nullable=True),
            sa.Column("tags", sa.Text(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("scores", sa.Text(), nullable=True),
            sa.Column("root_span_id", sa.String(length=64), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("trace_id"),
        )
        for col in (
            "trace_id",
            "parent_trace_id",
            "session_id",
            "user_id",
            "scope",
            "model",
            "status",
            "experiment_id",
        ):
            op.create_index(op.f(f"ix_agent_traces_{col}"), "agent_traces", [col], unique=False)
    elif not _has_column("agent_traces", "root_span_id"):
        # Table may have been created earlier by SQLModel.create_all without
        # this column; backfill so ORM selects succeed.
        op.add_column(
            "agent_traces",
            sa.Column("root_span_id", sa.String(length=64), nullable=True),
        )

    if not _has_table("agent_trace_spans"):
        op.create_table(
            "agent_trace_spans",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("span_id", sa.String(length=64), nullable=False),
            sa.Column("parent_span_id", sa.String(length=64), nullable=True),
            sa.Column("trace_id", sa.String(length=64), nullable=False),
            sa.Column("seq", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("name", sa.String(length=300), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("latency_ms", sa.Float(), nullable=False),
            sa.Column("attrs", sa.Text(), nullable=True),
            sa.Column("input_preview", sa.Text(), nullable=True),
            sa.Column("output_preview", sa.Text(), nullable=True),
            sa.Column("payload_ref", sa.String(length=500), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
        for col in ("span_id", "parent_span_id", "trace_id", "seq", "kind"):
            op.create_index(
                op.f(f"ix_agent_trace_spans_{col}"),
                "agent_trace_spans",
                [col],
                unique=False,
            )

    if not _has_table("agent_trace_experiments"):
        op.create_table(
            "agent_trace_experiments",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("experiment_id", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("session_id", sa.String(length=100), nullable=True),
            sa.Column("model_ids", sa.Text(), nullable=False),
            sa.Column("created_by", sa.String(length=100), nullable=True),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("experiment_id"),
        )
        for col in ("experiment_id", "session_id", "status"):
            op.create_index(
                op.f(f"ix_agent_trace_experiments_{col}"),
                "agent_trace_experiments",
                [col],
                unique=False,
            )

    if _has_table("llm_request_logs") and not _has_column("llm_request_logs", "run_id"):
        op.add_column(
            "llm_request_logs",
            sa.Column("run_id", sa.String(length=100), nullable=True),
        )
        idx = op.f("ix_llm_request_logs_run_id")
        if not _has_index("llm_request_logs", idx):
            op.create_index(idx, "llm_request_logs", ["run_id"], unique=False)


def downgrade() -> None:
    if _has_table("llm_request_logs") and _has_column("llm_request_logs", "run_id"):
        idx = op.f("ix_llm_request_logs_run_id")
        if _has_index("llm_request_logs", idx):
            op.drop_index(idx, table_name="llm_request_logs")
        op.drop_column("llm_request_logs", "run_id")

    for table in ("agent_trace_experiments", "agent_trace_spans", "agent_traces"):
        if _has_table(table):
            op.drop_table(table)
