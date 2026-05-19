"""Skills management REST endpoints.

Aligned with the Agent Skills v1.0 open spec:

- List / get / activate / deactivate skills.
- Inspect bundled resources and scripts.
- Read a resource and (with the env flag set) run a bundled script.
- Search the registry hub and install from it.
"""

from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from leagent.services.auth import CurrentUserId
from leagent.skills.github_monorepo_catalog import GitHubCatalogOverride
from leagent.skills.manager import (
    SkillActivationError,
    SkillFileNotEditableError,
    SkillFileUpdateError,
    SkillNotFoundError,
    SkillsManager,
    get_skills_manager,
)

router = APIRouter()


def _github_catalog_override_or_none(
    gh_owner: Optional[str],
    gh_repo: Optional[str],
    gh_ref: Optional[str],
    gh_skills_path: Optional[str],
) -> GitHubCatalogOverride | None:
    owner = (gh_owner or "").strip()
    repo = (gh_repo or "").strip()
    if owner or repo:
        if not owner or not repo:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Parameters gh_owner and gh_repo must be supplied together",
            )
        return GitHubCatalogOverride(
            owner=owner,
            repo=repo,
            ref=(gh_ref or "main").strip(),
            skills_path=(gh_skills_path or "skills").strip(),
        )
    return None


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class SkillInfo(BaseModel):
    name: str
    display_name: str
    description: str
    version: str
    category: str
    source: str
    status: str
    is_active: bool
    tags: list[str] = Field(default_factory=list)
    has_resources: bool = False
    has_scripts: bool = False


class SkillResourceInfo(BaseModel):
    path: str
    kind: str
    size: int
    extension: str


class SkillScriptInfo(BaseModel):
    path: str
    interpreter: str
    size: int
    extension: str


class SkillDetail(BaseModel):
    name: str
    description: str
    version: str
    display_name: str
    category: str
    source: str
    status: str
    is_active: bool
    tags: list[str] = Field(default_factory=list)
    author: Optional[str] = None
    license: Optional[str] = None
    compatibility: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    allowed_tools: list[str] = Field(default_factory=list)
    resources: list[SkillResourceInfo] = Field(default_factory=list)
    scripts: list[SkillScriptInfo] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    is_editable: bool = False


class SkillActivateRequest(BaseModel):
    config: dict[str, Any] = Field(default_factory=dict)


class SkillListResponse(BaseModel):
    skills: list[SkillInfo]
    total: int
    active_count: int


class SkillBodyResponse(BaseModel):
    name: str
    body: str
    truncated: bool = False


class SkillFileResponse(BaseModel):
    name: str
    content: str
    truncated: bool = False


class SkillFileUpdateRequest(BaseModel):
    content: str


class SkillInstallFromUrlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    sha256: Optional[str] = Field(default=None, max_length=64)


class SkillResourceResponse(BaseModel):
    path: str
    kind: str
    encoding: str
    size: int
    truncated: bool = False
    content: Optional[str] = None
    content_base64: Optional[str] = None


class SkillScriptRunRequest(BaseModel):
    args: list[str] = Field(default_factory=list)
    timeout_s: int = Field(default=60, ge=1, le=600)


class SkillHubSearchResponse(BaseModel):
    skills: list[dict[str, Any]]
    total: int


def get_manager() -> SkillsManager:
    return get_skills_manager()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _info_from_skill(skill: Any) -> SkillInfo:
    return SkillInfo(
        name=skill.name,
        display_name=skill.display_name,
        description=skill.description,
        version=skill.manifest.version,
        category=skill.manifest.category,
        source=skill.source.value,
        status=skill.status.value,
        is_active=skill.is_active,
        tags=skill.manifest.tags,
        has_resources=skill.manifest.has_resources,
        has_scripts=skill.manifest.has_scripts,
    )


