"""``leagent workflow-worker`` — launch a worker process.

Invoked as either::

    leagent workflow-worker --concurrency 2
    python -m leagent.workflow.cli.workflow_worker

Reads concurrency from config (or CLI flags) and starts
a :class:`WorkflowWorker` attached to the configured integration
services.
"""

from __future__ import annotations

import asyncio
import sys

import click

from leagent.utils.logging import get_logger

logger = get_logger(__name__)


@click.command("workflow-worker")
@click.option("--concurrency", default=None, type=int, help="Parallel jobs per worker.")
@click.option("--queue", default=None, type=click.Choice(["memory"]),
              help="Queue backend override.")
@click.option("--custom-nodes-dir", default=None, type=click.Path(),
              help="Directory to scan for custom node packs.")
def workflow_worker(concurrency: int | None, queue: str | None, custom_nodes_dir: str | None) -> None:
    """Start a workflow worker loop. Exits on SIGTERM / SIGINT."""
    from leagent.config.settings import get_settings
    from leagent.utils.logging import setup_logging

    settings = get_settings()
    setup_logging(level=settings.log_level, log_format=settings.log_format,
                  json_output=not settings.debug)
    try:
        asyncio.run(_run(concurrency=concurrency, queue_backend=queue,
                         custom_nodes_dir=custom_nodes_dir))
    except KeyboardInterrupt:
        sys.exit(0)


async def _run(
    *,
    concurrency: int | None,
    queue_backend: str | None,
    custom_nodes_dir: str | None,
) -> None:
    from leagent.config import get_settings
    from leagent.services.service_manager import get_service_manager
    from leagent.workflow.engine.executor import WorkflowExecutor
    from leagent.workflow.queue.memory import InMemoryPromptQueue
    from leagent.workflow.server.event_bus import ExecutionEventBus, get_event_bus
    from leagent.workflow.worker import (
        WorkerOptions,
        WorkflowWorker,
        make_db_flow_loader,
    )

    settings = get_settings()
    try:
        sm = get_service_manager()
    except RuntimeError:
        from leagent.services.service_manager import init_service_manager
        sm = init_service_manager(settings)
    if not sm.is_started:
        await sm.start_all()

    wf_settings = settings.workflow

    queue = InMemoryPromptQueue()

    tool_registry = None
    tool_executor = None
    try:
        from leagent.bootstrap import bootstrap_tools
        from leagent.tools.executor import ToolExecutor
        from leagent.tools.registry import get_registry

        summary = await bootstrap_tools()
        tool_registry = get_registry()
        tool_executor = ToolExecutor(registry=tool_registry, service_manager=sm)
        logger.info(
            "workflow_worker_tools_ready",
            tools=summary["tools"],
            nodes=len(summary["nodes"]),
        )
    except Exception:  # noqa: BLE001
        logger.warning("tool_services_unavailable_for_worker", exc_info=True)

    agent_runtime = None
    try:
        from leagent.runtime import AgentRuntime

        agent_runtime = AgentRuntime.from_service_manager(sm, executor=tool_executor)
    except Exception:  # noqa: BLE001
        logger.warning("agent_runtime_unavailable_for_worker", exc_info=True)

    executor = WorkflowExecutor(
        tool_registry=tool_registry,
        tool_executor=tool_executor,
        llm_service=sm.llm_service,
        review_service=None,
        workflow_registry=None,
        agent_runtime=agent_runtime,
        cache_mode=wf_settings.cache_mode,
    )

    event_bus: ExecutionEventBus = await get_event_bus(sm)

    options = WorkerOptions(
        concurrency=concurrency or wf_settings.worker_concurrency,
        custom_nodes_dir=custom_nodes_dir or wf_settings.custom_nodes_dir or None,
    )

    worker = WorkflowWorker(
        queue=queue,
        executor=executor,
        flow_loader=make_db_flow_loader(sm.database_service) if sm.database_service else _null_flow_loader,
        publish=event_bus.publish_event,
        update_execution_state=(
            sm.workflow_service.update_execution_by_prompt_id
            if sm.workflow_service is not None
            else None
        ),
        options=options,
    )
    logger.info(
        "workflow_worker_starting",
        concurrency=options.concurrency,
        queue=queue_backend or "memory",
    )
    await worker.start()


async def _null_flow_loader(flow_id: str):  # type: ignore[no-untyped-def]
    return None


if __name__ == "__main__":
    workflow_worker()
