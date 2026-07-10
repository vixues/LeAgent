"""Service facade for coding-project lifecycle.

The manager is the single entry point for both the REST/SSE API and
the agent tools. It orchestrates the persistence layer
(:class:`CodingProject` rows + linked :class:`Folder` rows), the
template loader, the port allocator, and the dev-server supervisor.

Public surface:

* :meth:`scaffold` — copy a template into a new directory and
  persist a row + a project-mode folder.
* :meth:`start` — install dependencies if needed and boot the dev
  server; mint a preview JWT and update the row to ``running``.
* :meth:`stop` — graceful then forced shutdown.
* :meth:`delete` — soft-delete the row; the on-disk dir is left
  alone so users don't lose work; supervisors are stopped first.
* :meth:`list_for_user`, :meth:`get`, :meth:`get_for_user`,
  :meth:`tail_logs`, :meth:`build_preview_url`.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

import structlog
from sqlmodel import col, select

from leagent.config.settings import Settings
from leagent.project.ports import PortAllocator
from leagent.project.preview_tokens import (
    mint_preview_token,
    preview_query_path,
)
from leagent.project.runtime import (
    DevServerSupervisor,
    LogLine,
    RunningServer,
)
from leagent.project.templates import (
    Template,
    TemplateNotFoundError,
    copy_template_into,
    list_templates,
    load_template,
)
from leagent.db.models import (
    CodingProject,
    CodingProjectRuntimeKind,
    CodingProjectStatus,
    Folder,
)
from leagent.db.sqlite_compat import load_entity_by_id
from leagent.project.paths import (
    ProjectPathSafetyError,
    validate_project_path,
)

if TYPE_CHECKING:  # pragma: no cover
    from leagent.db.service import DatabaseService

logger = structlog.get_logger(__name__)


class CodingProjectNotFoundError(LookupError):
    """Raised when a project ID does not match the calling user's projects."""


class CodingProjectQuotaError(RuntimeError):
    """Raised when the per-user concurrent dev-server cap is hit."""


