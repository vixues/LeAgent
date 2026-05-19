"""Project-aware coding tools for LeAgent.

This package provides the toolbox a real coding agent needs to author
multi-file projects on disk: read with line numbers, full-file write,
surgical string-replace edit, unified-diff apply, multi-file regex grep,
glob discovery, compact directory tree, and a curated shell.

All tools resolve paths against the per-request "project root" stamped
on :attr:`leagent.tools.base.ToolContext.extra` under the key
``project_roots`` (a list of absolute directories). The
:mod:`leagent.tools._sandbox.paths` module folds those roots into the
allow-list for the duration of the call so the existing path sandbox
keeps protecting the rest of the host filesystem.

Tools registered here:

* ``project_read``         — line-numbered read with offset/limit.
* ``project_write``        — whole-file write (creates parent dirs).
* ``project_edit``         — uniqueness-checked string replace.
* ``project_apply_patch``  — apply a unified diff across one or more files.
* ``project_grep``         — regex search across the project (rg-aware).
* ``project_glob``         — find files by glob, sorted by mtime.
* ``project_outline``       — Python top-level symbols and imports (``ast``).
* ``project_shell``        — run a curated whitelist of build/test/git
  commands inside the project root, with rlimits + timeouts.
"""

from __future__ import annotations

from leagent.tools.project.edit import ProjectEditTool
from leagent.tools.project.glob import ProjectGlobTool
from leagent.tools.project.grep import ProjectGrepTool
from leagent.tools.project.outline import ProjectOutlineTool
from leagent.tools.project.patch import ProjectApplyPatchTool
from leagent.tools.project.read import ProjectReadTool
from leagent.tools.project.shell import ProjectShellTool
from leagent.tools.project.tree import ProjectTreeTool
from leagent.tools.project.write import ProjectWriteTool

__all__ = [
    "ProjectReadTool",
    "ProjectWriteTool",
    "ProjectEditTool",
    "ProjectApplyPatchTool",
    "ProjectGrepTool",
    "ProjectGlobTool",
    "ProjectTreeTool",
    "ProjectOutlineTool",
    "ProjectShellTool",
]
