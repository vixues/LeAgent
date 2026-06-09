"""Global FastAPI exception handlers and recovery strategies."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from leagent.api.schemas.errors import build_error_payload
from leagent.exceptions.base import LeAgentError
from leagent.exceptions.llm import LLMRateLimitError, LLMServiceError
from leagent.exceptions.tool import ToolExecutionError
from leagent.exceptions.workflow import WorkflowError

logger = logging.getLogger(__name__)

RECOVERY_STRATEGIES: dict[str, dict[str, Any]] = {
    "TOOL_EXEC_FAILED": {
        "action": "replan",
        "description": "Tool failed after retries — escalate to planner for replanning",
    },
    "LLM_SERVICE_ERROR": {
        "action": "retry_with_fallback",
        "description": "Try fallback model tier",
    },
    "LLM_TIMEOUT": {
        "action": "retry_with_fallback",
        "description": "Retry with a smaller/faster model",
    },
    "LLM_RATE_LIMIT": {
        "action": "backoff_retry",
        "description": "Exponential backoff then retry",
    },
    "WORKFLOW_ERROR": {
        "action": "error_node",
        "description": "Execute the workflow error-handler node if defined",
    },
    "WORKFLOW_TIMEOUT": {
        "action": "fail_gracefully",
        "description": "Mark workflow as timed-out and notify user",
    },
    "AUTHENTICATION_ERROR": {
        "action": "reject",
        "description": "Return 401 immediately",
    },
    "AUTHORIZATION_ERROR": {
        "action": "reject",
        "description": "Return 403 immediately",
    },
}


def get_recovery_strategy(error_code: str) -> dict[str, Any]:
    """Look up the recommended recovery strategy for an error code."""
    return RECOVERY_STRATEGIES.get(error_code, {
        "action": "fail",
        "description": "No recovery strategy defined",
    })


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app."""

    @app.exception_handler(LeAgentError)
    async def leagent_error_handler(request: Request, exc: LeAgentError) -> JSONResponse:
        logger.error(
            "LeAgentError: %s [%s] %s",
            exc.error_code,
            exc.status_code,
            exc.message,
            extra={
                "error_code": exc.error_code,
                "details": exc.details,
                "path": str(request.url),
                "method": request.method,
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(
                error_code=exc.error_code,
                message=exc.message,
                details=exc.details,
                recovery=get_recovery_strategy(exc.error_code),
                request=request,
            ),
        )

    @app.exception_handler(ToolExecutionError)
    async def tool_error_handler(request: Request, exc: ToolExecutionError) -> JSONResponse:
        logger.error(
            "ToolExecutionError: tool=%s msg=%s",
            exc.tool_name,
            exc.message,
            extra={"details": exc.details, "path": str(request.url)},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(
                error_code=exc.error_code,
                message=exc.message,
                details=exc.details,
                recovery=get_recovery_strategy(exc.error_code),
                request=request,
            ),
        )

    @app.exception_handler(LLMServiceError)
    async def llm_error_handler(request: Request, exc: LLMServiceError) -> JSONResponse:
        headers = {}
        if isinstance(exc, LLMRateLimitError) and exc.retry_after:
            headers["Retry-After"] = str(int(exc.retry_after))
        logger.error(
            "LLMServiceError: model=%s msg=%s",
            exc.model,
            exc.message,
            extra={"details": exc.details, "path": str(request.url)},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(
                error_code=exc.error_code,
                message=exc.message,
                details=exc.details,
                recovery=get_recovery_strategy(exc.error_code),
                request=request,
            ),
            headers=headers,
        )

    @app.exception_handler(WorkflowError)
    async def workflow_error_handler(request: Request, exc: WorkflowError) -> JSONResponse:
        logger.error(
            "WorkflowError: workflow=%s msg=%s",
            exc.workflow_id,
            exc.message,
            extra={"details": exc.details, "path": str(request.url)},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(
                error_code=exc.error_code,
                message=exc.message,
                details=exc.details,
                recovery=get_recovery_strategy(exc.error_code),
                request=request,
            ),
        )

    from fastapi.exceptions import RequestValidationError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = exc.errors()
        logger.warning(
            "Request validation error: %d error(s) at %s",
            len(errors),
            str(request.url),
            extra={"errors": errors},
        )
        return JSONResponse(
            status_code=422,
            content=build_error_payload(
                error_code="VALIDATION_ERROR",
                message="Request validation failed",
                details={"errors": errors},
                request=request,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # ``HTTPException(detail=...)`` may carry a string or a structured dict.
        # Preserve dict details under ``details`` instead of stringifying them.
        detail = exc.detail
        if isinstance(detail, dict):
            message = str(detail.get("message") or detail.get("detail") or "Request failed")
            details = detail
        else:
            message = str(detail)
            details = {}
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_payload(
                error_code=f"HTTP_{exc.status_code}",
                message=message,
                details=details,
                request=request,
            ),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled exception: %s",
            str(exc),
            extra={"path": str(request.url), "method": request.method},
        )
        return JSONResponse(
            status_code=500,
            content=build_error_payload(
                error_code="INTERNAL_ERROR",
                message="An unexpected error occurred",
                request=request,
            ),
        )
