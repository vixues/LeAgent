"""Workflow template gallery API endpoints.

Provides listing, detail, category browsing, and "apply" (create flow from template).
"""

from __future__ import annotations

import json
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from leagent.services.auth import CurrentUserId
from leagent.db import DatabaseService, get_database_service
from leagent.db.models import Flow, FlowStatus, FlowType
from leagent.workflow.layout import layout_document
from leagent.workflow.template_service import TemplateService, get_template_service

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class TemplateListItem(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = "general"
    category_label: str = "General"
    icon: str = "📋"
    tags: list[str] = []
    node_count: int = 0
    version: str = "1.0"
    source: str = "yaml"


class TemplateListResponse(BaseModel):
    templates: list[TemplateListItem]
    total: int


class CategoryItem(BaseModel):
    id: str
    label: str
    icon: str = "📋"
    count: int = 0


class CategoriesResponse(BaseModel):
    categories: list[CategoryItem]


class TemplateDetail(BaseModel):
    id: str
    name: str
    description: str = ""
    category: str = "general"
    category_label: str = "General"
    icon: str = "📋"
    tags: list[str] = []
    node_count: int = 0
    version: str = "1.0"
    source: str = "yaml"
    definition: dict[str, Any] = {}


class ApplyTemplateRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    folder_id: Optional[UUID] = None


class ApplyTemplateResponse(BaseModel):
    flow_id: UUID
    name: str
    message: str = "Flow created from template"


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=TemplateListResponse)
async def list_templates(
    category: Optional[str] = Query(None, description="Filter by category"),
    search: Optional[str] = Query(None, description="Search by name or description"),
    svc: TemplateService = Depends(get_template_service),
):
    """List all workflow templates, optionally filtered by category."""
    templates = svc.list_templates(category=category)

    if search:
        q = search.lower()
        templates = [
            t
            for t in templates
            if q in t["name"].lower()
            or q in t.get("description", "").lower()
            or any(q in tag.lower() for tag in t.get("tags", []))
        ]

    return TemplateListResponse(templates=templates, total=len(templates))


@router.get("/categories", response_model=CategoriesResponse)
async def list_categories(
    svc: TemplateService = Depends(get_template_service),
):
    """List all template categories with counts."""
    return CategoriesResponse(categories=svc.list_categories())


@router.get("/{template_id}", response_model=TemplateDetail)
async def get_template(
    template_id: str,
    svc: TemplateService = Depends(get_template_service),
):
    """Get full template detail including its workflow definition."""
    info = svc.get_template_info(template_id)
    if not info:
        raise HTTPException(status_code=404, detail="Template not found")

    definition = svc.get_template(template_id) or {}

    return TemplateDetail(
        **info,
        definition=definition,
    )


@router.post("/{template_id}/apply", response_model=ApplyTemplateResponse)
async def apply_template(
    template_id: str,
    body: ApplyTemplateRequest,
    user_id: CurrentUserId,
    db: DatabaseService = Depends(get_database_service),
    svc: TemplateService = Depends(get_template_service),
):
    """Create a new flow from a template."""
    definition = svc.get_template(template_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Template not found")

    info = svc.get_template_info(template_id)

    flow_name = body.name or (f"{info['name']} (from template)" if info else f"Flow from {template_id}")
    flow_desc = body.description or (info.get("description", "") if info else "")

    # Attach a pre-computed layout so the canvas renders the template
    # with a clean left-to-right topology the first time it opens. The
    # canonical fields stay untouched — the engine ignores the sibling
    # "ui" block during execution.
    laid_out = layout_document(definition)
    flow_data = json.dumps(laid_out, ensure_ascii=False)

    flow = Flow(
        name=flow_name,
        description=flow_desc,
        icon=info.get("icon", "📋") if info else "📋",
        flow_type=FlowType.WORKFLOW,
        status=FlowStatus.DRAFT,
        data=flow_data,
        tags=",".join(definition.get("tags", [])),
        folder_id=body.folder_id,
        user_id=user_id,
    )

    async with db.session() as session:
        session.add(flow)
        await session.commit()
        await session.refresh(flow)

    return ApplyTemplateResponse(
        flow_id=flow.id,
        name=flow.name,
        message=f"Flow '{flow.name}' created from template '{template_id}'",
    )
