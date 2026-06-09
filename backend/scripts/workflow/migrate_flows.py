"""One-shot migration of legacy ``Flow.data`` rows to the canonical workflow schema.

The workflow engine has a **single** canonical document shape — there
is no runtime version migration. This script is the only place that
understands historical payloads; run it **once** per environment before
deploying the new engine.

Historical payload shapes accepted as input:

* v1 (nodes as list, top-level ``edges``, ``version: "1.0"``).
* v2 transitional (nodes as dict but still carrying ``schema_version``).
* Already canonical (handled as a no-op).

Everything else is reported as ``failed`` and must be hand-fixed before
re-running with ``--commit``.

Usage::

    python -m scripts.workflow.migrate_flows --dry-run      # preview (default)
    python -m scripts.workflow.migrate_flows --commit       # apply
    python -m scripts.workflow.migrate_flows --scan-only    # audit-only: no upgrade, just count non-canonical rows
    python -m scripts.workflow.migrate_flows --relayout     # (re)compute the ``ui`` layout block for existing rows
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _is_canonical(raw: Any) -> bool:
    return (
        isinstance(raw, dict)
        and isinstance(raw.get("nodes"), dict)
        and isinstance(raw.get("control"), dict)
        and all(
            isinstance(n, dict) and "class_type" in n
            for n in raw["nodes"].values()
        )
    )


def _legacy_upgrade(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert legacy/authoring dict into canonical shape via shared converter."""
    from leagent.workflow.io.authoring import to_canonical

    if "workflow" in raw and isinstance(raw["workflow"], dict):
        raw = raw["workflow"]

    out = to_canonical(raw)
    out.pop("schema_version", None)
    out.pop("version", None)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def _run(
    *,
    commit: bool,
    limit: int | None,
    scan_only: bool,
    relayout: bool,
) -> int:
    from sqlmodel import select

    from leagent.config import get_settings
    from leagent.db.service import init_database_service
    from leagent.db.models.flow import Flow
    from leagent.workflow.io import load, to_json, validate
    from leagent.workflow.layout import layout_document
    from leagent.workflow.nodes import bootstrap as bootstrap_nodes

    settings = get_settings()
    db = init_database_service(settings)
    await bootstrap_nodes()

    migrated = 0
    skipped_canonical = 0
    unchanged = 0
    failed = 0
    non_canonical_seen = 0
    relayouted = 0

    async with db.session() as session:
        q = select(Flow).where(Flow.is_deleted == False)  # noqa: E712
        if limit:
            q = q.limit(limit)
        result = await session.exec(q)
        flows = list(result.all())

    logger.info(
        "flow_migration_scan",
        total=len(flows),
        commit=commit,
        scan_only=scan_only,
        relayout=relayout,
    )

    for flow in flows:
        if not flow.data:
            continue
        try:
            raw: Any = json.loads(flow.data)
        except json.JSONDecodeError:
            logger.warning("flow_unparseable", flow_id=str(flow.id))
            failed += 1
            continue

        already_canonical = (
            _is_canonical(raw) and "schema_version" not in raw and "version" not in raw
        )

        if relayout:
            # Relayout path: upgrade if needed, then (re)compute the UI
            # block even for already-canonical rows so a one-shot call
            # backfills positions for flows created before this feature.
            if scan_only:
                has_ui = isinstance(raw, dict) and isinstance(raw.get("ui"), dict)
                if not has_ui:
                    logger.info(
                        "flow_missing_ui", flow_id=str(flow.id), name=flow.name
                    )
                continue
            try:
                upgraded = raw if already_canonical else _legacy_upgrade(raw)
                doc = load(upgraded)
                ok, _, errs = validate(doc)
                if not ok:
                    logger.error(
                        "flow_migration_validation_failed",
                        flow_id=str(flow.id),
                        errors=list(errs.keys()),
                    )
                    failed += 1
                    continue
                new_payload = to_json(layout_document(upgraded), indent=None)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "flow_relayout_failed",
                    flow_id=str(flow.id),
                    error=str(exc),
                )
                failed += 1
                continue

            if new_payload == flow.data:
                unchanged += 1
                continue

            relayouted += 1
            if commit:
                async with db.session() as session:
                    row = await session.get(Flow, flow.id)
                    if row is None:
                        continue
                    row.data = new_payload
                    session.add(row)
                    await session.commit()
            continue

        if already_canonical:
            skipped_canonical += 1
            continue

        non_canonical_seen += 1
        if scan_only:
            logger.info("flow_non_canonical", flow_id=str(flow.id), name=flow.name)
            continue

        try:
            upgraded = _legacy_upgrade(raw)
            doc = load(upgraded)
            ok, _, errs = validate(doc)
            if not ok:
                logger.error(
                    "flow_migration_validation_failed",
                    flow_id=str(flow.id),
                    errors=list(errs.keys()),
                )
                failed += 1
                continue
            new_payload = to_json(doc, indent=None)
        except Exception as exc:  # noqa: BLE001
            logger.error(
                "flow_migration_failed",
                flow_id=str(flow.id),
                error=str(exc),
            )
            failed += 1
            continue

        if new_payload == flow.data:
            unchanged += 1
            continue

        migrated += 1
        if commit:
            async with db.session() as session:
                row = await session.get(Flow, flow.id)
                if row is None:
                    continue
                row.data = new_payload
                session.add(row)
                await session.commit()

    logger.info(
        "flow_migration_summary",
        total=len(flows),
        already_canonical=skipped_canonical,
        non_canonical_seen=non_canonical_seen,
        migrated=migrated,
        relayouted=relayouted,
        unchanged=unchanged,
        failed=failed,
        committed=commit,
    )
    return failed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="One-shot migration of Flow.data to the canonical workflow schema",
    )
    parser.add_argument("--commit", action="store_true", help="Write changes to the DB")
    parser.add_argument("--dry-run", action="store_true", help="Preview only (default)")
    parser.add_argument(
        "--scan-only",
        action="store_true",
        help="List non-canonical rows without attempting conversion",
    )
    parser.add_argument(
        "--relayout",
        action="store_true",
        help="(Re)compute the UI layout block for every row; also upgrades legacy rows",
    )
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args(argv)
    commit = args.commit and not args.dry_run and not args.scan_only
    failed = asyncio.run(
        _run(
            commit=commit,
            limit=args.limit,
            scan_only=args.scan_only,
            relayout=args.relayout,
        ),
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
