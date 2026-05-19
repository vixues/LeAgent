"""LeAgent CLI package.

Command groups:

**Local-first (no server process)** — ``chat`` / bare ``leagent`` (interactive
``QueryEngine``-backed turns via :class:`~leagent.agent.controller.AgentController`),
``init`` (``~/.leagent``), ``rules``, ``skills``, ``models`` (``providers.yaml``),
``config`` (per-repo ``.leagent/``), ``channels`` (runtime YAML), ``env``, ``clean``,
``prune``, ``doctor``, Alembic helpers (``migrate``, ``upgrade``, ``downgrade``).

**ASGI process** — ``run``, ``serve``, ``app`` (Uvicorn / Gunicorn for ``leagent.main:app``).

**HTTP API clients** — ``workflows``, ``tasks``, ``chats``, ``cron``, ``templates``,
``webhooks`` (``LEAGENT_API_URL``, optional ``LEAGENT_API_KEY``).

**Background** — ``daemon`` (PID file under ``LEAGENT_HOME``).

**Utilities** — ``execute`` (workflow run shortcut), ``shell`` (IPython / stdlib),
``version``, one-shot ``-m``.
"""

from leagent.cli.http import CLIHttpClient, CLIHttpError, get_client
from leagent.cli.main import cli, main
from leagent.cli.utils import (
    console,
    create_table,
    format_bytes,
    format_duration,
    print_error,
    print_info,
    print_success,
    print_warning,
    prompt_confirm,
    prompt_text,
    status_badge,
)

__all__ = [
    "cli",
    "main",
    "console",
    "create_table",
    "format_bytes",
    "format_duration",
    "print_error",
    "print_info",
    "print_success",
    "print_warning",
    "prompt_confirm",
    "prompt_text",
    "status_badge",
    "CLIHttpClient",
    "CLIHttpError",
    "get_client",
]
