"""Guard: core architectural packages use the canonical logger only.

``leagent.utils.logging.get_logger`` is the single accessor. Raw
``logging.getLogger`` / ``structlog.get_logger`` idioms bypass the shared
pipeline (correlation fields, OTel injection) and are forbidden inside the
agent/runtime/SDK core. The allowlist below is intentionally narrow — it is
the set already cleaned by the architecture upgrade; new core code must keep
it clean, and the allowlist can grow as more packages are converted.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_PKG = _BACKEND / "leagent"

# Directories whose every module must use the canonical logger.
CLEAN_DIRS = [
    _PKG / "sdk",
    _PKG / "runtime",
]

# Individual files that must use the canonical logger.
CLEAN_FILES = [
    _PKG / "agent" / "query.py",
    _PKG / "agent" / "subagent.py",
    _PKG / "telemetry" / "otel.py",
    _PKG / "services" / "session" / "manager.py",
    _PKG / "services" / "session" / "store.py",
    _PKG / "tasks" / "handlers" / "agent_handler.py",
    _PKG / "api" / "v1" / "chat_deps.py",
]

FORBIDDEN = ("logging.getLogger(", "structlog.get_logger(")


def _iter_clean_files():
    for d in CLEAN_DIRS:
        yield from d.rglob("*.py")
    yield from CLEAN_FILES


def test_core_uses_canonical_logger():
    offenders: list[str] = []
    for path in _iter_clean_files():
        text = path.read_text(encoding="utf-8")
        for idiom in FORBIDDEN:
            if idiom in text:
                offenders.append(f"{path.relative_to(_BACKEND)}: {idiom}")
    assert not offenders, (
        "Core modules must use leagent.utils.logging.get_logger; found: "
        + "; ".join(offenders)
    )


def test_telemetry_logging_shim_removed():
    """The second logging-config entrypoint must stay gone."""
    assert not (_PKG / "telemetry" / "logging.py").exists()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
