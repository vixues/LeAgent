"""Layer 2: Code execution — tools, workspace, sandbox, artifacts.

This package consolidates all code-execution concerns that previously
lived across ``tools/code/`` and ``services/code_execution/``.

Dependency rule: ``leagent.code`` may import from ``leagent.file``
but never from ``leagent.project``.
"""

from leagent.code.artifacts import (
    ArtifactKind,
    CodeArtifact,
    CodeArtifactRegistry,
)
from leagent.code.execution import (
    CodeExecutionConfig,
    CodeExecutionEnvelope,
    CodeExecutionTool,
    ErrorType,
    build_default_code_execution_config,
)
from leagent.code.fim import DeepSeekFimTool
from leagent.code.operations import (
    CodeExecOp,
    FileEditOp,
    FilePatchOp,
    FileWriteOp,
    JournalEntry,
    OperationJournal,
    PatchedFile,
)
from leagent.code.packages import UvPipInstallTool
from leagent.code.pipeline import CodeGenerationPipeline, get_pipeline
from leagent.code.syntax import SyntaxValidatorTool
from leagent.code.workspace_edit import CodeWorkspaceEditTool

__all__ = [
    "ArtifactKind",
    "CodeArtifact",
    "CodeArtifactRegistry",
    "CodeExecOp",
    "CodeExecutionConfig",
    "CodeExecutionEnvelope",
    "CodeExecutionTool",
    "CodeGenerationPipeline",
    "CodeWorkspaceEditTool",
    "DeepSeekFimTool",
    "ErrorType",
    "FileEditOp",
    "FilePatchOp",
    "FileWriteOp",
    "JournalEntry",
    "OperationJournal",
    "PatchedFile",
    "SyntaxValidatorTool",
    "UvPipInstallTool",
    "build_default_code_execution_config",
    "get_pipeline",
]
