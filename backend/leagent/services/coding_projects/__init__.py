"""Unified coding-project service layer.

This package is the single backend home for everything related to
"a coding project" — both the static side (an existing folder the
user has marked as a project, accessed via ``Folder.is_project`` and
``Folder.project_path``) and the dynamic side (a managed scaffold the
agent created under ``CODING_PROJECTS_ROOT`` and runs through a
supervised dev server).

Layout:

* :mod:`paths` — path validation that enforces
  ``FILES_PROJECTS_ALLOWED_ROOTS`` and resolves user input to an
  absolute, existing directory before any filesystem read; also the
  ``Folder``-ownership check.
* :mod:`git` — async ``git`` subprocess wrapper used by the folder
  project HTTP endpoints (log / show / diff / status / init).
* :mod:`binaries` — argv allow-list (``CODING_PROJECTS_ALLOWED_BINARIES``)
  applied before spawning a child process.
* :mod:`ports` — free-port allocator with a per-project lease table.
* :mod:`templates` — loaders that copy a template tree into an empty
  directory and parse its ``template.toml`` metadata.
* :mod:`runtime` — :class:`DevServerSupervisor` that spawns, watches,
  log-streams, and stops a child process. Cross-platform PG kill.
* :mod:`proxy` — HTTP and WebSocket reverse-proxy helpers used by the
  API to forward browser traffic into the supervised child.
* :mod:`preview_tokens` — short-lived JWT signed with the same secret
  as the canvas preview (audience: ``leagent-coding-preview``).
* :mod:`manager` — :class:`CodingProjectManager` is the service
  facade: scaffold / list / start / stop / delete / tail-logs.

The two flavours of project — adopted folder vs agent scaffold — share
the same path policy, the same git wrapper, and (when running) the same
supervisor / proxy. Keeping them in one package eliminates the older
static-project package vs live-runtime package split.
"""

from leagent.services.coding_projects.binaries import (
    CodingBinaryNotAllowedError,
    assert_argv_allowed,
    assert_path_under_roots,
    get_allowed_binaries,
    parse_allowed_binaries,
    resolve_executable,
)
from leagent.services.coding_projects.git import (
    GitCommandError,
    GitCommit,
    GitNotInstalledError,
    GitStatusEntry,
    git_diff_for_commit,
    git_diff_worktree,
    git_init,
    git_log,
    git_show_file,
    git_status_porcelain,
    is_git_repo,
    run_git,
)
from leagent.services.coding_projects.manager import (
    CodingProjectManager,
    CodingProjectNotFoundError,
    CodingProjectQuotaError,
    get_coding_projects_service,
    init_coding_projects_service,
)
from leagent.services.coding_projects.paths import (
    ProjectPathSafetyError,
    assert_folder_owner,
    get_allowed_project_roots,
    is_path_under,
    resolve_owned_project_folder,
    validate_project_path,
)
from leagent.services.coding_projects.ports import (
    PortAllocationError,
    PortAllocator,
)
from leagent.services.coding_projects.preview_tokens import (
    decode_preview_token,
    mint_preview_token,
    preview_query_path,
)
from leagent.services.coding_projects.runtime import (
    DevServerSupervisor,
    LogLine,
    RunningServer,
    ServerNotRunningError,
    StartTimeoutError,
)
from leagent.services.coding_projects.templates import (
    Template,
    TemplateNotFoundError,
    list_templates,
    load_template,
)

__all__ = [
    # paths
    "ProjectPathSafetyError",
    "assert_folder_owner",
    "get_allowed_project_roots",
    "is_path_under",
    "resolve_owned_project_folder",
    "validate_project_path",
    # git
    "GitCommandError",
    "GitNotInstalledError",
    "GitCommit",
    "GitStatusEntry",
    "run_git",
    "is_git_repo",
    "git_init",
    "git_log",
    "git_show_file",
    "git_diff_for_commit",
    "git_diff_worktree",
    "git_status_porcelain",
    # binaries
    "CodingBinaryNotAllowedError",
    "assert_argv_allowed",
    "assert_path_under_roots",
    "get_allowed_binaries",
    "parse_allowed_binaries",
    "resolve_executable",
    # manager
    "CodingProjectManager",
    "CodingProjectNotFoundError",
    "CodingProjectQuotaError",
    "get_coding_projects_service",
    "init_coding_projects_service",
    # ports
    "PortAllocationError",
    "PortAllocator",
    # preview tokens
    "decode_preview_token",
    "mint_preview_token",
    "preview_query_path",
    # runtime
    "DevServerSupervisor",
    "LogLine",
    "RunningServer",
    "ServerNotRunningError",
    "StartTimeoutError",
    # templates
    "Template",
    "TemplateNotFoundError",
    "list_templates",
    "load_template",
]
