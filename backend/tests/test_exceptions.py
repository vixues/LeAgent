"""Tests for all exception classes and FastAPI exception handlers."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ===========================================================================
# Base Exceptions
# ===========================================================================


class TestBaseExceptions:
    def test_leagent_error_defaults(self) -> None:
        from leagent.exceptions.base import LeAgentError

        err = LeAgentError("something went wrong")
        assert str(err) == "something went wrong"
        assert err.message == "something went wrong"
        assert err.error_code == "LEAGENT_ERROR"
        assert err.status_code == 500

    def test_leagent_error_custom_code(self) -> None:
        from leagent.exceptions.base import LeAgentError

        err = LeAgentError("custom", error_code="MY_ERROR", status_code=418)
        assert err.error_code == "MY_ERROR"
        assert err.status_code == 418

    def test_leagent_error_to_dict(self) -> None:
        from leagent.exceptions.base import LeAgentError

        err = LeAgentError("msg", details={"key": "val"})
        d = err.to_dict()
        assert d["message"] == "msg"
        assert d["details"]["key"] == "val"

    def test_validation_error(self) -> None:
        from leagent.exceptions.base import ValidationError

        err = ValidationError("bad input")
        assert err.status_code == 422
        assert err.error_code == "VALIDATION_ERROR"

    def test_resource_not_found(self) -> None:
        from leagent.exceptions.base import ResourceNotFoundError

        err = ResourceNotFoundError("item not found")
        assert err.status_code == 404

    def test_resource_conflict(self) -> None:
        from leagent.exceptions.base import ResourceConflictError

        err = ResourceConflictError("already exists")
        assert err.status_code == 409

    def test_configuration_error(self) -> None:
        from leagent.exceptions.base import ConfigurationError

        err = ConfigurationError("missing setting")
        assert err.status_code == 500


# ===========================================================================
# Tool Exceptions
# ===========================================================================


class TestToolExceptions:
    def test_tool_execution_error(self) -> None:
        from leagent.exceptions.tool import ToolExecutionError

        err = ToolExecutionError("pdf_reader failed", tool_name="pdf_reader")
        assert err.tool_name == "pdf_reader"
        assert err.status_code == 500
        assert err.error_code == "TOOL_EXEC_FAILED"

    def test_tool_not_found(self) -> None:
        from leagent.exceptions.tool import ToolNotFoundError

        err = ToolNotFoundError("unknown_tool")
        assert err.tool_name == "unknown_tool"
        assert err.status_code == 404
        assert "unknown_tool" in str(err)

    def test_tool_validation_error(self) -> None:
        from leagent.exceptions.tool import ToolValidationError

        err = ToolValidationError("missing param", tool_name="pdf_reader")
        assert err.status_code == 422


# ===========================================================================
# Auth Exceptions
# ===========================================================================


class TestAuthExceptions:
    def test_authentication_error(self) -> None:
        from leagent.exceptions.auth import AuthenticationError

        err = AuthenticationError()
        assert err.status_code == 401
        assert err.error_code == "AUTHENTICATION_ERROR"

    def test_authorization_error(self) -> None:
        from leagent.exceptions.auth import AuthorizationError

        err = AuthorizationError()
        assert err.status_code == 403
        assert err.error_code == "AUTHORIZATION_ERROR"

    def test_insufficient_permissions(self) -> None:
        from leagent.exceptions.auth import InsufficientPermissionsError

        err = InsufficientPermissionsError("admin:write", user_role="viewer")
        assert "admin:write" in str(err)
        assert err.details["user_role"] == "viewer"

    def test_token_expired(self) -> None:
        from leagent.exceptions.auth import TokenExpiredError

        err = TokenExpiredError()
        assert err.status_code == 401
        assert err.error_code == "TOKEN_EXPIRED"


# ===========================================================================
# LLM Exceptions
# ===========================================================================


class TestLLMExceptions:
    def test_llm_service_error(self) -> None:
        from leagent.exceptions.llm import LLMServiceError

        err = LLMServiceError("LLM failed")
        assert err.status_code in (500, 502, 503)

    def test_llm_rate_limit(self) -> None:
        from leagent.exceptions.llm import LLMRateLimitError

        err = LLMRateLimitError()
        assert err.status_code == 429


# ===========================================================================
# Rule Exceptions
# ===========================================================================


class TestRuleExceptions:
    def test_rule_evaluation_error(self) -> None:
        from leagent.exceptions.rule import RuleEvaluationError

        err = RuleEvaluationError("evaluation failed")
        assert isinstance(err, Exception)

    def test_rule_set_not_found(self) -> None:
        from leagent.exceptions.rule import RuleSetNotFoundError

        err = RuleSetNotFoundError("test_rules")
        assert "test_rules" in str(err)


# ===========================================================================
# Workflow Exceptions
# ===========================================================================


class TestWorkflowExceptions:
    def test_workflow_error(self) -> None:
        from leagent.exceptions.workflow import WorkflowError

        err = WorkflowError("workflow failed")
        assert isinstance(err, Exception)


# ===========================================================================
# FastAPI Exception Handlers
# ===========================================================================


class TestExceptionHandlers:
    def _make_app(self) -> FastAPI:
        from leagent.exceptions.handlers import register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app)
        return app

    def test_tool_not_found_returns_404(self) -> None:
        from leagent.exceptions.tool import ToolNotFoundError

        app = self._make_app()

        @app.get("/fail")
        async def fail():
            raise ToolNotFoundError("missing_tool")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/fail")
        assert resp.status_code == 404

    def test_authentication_error_returns_401(self) -> None:
        from leagent.exceptions.auth import AuthenticationError

        app = self._make_app()

        @app.get("/auth")
        async def auth():
            raise AuthenticationError("bad credentials")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/auth")
        assert resp.status_code == 401

    def test_authorization_error_returns_403(self) -> None:
        from leagent.exceptions.auth import AuthorizationError

        app = self._make_app()

        @app.get("/forbid")
        async def forbid():
            raise AuthorizationError("access denied")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/forbid")
        assert resp.status_code == 403

    def test_leagent_error_response_body(self) -> None:
        from leagent.exceptions.base import LeAgentError

        app = self._make_app()

        @app.get("/err")
        async def err():
            raise LeAgentError("test error", error_code="TEST_ERR", status_code=500)

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/err")
        body = resp.json()
        assert "error_code" in body or "detail" in body

    def test_get_recovery_strategy_known(self) -> None:
        from leagent.exceptions.handlers import get_recovery_strategy

        strategy = get_recovery_strategy("TOOL_EXEC_FAILED")
        assert strategy["action"] == "replan"

    def test_get_recovery_strategy_unknown(self) -> None:
        from leagent.exceptions.handlers import get_recovery_strategy

        strategy = get_recovery_strategy("UNKNOWN_CODE")
        assert strategy["action"] == "fail"
