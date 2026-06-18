"""Centralised service lifecycle manager"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from leagent.services.base import ServiceState

if TYPE_CHECKING:
    from leagent.config.settings import Settings
    from leagent.cron.manager import CronManager
    from leagent.file.service import FileService
    from leagent.llm.service import LLMService
    from leagent.mcp.manager import MCPClientManager
    from leagent.memory.agent_memory import AgentMemory
    from leagent.services.canvas.service import CanvasService
    from leagent.services.chat.service import ChatService
    from leagent.project.manager import CodingProjectManager
    from leagent.db.service import DatabaseService
    from leagent.services.event.manager import EventManager
    from leagent.services.event.webhook import WebhookEventManager
    from leagent.services.file_processing.service import FileProcessingService
    from leagent.services.session.manager import SessionManager
    from leagent.services.task_manager import TaskManager
    from leagent.runtime.context import RuntimeContext
    from leagent.services.variable.service import VariableService
    from leagent.workflow.services import WorkflowService

logger = logging.getLogger(__name__)


class ServiceManager:
    """Creates, starts, and stops all application services.

    Standalone local mode — no Redis, no Milvus, no MinIO, no auth.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

        self._db: DatabaseService | None = None
        self._chat: ChatService | None = None
        self._canvas: "CanvasService | None" = None
        self._coding_projects: "CodingProjectManager | None" = None
        self._variable: VariableService | None = None
        self._event: EventManager | None = None
        self._webhook: WebhookEventManager | None = None

        self._llm: Any = None
        self._llm_service: LLMService | None = None
        self._mcp_manager: MCPClientManager | None = None
        self._cron: CronManager | None = None
        self._workflow_service: WorkflowService | None = None
        self._workflow_event_bus: Any = None
        self._file_service: "FileService | None" = None
        self._file_processing: FileProcessingService | None = None
        self._rule_engine: Any = None
        self._task_manager: TaskManager | None = None
        self._session_manager: SessionManager | None = None
        self._agent_memory: AgentMemory | None = None
        self._runtime_context: RuntimeContext | None = None

        self._started = False

    @property
    def db(self) -> "DatabaseService | None":
        return self._db

    @property
    def auth(self) -> Any:
        return None

    @property
    def cache(self) -> Any:
        return None

    @property
    def chat(self) -> "ChatService | None":
        return self._chat

    @property
    def canvas(self) -> "CanvasService | None":
        return self._canvas

    @property
    def variable(self) -> "VariableService | None":
        return self._variable

    @property
    def coding_projects(self) -> "CodingProjectManager | None":
        return self._coding_projects

    @property
    def job_queue(self) -> Any:
        return None

    @property
    def file_store(self) -> Any:
        return None

    @property
    def event(self) -> "EventManager | None":
        return self._event

    @property
    def webhook(self) -> "WebhookEventManager | None":
        return self._webhook

    @property
    def redis(self) -> Any:
        return None

    @property
    def redis_client(self) -> Any:
        return None

    @property
    def database_service(self) -> Any:
        return self._db

    @property
    def minio(self) -> Any:
        return None

    @property
    def milvus(self) -> Any:
        return None

    @property
    def llm(self) -> Any:
        return self._llm

    @property
    def llm_service(self) -> "LLMService | None":
        return self._llm_service

    async def reload_llm_service(self) -> None:
        if self._llm_service is None:
            return
        try:
            from leagent.llm.provider_config import reset_provider_config_service

            reset_provider_config_service()
            # Art image-generation stack reads the same providers.yaml; reset
            # its config + backend service so credential/preset edits apply
            # without a restart.
            try:
                from leagent.llm.generation import reset_image_gen_config
                from leagent.llm.generation.service import reset_generation_service

                reset_image_gen_config()
                reset_generation_service()
            except Exception:  # noqa: BLE001 - art stack reload is best-effort
                logger.debug("generation service reload skipped", exc_info=True)
            self._llm_service.reload()
            logger.info(
                "LLMService reloaded with %d provider(s): %s",
                len(self._llm_service.list_providers()),
                self._llm_service.list_providers(),
            )
        except Exception:
            logger.warning("LLMService reload failed", exc_info=True)

    @property
    def mcp_manager(self) -> "MCPClientManager | None":
        return self._mcp_manager

    @property
    def cron(self) -> "CronManager | None":
        return self._cron

    @property
    def workflow_service(self) -> "WorkflowService | None":
        return self._workflow_service

    @property
    def runtime_context(self) -> "RuntimeContext":
        """Process-wide :class:`RuntimeContext` (lazy singleton).

        Central wiring point for agent execution: tool executor, hooks,
        checkpoint store, session manager, and LLM. Callers should prefer
        this over hand-constructing :class:`ToolExecutor` instances.
        """
        if self._runtime_context is None:
            from leagent.runtime.context import RuntimeContext

            self._runtime_context = RuntimeContext.from_service_manager(self)
        return self._runtime_context

    @property
    def file_service(self) -> "FileService | None":
        return self._file_service

    @property
    def file_processing(self) -> "FileProcessingService | None":
        return self._file_processing

    @property
    def rule_engine(self) -> Any:
        return self._rule_engine

    @property
    def task_manager(self) -> "TaskManager | None":
        return self._task_manager

    @property
    def task_registry(self) -> Any:
        return None

    @property
    def session_manager(self) -> "SessionManager | None":
        return self._session_manager

    @property
    def agent_memory(self) -> "AgentMemory | None":
        return self._agent_memory

    @property
    def is_started(self) -> bool:
        return self._started

    async def start_all(self) -> None:
        if self._started:
            logger.warning("Services already started")
            return

        logger.info("Starting services...")

        await self._start_database()
        await self._start_event()
        await self._start_chat()
        await self._start_canvas()
        await self._start_coding_projects()
        await self._start_variable()
        await self._start_llm()
        await self._start_file_service()
        await self._start_session_manager()
        await self._start_agent_memory()
        await self._start_rules()
        await self._start_workflow_service()
        await self._start_cron()
        await self._start_task_manager()
        await self._start_file_processing()

        self._started = True
        logger.info("All services started successfully")

    async def stop_all(self) -> None:
        logger.info("Stopping services...")

        if self._task_manager is not None:
            try:
                await self._task_manager.shutdown()
            except Exception:
                logger.warning("Task manager shutdown error", exc_info=True)

        if self._cron:
            try:
                await self._cron.stop()
            except Exception:
                logger.warning("Cron manager shutdown error", exc_info=True)

        if self._webhook:
            try:
                await self._webhook.stop()
            except Exception:
                logger.warning("Webhook service shutdown error", exc_info=True)

        if self._coding_projects:
            try:
                from leagent.project.manager import (
                    shutdown_coding_projects_service,
                )
                await shutdown_coding_projects_service()
            except Exception:
                logger.warning("Coding-projects service shutdown error", exc_info=True)

        if self._chat:
            try:
                await self._chat.stop()
            except Exception:
                logger.warning("Chat service shutdown error", exc_info=True)

        if self._llm_service:
            try:
                await self._llm_service.aclose()
            except Exception:
                logger.warning("LLM service shutdown error", exc_info=True)

        if self._event:
            try:
                await self._event.stop()
            except Exception:
                logger.warning("Event service shutdown error", exc_info=True)

        if self._db:
            try:
                await self._db.dispose()
            except Exception:
                logger.warning("Database shutdown error", exc_info=True)

        self._started = False
        logger.info("All services stopped")

    async def health_check(self) -> dict[str, Any]:
        results: dict[str, Any] = {"healthy": True, "services": {}}
        services = [
            ("database", self._db),
            ("chat", self._chat),
            ("variable", self._variable),
            ("event", self._event),
        ]
        for name, service in services:
            if service is None:
                results["services"][name] = {"status": "not_initialized"}
                continue
            try:
                if hasattr(service, "health_check"):
                    check = await service.health_check()
                    results["services"][name] = check
                elif hasattr(service, "state"):
                    results["services"][name] = {
                        "status": service.state.value,
                        "healthy": service.state == ServiceState.READY,
                    }
                else:
                    results["services"][name] = {"status": "ok"}
            except Exception as e:
                results["services"][name] = {
                    "status": "error",
                    "error": str(e),
                    "healthy": False,
                }
                results["healthy"] = False
        return results

    async def _start_database(self) -> None:
        try:
            from leagent.db.service import init_database_service
            self._db = init_database_service(self.settings)
            await self._db.create_tables()
            logger.info("Database service initialized (SQLite)")
        except Exception:
            logger.exception("Database initialization failed")
            raise

    async def _start_event(self) -> None:
        try:
            from leagent.services.event.manager import init_event_manager
            self._event = await init_event_manager(
                self.settings,
                keep_history=self.settings.debug,
                max_history=1000,
            )
            logger.info("Event manager initialized")
        except Exception:
            logger.warning("Event manager initialization skipped", exc_info=True)

    async def _start_chat(self) -> None:
        try:
            from leagent.services.chat.service import init_chat_service
            if self._db:
                self._chat = await init_chat_service(self.settings, self._db, None)
                logger.info("Chat service initialized")
        except Exception:
            logger.warning("Chat initialization skipped", exc_info=True)

    async def _start_canvas(self) -> None:
        try:
            from leagent.services.canvas.service import init_canvas_service
            if self._db:
                self._canvas = await init_canvas_service(self.settings, self._db, self._chat)
                logger.info("Canvas service initialized")
        except Exception:
            logger.warning("Canvas initialization skipped", exc_info=True)

    async def _start_coding_projects(self) -> None:
        if not getattr(self.settings, "coding_projects", None):
            return
        if not self.settings.coding_projects.enabled:
            return
        try:
            from leagent.project.manager import init_coding_projects_service
            if self._db is None:
                return
            self._coding_projects = await init_coding_projects_service(self.settings, self._db)
            logger.info("Coding-projects service initialized")
        except Exception:
            logger.warning("Coding-projects initialization skipped", exc_info=True)

    async def _start_variable(self) -> None:
        try:
            from leagent.services.variable.service import init_variable_service
            if self._db:
                self._variable = await init_variable_service(self.settings, self._db, None)
                logger.info("Variable service initialized")
        except Exception:
            logger.warning("Variable initialization skipped", exc_info=True)

    async def _start_llm(self) -> None:
        try:
            from leagent.llm.service import LLMService
            self._llm_service = LLMService.from_settings()
            self._llm = {"tasks": self._llm_service.list_tasks()}
            logger.info("LLMService initialised with %d provider(s)", len(self._llm_service.list_providers()))
        except Exception:
            logger.warning("LLMService initialisation skipped", exc_info=True)

    async def _start_rules(self) -> None:
        try:
            from pathlib import Path
            from leagent.config.constants import RULES_DIR
            from leagent.rules.engine import RuleEngine

            raw = (self.settings.rules_directory or "").strip()
            rules_path = Path(raw).expanduser().resolve() if raw else RULES_DIR
            engine = RuleEngine(llm_service=self._llm_service)
            count = await engine.safe_load_directory(rules_path)
            self._rule_engine = engine
            logger.info("RuleEngine initialised: %d rule set(s) from %s", count, rules_path)
        except Exception:
            logger.warning("RuleEngine initialisation skipped", exc_info=True)

    async def _start_workflow_service(self) -> None:
        if not self._db:
            return
        try:
            from leagent.workflow.engine import WorkflowExecutor
            from leagent.workflow.nodes import bootstrap as bootstrap_nodes
            from leagent.workflow.registry import FlowWorkflowRegistry
            from leagent.workflow.server.event_bus import InMemoryEventBus
            from leagent.workflow.services import WorkflowService

            wf_settings = self.settings.workflow
            await bootstrap_nodes(
                custom_dirs=(
                    [wf_settings.custom_nodes_dir]
                    if wf_settings.custom_nodes_dir
                    else None
                )
            )

            event_bus = InMemoryEventBus()
            # Share the bus with the WS router (`get_event_bus(service_manager)`)
            # so publishers (executor progress handler) and subscribers
            # (WebSocket endpoints) use one transport.
            self._workflow_event_bus = event_bus

            tool_registry = None
            tool_executor = None
            try:
                from leagent.tools.registry import get_registry as _get_tool_registry

                tool_registry = _get_tool_registry()
                tool_executor = self.runtime_context.executor
            except Exception:
                logger.warning("Tool registry/executor not available for workflow engine", exc_info=True)

            agent_runtime = None
            try:
                from leagent.runtime import AgentRuntime

                agent_runtime = AgentRuntime(self.runtime_context)
            except Exception:
                logger.warning("Agent runtime not available for workflow engine", exc_info=True)

            from leagent.workflow.state_store import build_workflow_state_store

            state_store = build_workflow_state_store(self._db)

            executor = WorkflowExecutor(
                tool_registry=tool_registry,
                tool_executor=tool_executor,
                llm_service=self._llm_service,
                review_service=None,
                workflow_registry=None,
                agent_runtime=agent_runtime,
                cache_mode=wf_settings.cache_mode,
                cache_provider=None,
                state_store=state_store,
            )

            async def _publish_to_event_bus(event: Any) -> None:
                try:
                    await event_bus.publish_event(event.prompt_id, event)
                except Exception:
                    logger.warning("Workflow event bus publish failed", exc_info=True)
                try:
                    if self._event is not None:
                        from leagent.runtime.execution_registry import get_execution_run_registry

                        exec_run = get_execution_run_registry().get_by_prompt_id(
                            getattr(event, "prompt_id", "") or ""
                        )
                        run_id = exec_run.run_id if exec_run else None
                        await self._event.bridge_workflow_progress_event(
                            event, run_id=run_id
                        )
                except Exception:
                    logger.debug("Workflow EventManager bridge failed", exc_info=True)

            executor.register_progress_handler(_publish_to_event_bus)
            registry = FlowWorkflowRegistry(self._db)

            from leagent.workflow.prompt_map import build_prompt_map
            prompt_map = build_prompt_map(None)

            self._workflow_service = WorkflowService(
                db=self._db,
                executor=executor,
                registry=registry,
                queue=None,
                prompt_map=prompt_map,
            )
            logger.info("WorkflowService initialized (async enqueue, no broker queue)")
        except Exception:
            logger.warning("WorkflowService initialization skipped", exc_info=True)

    async def _start_cron(self) -> None:
        try:
            from leagent.cron import CronExecutor, CronHookManager, CronManager

            if self._db:
                from leagent.cron.repository import DatabaseJobRepository
                repository = DatabaseJobRepository(self._db)
                await repository.initialize()
            else:
                from leagent.cron import JsonJobRepository
                repository = JsonJobRepository("/tmp/leagent/cron_jobs.json", auto_save_interval=30.0)
                await repository.initialize()

            workflow_executor = None
            workflow_registry = None
            if self._workflow_service is not None:
                workflow_executor = self._workflow_service._executor
                workflow_registry = self._workflow_service._registry

            executor = CronExecutor(
                workflow_executor=workflow_executor,
                workflow_registry=workflow_registry,
                workflow_service=self._workflow_service,
                default_timeout_sec=3600,
                max_concurrent_executions=10,
            )
            hook_manager = CronHookManager()
            self._cron = CronManager(
                repository=repository,
                executor=executor,
                hook_manager=hook_manager,
                timezone="UTC",
                redis_client=None,
            )
            await self._cron.start()
            logger.info("Cron manager started")
        except Exception:
            logger.warning("Cron manager initialization skipped", exc_info=True)

    async def _start_task_manager(self) -> None:
        try:
            from leagent.services.task_manager import init_task_manager
            manager = init_task_manager(self.settings)
            if self._event is not None:
                manager.attach_event_manager(self._event)
            self._task_manager = manager
            try:
                from leagent.tasks.registration import register_default_handlers
                registered = await register_default_handlers(self, manager)
                logger.info("TaskManager initialised with %d handler(s)", registered)
            except Exception:
                logger.warning("TaskManager handler registration skipped", exc_info=True)
        except Exception:
            logger.warning("TaskManager initialization skipped", exc_info=True)

    async def _start_file_service(self) -> None:
        try:
            from leagent.file.service import FileService
            from leagent.file.storage.local import LocalStorageBackend

            upload_dir = self.settings.files.upload_dir
            backend = LocalStorageBackend(upload_dir)
            self._file_service = FileService(
                default_backend=backend,
                default_backend_name="local",
                cache=None,
                database=self._db,
            )
            logger.info("FileService initialised (root=%s)", upload_dir)
        except Exception:
            logger.warning("FileService initialisation skipped", exc_info=True)

    async def _start_file_processing(self) -> None:
        try:
            from leagent.services.file_processing.service import FileProcessingService
            self._file_processing = FileProcessingService()
            logger.info("File processing service initialized")
        except Exception:
            logger.warning("File processing service initialization skipped", exc_info=True)

    async def _start_session_manager(self) -> None:
        try:
            from leagent.services.session.manager import SessionManager
            if self._db is None:
                return
            self._session_manager = SessionManager(
                self.settings,
                cache=None,
                database=self._db,
                file_service=self._file_service,
            )
            logger.info("SessionManager initialised (SQLite-only)")
        except Exception:
            logger.warning("SessionManager initialisation skipped", exc_info=True)

    async def _start_agent_memory(self) -> None:
        if self._db is None:
            return
        try:
            from leagent.memory.agent_memory import AgentMemory
            from leagent.memory.embeddings import (
                LLMServiceEmbeddingProvider,
                NullEmbeddingProvider,
            )
            from leagent.memory.episodic import EpisodicStore
            from leagent.memory.procedural import ProceduralStore
            from leagent.memory.semantic import SemanticStore

            embedding_dim = int(getattr(self.settings.llm, "embedding_dim", 1024) or 1024)

            if self._llm_service is not None:
                embeddings = LLMServiceEmbeddingProvider(
                    self._llm_service,
                    redis=None,
                    model=getattr(self.settings.llm, "embedding_model", None),
                    dimension=embedding_dim,
                )
            else:
                embeddings = NullEmbeddingProvider(dimension=embedding_dim)

            from leagent.memory.vector import MilvusConnectionConfig
            vector_connection = MilvusConnectionConfig(enabled=False)

            episodic = EpisodicStore(
                database=self._db,
                embeddings=embeddings,
                vector_connection=vector_connection,
            )
            semantic = SemanticStore(
                database=self._db,
                embeddings=embeddings,
                vector_connection=vector_connection,
            )
            procedural = ProceduralStore(
                database=self._db,
                embeddings=embeddings,
                vector_connection=vector_connection,
            )
            self._agent_memory = AgentMemory(
                episodic=episodic,
                semantic=semantic,
                procedural=procedural,
                embeddings=embeddings,
            )
            logger.info("AgentMemory initialised (embedding_dim=%d, vector=off)", embedding_dim)
        except Exception:
            logger.warning("AgentMemory initialisation skipped", exc_info=True)


_service_manager: ServiceManager | None = None


def get_service_manager() -> ServiceManager:
    from leagent.main import get_service_manager as _main_get_service_manager
    try:
        return _main_get_service_manager()
    except AssertionError:
        if _service_manager is None:
            raise RuntimeError("ServiceManager not initialized") from None
        return _service_manager


def init_service_manager(settings: "Settings") -> ServiceManager:
    global _service_manager
    _service_manager = ServiceManager(settings)
    return _service_manager
