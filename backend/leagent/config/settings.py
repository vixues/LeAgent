"""Pydantic-based application settings with nested configuration groups.

Standalone single-node configuration — SQLite-only, no external services.
"""

from __future__ import annotations

import leagent.config.env_bootstrap  # noqa: F401 — load ~/.leagent/.env early

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field

from leagent.config.constants import MAX_UPLOAD_SIZE_BYTES
from pydantic_settings import BaseSettings, SettingsConfigDict

LogFormat = Literal["json", "console", "auto"]
RuntimeProfile = Literal["standard", "coding_long", "coding_extended"]

CANVAS_PREVIEW_CSP_LOCAL: str = (
    "default-src 'none'; "
    "base-uri 'none'; "
    "img-src https: http: data: blob:; "
    "media-src mediastream: blob: 'self'; "
    "font-src https: http: data:; "
    "style-src https: http: 'unsafe-inline'; "
    "script-src https: http: 'unsafe-inline' 'unsafe-eval'; "
    "connect-src https: http: wss: ws:; "
    "frame-src https: http:; "
    "worker-src blob:; "
    "child-src blob: https: http:;"
)


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DB_")

    driver: str = "sqlite+aiosqlite"
    sqlite_path: str = ""
    echo: bool = False
    database_url: str = ""
    pool_size: int = 5
    max_overflow: int = 10
    # When true, a failed Alembic migration at startup aborts boot instead of
    # logging a warning and continuing on a potentially stale schema. Recommended
    # for production/PostgreSQL; defaults off to preserve the zero-config SQLite
    # dev experience.
    fail_fast_migrations: bool = False

    @property
    def is_postgresql(self) -> bool:
        return bool(self.database_url and "postgresql" in self.database_url)

    def _sqlite_file_path(self) -> str:
        from leagent.config.constants import LEAGENT_HOME

        raw = (self.sqlite_path or "").strip()
        if raw:
            return str(Path(raw).expanduser().resolve())
        return str((LEAGENT_HOME / "leagent.db").resolve())

    def _resolved_sqlite_path(self) -> Path:
        """Absolute SQLite file path with parent dirs created."""
        p = Path(self._sqlite_file_path())
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def url(self) -> str:
        if self.database_url:
            return self.database_url
        path = self._resolved_sqlite_path().as_posix()
        return f"{self.driver}:///{path}"

    @property
    def sync_url(self) -> str:
        if self.database_url:
            return self.database_url.replace("+asyncpg", "").replace("+aiopg", "")
        path = self._resolved_sqlite_path().as_posix()
        return f"sqlite:///{path}"


class LLMSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LLM_")

    embedding_endpoint: str = ""
    embedding_model: str = "bge-large-zh-v1.5"
    embedding_dim: int = 1024

    openai_api_key: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    dashscope_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_DASHSCOPE_API_KEY", "DASHSCOPE_API_KEY"),
    )
    dashscope_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        validation_alias=AliasChoices("LLM_DASHSCOPE_BASE_URL", "DASHSCOPE_BASE_URL"),
    )
    dashscope_enable_thinking: bool | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LLM_DASHSCOPE_ENABLE_THINKING",
            "DASHSCOPE_ENABLE_THINKING",
        ),
    )
    dashscope_enable_search: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "LLM_DASHSCOPE_ENABLE_SEARCH",
            "DASHSCOPE_ENABLE_SEARCH",
        ),
    )

    deepseek_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY"),
    )
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        validation_alias=AliasChoices("LLM_DEEPSEEK_BASE_URL", "DEEPSEEK_BASE_URL"),
    )
    deepseek_thinking_type: Literal["enabled", "disabled"] | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LLM_DEEPSEEK_THINKING_TYPE",
            "DEEPSEEK_THINKING_TYPE",
        ),
    )
    deepseek_reasoning_effort: Literal["high", "max"] | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "LLM_DEEPSEEK_REASONING_EFFORT",
            "DEEPSEEK_REASONING_EFFORT",
        ),
    )

    ollama_endpoint: str = ""
    ollama_model: str = "llama3.2"

    vllm_endpoint: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_VLLM_ENDPOINT", "VLLM_ENDPOINT"),
    )
    vllm_model: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_VLLM_MODEL", "VLLM_MODEL"),
    )
    vllm_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("LLM_VLLM_API_KEY", "VLLM_API_KEY"),
    )
    vllm_timeout: int = Field(
        default=120,
        validation_alias=AliasChoices("LLM_VLLM_TIMEOUT", "VLLM_TIMEOUT"),
    )
    vllm_enable_auto_tool_choice: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "LLM_VLLM_ENABLE_AUTO_TOOL_CHOICE",
            "VLLM_ENABLE_AUTO_TOOL_CHOICE",
        ),
    )

    local_only: bool = False


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENT_")

    runtime_profile: RuntimeProfile = "standard"
    max_iterations: int = 15
    default_timeout_sec: int = 300
    max_tool_calls_per_turn: int = 10
    browser_pool_size: int = 5
    celery_concurrency: int = 4
    context_window_tokens: int = 128_000
    max_output_tokens: int = 8192

    conversation_timeout_sec: int = 600
    max_executions_per_session: int = 5
    stream_drain_timeout_sec: int = 300
    stream_queue_maxsize: int = 512
    long_task_timeout_sec: int = 3600
    long_stream_drain_timeout_sec: int = 3600
    long_max_turns: int = 60
    long_max_tool_calls_per_turn: int = 20
    long_tool_timeout_sec: int = 1800
    long_max_concurrency_per_user: int = 1
    long_max_concurrency_per_workspace: int = 3
    extended_task_timeout_sec: int = 7200
    extended_stream_drain_timeout_sec: int = 7200
    extended_max_turns: int = 120
    extended_max_tool_calls_per_turn: int = 30
    extended_tool_timeout_sec: int = 3600
    extended_max_concurrency_per_user: int = 1
    extended_max_concurrency_per_workspace: int = 2


def _default_upload_dir() -> str:
    from leagent.config.constants import UPLOAD_DIR

    return str(UPLOAD_DIR)


class FilesSettings(BaseSettings):
    """Uploaded file storage for chat session attachments."""

    model_config = SettingsConfigDict(env_prefix="FILES_")

    upload_dir: str = Field(default_factory=_default_upload_dir)
    tool_argument_blob_persist: bool = Field(
        default=False,
        description=(
            "When true, finalized tool_argument_blob payloads are written under "
            "upload_dir/tool-argument-blobs/ and survive process restarts until consumed."
        ),
    )
    knowledge_storage_dir: str = Field(
        default="",
        validation_alias=AliasChoices("LEAGENT_KNOWLEDGE_DIR", "FILES_KNOWLEDGE_STORAGE_DIR"),
    )
    max_upload_bytes: int = Field(default=MAX_UPLOAD_SIZE_BYTES)
    preview_ttl_seconds: int = 15 * 60
    signed_url_secret: str = ""
    projects_allowed_roots: str = ""

    def resolved_knowledge_storage_dir(self) -> str:
        from leagent.config.constants import KNOWLEDGE_DIR

        raw = (self.knowledge_storage_dir or "").strip()
        if raw:
            return str(Path(raw).expanduser().resolve(strict=False))
        return str(KNOWLEDGE_DIR.resolve(strict=False))


class CanvasSettings(BaseSettings):
    """Agent canvas preview settings (local-mode defaults)."""

    model_config = SettingsConfigDict(env_prefix="CANVAS_")

    preview_public_base: str = ""
    preview_signing_secret: str = ""
    preview_token_ttl_seconds: int = 60 * 45
    max_html_bytes: int = 4 * 1024 * 1024
    max_ui_snapshot_bytes: int = 512 * 1024
    max_tree_depth: int = 96
    max_nodes_per_tree: int = 2000
    google_maps_api_key: str = ""
    preview_csp: str = CANVAS_PREVIEW_CSP_LOCAL
    embed_allow_loopback: bool = True