def _detail_from_skill(skill: Any, manager: SkillsManager) -> SkillDetail:
    return SkillDetail(
        name=skill.name,
        description=skill.description,
        version=skill.manifest.version,
        display_name=skill.display_name,
        category=skill.manifest.category,
        source=skill.source.value,
        status=skill.status.value,
        is_active=skill.is_active,
        tags=skill.manifest.tags,
        author=skill.manifest.author or None,
        license=skill.manifest.license,
        compatibility=skill.manifest.compatibility,
        metadata=dict(skill.manifest.metadata),
        allowed_tools=list(skill.manifest.allowed_tools),
        resources=[SkillResourceInfo(**r.to_dict()) for r in skill.manifest.resources],
        scripts=[SkillScriptInfo(**s.to_dict()) for s in skill.manifest.scripts],
        config={k: v for k, v in skill.config.items() if not k.startswith("_")},
        error=skill.error,
        is_editable=manager.is_skill_editable(skill.name),
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("", response_model=SkillListResponse)
async def list_skills(
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
    category: Optional[str] = Query(default=None, max_length=50),
    tag: Optional[str] = Query(default=None, max_length=50),
    active_only: bool = Query(default=False),
    search: Optional[str] = Query(default=None, max_length=100),
) -> SkillListResponse:
    """List all discovered skills."""
    if category:
        skills = manager.list_by_category(category)
    elif tag:
        skills = manager.list_by_tag(tag)
    elif search:
        skills = manager.search(search)
    else:
        skills = manager.all_skills

    if active_only:
        skills = [s for s in skills if s.is_active]

    infos = [_info_from_skill(s) for s in skills]
    return SkillListResponse(
        skills=infos,
        total=len(infos),
        active_count=sum(1 for s in skills if s.is_active),
    )


@router.post("/install/url", response_model=SkillDetail)
async def install_skill_from_url_endpoint(
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
    data: SkillInstallFromUrlRequest,
) -> SkillDetail:
    """Install a skill from an HTTPS URL pointing to a .zip or .tar.gz archive."""
    from leagent.skills.url_install import SkillURLError

    try:
        skill = await manager.install_from_url(data.url, sha256=data.sha256)
    except SkillURLError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Skill install directory not configured or install failed",
        )
    return _detail_from_skill(skill, manager)


@router.get("/{skill_name}", response_model=SkillDetail)
async def get_skill(
    skill_name: str,
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
) -> SkillDetail:
    skill = manager.get_skill(skill_name)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_name}' not found",
        )
    return _detail_from_skill(skill, manager)


@router.get("/{skill_name}/file", response_model=SkillFileResponse)
async def get_skill_file(
    skill_name: str,
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
    max_chars: int = Query(default=200_000, ge=512, le=500_000),
) -> SkillFileResponse:
    """Return the raw SKILL.md file (frontmatter + body) for editing."""
    skill = manager.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found")
    md = skill.skill_md_path
    if not md or not md.exists():
        return SkillFileResponse(name=skill.name, content="", truncated=False)
    try:
        text = md.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read SKILL.md: {exc}",
        ) from exc
    truncated = len(text) > max_chars
    return SkillFileResponse(name=skill.name, content=text[:max_chars], truncated=truncated)


@router.put("/{skill_name}/file", response_model=SkillDetail)
async def put_skill_file(
    skill_name: str,
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
    data: SkillFileUpdateRequest,
) -> SkillDetail:
    """Replace SKILL.md after validation and reload the skill."""
    try:
        skill = await manager.update_skill_file(skill_name, data.content)
    except SkillNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_name}' not found",
        ) from None
    except SkillFileNotEditableError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Skill '{skill_name}' is not editable (builtin or read-only)",
        ) from None
    except SkillFileUpdateError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.reason,
        ) from None
    return _detail_from_skill(skill, manager)


@router.get("/{skill_name}/body", response_model=SkillBodyResponse)
async def get_skill_body(
    skill_name: str,
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
    max_chars: int = Query(default=200_000, ge=512, le=500_000),
) -> SkillBodyResponse:
    """Return the lazily-read SKILL.md body for UI preview."""
    skill = manager.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found")
    body = skill.read_body()
    truncated = len(body) > max_chars
    return SkillBodyResponse(name=skill.name, body=body[:max_chars], truncated=truncated)


@router.post("/{skill_name}/activate", response_model=SkillDetail)
async def activate_skill(
    skill_name: str,
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
    data: Optional[SkillActivateRequest] = None,
) -> SkillDetail:
    try:
        config = data.config if data else None
        skill = await manager.activate(skill_name, config)
    except SkillNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found")
    except SkillActivationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to activate skill: {exc.reason}")
    return _detail_from_skill(skill, manager)


@router.post("/{skill_name}/deactivate")
async def deactivate_skill(
    skill_name: str,
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
) -> dict[str, Any]:
    success = await manager.deactivate(skill_name)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found")
    return {"skill_name": skill_name, "is_active": False, "message": "Skill deactivated successfully"}


@router.get("/{skill_name}/resources", response_model=list[SkillResourceInfo])
async def list_resources(
    skill_name: str,
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
) -> list[SkillResourceInfo]:
    skill = manager.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found")
    return [SkillResourceInfo(**r.to_dict()) for r in skill.manifest.resources]


