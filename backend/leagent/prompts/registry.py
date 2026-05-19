"""File-system registry for prompt templates.

Templates live under ``leagent/prompts/templates/*.md`` and use YAML
front-matter for metadata. The body (everything after the closing
``---``) is used as the Persona layer source text.

Front-matter schema::

    ---
    name: default_agent         # variant name (required)
    variant: default            # optional sub-variant (defaults to "default")
    layers:                     # optional - limits which layers run
      - persona
      - capabilities
      - policies
      - environment
      - project_memory
      - recall
      - session_state
      - turn_extras
    policies:                   # additional policy snippets (template names)
      - file_access
      - database_tool
    budget_chars:               # per-layer char cap overrides
      capabilities: 2000
    tags: [agent, office]
    description: Short, human-readable summary.
    ---

    You are LeAgent. ... persona body ...

The registry scans the templates directory on first use and caches
parsed :class:`PromptVariant` instances. In development hot-reload is
cheap (mtime check) so test fixtures can mutate templates between
runs. Production installs flip hot-reload off in settings.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import structlog
import yaml

from leagent.prompts.types import PromptVariant

_DEFAULT_LAYERS: tuple[str, ...] = (
    "persona",
    "capabilities",
    "policies",
    "environment",
    "project_memory",
    "recall",
    "session_state",
    "turn_extras",
)

logger = structlog.get_logger(__name__)

_BUILTIN_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"


class PromptTemplateNotFound(LookupError):
    """Raised when no variant matches ``name`` / ``variant``."""

    def __init__(self, name: str, variant: str, searched: list[Path]):
        self.name = name
        self.variant = variant
        self.searched = searched
        super().__init__(
            f"Prompt template '{name}' (variant={variant}) not found; "
            f"searched {[str(p) for p in searched]}"
        )


class PromptTemplateParseError(ValueError):
    """Raised when a template's front-matter or body is malformed."""


class PromptRegistry:
    """Load and cache prompt variants from the file system.

    The registry is process-safe via an internal lock. It never mutates
    the template files on disk — writes are the purview of the admin
    UI (a future concern) or the author editing the file manually.
    """

    def __init__(
        self,
        *,
        templates_dir: Path | str | None = None,
        hot_reload: bool = False,
    ) -> None:
        self._roots: list[Path] = []
        if templates_dir is not None:
            root = Path(templates_dir).resolve()
            if root.exists():
                self._roots.append(root)
        if _BUILTIN_TEMPLATES_DIR.exists() and _BUILTIN_TEMPLATES_DIR not in self._roots:
            self._roots.append(_BUILTIN_TEMPLATES_DIR)
        self._hot_reload = hot_reload
        self._cache: dict[str, tuple[float, PromptVariant]] = {}
        self._lock = threading.Lock()

    @property
    def roots(self) -> list[Path]:
        return list(self._roots)

    def get(self, name: str, variant: str = "default") -> PromptVariant:
        """Return the :class:`PromptVariant` for ``name``/``variant``.

        Raises :class:`PromptTemplateNotFound` when no file matches.
        """
        key = f"{name}:{variant}"
        path = self._locate(name, variant)
        if path is None:
            raise PromptTemplateNotFound(
                name=name, variant=variant, searched=list(self._roots)
            )
        with self._lock:
            entry = self._cache.get(key)
            mtime = path.stat().st_mtime
            if entry is not None and (not self._hot_reload or entry[0] == mtime):
                return entry[1]
            parsed = self._parse_file(path, default_name=name, default_variant=variant)
            self._cache[key] = (mtime, parsed)
            return parsed

    def try_get(self, name: str, variant: str = "default") -> PromptVariant | None:
        try:
            return self.get(name, variant)
        except PromptTemplateNotFound:
            return None

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    # -- loading --------------------------------------------------------

    def _locate(self, name: str, variant: str) -> Path | None:
        """Return the first matching file across the configured roots.

        Search order per root:
          1. ``<name>.<variant>.md``
          2. ``<name>/<variant>.md``
          3. ``<name>.md`` (only for ``variant='default'``)
        """
        candidates: list[str] = [f"{name}.{variant}.md", f"{name}/{variant}.md"]
        if variant == "default":
            candidates.append(f"{name}.md")
        for root in self._roots:
            for rel in candidates:
                candidate = root / rel
                if candidate.is_file():
                    return candidate
        return None

    def _parse_file(
        self, path: Path, *, default_name: str, default_variant: str
    ) -> PromptVariant:
        raw = path.read_text(encoding="utf-8")
        front_matter, body = _split_front_matter(raw)
        meta: dict[str, Any] = {}
        if front_matter:
            try:
                meta = yaml.safe_load(front_matter) or {}
            except yaml.YAMLError as exc:
                raise PromptTemplateParseError(
                    f"Invalid YAML front-matter in {path}: {exc}"
                ) from exc
            if not isinstance(meta, dict):
                raise PromptTemplateParseError(
                    f"Front-matter in {path} must be a mapping, got {type(meta).__name__}"
                )
        name = str(meta.get("name") or default_name)
        variant = str(meta.get("variant") or default_variant)
        layers = meta.get("layers")
        budget_chars = meta.get("budget_chars") or {}
        tags = meta.get("tags") or []
        policies = meta.get("policies") or []
        requires_tools = meta.get("requires_tools") or []
        description = str(meta.get("description") or "")
        return PromptVariant(
            name=name,
            variant=variant,
            body=body.strip(),
            layers=[str(x) for x in layers] if layers else list(_DEFAULT_LAYERS),
            budget_chars={str(k): int(v) for k, v in (budget_chars or {}).items()},
            tags=[str(t) for t in tags],
            policies=[str(p) for p in policies],
            requires_tools=[str(t) for t in requires_tools],
            description=description,
            source_path=str(path),
        )


