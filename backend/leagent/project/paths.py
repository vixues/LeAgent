"""Path / ownership validation for coding-project mode folders.

This module is the single home for the path-safety primitives used by
both the static "adopt-an-existing-folder" flow (``Folder.is_project``
+ ``Folder.project_path``, served by ``api/v1/folders.py``) and the
agent-managed scaffold flow (``CodingProject.root_path`` under
``CODING_PROJECTS_ROOT``, served by ``api/v1/coding_projects.py``).

Two policy knobs:

1. ``FILES_PROJECTS_ALLOWED_ROOTS`` — comma/semicolon-separated
   prefixes that user-supplied paths must live under. Empty = the
   single-user dev mode "unrestricted".
2. ``CODING_PROJECTS_ROOT`` — managed scratchpad root for agent-scaffolded
   projects (handled by :mod:`leagent.services.coding_projects.manager`).

Logic here is intentionally pure / synchronous so it can be unit-tested
without a running database. Binary allow-list checks (for spawning child
processes) live in :mod:`leagent.services.coding_projects.binaries`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable
from uuid import UUID

import structlog

from leagent.file.primitives import is_path_inside

from leagent.config.settings import get_settings

logger = structlog.get_logger(__name__)


class ProjectPathSafetyError(ValueError):
    """Raised when a project path fails policy or ownership checks."""


def _parse_allowed_roots(raw: str) -> tuple[Path, ...]:
    """Split the comma/colon-separated ``raw`` setting into resolved roots.

    Empty / whitespace entries are dropped. Non-existent prefixes are
    kept so a misconfigured deployment fails closed (no path matches
    a missing prefix).
    """
    if not raw:
        return ()
    out: list[Path] = []
    for chunk in raw.replace(";", ",").split(","):
        token = chunk.strip()
        if not token:
            continue
        try:
            resolved = Path(token).expanduser().resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            continue
        out.append(resolved)
    return tuple(out)


def get_allowed_project_roots() -> tuple[Path, ...]:
    """Return the configured allow-list of project root prefixes.

    Reads ``FILES_PROJECTS_ALLOWED_ROOTS`` (comma- or semicolon-
    separated). Returns an empty tuple when unset, which means
    "unrestricted" — appropriate for single-user dev deployments.
    """
    settings = get_settings()
    raw = getattr(settings.files, "projects_allowed_roots", "") or ""
    return _parse_allowed_roots(raw)


def is_path_under(candidate: Path, roots: Iterable[Path]) -> bool:
    """Return True iff ``candidate`` is equal to or nested under any root.

    Delegates to :func:`leagent.file.primitives.is_path_inside`.
    """
    return is_path_inside(candidate, roots)


def validate_project_path(raw_path: str) -> Path:
    """Resolve ``raw_path`` to an absolute, existing directory.

    Validation steps (in order):

    1. The string is non-empty and absolute (after ``~`` expansion).
    2. ``Path.resolve(strict=True)`` succeeds, i.e. the directory
       actually exists right now.
    3. The resolved path is a directory (not a file or symlink loop).
    4. When ``FILES_PROJECTS_ALLOWED_ROOTS`` is configured, the
       resolved path is inside one of those prefixes.

    Raises :class:`ProjectPathSafetyError` with a user-readable
    message on every failure mode.
    """
    if raw_path is None or not str(raw_path).strip():
        raise ProjectPathSafetyError("project_path is empty.")

    try:
        candidate = Path(str(raw_path)).expanduser()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProjectPathSafetyError(
            f"project_path is not a valid path: {exc}"
        ) from exc

    if not candidate.is_absolute():
        raise ProjectPathSafetyError(
            "project_path must be an absolute filesystem path."
        )

    try:
        resolved = candidate.resolve(strict=True)
    except FileNotFoundError as exc:
        raise ProjectPathSafetyError(
            f"project_path does not exist: {raw_path!r}"
        ) from exc
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProjectPathSafetyError(
            f"project_path could not be resolved: {exc}"
        ) from exc

    if not resolved.is_dir():
        raise ProjectPathSafetyError(
            f"project_path {raw_path!r} is not a directory."
        )

    allowed = get_allowed_project_roots()
    if allowed and not is_path_under(resolved, allowed):
        logger.warning(
            "project_path_rejected_by_policy",
            path=str(resolved),
            allowed_roots=[str(r) for r in allowed],
        )
        raise ProjectPathSafetyError(
            "project_path is outside the deployment's allowed project roots. "
            "Ask an administrator to extend FILES_PROJECTS_ALLOWED_ROOTS."
        )

    return resolved


def assert_folder_owner(folder: object, user_id: UUID) -> None:
    """Raise :class:`ProjectPathSafetyError` when ``user_id`` does not own ``folder``."""
    owner = getattr(folder, "user_id", None)
    if owner is None or owner != user_id:
        raise ProjectPathSafetyError(
            "You do not own this folder."
        )


def resolve_owned_project_folder(folder: object, user_id: UUID) -> Path:
    """Return the validated project path of a folder owned by ``user_id``.

    Convenience helper that sequentially calls :func:`assert_folder_owner`,
    requires :attr:`Folder.is_project` to be ``True`` and
    :attr:`Folder.project_path` to be set, and finally re-validates
    the path against the live policy. The re-validation matters
    because ``FILES_PROJECTS_ALLOWED_ROOTS`` may have tightened since
    the path was first stored, and the directory may have been
    deleted out from under us.
    """
    assert_folder_owner(folder, user_id)
    if not getattr(folder, "is_project", False):
        raise ProjectPathSafetyError("Folder is not in code-project mode.")
    project_path = getattr(folder, "project_path", None)
    if not project_path:
        raise ProjectPathSafetyError("Folder has no project_path configured.")
    return validate_project_path(project_path)


__all__ = [
    "ProjectPathSafetyError",
    "assert_folder_owner",
    "get_allowed_project_roots",
    "is_path_under",
    "resolve_owned_project_folder",
    "validate_project_path",
]
