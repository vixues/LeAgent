"""Built-in node classes.

``BUILTIN_NODES`` is the curated list the loader registers on startup.
Add a new file + entry here to expose a new stock node; user packs should
use :class:`NodeExtension` instead of editing this list.
"""

from __future__ import annotations

from leagent.workflow.nodes.base import WorkflowNode

from .script_agent import ScriptAgentNode
from .coding_agent import CodingAgentNode
from .condition import ConditionNode
from .end import EndNode
from .error_handler import ErrorHandlerNode
from .human_review import HumanReviewNode
from .llm_call import LLMCallNode
from .parallel import ParallelNode
from .script import ScriptNode
from .start import StartNode
from .subworkflow import SubworkflowNode
from .tool_call import ToolCallNode
from .transform import TransformNode
from .wait import WaitNode

BUILTIN_NODES: list[type[WorkflowNode]] = [
    StartNode,
    EndNode,
    ToolCallNode,
    LLMCallNode,
    ConditionNode,
    ParallelNode,
    HumanReviewNode,
    ErrorHandlerNode,
    TransformNode,
    SubworkflowNode,
    WaitNode,
    ScriptNode,
    ScriptAgentNode,
    CodingAgentNode,
]

__all__ = [
    "BUILTIN_NODES",
    "ScriptAgentNode",
    "CodingAgentNode",
    "ConditionNode",
    "EndNode",
    "ErrorHandlerNode",
    "HumanReviewNode",
    "LLMCallNode",
    "ParallelNode",
    "ScriptNode",
    "StartNode",
    "SubworkflowNode",
    "ToolCallNode",
    "TransformNode",
    "WaitNode",
]
