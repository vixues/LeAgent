"""Populate os.environ from dotenv files before Settings is instantiated.

``~/.leagent/.env`` holds user-level keys (e.g. DashScope / 千问). The process
otherwise only sees the shell environment, so keys there were ignored.

Load order (``override=False``): current working directory ``.env`` first, then
``$LEAGENT_HOME/.env``, so existing process env (Docker ``-e``, exports) always
wins, project-local file fills gaps, then home file fills remaining gaps.

If only ``DASHSCOPE_API_KEY`` is set (common in CLI templates), map it to
``LEAGENT_LLM__*`` keys expected by :class:`Settings` when those are unset.
"""

from __future__ import annotations

import os
from pathlib import Path

from leagent.config.constants import LEAGENT_HOME


def _bridge_dashscope_key() -> None:
    raw = (os.getenv("DASHSCOPE_API_KEY") or "").strip()
    if not raw:
        return
    for name in (
        "LEAGENT_LLM__DASHSCOPE_API_KEY",
        "LEAGENT_LLM__TIER1_API_KEY",
        "LEAGENT_LLM__TIER2_API_KEY",
    ):
        if not (os.getenv(name) or "").strip():
            os.environ[name] = raw


def load_dotenv_files() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        _bridge_dashscope_key()
        return

    cwd_env = Path.cwd() / ".env"
    if cwd_env.is_file():
        load_dotenv(cwd_env, override=False)

    home_env = LEAGENT_HOME / ".env"
    if home_env.is_file() and home_env.resolve() != cwd_env.resolve():
        load_dotenv(home_env, override=False)

    _bridge_dashscope_key()


load_dotenv_files()
