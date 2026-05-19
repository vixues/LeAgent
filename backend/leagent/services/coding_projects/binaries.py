"""Binary allow-list policy for the coding-project supervisor.

The supervisor will spawn arbitrary child processes (``npm run dev``,
``uvicorn``, ``python -m http.server``) inside an allocated working
directory. Two policies live in this package:

1. **Binary allow-list** (this module). Children are spawned via
   :func:`asyncio.create_subprocess_exec` with absolute paths
   resolved by :func:`shutil.which`. Before exec, the basename of
   that absolute path must match an entry in
   ``CODING_PROJECTS_ALLOWED_BINARIES``. This blocks the LLM from
   asking the supervisor to launch ``rm`` / ``curl | sh`` style
   commands.
2. **Path containment** (see :mod:`leagent.services.coding_projects.paths`).
   Every project's ``root_path`` must be under either
   ``CODING_PROJECTS_ROOT`` or, when the project was "adopted" from
   a folder, the folder's existing ``project_path``. The same path
   policy applies to manual folder configuration and agent-managed
   scaffolds.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Iterable, Sequence

import structlog

from leagent.config.settings import get_settings
from leagent.services.coding_projects.paths import (
    ProjectPathSafetyError,
    is_path_under,
)

logger = structlog.get_logger(__name__)


class CodingBinaryNotAllowedError(PermissionError):
    """Raised when a supervisor argv targets a non-allowlisted binary."""


def parse_allowed_binaries(raw: str) -> tuple[str, ...]:
    """Split the comma-separated env value into a tuple of binary names."""
    if not raw:
        return ()
    return tuple(
        token.strip()
        for token in raw.replace(";", ",").split(",")
        if token.strip()
    )


def get_allowed_binaries() -> tuple[str, ...]:
    """Return the configured binary basenames allowed at exec time."""
    settings = get_settings()
    return parse_allowed_binaries(settings.coding_projects.allowed_binaries or "")


def resolve_executable(name: str) -> str:
    """Resolve ``name`` to an absolute path on PATH and enforce the allow-list.

    On Windows, ``shutil.which`` adds the ``.exe`` / ``.cmd`` suffix
    automatically; we keep the lookup name basename so the allow-list
    stays readable (``"npm"``, not ``"npm.cmd"``).
    """
    resolved = shutil.which(name)
    if not resolved and name.lower() in {"python", "python3", "py"}:
        candidate = Path(sys.executable)
        if candidate.exists():
            resolved = str(candidate)
    if not resolved:
        raise CodingBinaryNotAllowedError(
            f"Executable {name!r} is not on PATH on the server."
        )
    allowed = get_allowed_binaries()
    if not allowed:
        return resolved
    base = Path(resolved).name.lower()
    base_no_ext = Path(resolved).stem.lower()
    if base in {b.lower() for b in allowed} or base_no_ext in {
        b.lower() for b in allowed
    }:
        return resolved
    logger.warning(
        "coding_projects_binary_denied",
        requested=name,
        resolved=resolved,
        allowed=list(allowed),
    )
    raise CodingBinaryNotAllowedError(
        f"Binary {base!r} is not in CODING_PROJECTS_ALLOWED_BINARIES."
    )


def assert_argv_allowed(argv: Sequence[str]) -> tuple[str, ...]:
    """Resolve and allow-list-check an argv before spawning.

    Returns the same argv with ``argv[0]`` replaced by the absolute
    path :func:`shutil.which` resolved. Raises
    :class:`CodingBinaryNotAllowedError` when the binary is missing
    or outside the allow-list.
    """
    if not argv:
        raise CodingBinaryNotAllowedError("argv is empty.")
    resolved = resolve_executable(argv[0])
    return (resolved, *tuple(str(a) for a in argv[1:]))


def assert_path_under_roots(candidate: Path, roots: Iterable[Path]) -> None:
    """Reject ``candidate`` that escapes every prefix in ``roots``."""
    if not is_path_under(candidate, roots):
        raise ProjectPathSafetyError(
            f"Path {candidate!s} is outside the configured coding-project roots."
        )


__all__ = [
    "CodingBinaryNotAllowedError",
    "assert_argv_allowed",
    "assert_path_under_roots",
    "get_allowed_binaries",
    "parse_allowed_binaries",
    "resolve_executable",
]
