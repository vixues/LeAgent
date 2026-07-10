"""coding_projects.kind (managed | adopted)

Revision ID: 0007_coding_project_kind
Revises: 0006_document_chunks
Create Date: 2026-07-08

Phase 5 of the library consolidation: `coding_projects` becomes the single
project model. `kind` distinguishes manager-scaffolded projects (`managed`)
from existing on-disk directories bound via folder project-mode (`adopted`).
Rows whose linked folder carries a `project_path` different from their own
`root_path` history are handled by the runtime backfill
(`leagent.project.adoption.adopt_project_folders`), which also creates
adopted rows for `Folder.is_project` folders that have no project row yet.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0007_coding_project_kind"
down_revision: Union[str, None] = "0006_document_chunks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return table_name in inspect(op.get_bind()).get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(
        c["name"] == column_name
        for c in inspect(op.get_bind()).get_columns(table_name)
    )


def upgrade() -> None:
    # Fresh installs create the table via SQLModel metadata (kind included);
    # only pre-existing tables need the ALTER.
    if _has_table("coding_projects") and not _has_column("coding_projects", "kind"):
        op.add_column(
            "coding_projects",
            sa.Column(
                "kind",
                sa.String(length=16),
                nullable=False,
                server_default="managed",
            ),
        )
        op.create_index(
            op.f("ix_coding_projects_kind"), "coding_projects", ["kind"], unique=False
        )


def downgrade() -> None:
    if _has_column("coding_projects", "kind"):
        op.drop_index(op.f("ix_coding_projects_kind"), table_name="coding_projects")
        op.drop_column("coding_projects", "kind")
