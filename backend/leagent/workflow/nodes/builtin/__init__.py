"""Built-in node classes.

``BUILTIN_NODES`` is the curated list the loader registers on startup.
Add a new file + entry here to expose a new stock node; user packs should
use :class:`NodeExtension` instead of editing this list.
"""

from __future__ import annotations

from leagent.workflow.nodes.base import WorkflowNode

from .script_agent import ScriptAgentNode
from .asset_export import AssetExportNode
from .coding_agent import CodingAgentNode
from .condition import ConditionNode
from .end import EndNode
from .error_handler import ErrorHandlerNode
from .human_review import HumanReviewNode
from .iterative_refine import IterativeRefineNode
from .llm_call import LLMCallNode
from .load_image import LoadImageNode
from .load_mesh3d import LoadMesh3DNode
from .parallel import ParallelNode
from .quality_gate import QualityGateNode
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
    QualityGateNode,
    IterativeRefineNode,
    AssetExportNode,
    LoadImageNode,
    LoadMesh3DNode,
]

__all__ = [
    "BUILTIN_NODES",
    "AssetExportNode",
    "ScriptAgentNode",
    "CodingAgentNode",
    "ConditionNode",
    "EndNode",
    "ErrorHandlerNode",
    "HumanReviewNode",
    "IterativeRefineNode",
    "LLMCallNode",
    "LoadImageNode",
    "LoadMesh3DNode",
    "ParallelNode",
    "QualityGateNode",
    "ScriptNode",
    "StartNode",
    "SubworkflowNode",
    "ToolCallNode",
    "TransformNode",
    "WaitNode",
]