class ImageSearchSettings(BaseSettings):
    """Web image search (e.g. Google Custom Search API image mode)."""

    model_config = SettingsConfigDict(env_prefix="IMAGE_SEARCH_")

    provider: Literal["google_cse"] = "google_cse"
    api_key: str = ""
    cx: str = ""
    endpoint: str = "https://www.googleapis.com/customsearch/v1"
    max_results_default: int = 8


class WebBrowserSettings(BaseSettings):
    """Playwright defaults for web automation tools (locale / timezone / UA)."""

    model_config = SettingsConfigDict(env_prefix="WEB_BROWSER_")

    headless: bool = True
    locale: str = "en-US"
    timezone: str = "America/New_York"
    user_agent: str = ""
    ignore_https_errors: bool = False


class WebSearchSettings(BaseSettings):
    """General web search (HTTP APIs + lite HTML; respects HTTP(S)_PROXY via trust_env)."""

    model_config = SettingsConfigDict(env_prefix="WEB_SEARCH_")

    provider: Literal[
        "auto",
        "bing_playwright",
        "duckduckgo_lite",
        "searxng",
        "bing",
        "brave",
        "tavily",
        "exa",
        "firecrawl",
        "serper",
    ] = "tavily"
    searxng_base_url: str = ""
    bing_api_key: str = ""
    bing_endpoint: str = "https://api.bing.microsoft.com/v7.0/search"
    brave_api_key: str = ""
    tavily_api_key: str = ""
    exa_api_key: str = ""
    firecrawl_api_key: str = ""
    firecrawl_api_url: str = ""
    serper_api_key: str = ""
    user_agent: str = "LeAgent/1.0 web_search (+https://github.com)"
    timeout_sec: float = 25.0
    max_results_default: int = 8
    cache_ttl_minutes: float = 15.0
    allowlist_config_path: str = ""


class WebFetchSettings(BaseSettings):
    """Polite outbound HTTP defaults for single-machine installs (spacing, retries, robots).

    Designed to reduce accidental rate-limit / soft-block triggers—not to defeat protections.
    Also drives the lightweight ``web_fetch`` tool (cache + size-gated summarization).
    """

    model_config = SettingsConfigDict(env_prefix="WEB_FETCH_")

    enabled: bool = True
    min_interval_ms: float = 750.0
    jitter_ms_max: float = 400.0
    max_retries: int = 2
    retry_backoff_base_ms: float = 650.0
    check_robots_txt: bool = True
    pre_navigation_delay_ms: float = 350.0
    robots_cache_ttl_sec: float = 3600.0
    user_agent: str = ""
    cache_ttl_minutes: float = 15.0
    max_content_chars: int = 200_000
    summarize_threshold_chars: int = 5_000
    summarize_output_chars: int = 5_000
    refuse_over_chars: int = 2_000_000
    timeout_sec: float = 30.0


class RtspStreamSettings(BaseSettings):
    """RTSP -> browser preview via server-side ffmpeg (MJPEG over HTTP)."""

    model_config = SettingsConfigDict(env_prefix="RTSP_STREAM_")

    enabled: bool = False
    ffmpeg_path: str = "ffmpeg"
    token_ttl_seconds: int = 15 * 60
    max_url_chars: int = 2048
    scale_max_width: int = 1280
    jpeg_quality: int = 7


class CodingProjectsSettings(BaseSettings):
    """Configuration for the coding-project live-preview service."""

    model_config = SettingsConfigDict(env_prefix="CODING_PROJECTS_")

    enabled: bool = True
    root: str = ""
    bind_host: str = "127.0.0.1"
    port_range_min: int = 39000
    port_range_max: int = 39999
    max_concurrent_per_user: int = 3
    idle_ttl_sec: int = 1800
    npm_install_timeout_sec: int = 600
    dev_server_startup_timeout_sec: int = 120
    log_buffer_lines: int = 4000
    allowed_binaries: str = "node,npm,pnpm,yarn,python,python3,uvicorn"
    preview_token_ttl_seconds: int = 60 * 30
    use_docker: bool = False