def _split_front_matter(raw: str) -> tuple[str, str]:
    """Return ``(front_matter, body)`` for a file with optional YAML header.

    Accepts the conventional ``---\\n...\\n---\\n`` delimiter. If the file
    does not start with ``---`` the whole content is treated as body.
    """
    if not raw.startswith("---"):
        return "", raw
    end = raw.find("\n---", 3)
    if end == -1:
        return "", raw
    header = raw[3:end].strip()
    after = raw[end + 4 :]
    if after.startswith("\n"):
        after = after[1:]
    return header, after


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_singleton: PromptRegistry | None = None
_singleton_lock = threading.Lock()


def get_prompt_registry(
    *,
    templates_dir: Path | str | None = None,
    hot_reload: bool | None = None,
    refresh: bool = False,
) -> PromptRegistry:
    """Return (and memoise) a process-wide :class:`PromptRegistry`.

    The first call resolves ``templates_dir`` / ``hot_reload`` from
    :class:`PromptSettings` when the caller didn't pass explicit
    overrides. Subsequent calls ignore those arguments unless
    ``refresh=True`` (used by tests to pin a fixture directory).
    """
    global _singleton
    with _singleton_lock:
        if _singleton is None or refresh:
            resolved_dir = templates_dir
            resolved_hot = hot_reload
            if resolved_dir is None or resolved_hot is None:
                try:
                    from leagent.config.settings import get_settings

                    prompt_settings = get_settings().prompt
                    if resolved_dir is None and prompt_settings.templates_dir:
                        resolved_dir = prompt_settings.templates_dir
                    if resolved_hot is None:
                        resolved_hot = prompt_settings.hot_reload
                except Exception as exc:  # noqa: BLE001
                    logger.debug("prompt_settings_unavailable", error=str(exc))
            _singleton = PromptRegistry(
                templates_dir=resolved_dir,
                hot_reload=bool(resolved_hot) if resolved_hot is not None else False,
            )
        return _singleton


__all__ = [
    "PromptRegistry",
    "PromptTemplateNotFound",
    "PromptTemplateParseError",
    "get_prompt_registry",
]
