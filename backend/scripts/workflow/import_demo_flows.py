"""Import canonical demo workflow YAML files into the ``flows`` table.

Run from ``backend/``::

    uv run python -m scripts.workflow.import_demo_flows

Uses the same persistence shape as ``POST /api/v1/workflow/flows/import``:
``load()`` → ``export()`` → ``Flow.data`` JSON.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog
from sqlmodel import select

logger = structlog.get_logger(__name__)


def _repo_root() -> Path:
    # backend/scripts/workflow/import_demo_flows.py → parents[3] = repo root
    return Path(__file__).resolve().parents[3]


def _default_demo_dir() -> Path:
    return _repo_root() / "config" / "demo-workflows"


async def _import_all(
    *,
    demo_dir: Path,
    user_id: UUID,
    skip_existing: bool,
) -> int:
    from leagent.config import get_settings
    from leagent.services.database.models.flow import Flow
    from leagent.services.database.service import init_database_service
    from leagent.workflow.io import export, load, validate
    from leagent.workflow.nodes import bootstrap, get_registry

    if not demo_dir.is_dir():
        logger.error("demo_dir_missing", path=str(demo_dir))
        return 2

    yaml_files = sorted(demo_dir.glob("demo-*.yaml"))
    if not yaml_files:
        logger.error("no_demo_yaml", path=str(demo_dir))
        return 2

    await bootstrap()
    registry = get_registry()
    settings = get_settings()
    db = init_database_service(settings)

    created: list[dict[str, Any]] = []
    async with db.session() as session:
        for path in yaml_files:
            doc = load(path)
            ok, _, errors = validate(doc, registry=registry)
            if not ok:
                logger.error("demo_flow_validate_failed", path=str(path), errors=errors)
                return 1

            name = doc.name or doc.id or path.stem
            if skip_existing:
                dup = await session.exec(
                    select(Flow).where(
                        Flow.user_id == user_id,
                        Flow.name == name,
                        Flow.is_deleted == False,  # noqa: E712
                    )
                )
                if dup.first() is not None:
                    logger.info("demo_flow_skip_existing", name=name)
                    continue

            flow = Flow(
                name=name,
                description=doc.description or "",
                data=json.dumps(export(doc)),
                user_id=user_id,
                folder_id=None,
            )
            session.add(flow)
            await session.flush()
            await session.refresh(flow)
            created.append({"flow_id": str(flow.id), "name": flow.name, "path": str(path)})

        await session.commit()

    for row in created:
        print(f"Imported {row['name']}  flow_id={row['flow_id']}")
    if not created and skip_existing:
        print("No new flows imported (all names already exist or no files).")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dir",
        type=Path,
        default=None,
        help=f"Directory with demo-*.yaml (default: {_default_demo_dir()})",
    )
    parser.add_argument(
        "--user-id",
        type=UUID,
        default=None,
        help="Owner user UUID (default: LOCAL_USER_ID)",
    )
    parser.add_argument(
        "--no-skip-existing",
        action="store_true",
        help="Import even when a flow with the same name already exists for the user.",
    )
    args = parser.parse_args()
    demo_dir = args.dir or _default_demo_dir()
    from leagent.services.auth.service import LOCAL_USER_ID

    user_id = args.user_id or LOCAL_USER_ID
    skip_existing = not args.no_skip_existing
    code = asyncio.run(_import_all(demo_dir=demo_dir, user_id=user_id, skip_existing=skip_existing))
    sys.exit(code)


if __name__ == "__main__":
    main()
