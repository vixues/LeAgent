"""add chat_projects.folder_id for shared file space

Revision ID: 0010_chat_project_folder
Revises: 0009_change_reviews
Create Date: 2026-07-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0010_chat_project_folder"
down_revision: Union[str, None] = "0009_change_reviews"
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
        return
    if not _has_column("chat_projects", "folder_id"):
        if _dialect_name() == "sqlite":
            op.add_column(
                "chat_projects",
                sa.Column("folder_id", sa.Uuid(), nullable=True),
            )
        else:
            op.add_column(
                "chat_projects",
                sa.Column("folder_id", sa.Uuid(), nullable=True),
            )
            op.create_foreign_key(
                "fk_chat_projects_folder_id_folders",
                "chat_projects",
                "folders",
                ["folder_id"],
                ["id"],
            )
    if not _has_index("chat_projects", op.f("ix_chat_projects_folder_id")):
        op.create_index(
            op.f("ix_chat_projects_folder_id"),
            "chat_projects",
            ["folder_id"],
            unique=True,
        )


def downgrade() -> None:
    if not _has_table("chat_projects"):
        return
    if _has_index("chat_projects", op.f("ix_chat_projects_folder_id")):
        op.drop_index(op.f("ix_chat_projects_folder_id"), table_name="chat_projects")
    if _has_column("chat_projects", "folder_id"):
        if _dialect_name() == "sqlite":
            with op.batch_alter_table("chat_projects") as batch_op:
                batch_op.drop_column("folder_id")
        else:
            op.drop_constraint(
                "fk_chat_projects_folder_id_folders",
                "chat_projects",
                type_="foreignkey",
            )
            op.drop_column("chat_projects", "folder_id")
