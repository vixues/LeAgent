"""Worktree workspace mode + change-review queue API (Codex Review Queue).

Endpoints:

* ``POST /sessions/{id}/workspace-mode`` — switch a session to
  ``worktree`` mode (creates the git worktree + branch) or back to
  ``direct``.
* ``GET  /sessions/{id}/workspace-mode`` — current mode + worktrees.
* ``POST /sessions/{id}/change-reviews`` — snapshot the session's
  worktree into a pending review (title/summary + diff stats).
* ``GET  /sessions/{id}/change-reviews`` — list reviews for a session.
* ``GET  /change-reviews/{rid}/diff`` — live unified diff vs base.
* ``POST /change-reviews/{rid}/approve`` — commit + merge into base.
* ``POST /change-reviews/{rid}/reject`` — mark rejected (worktree kept).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from fastapi import APIRouter, HTTPException, status
from sqlmodel import select

from leagent.api.v1.chat_deps import ChatSvc
from leagent.db.models.change_review import ChangeReview
from leagent.project.worktree import (
    WorktreeError,
    WorktreeInfo,
    get_worktree_manager,
    get_worktree_registry,
)
from leagent.services.auth import CurrentUserId  # noqa: TC001

logger = structlog.get_logger(__name__)

router = APIRouter()


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _get_db():
    from leagent.main import get_service_manager

    sm = get_service_manager()
    db = getattr(sm, "database_service", None) if sm else None
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        )
    return db


def _review_to_dict(row: ChangeReview) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "session_id": row.session_id,
        "run_id": row.run_id,
        "workspace_mode": row.workspace_mode,
        "project_root": row.project_root,
        "worktree_path": row.worktree_path,
        "branch": row.branch,
        "base_branch": row.base_branch,
        "title": row.title,
        "summary": row.summary,
        "files_changed": row.files_changed,
        "additions": row.additions,
        "deletions": row.deletions,
        "status": row.status,
        "created_at": row.created_at.isoformat(),
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "decided_by": row.decided_by,
        "reject_reason": row.reject_reason,
    }


def _info_from_review(row: ChangeReview) -> WorktreeInfo:
    return WorktreeInfo(
        session_id=row.session_id,
        project_root=row.project_root,
        worktree_path=row.worktree_path or "",
        branch=row.branch or "",
        base_branch=row.base_branch or "",
    )


# ---------------------------------------------------------------------------
# Workspace mode
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/workspace-mode")
async def set_workspace_mode(
    session_id: UUID,
    body: dict[str, Any],
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> dict[str, Any]:
    """Switch the session between ``direct`` and ``worktree`` coding modes."""
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    mode = str((body or {}).get("mode") or "").strip().lower()
    project_path = str((body or {}).get("project_path") or "").strip()
    if mode not in ("direct", "worktree"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="mode must be 'direct' or 'worktree'",
        )

    registry = get_worktree_registry()
    sid = str(session_id)

    if mode == "direct":
        for info in registry.for_session(sid):
            registry.unregister(sid, info.project_root)
        return {"session_id": sid, "mode": "direct", "worktrees": []}

    if not project_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="project_path is required for worktree mode",
        )

    existing = registry.resolve(sid, project_path)
    if existing is not None:
        return {"session_id": sid, "mode": "worktree", "worktrees": [existing.to_dict()]}

    try:
        info = await get_worktree_manager().create(project_path, sid)
    except WorktreeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc),
        ) from exc
    registry.register(info)
    return {"session_id": sid, "mode": "worktree", "worktrees": [info.to_dict()]}


@router.get("/sessions/{session_id}/workspace-mode")
async def get_workspace_mode(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> dict[str, Any]:
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    infos = get_worktree_registry().for_session(str(session_id))
    return {
        "session_id": str(session_id),
        "mode": "worktree" if infos else "direct",
        "worktrees": [i.to_dict() for i in infos],
    }


# ---------------------------------------------------------------------------
# Change reviews
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/change-reviews")
async def create_change_review(
    session_id: UUID,
    body: dict[str, Any],
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> dict[str, Any]:
    """Snapshot the session's worktree changes into a pending review."""
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    sid = str(session_id)
    infos = get_worktree_registry().for_session(sid)
    if not infos:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Session has no active worktree; enable workspace_mode=worktree first.",
        )
    info = infos[0]
    manager = get_worktree_manager()
    stats = await manager.diff_stats(info)
    if stats["files_changed"] == 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Worktree has no changes vs the base branch.",
        )

    title = str((body or {}).get("title") or "").strip() or f"Changes from session {sid[:8]}"
    summary = str((body or {}).get("summary") or "").strip() or None
    run_id = str((body or {}).get("run_id") or "").strip() or None

    row = ChangeReview(
        session_id=sid,
        user_id=str(user_id) if user_id else None,
        run_id=run_id,
        workspace_mode="worktree",
        project_root=info.project_root,
        worktree_path=info.worktree_path,
        branch=info.branch,
        base_branch=info.base_branch,
        title=title[:500],
        summary=summary[:4000] if summary else None,
        files_changed=stats["files_changed"],
        additions=stats["additions"],
        deletions=stats["deletions"],
        status="pending",
    )
    db = _get_db()
    async with db.session() as s:
        s.add(row)
        await s.commit()
        await s.refresh(row)
    logger.info("change_review_created", review_id=str(row.id), session_id=sid)
    return _review_to_dict(row)


