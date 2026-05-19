"""Rule management API endpoints."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from leagent.exceptions.rule import RuleSetNotFoundError
from leagent.rules.base import RuleDefinition, RuleSet, RuleSetResult, Severity
from leagent.rules.engine import RuleEngine
from leagent.services.auth import CurrentUserId

router = APIRouter()

_rule_engine: RuleEngine | None = None
_loaded: bool = False


def _rules_load_path() -> Path:
    from leagent.config.constants import RULES_DIR
    from leagent.config.settings import get_settings

    raw = (get_settings().rules_directory or "").strip()
    return Path(raw).expanduser().resolve() if raw else RULES_DIR


def get_rule_engine() -> RuleEngine:
    """Get the global rule engine instance, auto-loading ``rules_directory`` on first access."""
    global _rule_engine, _loaded
    if _rule_engine is None:
        _rule_engine = RuleEngine()

    if not _loaded:
        _loaded = True
        try:
            rules_path = _rules_load_path()
            if rules_path.exists():
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(_rule_engine.safe_load_directory(rules_path))
                else:
                    loop.run_until_complete(_rule_engine.safe_load_directory(rules_path))
        except Exception:
            pass

    return _rule_engine


class RuleSetInfo(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    enabled: bool
    rule_count: int
    tags: list[str] = Field(default_factory=list)


class RuleSetDetail(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    enabled: bool
    version: str
    rules: list[dict[str, Any]]
    tags: list[str] = Field(default_factory=list)


class RuleSetCreateRequest(BaseModel):
    id: str = Field(..., min_length=1, max_length=100)
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    enabled: bool = Field(default=True)
    rules: list[dict[str, Any]] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class RuleSetUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    enabled: Optional[bool] = None
    rules: Optional[list[dict[str, Any]]] = None
    tags: Optional[list[str]] = None


class RuleEvaluateRequest(BaseModel):
    data: dict[str, Any]
    tags: Optional[list[str]] = None
    skip_disabled: bool = Field(default=True)
    fail_fast: bool = Field(default=False)


class RuleEvaluateResponse(BaseModel):
    rule_set_id: str
    passed: bool
    total_rules: int
    error_count: int
    warning_count: int
    info_count: int
    execution_time_ms: float
    results: list[dict[str, Any]]


def _parse_rule_definitions(raw_rules: list[dict[str, Any]]) -> list[RuleDefinition]:
    """Parse raw dicts into validated RuleDefinition objects."""
    parsed: list[RuleDefinition] = []
    for rule_data in raw_rules:
        parsed.append(RuleDefinition.model_validate(rule_data))
    return parsed


@router.get("", response_model=list[RuleSetInfo])
async def list_rule_sets(
    user_id: CurrentUserId,
    engine: Annotated[RuleEngine, Depends(get_rule_engine)],
    enabled: Optional[bool] = Query(default=None),
) -> list[RuleSetInfo]:
    """List all registered rule sets."""
    rule_set_ids = engine.list_rule_sets()
    result = []
    for rs_id in rule_set_ids:
        rule_set = engine.get_rule_set(rs_id)
        if rule_set:
            if enabled is not None and rule_set.enabled != enabled:
                continue
            result.append(
                RuleSetInfo(
                    id=rule_set.id,
                    name=rule_set.name,
                    description=rule_set.description,
                    enabled=rule_set.enabled,
                    rule_count=len(rule_set.rules),
                    tags=rule_set.tags,
                )
            )
    return result


@router.post("", response_model=RuleSetInfo, status_code=status.HTTP_201_CREATED)
async def create_rule_set(
    data: RuleSetCreateRequest,
    user_id: CurrentUserId,
    engine: Annotated[RuleEngine, Depends(get_rule_engine)],
) -> RuleSetInfo:
    """Create a new rule set programmatically."""
    existing = engine.get_rule_set(data.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Rule set with ID '{data.id}' already exists",
        )

    rules: list[RuleDefinition] = []
    if data.rules:
        try:
            rules = _parse_rule_definitions(data.rules)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid rule definitions: {exc}",
            )

    rule_set = RuleSet(
        id=data.id,
        name=data.name,
        description=data.description,
        enabled=data.enabled,
        rules=rules,
        tags=data.tags,
    )
    engine.register_rule_set(rule_set)

    return RuleSetInfo(
        id=rule_set.id,
        name=rule_set.name,
        description=rule_set.description,
        enabled=rule_set.enabled,
        rule_count=len(rule_set.rules),
        tags=rule_set.tags,
    )


@router.get("/{rule_set_id}", response_model=RuleSetDetail)
async def get_rule_set(
    rule_set_id: str,
    user_id: CurrentUserId,
    engine: Annotated[RuleEngine, Depends(get_rule_engine)],
) -> RuleSetDetail:
    """Get detailed information about a rule set."""
    rule_set = engine.get_rule_set(rule_set_id)
    if not rule_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule set '{rule_set_id}' not found",
        )
    return RuleSetDetail(
        id=rule_set.id,
        name=rule_set.name,
        description=rule_set.description,
        enabled=rule_set.enabled,
        version=rule_set.version,
        rules=[
            {
                "id": r.id,
                "name": r.name,
                "description": r.description,
                "enabled": r.enabled,
                "severity": r.severity.value,
                "condition_type": r.condition.type.value,
                "message": r.message,
                "tags": r.tags,
            }
            for r in rule_set.rules
        ],
        tags=rule_set.tags,
    )


@router.put("/{rule_set_id}", response_model=RuleSetInfo)
async def update_rule_set(
    rule_set_id: str,
    data: RuleSetUpdateRequest,
    user_id: CurrentUserId,
    engine: Annotated[RuleEngine, Depends(get_rule_engine)],
) -> RuleSetInfo:
    """Update a rule set."""
    rule_set = engine.get_rule_set(rule_set_id)
    if not rule_set:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule set '{rule_set_id}' not found",
        )

    if data.name is not None:
        rule_set.name = data.name
    if data.description is not None:
        rule_set.description = data.description
    if data.enabled is not None:
        rule_set.enabled = data.enabled
    if data.tags is not None:
        rule_set.tags = data.tags
    if data.rules is not None:
        try:
            rule_set.rules = _parse_rule_definitions(data.rules)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid rule definitions: {exc}",
            )

    return RuleSetInfo(
        id=rule_set.id,
        name=rule_set.name,
        description=rule_set.description,
        enabled=rule_set.enabled,
        rule_count=len(rule_set.rules),
        tags=rule_set.tags,
    )


@router.post("/{rule_set_id}/evaluate", response_model=RuleEvaluateResponse)
async def evaluate_rules(
    rule_set_id: str,
    data: RuleEvaluateRequest,
    user_id: CurrentUserId,
    engine: Annotated[RuleEngine, Depends(get_rule_engine)],
) -> RuleEvaluateResponse:
    """Evaluate a rule set against provided data."""
    try:
        result = await engine.evaluate(
            rule_set_id=rule_set_id,
            data=data.data,
            tags=data.tags,
            skip_disabled=data.skip_disabled,
            fail_fast=data.fail_fast,
        )
    except RuleSetNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Rule set '{rule_set_id}' not found",
        )

    return RuleEvaluateResponse(
        rule_set_id=result.rule_set_id,
        passed=result.passed,
        total_rules=result.total_rules,
        error_count=result.error_count,
        warning_count=result.warning_count,
        info_count=result.info_count,
        execution_time_ms=result.execution_time_ms,
        results=[
            {
                "rule_id": r.rule_id,
                "rule_name": r.rule_name,
                "passed": r.passed,
                "severity": r.severity.value,
                "message": r.message,
                "details": r.details,
                "execution_time_ms": r.execution_time_ms,
            }
            for r in result.results
        ],
    )


@router.post("/reload", status_code=status.HTTP_200_OK)
async def reload_rules(
    user_id: CurrentUserId,
    engine: Annotated[RuleEngine, Depends(get_rule_engine)],
) -> dict[str, Any]:
    """Re-scan ``rules_directory`` and reload all rule sets."""
    count = await engine.safe_load_directory(_rules_load_path())
    return {"reloaded": True, "rule_sets": count}
