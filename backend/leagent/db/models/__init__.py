"""Database models for LeAgent (standalone local deployment)."""

from leagent.db.models.agent_checkpoint import AgentCheckpoint
from leagent.db.models.approval_decision import ApprovalDecisionLog
from leagent.db.models.change_review import ChangeReview
from leagent.db.models.agent_memory import (
    AgentEpisode,
    AgentFact,
    AgentProcedure,
)
from leagent.db.models.identity_stub import (
    UserStub,
    WorkspaceStub,
)
from leagent.db.models.cron import (
    CronExecutionModel,
    CronJobModel,
    CronJobRead,
)
from leagent.db.models.workflow_execution import (
    WorkflowExecution,
    WorkflowExecutionRead,
)
from leagent.db.models.workflow_state_snapshot import WorkflowStateSnapshot
from leagent.db.models.base import (
    BaseModel,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
    utc_now,
)
from leagent.db.models.file import (
    File,
    FileCreate,
    FileRead,
    FileStatus,
    FileType,
    FileUpdate,
    InboxState,
    LibraryScope,
)
from leagent.db.models.pet_project import (
    PetProject,
    PetProjectFile,
)
from leagent.db.models.chat_project import ChatProject
from leagent.db.models.flow import (
    Flow,
    FlowCreate,
    FlowRead,
    FlowStatus,
    FlowType,
    FlowUpdate,
    FlowVersion,
)
from leagent.db.models.folder import (
    Folder,
    FolderCreate,
    FolderProjectUpdate,
    FolderRead,
    FolderUpdate,
)
from leagent.db.models.coding_project import (
    CodingProject,
    CodingProjectCreate,
    CodingProjectRead,
    CodingProjectRuntimeKind,
    CodingProjectStatus,
    CodingProjectUpdate,
)
from leagent.db.models.canvas import (
    CanvasContentType,
    CanvasDocument,
)
from leagent.db.models.document_chunk import (
    DocumentChunk,
    DocumentChunkRead,
)
from leagent.db.models.message import (
    ChatSession,
    Message,
    MessageCreate,
    MessageRead,
    MessageRole,
    MessageStatus,
    SessionCreate,
    SessionRead,
)
from leagent.db.models.llm_request_log import LLMRequestLog
from leagent.db.models.agent_trace import (
    AgentTrace,
    AgentTraceExperiment,
    AgentTraceSpan,
)
from leagent.db.models.task import (
    Task,
    TaskContext,
    TaskCreate,
    TaskPriority,
    TaskRead,
    TaskStatus,
    TaskType,
    TaskUpdate,
    create_task_state_base,
    generate_task_id,
    is_terminal_task_status,
)

__all__ = [
    # Agent checkpoints
    "AgentCheckpoint",
    # Approval audit
    "ApprovalDecisionLog",
    # Change reviews (worktree review queue)
    "ChangeReview",
    # Agent memory
    "AgentEpisode",
    "AgentFact",
    "AgentProcedure",
    # Identity stubs
    "UserStub",
    "WorkspaceStub",
    # Cron
    "CronJobModel",
    "CronExecutionModel",
    "CronJobRead",
    # Workflow execution
    "WorkflowExecution",
    "WorkflowExecutionRead",
    "WorkflowStateSnapshot",
    # Base
    "BaseModel",
    "TimestampMixin",
    "UUIDMixin",
    "SoftDeleteMixin",
    "utc_now",
    # Flow
    "Flow",
    "FlowVersion",
    "FlowStatus",
    "FlowType",
    "FlowCreate",
    "FlowUpdate",
    "FlowRead",
    # Canvas
    "CanvasContentType",
    "CanvasDocument",
    # Document chunks (knowledge storage layer)
    "DocumentChunk",
    "DocumentChunkRead",
    # Message
    "Message",
    "ChatSession",
    "MessageRole",
    "MessageStatus",
    "MessageCreate",
    "MessageRead",
    "SessionCreate",
    "SessionRead",
    "LLMRequestLog",
    # Agent traces (debug/eval)
    "AgentTrace",
    "AgentTraceSpan",
    "AgentTraceExperiment",
    # Task
    "Task",
    "TaskContext",
    "TaskStatus",
    "TaskPriority",
    "TaskType",
    "TaskCreate",
    "TaskUpdate",
    "TaskRead",
    "is_terminal_task_status",
    "generate_task_id",
    "create_task_state_base",
    # File
    "File",
    "FileType",
    "FileStatus",
    "FileCreate",
    "FileUpdate",
    "FileRead",
    "LibraryScope",
    "InboxState",
    # Pet Space
    "PetProject",
    "PetProjectFile",
    # Chat Projects
    "ChatProject",
    # Folder
    "Folder",
    "FolderCreate",
    "FolderUpdate",
    "FolderProjectUpdate",
    "FolderRead",
    # Coding Project
    "CodingProject",
    "CodingProjectCreate",
    "CodingProjectRead",
    "CodingProjectRuntimeKind",
    "CodingProjectStatus",
    "CodingProjectUpdate",
]
