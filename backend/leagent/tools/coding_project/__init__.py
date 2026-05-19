"""Agent tools for the coding-project live-runtime feature.

These tools wrap :class:`leagent.services.coding_projects.manager.CodingProjectManager`
so the LLM can scaffold, run, stop, and inspect a generated project
the same way a human user would through the REST API.

Each tool maps to one supervisor primitive:

* :class:`CodingProjectScaffoldTool` — copy a template into a new
  on-disk root and persist a row.
* :class:`CodingProjectRunTool` — boot the dev server and return a
  signed preview URL.
* :class:`CodingProjectStopTool` — gracefully stop the supervisor.
* :class:`CodingProjectStatusTool` — report current state.
* :class:`CodingProjectLogsTool` — return the last N log lines.
* :class:`CodingProjectReadTool` — read a text file under the project root.
"""

from leagent.tools.coding_project.tools import (
    CodingProjectLogsTool,
    CodingProjectReadTool,
    CodingProjectRunTool,
    CodingProjectScaffoldTool,
    CodingProjectStatusTool,
    CodingProjectStopTool,
)

__all__ = [
    "CodingProjectLogsTool",
    "CodingProjectReadTool",
    "CodingProjectRunTool",
    "CodingProjectScaffoldTool",
    "CodingProjectStatusTool",
    "CodingProjectStopTool",
]
