"""Built-in scaffold templates for the coding-project supervisor.

Each template lives at
``leagent/services/coding_projects/templates/<name>/`` and ships:

* a tree of files that gets copied verbatim into the target project
  directory at scaffold time,
* a ``template.toml`` next to the tree containing supervisor
  metadata: which runtime kind it is, what argv to spawn, the regex
  to wait for on stdout/stderr before declaring "ready", and the
  health-check URL the API will poll.

The ``$PORT`` placeholder in argv is replaced at run time with the
allocated port, and ``$HOST`` with the configured bind host. We use
shell-style placeholders rather than ``str.format`` so template
authors don't have to escape literal ``{}`` characters in JS / TS.
"""

from __future__ import annotations

import shutil
import sys
import tomllib  # py311+
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

import structlog

logger = structlog.get_logger(__name__)


TEMPLATES_DIR = Path(__file__).resolve().parent / "template_data"


class TemplateNotFoundError(KeyError):
    """Raised when a requested template does not exist on disk."""


@dataclass(frozen=True)
class Template:
    """Metadata + on-disk file tree for a single scaffold template."""

    name: str
    runtime_kind: str
    title: str
    description: str
    files_dir: Path
    install_argv: tuple[str, ...] = ()
    start_argv: tuple[str, ...] = ()
    ready_regex: str = ""
    health_path: str = "/"
    needs_install: bool = False
    install_marker_relpath: str = ""
    extra: Mapping[str, object] = field(default_factory=dict)

    def expand_argv(
        self,
        argv: tuple[str, ...],
        *,
        host: str,
        port: int,
        preview_base: str = "/",
    ) -> tuple[str, ...]:
        """Replace ``$PORT`` / ``$HOST`` / ``$PREVIEW_BASE`` tokens in ``argv``.

        ``$PREVIEW_BASE`` is the URL prefix of the token-gated reverse
        proxy (e.g. ``/api/v1/coding-projects/{id}/preview/``); dev
        servers that support a base path (Vite) mount there so the HTML
        they emit references assets *inside* the proxy prefix. Any other
        unsupported placeholder is left as-is (which usually surfaces as
        the child failing to parse its CLI, making the bug obvious).
        """
        out: list[str] = []
        for raw in argv:
            tok = str(raw)
            tok = tok.replace("$PORT", str(port))
            tok = tok.replace("$HOST", str(host))
            tok = tok.replace("$PREVIEW_BASE", preview_base)
            out.append(tok)
        return tuple(out)

    def uses_preview_base(self) -> bool:
        """True when the dev server is started with the proxy prefix as base."""
        return any("$PREVIEW_BASE" in str(a) for a in self.start_argv)


def _coerce_str_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        return tuple(str(v) for v in value)
    if isinstance(value, str):
        return (value,)
    raise ValueError(f"Expected list[str] or str, got {type(value).__name__}")


def _load_template_meta(template_root: Path) -> Template:
    meta_file = template_root / "template.toml"
    if not meta_file.is_file():
        raise TemplateNotFoundError(
            f"template.toml missing for {template_root.name!r}"
        )
    with meta_file.open("rb") as f:
        raw = tomllib.load(f)

    runtime_kind = str(raw.get("runtime_kind", "frontend")).strip()
    title = str(raw.get("title") or template_root.name)
    description = str(raw.get("description") or "")
    install_argv = _coerce_str_tuple(raw.get("install_argv"))
    start_argv = _coerce_str_tuple(raw.get("start_argv"))
    ready_regex = str(raw.get("ready_regex") or "")
    health_path = str(raw.get("health_path") or "/")
    needs_install = bool(raw.get("needs_install", bool(install_argv)))
    install_marker = str(raw.get("install_marker") or "")

    files_dir = template_root / "files"
    if not files_dir.is_dir():
        raise TemplateNotFoundError(
            f"template {template_root.name!r} has no files/ directory"
        )

    return Template(
        name=template_root.name,
        runtime_kind=runtime_kind,
        title=title,
        description=description,
        files_dir=files_dir,
        install_argv=install_argv,
        start_argv=start_argv,
        ready_regex=ready_regex,
        health_path=health_path,
        needs_install=needs_install,
        install_marker_relpath=install_marker,
        extra={
            k: v
            for k, v in raw.items()
            if k
            not in {
                "runtime_kind",
                "title",
                "description",
                "install_argv",
                "start_argv",
                "ready_regex",
                "health_path",
                "needs_install",
                "install_marker",
            }
        },
    )


def list_templates() -> list[Template]:
    """Return every template that ships with the package."""
    if not TEMPLATES_DIR.is_dir():
        return []
    out: list[Template] = []
    for child in sorted(TEMPLATES_DIR.iterdir()):
        if not child.is_dir():
            continue
        try:
            out.append(_load_template_meta(child))
        except TemplateNotFoundError as exc:
            logger.warning(
                "coding_projects_template_skip",
                template=child.name,
                error=str(exc),
            )
    return out


def load_template(name: str) -> Template:
    """Look up a single template by directory name."""
    candidate = TEMPLATES_DIR / name
    if not candidate.is_dir():
        raise TemplateNotFoundError(f"Unknown template: {name!r}")
    return _load_template_meta(candidate)


def copy_template_into(template: Template, target: Path, *, overwrite: bool = False) -> None:
    """Copy ``template.files_dir`` into ``target`` (which is created).

    When ``overwrite`` is False the function refuses to write into a
    non-empty directory. The check is intentionally crude (just
    ``any(iterdir())``) — tightening it to "no overlap" would make
    the API surface much larger for a feature we don't need yet.
    """
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()) and not overwrite:
        raise FileExistsError(
            f"Target directory {target!s} is not empty; pass overwrite=True"
        )
    if sys.version_info >= (3, 12):
        shutil.copytree(
            template.files_dir, target, dirs_exist_ok=True
        )
    else:  # pragma: no cover — leagent requires py311+, kept defensive
        shutil.copytree(template.files_dir, target, dirs_exist_ok=True)
