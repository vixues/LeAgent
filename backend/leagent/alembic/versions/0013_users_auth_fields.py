"""Expand users table for named accounts (security control plane).

Revision ID: 0013_users_auth_fields
Revises: 0012_agent_traces_root_span
Create Date: 2026-07-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0013_users_auth_fields"
down_revision: Union[str, None] = "0012_agent_traces_root_span"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return table_name in inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(c["name"] == column_name for c in inspect(op.get_bind()).get_columns(table_name))


def upgrade() -> None:
    if not _has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.Uuid(), primary_key=True),
            sa.Column("username", sa.String(length=128), nullable=True),
            sa.Column("password_hash", sa.String(length=512), nullable=True),
            sa.Column("display_name", sa.String(length=256), nullable=True),
            sa.Column("role", sa.String(length=32), nullable=False, server_default="user"),
            sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
        op.create_index("ix_users_username", "users", ["username"])
        return

    if not _has_column("users", "username"):
        op.add_column("users", sa.Column("username", sa.String(length=128), nullable=True))
        op.create_index("ix_users_username", "users", ["username"])
    if not _has_column("users", "password_hash"):
        op.add_column("users", sa.Column("password_hash", sa.String(length=512), nullable=True))
    if not _has_column("users", "display_name"):
        op.add_column("users", sa.Column("display_name", sa.String(length=256), nullable=True))
    if not _has_column("users", "role"):
        op.add_column(
            "users",
            sa.Column("role", sa.String(length=32), nullable=False, server_default="user"),
        )
    if not _has_column("users", "disabled"):
        op.add_column(
            "users",
            sa.Column("disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    if not _has_column("users", "created_at"):
        op.add_column("users", sa.Column("created_at", sa.DateTime(), nullable=True))
    if not _has_column("users", "updated_at"):
        op.add_column("users", sa.Column("updated_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    # Keep columns — dropping would break FK-dependent tables in mixed deployments.
    pass
