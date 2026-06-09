"""Layer 3: Coding project — tools, workspace, runtime, scaffold.

This package consolidates all coding-project concerns that previously
lived across ``tools/project/``, ``tools/coding_project/``, and
``services/coding_projects/``.

Dependency rule: ``leagent.project`` may import from ``leagent.file``
but never from ``leagent.code``.  Project edits write directly to disk
via ``resolve_in_project()`` and never create ``File`` DB rows.
"""

from leagent.project.tools.edit import ProjectEditTool
from leagent.project.tools.glob import ProjectGlobTool
from leagent.project.tools.grep import ProjectGrepTool
from leagent.project.tools.multiedit import ProjectMultieditTool
from leagent.project.tools.outline import ProjectOutlineTool
from leagent.project.tools.patch import ProjectApplyPatchTool
from leagent.project.tools.read import ProjectReadTool
from leagent.project.tools.shell import ProjectShellTool
from leagent.project.tools.tree import ProjectTreeTool
from leagent.project.tools.write import ProjectWriteTool

__all__ = [
    "ProjectApplyPatchTool",
    "ProjectEditTool",
    "ProjectGlobTool",
    "ProjectGrepTool",
    "ProjectMultieditTool",
    "ProjectOutlineTool",
    "ProjectReadTool",
    "ProjectShellTool",
    "ProjectTreeTool",
    "ProjectWriteTool",
]
