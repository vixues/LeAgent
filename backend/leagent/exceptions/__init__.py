"""Exception hierarchy for LeAgent."""

from leagent.exceptions.auth import (
    AuthenticationError,
    AuthorizationError,
    InsufficientPermissionsError,
    InvalidTokenError,
    TokenExpiredError,
)
from leagent.exceptions.base import (
    ConfigurationError,
    ResourceConflictError,
    ResourceNotFoundError,
    ValidationError,
    LeAgentError,
)
from leagent.exceptions.llm import (
    LLMRateLimitError,
    LLMServiceError,
    LLMTimeoutError,
    ModelNotFoundError,
)
from leagent.exceptions.rule import (
    RuleError,
    RuleEvaluationError,
    RuleLoadError,
    RuleSetNotFoundError,
    RuleValidationError,
)
from leagent.exceptions.tool import (
    ToolExecutionError,
    ToolNotFoundError,
    ToolTimeoutError,
    ToolValidationError,
)
from leagent.exceptions.workflow import (
    WorkflowError,
    WorkflowNodeError,
    WorkflowTimeoutError,
    WorkflowValidationError,
)

__all__ = [
    "AuthenticationError",
    "AuthorizationError",
    "ConfigurationError",
    "InsufficientPermissionsError",
    "InvalidTokenError",
    "LLMRateLimitError",
    "LLMServiceError",
    "LLMTimeoutError",
    "ModelNotFoundError",
    "ResourceConflictError",
    "ResourceNotFoundError",
    "RuleError",
    "RuleEvaluationError",
    "RuleLoadError",
    "RuleSetNotFoundError",
    "RuleValidationError",
    "TokenExpiredError",
    "ToolExecutionError",
    "ToolNotFoundError",
    "ToolTimeoutError",
    "ToolValidationError",
    "ValidationError",
    "LeAgentError",
    "WorkflowError",
    "WorkflowNodeError",
    "WorkflowTimeoutError",
    "WorkflowValidationError",
]