@router.get("/{skill_name}/resources/{resource_path:path}", response_model=SkillResourceResponse)
async def read_resource(
    skill_name: str,
    resource_path: str,
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
    max_bytes: int = Query(default=200_000, ge=512, le=500_000),
) -> SkillResourceResponse:
    """Read a bundled resource file from a skill."""
    from leagent.tools.skills.resource import _read_resource_payload
    from leagent.skills.loader import is_path_inside

    skill = manager.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found")
    resource = skill.get_resource(resource_path)
    if not resource or not skill.path or not is_path_inside(skill.path, resource.absolute_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Resource '{resource_path}' not found for skill '{skill_name}'",
        )
    payload = _read_resource_payload(
        resource.absolute_path,
        max_bytes=max_bytes,
        resource=resource,
        skill_name=skill_name,
    )
    if not payload.get("found"):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=payload.get("error", "Read failed"))
    return SkillResourceResponse(
        path=resource.relative_path,
        kind=resource.kind.value,
        encoding=payload.get("encoding", "utf-8"),
        size=payload.get("size", 0),
        truncated=bool(payload.get("truncated")),
        content=payload.get("content"),
        content_base64=payload.get("content_base64"),
    )


@router.get("/{skill_name}/scripts", response_model=list[SkillScriptInfo])
async def list_scripts(
    skill_name: str,
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
) -> list[SkillScriptInfo]:
    skill = manager.get_skill(skill_name)
    if not skill:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found")
    return [SkillScriptInfo(**s.to_dict()) for s in skill.manifest.scripts]


@router.post("/{skill_name}/scripts/{script_path:path}/run")
async def run_script(
    skill_name: str,
    script_path: str,
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
    data: SkillScriptRunRequest | None = None,
) -> dict[str, Any]:
    """Execute a bundled script when ``Settings.skill_scripts_enabled`` is true."""
    from leagent.tools.base import ToolContext
    from leagent.tools.skills.script import SkillScriptTool

    tool = SkillScriptTool()
    params = {
        "skill_name": skill_name,
        "script_path": script_path,
        "args": (data.args if data else []) or [],
        "timeout_s": (data.timeout_s if data else 60),
    }
    ctx = ToolContext(user_id=user_id, session_id=None)
    return await tool.execute(params, ctx)


@router.get("/hub/search", response_model=SkillHubSearchResponse)
async def search_hub(
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
    query: str = Query(default="", max_length=100),
    category: Optional[str] = Query(default=None, max_length=50),
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    gh_owner: Optional[str] = Query(default=None, max_length=200),
    gh_repo: Optional[str] = Query(default=None, max_length=200),
    gh_ref: Optional[str] = Query(default=None, max_length=200),
    gh_skills_path: Optional[str] = Query(default=None, max_length=500),
) -> SkillHubSearchResponse:
    gh_override = _github_catalog_override_or_none(gh_owner, gh_repo, gh_ref, gh_skills_path)
    entries = await manager.search_hub(
        query=query,
        category=category,
        page=page,
        limit=limit,
        github_override=gh_override,
    )
    return SkillHubSearchResponse(
        skills=[e.to_dict() for e in entries],
        total=len(entries),
    )


@router.post("/hub/install/{skill_name}")
async def install_from_hub(
    skill_name: str,
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
    gh_owner: Optional[str] = Query(default=None, max_length=200),
    gh_repo: Optional[str] = Query(default=None, max_length=200),
    gh_ref: Optional[str] = Query(default=None, max_length=200),
    gh_skills_path: Optional[str] = Query(default=None, max_length=500),
) -> dict[str, Any]:
    gh_override = _github_catalog_override_or_none(gh_owner, gh_repo, gh_ref, gh_skills_path)
    try:
        skill = await manager.install_from_hub(skill_name, github_override=gh_override)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"Registry unavailable or install failed: {exc}",
        )
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to install skill '{skill_name}'",
        )
    return {
        "skill_name": skill.name,
        "version": skill.manifest.version,
        "installed": True,
        "message": "Skill installed successfully",
    }


@router.delete("/{skill_name}")
async def uninstall_skill(
    skill_name: str,
    user_id: CurrentUserId,
    manager: Annotated[SkillsManager, Depends(get_manager)],
) -> dict[str, Any]:
    ok = await manager.uninstall(skill_name)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill '{skill_name}' not found")
    return {"skill_name": skill_name, "uninstalled": True}
