"""unified library layer columns on files

Revision ID: 0005_library_layer
Revises: 0004_llm_request_log_linkage
Create Date: 2026-07-08

Adds the unified library catalog columns (identity by column, not storage
path):

- ``library_scope``: ``workspace`` | ``knowledge`` | ``artifact``
- ``inbox_state``: ``new`` | ``triaged`` | ``dismissed`` (information hub)
- ``origin_type`` / ``origin_ref``: ingress provenance stamping
- ``is_pinned``: exempt from retention/GC

Backfill policy:

- Rows whose ``storage_path`` lives under the system knowledge roots become
  ``library_scope='knowledge'`` (this retires path-prefix identity).
- All existing rows get ``inbox_state='triaged'`` so the new information-hub
  inbox is not flooded with historical files.
- Historic tool outputs cannot be reliably distinguished from uploads (the
  ``category`` of a FileRef was never persisted), so no ``artifact`` backfill
  is attempted; artifact scope is stamped at ingress going forward.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "0005_library_layer"
down_revision: Union[str, None] = "0004_llm_request_log_linkage"
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


def _knowledge_roots() -> tuple[str, ...]:
    """Absolute dirs that historically identified system knowledge files."""
    import os

    try:
        from leagent.config.settings import get_settings

        base = get_settings().files.resolved_knowledge_storage_dir()
    except Exception:  # pragma: no cover - settings unavailable in exotic envs
        return ()
    return (
        os.path.normpath(os.path.join(base, "system")),
        os.path.normpath(os.path.join(base, "documents")),
    )


def upgrade() -> None:
    if not _has_table("files"):
        return

    if not _has_column("files", "library_scope"):
        op.add_column(
            "files",
            sa.Column(
                "library_scope",
                sa.String(length=20),
                nullable=False,
                server_default="workspace",
            ),
        )
    if not _has_column("files", "inbox_state"):
        # Existing rows land as 'triaged' via the server default; new rows are
        # stamped 'new' by the ORM model default.
        op.add_column(
            "files",
            sa.Column(
                "inbox_state",
                sa.String(length=20),
                nullable=False,
                server_default="triaged",
            ),
        )
    if not _has_column("files", "origin_type"):
        op.add_column("files", sa.Column("origin_type", sa.String(length=40), nullable=True))
    if not _has_column("files", "origin_ref"):
        op.add_column("files", sa.Column("origin_ref", sa.String(length=100), nullable=True))
    if not _has_column("files", "is_pinned"):
        op.add_column(
            "files",
            sa.Column("is_pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        )

    for col in ("library_scope", "inbox_state", "origin_type", "origin_ref"):
        idx = op.f(f"ix_files_{col}")
        if not _has_index("files", idx):
            op.create_index(idx, "files", [col], unique=False)

    # Backfill knowledge scope from the historical path-prefix identity.
    import os

    bind = op.get_bind()
    for root in _knowledge_roots():
        bind.execute(
            sa.text(
                "UPDATE files SET library_scope = 'knowledge' "
                "WHERE storage_path = :root OR storage_path LIKE :prefix"
            ),
            {"root": root, "prefix": root + os.sep + "%"},
        )


def downgrade() -> None:
    if not _has_table("files"):
        return
    for col in ("origin_ref", "origin_type", "inbox_state", "library_scope"):
        idx = op.f(f"ix_files_{col}")
        if _has_index("files", idx):
            op.drop_index(idx, table_name="files")
    for col in ("is_pinned", "origin_ref", "origin_type", "inbox_state", "library_scope"):
        if _has_column("files", col):
            with op.batch_alter_table("files") as batch_op:
                batch_op.drop_column(col)