class SessionSettings(BaseSettings):
    """Configuration for SessionManager + session store."""

    model_config = SettingsConfigDict(env_prefix="SESSION_")

    in_memory_lru_size: int = 256
    max_messages_per_session: int = 2000
    autocompact_token_threshold: int = 96_000
    autocompact_keep_recent: int = 20
    inactive_session_ttl_days: int = 90
    workspace_file_ttl_hours: int = 168
    object_store_ttl_days: int = 30


class PromptSettings(BaseSettings):
    """Configuration for the leagent.prompts package."""

    model_config = SettingsConfigDict(env_prefix="LEAGENT_PROMPT_")

    templates_dir: str = ""
    hot_reload: bool = False
    max_total_chars: int = 24_000
    per_layer_budget_chars: dict[str, int] = Field(default_factory=dict)
    enable_cache_boundaries: bool = True


class ContextSettings(BaseSettings):
    """Configuration for the context management system."""

    model_config = SettingsConfigDict(env_prefix="LEAGENT_CONTEXT_")

    project_memory_denylist: list[str] = Field(
        default_factory=lambda: ["**/leagent/AGENTS.md", "**/backend/AGENTS.md"],
    )
    project_memory_allowlist: list[str] = Field(default_factory=list)
    respect_git_boundary: bool = True

    file_state_max_entries: int = 64
    file_state_max_tokens: int = 16_000

    working_set_excerpt_head_lines: int = 20
    working_set_excerpt_tail_lines: int = 10

    recall_attachment_limit: int = 5
    tool_history_attachment_limit: int = 5
    recent_reads_attachment_limit: int = 5

    budget_max_chars: int = 24_000
    freshness_half_life_seconds: float = 300.0


class WorkflowEngineSettings(BaseSettings):
    """Settings for the workflow engine (in-memory queue only)."""

    model_config = SettingsConfigDict(env_prefix="LEAGENT_WORKFLOW_")

    queue_backend: Literal["memory"] = "memory"
    cache_mode: Literal["lru", "ram", "none"] = "lru"
    cache_lru_size: int = 128
    cache_ram_mb: int = 256
    worker_concurrency: int = 1
    custom_nodes_dir: str = ""
    hot_reload: bool = False
    event_bus_prefix: str = "workflow:events"


class TraceSettings(BaseSettings):
    """Durable agent running-trace (debug/eval) plane.

    Separate from ``CheckpointStore`` (resume) and chat transcript SSOT.
    Env prefix: ``LEAGENT_TRACE_*``.
    """

    model_config = SettingsConfigDict(env_prefix="LEAGENT_TRACE_")

    enabled: bool = True
    capture_payloads: bool = False
    preview_chars: int = Field(default=4096, ge=256, le=64_000)
    retention_days: int = Field(default=30, ge=1, le=3650)


