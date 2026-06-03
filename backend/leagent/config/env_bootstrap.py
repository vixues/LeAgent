"""Populate os.environ from dotenv files before Settings is instantiated.

Load order (``override=False``): cwd ``.env`` first, then ``$LEAGENT_HOME/.env``.

If deprecated ``*_TIER*`` variables are still present, startup fails with a pointer
to ``leagent models migrate`` (one-shot migration; no runtime tier compatibility).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from leagent.config.constants import LEAGENT_HOME
from leagent.config.tier_env_guard import detect_legacy_tier_env, detect_obsolete_llm_env


def _set_env_if_empty(name: str, value: str) -> None:
    if value and not (os.getenv(name) or "").strip():
        os.environ[name] = value


def _bridge_dashscope_key() -> None:
    raw = (os.getenv("DASHSCOPE_API_KEY") or "").strip()
    if not raw:
        return
    _set_env_if_empty("LEAGENT_LLM__DASHSCOPE_API_KEY", raw)


def _fail_on_legacy_tier_env() -> None:
    if any("migrate" in (arg or "") for arg in sys.argv):
        return
    legacy = detect_obsolete_llm_env()
    if not legacy:
        return
    keys = ", ".join(legacy[:6])
    suffix = "…" if len(legacy) > 6 else ""
    msg = (
        "Legacy tier1/tier2 and LLM_* model env vars are no longer supported.\n"
        f"Found: {keys}{suffix}\n\n"
        "Run once to migrate ~/.leagent/.env and providers.yaml:\n"
        "  cd backend && uv run leagent models migrate\n"
        "Or:\n"
        "  cd backend && uv run python ../scripts/migrate_to_v2.py\n"
    )
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def load_dotenv_files() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        _bridge_dashscope_key()
        _fail_on_legacy_tier_env()
        return

    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        load_dotenv(cwd_env, override=False)

    home_env = LEAGENT_HOME / ".env"
    if home_env.is_file() and home_env.resolve() != cwd_env.resolve():
        load_dotenv(home_env, override=False)

    _bridge_dashscope_key()
    _fail_on_legacy_tier_env()


load_dotenv_files()
