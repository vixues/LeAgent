"""Process-level startup helpers.

Everything that needs to run exactly once when the server (or a CLI /
worker) boots up lives here. Individual modules stay narrow:

* :mod:`leagent.bootstrap.tools` — populate the default
  :class:`ToolRegistry` (auto-discovery + curated utility tools +
  code-execution tool) and lift every registered tool into a dedicated
  workflow node via the tool factory.

Callers should prefer these helpers over ad-hoc copy-pasted
``discover_all()`` + ``_register_utility_tools()`` blocks so every
entrypoint ends up with the same tool surface and the same
auto-generated workflow nodes.
"""

from __future__ import annotations

from .tools import (
    bootstrap_tools,
    bootstrap_tools_sync,
    register_coding_agent_tool,
    register_default_tools,
    register_script_agent_tool,
    register_subagent_tool,
    register_workflow_tool_nodes,
)

__all__ = [
    "bootstrap_tools",
    "bootstrap_tools_sync",
    "register_script_agent_tool",
    "register_coding_agent_tool",
    "register_default_tools",
    "register_subagent_tool",
    "register_workflow_tool_nodes",
]
