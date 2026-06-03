#!/usr/bin/env python3
"""Migrate LeAgent from tier1/tier2 config to providers.yaml v2 task routing.

Usage (from repo root)::

    cd backend && uv run python ../scripts/migrate_to_v2.py
    cd backend && uv run leagent models migrate
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_BACKEND = _REPO / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate tier config to v2 task routing")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    parser.add_argument("--env-only", action="store_true", help="Migrate ~/.leagent/.env only")
    parser.add_argument("--providers-only", action="store_true", help="Migrate providers.yaml only")
    args = parser.parse_args()

    from leagent.config.migrate_v2 import run_migration

    report = run_migration(
        migrate_env=not args.providers_only,
        migrate_providers=not args.env_only,
        dry_run=args.dry_run,
        in_place=True,
    )

    print(json.dumps(
        {
            "env_changed": report.env_changed,
            "env_removed_keys": report.env_removed_keys,
            "env_added_keys": report.env_added_keys,
            "providers_changed": report.providers_changed,
            "providers_backup": str(report.providers_backup) if report.providers_backup else None,
            "routing_tasks": report.routing_tasks,
            "notes": report.notes,
        },
        indent=2,
        ensure_ascii=False,
    ))

    if args.dry_run:
        print("\n(dry-run: no files written)", file=sys.stderr)
    else:
        print("\nMigration complete. Restart LeAgent.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
