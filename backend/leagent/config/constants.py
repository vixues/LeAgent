"""Application-wide constants and enumerations."""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Directory layout
# ---------------------------------------------------------------------------

LEAGENT_HOME = Path(os.getenv("LEAGENT_HOME", Path.home() / ".leagent"))
WORKING_DIR = LEAGENT_HOME / "working"
SECRET_DIR = LEAGENT_HOME / "secrets"
CONFIG_PATH = LEAGENT_HOME / "config.yaml"
PROVIDERS_PATH = LEAGENT_HOME / "providers.yaml"
JOBS_PATH = LEAGENT_HOME / "jobs"

UPLOAD_DIR = WORKING_DIR / "uploads"
OUTPUT_DIR = WORKING_DIR / "outputs"
TEMP_DIR = WORKING_DIR / "tmp"
LOG_DIR = LEAGENT_HOME / "logs"
TEMPLATE_DIR = LEAGENT_HOME / "templates"
RULES_DIR = LEAGENT_HOME / "rules"
WORKFLOWS_DIR = LEAGENT_HOME / "workflows"
CACHE_DIR = WORKING_DIR / "cache"
# Subprocess ``code_execution`` sandboxes (per-session dirs under this root).
CODE_EXEC_ROOT = WORKING_DIR / "code-exec"
# Indexed knowledge / document blobs (default; override via ``FilesSettings.knowledge_storage_dir``).
KNOWLEDGE_DIR = LEAGENT_HOME / "knowledge"

ALL_DIRS = [
    LEAGENT_HOME,
    WORKING_DIR,
    SECRET_DIR,
    UPLOAD_DIR,
    OUTPUT_DIR,
    TEMP_DIR,
    LOG_DIR,
    TEMPLATE_DIR,
    RULES_DIR,
    WORKFLOWS_DIR,
    JOBS_PATH,
    CACHE_DIR,
    CODE_EXEC_ROOT,
    KNOWLEDGE_DIR,
]

# ---------------------------------------------------------------------------
# JWT / Auth
# ---------------------------------------------------------------------------

JWT_ALGORITHM = "HS256"
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 24 hours
JWT_REFRESH_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days
JWT_ISSUER = "leagent"

# ---------------------------------------------------------------------------
# Agent settings
# ---------------------------------------------------------------------------

AGENT_MAX_ITERATIONS = 15
AGENT_DEFAULT_TIMEOUT_SEC = 300
AGENT_MAX_TOOL_CALLS_PER_TURN = 10
AGENT_CONTEXT_WINDOW_TOKENS = 128_000
AGENT_MAX_OUTPUT_TOKENS = 4096
AGENT_BROWSER_POOL_SIZE = 5

# ---------------------------------------------------------------------------
# Model tier triggers (keywords → tier routing)
# ---------------------------------------------------------------------------

TIER1_TRIGGERS = [
    "plan", "analyze", "report", "compare", "evaluate",
    "reason", "generate report", "审核", "分析", "评估", "规划",
]
TIER2_TRIGGERS = [
    "classify", "extract", "summarize", "format", "translate",
    "tag", "分类", "提取", "摘要", "格式化", "翻译",
]

# ---------------------------------------------------------------------------
# Supported file types
# ---------------------------------------------------------------------------

SUPPORTED_DOCUMENT_TYPES = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv",
    ".ppt", ".pptx", ".txt", ".md", ".rtf",
}
SUPPORTED_IMAGE_TYPES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}
SUPPORTED_ARCHIVE_TYPES = {".zip", ".tar", ".gz", ".rar", ".7z"}
ALL_SUPPORTED_TYPES = SUPPORTED_DOCUMENT_TYPES | SUPPORTED_IMAGE_TYPES | SUPPORTED_ARCHIVE_TYPES

MAX_UPLOAD_SIZE_MB = 1024
MAX_UPLOAD_SIZE_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024

# ---------------------------------------------------------------------------
# RBAC roles
# ---------------------------------------------------------------------------

RBAC_ROLES = {
    "admin": {
        "description": "Full system access",
        "permissions": ["*"],
    },
    "manager": {
        "description": "Department-level management",
        "permissions": [
            "workflow:read", "workflow:execute",
            "task:read", "task:create", "task:cancel",
            "document:read", "document:upload",
            "rule:read",
            "user:read",
            "report:read", "report:create",
        ],
    },
    "operator": {
        "description": "Standard operational access",
        "permissions": [
            "workflow:read", "workflow:execute",
            "task:read", "task:create",
            "document:read", "document:upload",
            "rule:read",
            "report:read",
        ],
    },
    "viewer": {
        "description": "Read-only access",
        "permissions": [
            "workflow:read",
            "task:read",
            "document:read",
            "rule:read",
            "report:read",
        ],
    },
}

# ---------------------------------------------------------------------------
# Tool categories
# ---------------------------------------------------------------------------

TOOL_CATEGORIES = [
    "doc",          # Document parsing tools
    "web",          # Web scraping / RPA tools
    "data",         # Data processing tools
    "gen",          # Document generation tools
    "integration",  # OA / external system integration
    "util",         # Utility / helper tools
]

# ---------------------------------------------------------------------------
# Rule types
# ---------------------------------------------------------------------------

RULE_TYPES = [
    "compare",
    "date_range",
    "threshold",
    "contains_all",
    "date_diff",
    "regex",
    "in_set",
    "custom_expr",
    "llm_judge",
]

# ---------------------------------------------------------------------------
# Workflow node types
# ---------------------------------------------------------------------------

WORKFLOW_NODE_TYPES = [
    "start",
    "end",
    "tool_call",
    "llm_call",
    "condition",
    "parallel",
    "loop",
    "human_review",
    "sub_workflow",
    "wait_timer",
    "error_handler",
]

# ---------------------------------------------------------------------------
# Business modules
# ---------------------------------------------------------------------------

BUSINESS_MODULES = {
    "finance": {
        "code": "F",
        "name": "财务模块",
        "name_en": "Finance",
        "workflows": ["F-001", "F-002", "F-003", "F-004"],
    },
    "hr": {
        "code": "H",
        "name": "人力模块",
        "name_en": "Human Resources",
        "workflows": ["H-001", "H-002", "H-003", "H-004", "H-005", "H-006", "H-007", "H-008"],
    },
    "logistics": {
        "code": "L",
        "name": "后勤模块",
        "name_en": "Logistics",
        "workflows": ["L-001"],
    },
    "research": {
        "code": "R",
        "name": "科研模块",
        "name_en": "Research",
        "workflows": ["R-001", "R-002"],
    },
    "education": {
        "code": "E",
        "name": "教育模块",
        "name_en": "Education",
        "workflows": ["E-001", "E-002"],
    },
    "qianhai": {
        "code": "Q",
        "name": "前海模块",
        "name_en": "Qianhai Policy",
        "workflows": ["Q-001"],
    },
}

# ---------------------------------------------------------------------------
# Miscellaneous
# ---------------------------------------------------------------------------

DEFAULT_PAGINATION_LIMIT = 20
MAX_PAGINATION_LIMIT = 100
SSE_KEEPALIVE_INTERVAL = 15
WEBSOCKET_HEARTBEAT_INTERVAL = 30
