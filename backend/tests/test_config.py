"""Tests for the LeAgent configuration system.

Validates Settings structure, all nested sub-settings groups, and helper
properties (database URL, etc.) without relying on any external environment.
"""

from __future__ import annotations

import pytest

from leagent.config.settings import (
    AgentSettings,
    CanvasSettings,
    ContextSettings,
    DatabaseSettings,
    FilesSettings,
    LLMSettings,
    PromptSettings,
    SessionSettings,
    Settings,
    WorkflowEngineSettings,
    get_settings,
)


# ===========================================================================
# get_settings singleton
# ===========================================================================


class TestGetSettings:
    def test_returns_settings_instance(self) -> None:
        assert isinstance(get_settings(), Settings)

    def test_singleton(self) -> None:
        assert get_settings() is get_settings()


# ===========================================================================
# Top-level Settings fields
# ===========================================================================


class TestSettingsTopLevel:
    def test_app_name(self) -> None:
        s = get_settings()
        assert s.app_name == "LeAgent"

    def test_has_debug(self) -> None:
        s = get_settings()
        assert isinstance(s.debug, bool)

    def test_has_environment(self) -> None:
        s = get_settings()
        assert s.environment in ("development", "staging", "production")

    def test_has_log_level(self) -> None:
        s = get_settings()
        assert isinstance(s.log_level, str)
        assert s.log_level.upper() in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

    def test_has_version(self) -> None:
        s = get_settings()
        assert isinstance(s.version, str)
        assert len(s.version) > 0

    def test_has_host_and_port(self) -> None:
        s = get_settings()
        assert isinstance(s.host, str)
        assert isinstance(s.port, int)
        assert 1 <= s.port <= 65535

    def test_has_workers(self) -> None:
        assert isinstance(get_settings().workers, int)

    def test_rules_directory(self) -> None:
        assert isinstance(get_settings().rules_directory, str)

    def test_workflows_directory(self) -> None:
        assert isinstance(get_settings().workflows_directory, str)

    def test_health_check_path(self) -> None:
        assert get_settings().health_check_path == "/health"


# ===========================================================================
# Sub-settings groups
# ===========================================================================


class TestDatabaseSettings:
    def test_has_settings(self) -> None:
        assert isinstance(get_settings().database, DatabaseSettings)

    def test_url_property(self) -> None:
        db = get_settings().database
        url = db.url
        assert "://" in url
        if "sqlite" in db.driver.lower():
            assert "sqlite" in url.lower()
            assert "leagent.db" in url
        else:
            assert db.user in url
            assert db.name in url

    def test_sync_url_no_asyncpg(self) -> None:
        db = get_settings().database
        assert "asyncpg" not in db.sync_url

    def test_sync_url_sqlite(self) -> None:
        db = get_settings().database
        assert db.sync_url.startswith("sqlite:///")


class TestLLMSettings:
    def test_has_settings(self) -> None:
        assert isinstance(get_settings().llm, LLMSettings)

    def test_embedding_fields(self) -> None:
        llm = get_settings().llm
        assert isinstance(llm.embedding_endpoint, str)
        assert llm.embedding_model
        assert llm.embedding_dim > 0

    def test_local_only_is_bool(self) -> None:
        assert isinstance(get_settings().llm.local_only, bool)


class TestAgentSettings:
    def test_has_settings(self) -> None:
        assert isinstance(get_settings().agent, AgentSettings)

    def test_max_iterations_positive(self) -> None:
        assert get_settings().agent.max_iterations > 0

    def test_timeout_positive(self) -> None:
        assert get_settings().agent.default_timeout_sec > 0

    def test_context_window_positive(self) -> None:
        assert get_settings().agent.context_window_tokens > 0

    def test_max_output_tokens(self) -> None:
        assert get_settings().agent.max_output_tokens > 0


class TestFilesSettings:
    def test_has_settings(self) -> None:
        assert isinstance(get_settings().files, FilesSettings)

    def test_upload_dir_present(self) -> None:
        assert isinstance(get_settings().files.upload_dir, str)
        assert len(get_settings().files.upload_dir) > 0


class TestSessionSettings:
    def test_has_settings(self) -> None:
        assert isinstance(get_settings().session, SessionSettings)

    def test_lru_size_positive(self) -> None:
        assert get_settings().session.in_memory_lru_size > 0


class TestCanvasSettings:
    def test_has_settings(self) -> None:
        assert isinstance(get_settings().canvas, CanvasSettings)

    def test_preview_ttl_positive(self) -> None:
        assert get_settings().canvas.preview_token_ttl_seconds > 0


class TestPromptSettings:
    def test_has_settings(self) -> None:
        assert isinstance(get_settings().prompt, PromptSettings)

    def test_max_total_chars_positive(self) -> None:
        assert get_settings().prompt.max_total_chars > 0


class TestContextSettings:
    def test_has_settings(self) -> None:
        assert isinstance(get_settings().context, ContextSettings)

    def test_budget_positive(self) -> None:
        assert get_settings().context.budget_max_chars > 0


class TestWorkflowSettings:
    def test_has_settings(self) -> None:
        assert isinstance(get_settings().workflow, WorkflowEngineSettings)

    def test_memory_queue_backend(self) -> None:
        assert get_settings().workflow.queue_backend == "memory"