class SecuritySettings(BaseSettings):
    """HTTP security hardening knobs.

    ``enforce_auth`` is tri-state: ``None`` (auto — enforce on non-loopback
    binds), ``True`` (always), ``False`` (never). Rate limiting auto-enables
    when auth is effectively enforced unless explicitly disabled with
    ``rate_limit_auto_with_auth=false``.
    """

    model_config = SettingsConfigDict(env_prefix="LEAGENT_SECURITY_")

    #: Comma-separated list of allowed CORS origins. ``*`` allows any origin
    #: (credentials are then automatically disabled per the CORS spec).
    cors_allow_origins: str = "*"
    cors_allow_credentials: bool = True
    #: Comma-separated allowed Host header values for ``TrustedHostMiddleware``.
    #: ``*`` disables host checking.
    trusted_hosts: str = "*"
    security_headers_enabled: bool = True
    #: Send HSTS (only meaningful behind HTTPS). Off by default for local http.
    hsts_enabled: bool = False
    rate_limit_enabled: bool | None = None
    rate_limit_auto_with_auth: bool = True
    rate_limit_per_minute: int = Field(default=300, ge=1)
    rate_limit_burst: int = Field(default=60, ge=1)
    #: ``None`` = auto (enforce when bind host is not loopback / not desktop).
    enforce_auth: bool | None = None
    #: Gate ``/api/v1/meta`` and ``/api/v1/metrics`` behind auth when enforced.
    gate_diagnostics: bool = True
    #: Allow OpenAPI docs only when authenticated (when auth enforced + debug).
    gate_openapi: bool = True
    #: Hard cap on streamed request bodies (defends against header-less / chunked
    #: uploads that bypass a ``Content-Length`` check). 0 disables the streaming cap.
    max_streaming_body_bytes: int = Field(default=0, ge=0)
    #: Soft per-user concurrent agent/sandbox quota (0 = unlimited beyond global).
    max_concurrent_per_user: int = Field(default=5, ge=0)

    def cors_origins_list(self) -> list[str]:
        raw = (self.cors_allow_origins or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [o.strip() for o in raw.split(",") if o.strip()]

    def trusted_hosts_list(self) -> list[str]:
        raw = (self.trusted_hosts or "").strip()
        if not raw or raw == "*":
            return ["*"]
        return [h.strip() for h in raw.split(",") if h.strip()]


class Settings(BaseSettings):
    """Root settings for standalone single-node deployment."""

    model_config = SettingsConfigDict(
        env_prefix="LEAGENT_",
        env_nested_delimiter="__",
        case_sensitive=False,
    )

    app_name: str = "LeAgent"
    version: str = "1.2.0"
    environment: Literal["development", "staging", "production"] = "development"
    debug: bool = True
    log_level: str = "INFO"
    log_format: LogFormat = "auto"
    log_file: str = ""
    host: str = "0.0.0.0"
    port: int = 7860
    workers: int = 1
    #: HMAC signing secret for session JWTs / signed URLs (also ``LEAGENT_SECRET_KEY``).
    secret_key: str = Field(
        default="",
        validation_alias=AliasChoices("LEAGENT_SECRET_KEY", "SECRET_KEY"),
    )

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    llm: LLMSettings = Field(default_factory=LLMSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    files: FilesSettings = Field(default_factory=FilesSettings)
    session: SessionSettings = Field(default_factory=SessionSettings)
    canvas: CanvasSettings = Field(default_factory=CanvasSettings)
    image_search: ImageSearchSettings = Field(default_factory=ImageSearchSettings)
    web_browser: WebBrowserSettings = Field(default_factory=WebBrowserSettings)
    web_search: WebSearchSettings = Field(default_factory=WebSearchSettings)
    web_fetch: WebFetchSettings = Field(default_factory=WebFetchSettings)
    rtsp_stream: RtspStreamSettings = Field(default_factory=RtspStreamSettings)
    coding_projects: CodingProjectsSettings = Field(default_factory=CodingProjectsSettings)
    prompt: PromptSettings = Field(default_factory=PromptSettings)
    context: "ContextSettings" = Field(default_factory=ContextSettings)
    workflow: WorkflowEngineSettings = Field(default_factory=WorkflowEngineSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    trace: TraceSettings = Field(default_factory=TraceSettings)

    rules_directory: str = ""
    workflows_directory: str = ""
    rules_hot_reload: bool = True
    workflows_hot_reload: bool = True

    @property
    def workflow_queue_backend(self) -> str:
        return self.workflow.queue_backend

    @property
    def workflow_cache_mode(self) -> str:
        return self.workflow.cache_mode

    @property
    def workflow_worker_concurrency(self) -> int:
        return self.workflow.worker_concurrency

    @property
    def workflow_custom_nodes_dir(self) -> str | None:
        return self.workflow.custom_nodes_dir or None

    health_check_path: str = "/health"
    api_v1_deprecation_date: str = ""
    api_v1_sunset_date: str = ""
    api_deprecation_policy_url: str = "/docs#api-versioning"

    build_git_sha: str = Field(default="", validation_alias=AliasChoices("LEAGENT_BUILD_SHA"))
    build_time: str = Field(default="", validation_alias=AliasChoices("LEAGENT_BUILD_TIME"))

    data_root: str = Field(default="", validation_alias=AliasChoices("LEAGENT_DATA_ROOT"))
    skills_directory: str = Field(default="", validation_alias=AliasChoices("LEAGENT_SKILLS_DIR"))
    skills_github_catalog_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("LEAGENT_SKILLS_GITHUB_CATALOG_ENABLED"),
    )
    skills_github_owner: str = Field(
        default="anthropics",
        validation_alias=AliasChoices("LEAGENT_SKILLS_GITHUB_OWNER"),
    )
    skills_github_repo: str = Field(
        default="skills",
        validation_alias=AliasChoices("LEAGENT_SKILLS_GITHUB_REPO"),
    )
    skills_github_ref: str = Field(
        default="main",
        validation_alias=AliasChoices("LEAGENT_SKILLS_GITHUB_REF"),
    )
    skills_github_skills_path: str = Field(
        default="skills",
        validation_alias=AliasChoices("LEAGENT_SKILLS_GITHUB_SKILLS_PATH"),
    )
    skill_scripts_enabled: bool = Field(
        default=True,
        description=(
            "Allow run_skill_script for bundles under skills/*/scripts/. "
            "Set LEAGENT_SKILL_SCRIPTS_ENABLED=0 to disable."
        ),
    )
    skill_load_bundle_default: bool = Field(
        default=False,
        description=(
            "When true, load_skill inlines bundled references + script sources unless "
            "the caller passes include_bundled_content explicitly. "
            "Env: LEAGENT_SKILL_LOAD_BUNDLE_DEFAULT."
        ),
    )
    skill_python_deps_auto_install: bool = Field(
        default=True,
        description=(
            "When true, run_skill_script (and code_execution with skill_name) may run "
            "`uv pip install` for skill-declared deps (requirements.txt, pyproject "
            "dependencies, metadata.leagent.python_dependencies). "
            "Disable on locked-down hosts via LEAGENT_SKILL_PYTHON_DEPS_AUTO_INSTALL=0."
        ),
        validation_alias=AliasChoices("LEAGENT_SKILL_PYTHON_DEPS_AUTO_INSTALL"),
    )
    skill_python_deps_install_timeout_sec: float = Field(
        default=300.0,
        ge=5.0,
        le=3600.0,
        description=(
            "Wall-clock timeout for each uv pip install syncing a skill's Python deps."
        ),
        validation_alias=AliasChoices("LEAGENT_SKILL_PYTHON_DEPS_INSTALL_TIMEOUT_SEC"),
    )
    agent_uv_pip_install_enabled: bool = Field(
        default=True,
        description=(
            "When true, the uv_pip_install tool may run `uv pip install` into the "
            "same Python interpreter as code_execution (typically the backend venv). "
            "Disable on locked-down hosts via LEAGENT_AGENT_UV_PIP_INSTALL_ENABLED=0."
        ),
        validation_alias=AliasChoices("LEAGENT_AGENT_UV_PIP_INSTALL_ENABLED"),
    )
    backend_python_executable: str = Field(
        default="",
        description=(
            "Optional absolute Python executable for backend-managed code execution "
            "and dependency installs. When empty, LeAgent resolves "
            "UV_PROJECT_ENVIRONMENT, then backend/.venv, then sys.executable."
        ),
        validation_alias=AliasChoices("LEAGENT_BACKEND_PYTHON"),
    )
    skills_activate_all_on_start: bool = Field(
        default=True,
        description=(
            "After load_all(), activate every discovered skill so they are advertised "
            "in prompts and slash/mention UIs. "
            "Set LEAGENT_SKILLS_ACTIVATE_ALL_ON_START=0 to keep skills inactive until "
            "enabled in the skills UI or via API."
        ),
        validation_alias=AliasChoices("LEAGENT_SKILLS_ACTIVATE_ALL_ON_START"),
    )
    code_execution_workspace_root: str = Field(
        default="",
        validation_alias=AliasChoices("LEAGENT_CODE_EXEC_ROOT"),
    )
    code_execution_extra_import_roots: str = Field(
        default="",
        validation_alias=AliasChoices("LEAGENT_CODE_EXEC_EXTRA_IMPORT_ROOTS"),
    )
    code_execution_import_tier: str = Field(
        default="unrestricted",
        validation_alias=AliasChoices("LEAGENT_CODE_EXEC_IMPORT_TIER"),
    )
    code_execution_isolation_mode: str = Field(
        default="none",
        validation_alias=AliasChoices("LEAGENT_CODE_EXEC_ISOLATION"),
    )
    code_execution_permissive: bool = Field(
        default=True,
        validation_alias=AliasChoices("LEAGENT_CODE_EXEC_PERMISSIVE"),
    )
    code_execution_long_default_timeout_sec: float = Field(
        default=300.0,
        validation_alias=AliasChoices("LEAGENT_CODE_EXEC_LONG_DEFAULT_TIMEOUT_SEC"),
    )
    code_execution_long_max_timeout_sec: float = Field(
        default=1800.0,
        validation_alias=AliasChoices("LEAGENT_CODE_EXEC_LONG_MAX_TIMEOUT_SEC"),
    )
    code_execution_extended_default_timeout_sec: float = Field(
        default=600.0,
        validation_alias=AliasChoices("LEAGENT_CODE_EXEC_EXTENDED_DEFAULT_TIMEOUT_SEC"),
    )
    code_execution_extended_max_timeout_sec: float = Field(
        default=3600.0,
        validation_alias=AliasChoices("LEAGENT_CODE_EXEC_EXTENDED_MAX_TIMEOUT_SEC"),
    )

    # Outbound SMTP defaults for email_send / Settings UI (~/.leagent/.env via /settings/tokens).
    smtp_host: str = Field(default="", validation_alias=AliasChoices("LEAGENT_SMTP_HOST"))
    smtp_port: int = Field(default=587, validation_alias=AliasChoices("LEAGENT_SMTP_PORT"))
    smtp_username: str = Field(default="", validation_alias=AliasChoices("LEAGENT_SMTP_USERNAME"))
    smtp_password: str = Field(default="", validation_alias=AliasChoices("LEAGENT_SMTP_PASSWORD"))
    smtp_use_tls: bool = Field(default=True, validation_alias=AliasChoices("LEAGENT_SMTP_USE_TLS"))
    smtp_use_ssl: bool = Field(default=False, validation_alias=AliasChoices("LEAGENT_SMTP_USE_SSL"))
    smtp_from_email: str = Field(default="", validation_alias=AliasChoices("LEAGENT_SMTP_FROM_EMAIL"))
    smtp_from_name: str = Field(default="", validation_alias=AliasChoices("LEAGENT_SMTP_FROM_NAME"))

    coding_agent_free_shell: bool = True

    edition: str = Field(
        default="standalone",
        validation_alias=AliasChoices("LEAGENT_EDITION"),
    )
    desktop_mode: bool = Field(
        default=False,
        validation_alias=AliasChoices("LEAGENT_DESKTOP_MODE"),
    )
    local_mode: bool = Field(
        default=True,
        validation_alias=AliasChoices("LEAGENT_LOCAL_MODE"),
    )
    license_offline_registry_path: str = Field(
        default="",
        validation_alias=AliasChoices("LEAGENT_LICENSE_OFFLINE_REGISTRY_PATH"),
    )

    @property
    def is_single_machine_profile(self) -> bool:
        """Always True — this is a standalone local deployment."""
        return True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton of application settings."""
    return Settings()
