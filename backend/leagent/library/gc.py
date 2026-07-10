"""Blob garbage collection for the unified file catalog.

Reaps on-disk bytes for:

- soft-deleted rows past a grace period (default 7 days)
- rows whose ``expires_at`` has passed

Honors ``is_pinned`` and never deletes a ``storage_path`` still referenced by
any live (non-deleted) row — content dedup may share one blob across many
catalog entries.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

import sqlalchemy as sa
from sqlmodel import select

if TYPE_CHECKING:
    from leagent.db.service import DatabaseService

logger = logging.getLogger(__name__)

DEFAULT_GRACE_HOURS = 168  # 7 days


async def run_file_gc(
    db: "DatabaseService",
    *,
    grace_hours: int = DEFAULT_GRACE_HOURS,
    dry_run: bool = False,
) -> dict[str, int]:
    """Reap orphaned blobs and return summary counters."""
    from leagent.db.models.file import File

    now = datetime.now(UTC).replace(tzinfo=None)
    grace_cutoff = now - timedelta(hours=grace_hours)
    removed_blobs = 0
    skipped_shared = 0
    skipped_pinned = 0
    candidates: list[tuple[UUID, str]] = []

    async with db.session() as session:
        stmt = select(File).where(File.is_deleted == True)  # noqa: E712
        result = await session.exec(stmt)
        for row in result.all():
            if row.is_pinned:
                skipped_pinned += 1
                continue
            if row.deleted_at and row.deleted_at > grace_cutoff:
                continue
            if row.storage_path:
                candidates.append((row.id, row.storage_path))

        expired_stmt = select(File).where(
            File.is_deleted == False,  # noqa: E712
            File.expires_at.is_not(None),  # type: ignore[attr-defined]
            File.expires_at < now,
            File.is_pinned == False,  # noqa: E712
        )
        expired_result = await session.exec(expired_stmt)
        for row in expired_result.all():
            if row.storage_path:
                candidates.append((row.id, row.storage_path))
            row.is_deleted = True
            row.deleted_at = now
            session.add(row)

    seen_paths: set[str] = set()
    for _fid, storage_path in candidates:
        if storage_path in seen_paths:
            continue
        seen_paths.add(storage_path)
        if not await _storage_path_is_exclusive(db, storage_path):
            skipped_shared += 1
            continue
        if not os.path.isfile(storage_path):
            continue
        if dry_run:
            removed_blobs += 1
            continue
        try:
            os.unlink(storage_path)
            removed_blobs += 1
            logger.info("gc_removed_blob path=%s", storage_path)
        except OSError as exc:
            logger.warning("gc_unlink_failed path=%s err=%s", storage_path, exc)

    return {
        "removed_blobs": removed_blobs,
        "skipped_shared": skipped_shared,
        "skipped_pinned": skipped_pinned,
        "candidates": len(candidates),
    }


async def _storage_path_is_exclusive(db: "DatabaseService", storage_path: str) -> bool:
    """True when no live row still references *storage_path*."""
    from leagent.db.models.file import File

    async with db.session() as session:
        result = await session.exec(
            select(sa.func.count())
            .select_from(File)
            .where(File.storage_path == storage_path)
            .where(File.is_deleted == False)  # noqa: E712
        )
        count = result.one()
        return int(count or 0) == 0
