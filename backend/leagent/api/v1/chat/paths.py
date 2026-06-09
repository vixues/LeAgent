"""Filesystem path normalization shared across chat context resolution.

Leaf module (no intra-package imports) so attachment and context-source
resolvers can depend on it without creating import cycles.
"""

from __future__ import annotations

from pathlib import Path


def dedupe_resolved_paths(paths: list[str]) -> list[str]:
    """Return de-duplicated, absolutely-resolved paths while preserving order."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        if not raw:
            continue
        try:
            resolved = str(Path(raw).expanduser().resolve())
        except Exception:  # noqa: BLE001
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(resolved)
    return out


def attachment_local_path_for_sse(storage_path: str | None) -> str | None:
    """Absolute path for the UI when running in desktop/local single-machine mode.

    Returns ``None`` in multi-machine deployments where the frontend cannot read
    the backend filesystem directly.
    """
    if not storage_path or not str(storage_path).strip():
        return None
    try:
        from leagent.config.settings import get_settings

        if not get_settings().is_single_machine_profile:
            return None
        return str(Path(storage_path).expanduser().resolve(strict=False))
    except Exception:  # noqa: BLE001
        return str(storage_path).strip()