@router.get("/sessions/{session_id}/change-reviews")
async def list_change_reviews(
    session_id: UUID,
    user_id: CurrentUserId,
    chat_svc: ChatSvc,
) -> dict[str, Any]:
    session = await chat_svc.get_session(session_id, user_id=user_id)
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
    db = _get_db()
    async with db.session() as s:
        rows = (
            await s.execute(
                select(ChangeReview)
                .where(ChangeReview.session_id == str(session_id))
                .order_by(ChangeReview.created_at.desc())  # type: ignore[attr-defined]
            )
        ).scalars().all()
    return {"session_id": str(session_id), "reviews": [_review_to_dict(r) for r in rows]}


async def _load_review(review_id: UUID) -> ChangeReview:
    db = _get_db()
    async with db.session() as s:
        row = await s.get(ChangeReview, review_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    return row


@router.get("/change-reviews/{review_id}/diff")
async def get_change_review_diff(
    review_id: UUID,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """Live unified diff of the review's worktree vs its base branch."""
    row = await _load_review(review_id)
    info = _info_from_review(row)
    manager = get_worktree_manager()
    try:
        diff = await manager.diff(info)
        files = await manager.changed_files(info)
    except WorktreeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc),
        ) from exc
    # Bound the payload; the UI shows the head and links out for the rest.
    max_bytes = 512 * 1024
    truncated = len(diff) > max_bytes
    if truncated:
        diff = diff[:max_bytes] + "\n... [diff truncated]"
    return {
        "review_id": str(review_id),
        "diff": diff,
        "files": files,
        "truncated": truncated,
    }


@router.post("/change-reviews/{review_id}/approve")
async def approve_change_review(
    review_id: UUID,
    user_id: CurrentUserId,
) -> dict[str, Any]:
    """Approve: commit pending worktree changes and merge into the base branch."""
    row = await _load_review(review_id)
    if row.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Review is {row.status}, not pending.",
        )
    info = _info_from_review(row)
    manager = get_worktree_manager()
    try:
        await manager.merge_into_base(info, message=f"leagent: {row.title}")
        new_status = "merged"
        reject_reason = None
    except WorktreeError as exc:
        new_status = "failed"
        reject_reason = str(exc)[:1000]

    db = _get_db()
    async with db.session() as s:
        fresh = await s.get(ChangeReview, review_id)
        if fresh is not None:
            fresh.status = new_status
            fresh.decided_at = _naive_utc_now()
            fresh.decided_by = str(user_id) if user_id else "user"
            fresh.reject_reason = reject_reason
            fresh.updated_at = _naive_utc_now()
            s.add(fresh)
            await s.commit()
            await s.refresh(fresh)
            row = fresh

    if new_status == "merged":
        # Retire the worktree after a successful merge.
        try:
            await manager.remove(info)
        except Exception:  # noqa: BLE001
            logger.warning("worktree_cleanup_failed", exc_info=True)
        get_worktree_registry().unregister(row.session_id, row.project_root)
        logger.info("change_review_merged", review_id=str(review_id))
    else:
        logger.warning(
            "change_review_merge_failed", review_id=str(review_id), error=reject_reason,
        )
    return _review_to_dict(row)


@router.post("/change-reviews/{review_id}/reject")
async def reject_change_review(
    review_id: UUID,
    user_id: CurrentUserId,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Reject: mark the review rejected. The worktree is kept for iteration."""
    row = await _load_review(review_id)
    if row.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Review is {row.status}, not pending.",
        )
    reason = str((body or {}).get("reason") or "").strip() or None

    db = _get_db()
    async with db.session() as s:
        fresh = await s.get(ChangeReview, review_id)
        if fresh is not None:
            fresh.status = "rejected"
            fresh.decided_at = _naive_utc_now()
            fresh.decided_by = str(user_id) if user_id else "user"
            fresh.reject_reason = reason[:1000] if reason else None
            fresh.updated_at = _naive_utc_now()
            s.add(fresh)
            await s.commit()
            await s.refresh(fresh)
            row = fresh
    logger.info("change_review_rejected", review_id=str(review_id))
    return _review_to_dict(row)
