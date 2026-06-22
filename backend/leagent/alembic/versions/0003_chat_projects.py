"""add chat projects

Revision ID: 0003_chat_projects
Revises: 0002_workflow_state_snapshots
Create Date: 2026-06-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect
import sqlmodel

revision: str = "0003_chat_projects"
down_revision: Union[str, None] = "0002_workflow_state_snapshots"
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


def _dialect_name() -> str:
    return op.get_bind().dialect.name


def upgrade() -> None:
    if not _has_table("chat_projects"):
        op.create_table(
            "chat_projects",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("is_deleted", sa.Boolean(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(), nullable=True),
            sa.Column("user_id", sa.Uuid(), nullable=False),
            sa.Column("workspace_id", sa.Uuid(), nullable=True),
            sa.Column("name", sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("design_context", sa.Text(), nullable=True),
            sa.Column("settings", sa.Text(), nullable=True),
            sa.Column("password_hash", sqlmodel.sql.sqltypes.AutoString(length=512), nullable=True),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _has_index("chat_projects", op.f("ix_chat_projects_user_id")):
        op.create_index(op.f("ix_chat_projects_user_id"), "chat_projects", ["user_id"], unique=False)
    if not _has_index("chat_projects", op.f("ix_chat_projects_workspace_id")):
        op.create_index(
            op.f("ix_chat_projects_workspace_id"),
            "chat_projects",
            ["workspace_id"],
            unique=False,
        )

    if not _has_column("chat_sessions", "project_id"):
        if _dialect_name() == "sqlite":
            op.add_column(
                "chat_sessions",
                sa.Column(
                    "project_id",
                    sa.Uuid(),
                    nullable=True,
                ),
            )
        else:
            op.add_column("chat_sessions", sa.Column("project_id", sa.Uuid(), nullable=True))
            op.create_foreign_key(
                "fk_chat_sessions_project_id_chat_projects",
                "chat_sessions",
                "chat_projects",
                ["project_id"],
                ["id"],
            )
    if not _has_index("chat_sessions", op.f("ix_chat_sessions_project_id")):
        op.create_index(
            op.f("ix_chat_sessions_project_id"),
            "chat_sessions",
            ["project_id"],
            unique=False,
        )
    if not _has_index("chat_sessions", "ix_chat_sessions_user_project_updated"):
        op.create_index(
            "ix_chat_sessions_user_project_updated",
            "chat_sessions",
            ["user_id", "project_id", "updated_at"],
            unique=False,
        )


def downgrade() -> None:
    if _has_index("chat_sessions", "ix_chat_sessions_user_project_updated"):
        op.drop_index("ix_chat_sessions_user_project_updated", table_name="chat_sessions")
    if _has_index("chat_sessions", op.f("ix_chat_sessions_project_id")):
        op.drop_index(op.f("ix_chat_sessions_project_id"), table_name="chat_sessions")
    if _has_column("chat_sessions", "project_id"):
        if _dialect_name() == "sqlite":
            with op.batch_alter_table("chat_sessions") as batch_op:
                batch_op.drop_column("project_id")
        else:
            op.drop_constraint(
                "fk_chat_sessions_project_id_chat_projects",
                "chat_sessions",
                type_="foreignkey",
            )
            op.drop_column("chat_sessions", "project_id")

    if _has_index("chat_projects", op.f("ix_chat_projects_workspace_id")):
        op.drop_index(op.f("ix_chat_projects_workspace_id"), table_name="chat_projects")
    if _has_index("chat_projects", op.f("ix_chat_projects_user_id")):
        op.drop_index(op.f("ix_chat_projects_user_id"), table_name="chat_projects")
    if _has_table("chat_projects"):
        op.drop_table("chat_projects")