def _utc_naive_now() -> datetime:
    """Match the rest of the schema which stores naive UTC timestamps."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CodingProjectManager:
    """Process-wide manager for the coding-project live-runtime feature."""

    def __init__(
        self,
        settings: Settings,
        database: "DatabaseService",
        *,
        ports: PortAllocator | None = None,
        supervisor: DevServerSupervisor | None = None,
    ) -> None:
        self._settings = settings
        self._db = database
        self._ports = ports or PortAllocator(
            host=settings.coding_projects.bind_host,
            low=settings.coding_projects.port_range_min,
            high=settings.coding_projects.port_range_max,
        )
        self._supervisor = supervisor or DevServerSupervisor(
            log_buffer_lines=settings.coding_projects.log_buffer_lines,
            startup_timeout_sec=settings.coding_projects.dev_server_startup_timeout_sec,
        )
        self._root = self._resolve_root(settings)
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def root(self) -> Path:
        return self._root

    @property
    def supervisor(self) -> DevServerSupervisor:
        return self._supervisor

    @property
    def ports(self) -> PortAllocator:
        return self._ports

    @staticmethod
    def _resolve_root(settings: Settings) -> Path:
        raw = (settings.coding_projects.root or "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
        from leagent.config.constants import LEAGENT_HOME

        return (LEAGENT_HOME / "coding-projects").resolve()

    # -- discovery -----------------------------------------------------

    def list_templates(self) -> list[Template]:
        return list_templates()

    def get_template(self, name: str) -> Template:
        return load_template(name)

    @staticmethod
    def _maybe_git_init(project_dir: Path) -> None:
        """Create a Git repo when ``git`` is on PATH and ``.git`` is absent."""
        if (project_dir / ".git").exists():
            return
        if not shutil.which("git"):
            return
        try:
            subprocess.run(
                ["git", "init"],
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                timeout=90,
                check=False,
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(
                "coding_project_git_init_skipped",
                path=str(project_dir),
                error=str(exc),
            )

    # -- lifecycle -----------------------------------------------------

    async def scaffold(
        self,
        *,
        user_id: UUID,
        name: str,
        template: str,
        folder_id: Optional[UUID] = None,
        into_path: Optional[str] = None,
        description: Optional[str] = None,
    ) -> CodingProject:
        """Create a new coding-project row and copy the template files.

        ``into_path``, when provided, must be an absolute path that
        resolves to an existing directory **owned by** the calling
        user (i.e. either already a project-mode folder, or under
        ``CODING_PROJECTS_ROOT``). When omitted, the manager creates
        a new directory ``CODING_PROJECTS_ROOT/<uuid>`` and pairs it
        with a freshly created project-mode :class:`Folder`.
        """
        try:
            tmpl = load_template(template)
        except TemplateNotFoundError as exc:
            raise ValueError(f"Unknown template: {template!r}") from exc

        target_dir = await self._allocate_target_dir(user_id, into_path)
        copy_template_into(tmpl, target_dir, overwrite=False)
        self._maybe_git_init(target_dir)

        _KIND_MAP = {
            "fastapi": CodingProjectRuntimeKind.FASTAPI,
            "python": CodingProjectRuntimeKind.PYTHON,
        }
        runtime_kind = _KIND_MAP.get(
            tmpl.runtime_kind, CodingProjectRuntimeKind.FRONTEND
        )

        async with self._db.session() as session:
            folder_uuid = folder_id
            if folder_uuid is None:
                folder = Folder(
                    name=name,
                    description=description,
                    icon="🛠️",
                    user_id=user_id,
                    is_project=True,
                    project_path=str(target_dir),
                    project_path_checked_at=_utc_naive_now(),
                )
                session.add(folder)
                await session.flush()
                folder_uuid = folder.id
            else:
                folder = await load_entity_by_id(
                    session, Folder, folder_uuid, parent_table="folders"
                )
                if folder is None or folder.user_id != user_id or folder.is_deleted:
                    raise ProjectPathSafetyError(
                        "Folder not found or not owned by user."
                    )
                folder.is_project = True
                folder.project_path = str(target_dir)
                folder.project_path_checked_at = _utc_naive_now()
                session.add(folder)

            project = CodingProject(
                id=uuid4(),
                name=name,
                description=description,
                template=template,
                runtime_kind=runtime_kind,
                user_id=user_id,
                folder_id=folder_uuid,
                root_path=str(target_dir),
                status=CodingProjectStatus.IDLE,
                install_marker=tmpl.install_marker_relpath or None,
            )
            session.add(project)
            await session.flush()
            await session.refresh(project)

        logger.info(
            "coding_projects_scaffolded",
            project_id=str(project.id),
            template=template,
            user_id=str(user_id),
            root=str(target_dir),
        )
        return project

    async def _allocate_target_dir(
        self,
        user_id: UUID,
        into_path: Optional[str],
    ) -> Path:
        if into_path:
            try:
                resolved = validate_project_path(into_path)
            except ProjectPathSafetyError:
                raise
            return resolved

        candidate = self._root / str(uuid4())
        candidate.mkdir(parents=True, exist_ok=False)
        # Touch a hidden marker so the path exists and our safety
        # validator (which requires a real directory) accepts it on
        # subsequent restart.
        return candidate

    async def start(
        self,
        *,
        project_id: UUID,
        user_id: UUID,
    ) -> tuple[CodingProject, RunningServer, str]:
        """Boot the dev server and mint a preview token.

        Returns the freshly-loaded row, the running-server snapshot,
        and the bearer token (the URL is built by the API caller).
        """
        project = await self._get_for_user(project_id, user_id)
        await self._enforce_concurrency_cap(user_id, project_id)
        tmpl = load_template(project.template)
        cwd = Path(project.root_path)
        if not cwd.is_dir():
            raise FileNotFoundError(
                f"Project root has been removed from disk: {cwd!s}"
            )

        if tmpl.needs_install and tmpl.install_argv:
            await self._maybe_install(project, tmpl)

        port = self._ports.allocate(str(project_id))
        argv = tmpl.expand_argv(
            tmpl.start_argv,
            host=self._settings.coding_projects.bind_host,
            port=port,
        )

        env = {
            "PORT": str(port),
            "HOST": self._settings.coding_projects.bind_host,
            "PYTHONUNBUFFERED": "1",
            "NODE_OPTIONS": "--unhandled-rejections=warn",
        }

        try:
            running = await self._supervisor.start(
                project_id=project_id,
                cwd=cwd,
                argv=argv,
                host=self._settings.coding_projects.bind_host,
                port=port,
                ready_regex=tmpl.ready_regex or None,
                env=env,
                startup_timeout_sec=self._settings.coding_projects.dev_server_startup_timeout_sec,
            )
        except Exception:
            self._ports.release(str(project_id))
            await self._set_status(project_id, CodingProjectStatus.CRASHED, port=port)
            raise

        await self._set_status(
            project_id,
            CodingProjectStatus.RUNNING,
            port=port,
            pid=running.pid,
            last_started_at=_utc_naive_now(),
        )
        token = mint_preview_token(
            self._settings,
            project_id=project_id,
            run_seq=running.run_seq,
            user_id=user_id,
        )
        project = await self._get_for_user(project_id, user_id)
        return project, running, token

    async def _maybe_install(self, project: CodingProject, tmpl: Template) -> None:
        marker = (
            Path(project.root_path) / project.install_marker
            if project.install_marker
            else None
        )
        if marker is not None and marker.exists():
            return

        from leagent.project.binaries import assert_argv_allowed
        import asyncio
        import subprocess

        argv = tmpl.expand_argv(
            tmpl.install_argv,
            host=self._settings.coding_projects.bind_host,
            port=0,
        )
        checked = assert_argv_allowed(argv)

        logger.info(
            "coding_projects_install_start",
            project_id=str(project.id),
            argv=list(checked),
        )
        proc = await asyncio.create_subprocess_exec(
            *checked,
            cwd=str(Path(project.root_path)),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self._settings.coding_projects.npm_install_timeout_sec,
            )
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise TimeoutError(
                "Dependency install timed out for project "
                f"{project.id}; see logs for argv {' '.join(checked)!r}."
            )
        if proc.returncode != 0:
            tail = (stderr or stdout or b"").decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Dependency install failed (exit {proc.returncode}): "
                f"{tail.strip()[-1000:]}"
            )

    async def stop(
        self,
        *,
        project_id: UUID,
        user_id: UUID,
    ) -> CodingProject:
        await self._get_for_user(project_id, user_id)
        await self._supervisor.stop(project_id)
        self._ports.release(str(project_id))
        await self._set_status(
            project_id,
            CodingProjectStatus.IDLE,
            port=None,
            pid=None,
            last_stopped_at=_utc_naive_now(),
        )
        return await self._get_for_user(project_id, user_id)

    async def delete(
        self,
        *,
        project_id: UUID,
        user_id: UUID,
    ) -> None:
        # Always stop first; we keep the on-disk dir intact.
        try:
            await self._supervisor.stop(project_id)
        except Exception:  # noqa: BLE001
            logger.warning(
                "coding_projects_delete_stop_failed",
                project_id=str(project_id),
                exc_info=True,
            )
        self._ports.release(str(project_id))
        async with self._db.session() as session:
            project = await load_entity_by_id(
                session, CodingProject, project_id, parent_table="coding_projects"
            )
            if project is None or project.user_id != user_id:
                raise CodingProjectNotFoundError(str(project_id))
            project.is_deleted = True
            project.deleted_at = _utc_naive_now()
            session.add(project)

    # -- query ---------------------------------------------------------

    async def list_for_user(self, user_id: UUID) -> list[CodingProject]:
        async with self._db.session() as session:
            stmt = (
                select(CodingProject)
                .where(CodingProject.user_id == user_id)
                .where(col(CodingProject.is_deleted).is_(False))
                .order_by(col(CodingProject.created_at).desc())
            )
            result = await session.exec(stmt)
            return list(result.all())

    async def get_for_user(
        self,
        project_id: UUID,
        user_id: UUID,
    ) -> CodingProject:
        return await self._get_for_user(project_id, user_id)

    async def get_by_folder_for_user(
        self,
        folder_id: UUID,
        user_id: UUID,
    ) -> CodingProject:
        """Return the runtime row bound to a project-mode folder."""
        async with self._db.session() as session:
            stmt = (
                select(CodingProject)
                .where(CodingProject.folder_id == folder_id)
                .where(CodingProject.user_id == user_id)
                .where(col(CodingProject.is_deleted).is_(False))
            )
            result = await session.exec(stmt)
            project = result.first()
            if project is None:
                raise CodingProjectNotFoundError(f"folder:{folder_id}")
            return project

    async def _get_for_user(
        self,
        project_id: UUID,
        user_id: UUID,
    ) -> CodingProject:
        async with self._db.session() as session:
            project = await load_entity_by_id(
                session, CodingProject, project_id, parent_table="coding_projects"
            )
            if (
                project is None
                or project.is_deleted
                or project.user_id != user_id
            ):
                raise CodingProjectNotFoundError(str(project_id))
            return project

    async def _enforce_concurrency_cap(
        self,
        user_id: UUID,
        starting_project: UUID,
    ) -> None:
        cap = self._settings.coding_projects.max_concurrent_per_user
        if cap <= 0:
            return
        running = [
            srv
            for srv in self._supervisor.list_running()
            if srv.project_id != starting_project
        ]
        if not running:
            return
        # Filter to the calling user's running servers.
        async with self._db.session() as session:
            stmt = select(CodingProject).where(
                CodingProject.user_id == user_id,
                col(CodingProject.is_deleted).is_(False),
            )
            result = await session.exec(stmt)
            owned_ids = {p.id for p in result.all()}
        owned_running = [s for s in running if s.project_id in owned_ids]
        if len(owned_running) >= cap:
            raise CodingProjectQuotaError(
                f"At most {cap} dev servers may run concurrently per user."
            )

    async def _set_status(
        self,
        project_id: UUID,
        status: CodingProjectStatus,
        *,
        port: Optional[int] = ...,
        pid: Optional[int] = ...,
        last_started_at: Optional[datetime] = None,
        last_stopped_at: Optional[datetime] = None,
    ) -> None:
        async with self._db.session() as session:
            project = await load_entity_by_id(
                session, CodingProject, project_id, parent_table="coding_projects"
            )
            if project is None:
                return
            project.status = status
            if port is not ...:
                project.port = port
            if pid is not ...:
                project.pid = pid
            if last_started_at is not None:
                project.last_started_at = last_started_at
            if last_stopped_at is not None:
                project.last_stopped_at = last_stopped_at
            project.updated_at = _utc_naive_now()
            session.add(project)

    # -- preview helpers ----------------------------------------------

    def build_preview_url(
        self,
        project_id: UUID,
        token: str,
        *,
        sub_path: str = "",
    ) -> str:
        return preview_query_path(project_id, token, sub_path=sub_path)

    def supervised_target_base(self, server: RunningServer) -> str:
        return f"http://{server.host}:{server.port}"

    def supervised_ws_target(self, server: RunningServer, sub_path: str) -> str:
        cleaned = sub_path.lstrip("/")
        return f"ws://{server.host}:{server.port}/{cleaned}"

    # -- log access ---------------------------------------------------

    def snapshot_logs(self, project_id: UUID, *, max_lines: int = 200) -> list[LogLine]:
        return self._supervisor.snapshot_logs(project_id, max_lines=max_lines)

    async def stream_logs(self, project_id: UUID):
        async for line in self._supervisor.stream_logs(project_id):
            yield line

    # -- shutdown -----------------------------------------------------

    async def shutdown(self) -> None:
        await self._supervisor.shutdown_all()
        self._ports.reset()


# ---------------------------------------------------------------------------
# Process-wide singleton (matches the chat / file-store pattern)
# ---------------------------------------------------------------------------

_coding_projects_service: CodingProjectManager | None = None


def get_coding_projects_service() -> CodingProjectManager:
    if _coding_projects_service is None:
        raise RuntimeError("CodingProjectManager not initialized")
    return _coding_projects_service


async def init_coding_projects_service(
    settings: Settings,
    database: "DatabaseService",
) -> CodingProjectManager:
    """Initialise the process-wide manager singleton."""
    global _coding_projects_service
    if _coding_projects_service is not None:
        return _coding_projects_service
    manager = CodingProjectManager(settings, database)
    _coding_projects_service = manager
    logger.info(
        "coding_projects_service_ready",
        root=str(manager.root),
        bind_host=settings.coding_projects.bind_host,
        ports=f"{settings.coding_projects.port_range_min}-{settings.coding_projects.port_range_max}",
    )
    return manager


async def shutdown_coding_projects_service() -> None:
    global _coding_projects_service
    if _coding_projects_service is None:
        return
    try:
        await _coding_projects_service.shutdown()
    except Exception:  # noqa: BLE001
        logger.warning("coding_projects_service_shutdown_error", exc_info=True)
    _coding_projects_service = None
