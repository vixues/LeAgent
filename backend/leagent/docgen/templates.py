"""Reusable document / deck templates for the docgen subsystem.

A *doc template* is a named, parameterized skeleton stored as YAML under
``LEAGENT_HOME/templates/docgen/``. It captures everything a polished
deliverable needs — markdown body (documents) or slide list (decks) with
Jinja2 ``{{ variable }}`` placeholders, a theme, declared variables, and
default generation options — so agents can turn a one-off document into a
repeatable, brand-consistent template and instantiate it later with fresh
data.

Rendered output is *system-compatible by construction*: instantiation
produces exactly the payload shape ``document_generate`` /
``slides_generate`` consume, and saving validates a test render against the
real Document/Deck IR so broken templates are rejected up front.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

logger = structlog.get_logger(__name__)

__all__ = [
    "DocTemplate",
    "TemplateVariable",
    "delete_template",
    "list_templates",
    "load_template",
    "render_template",
    "save_template",
    "templates_dir",
]

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


def templates_dir() -> Path:
    """Doc-template YAML directory (honors ``LEAGENT_HOME``)."""
    home = Path(os.getenv("LEAGENT_HOME", str(Path.home() / ".leagent")))
    return home / "templates" / "docgen"


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class TemplateVariable(_Model):
    """One declared template variable."""

    name: str
    description: str | None = None
    default: Any = None
    required: bool = False


class DocTemplate(_Model):
    """A parameterized document or deck skeleton."""

    name: str
    kind: Literal["document", "deck"] = "document"
    description: str | None = None
    # Theme *name* (built-in or custom saved via the theming module).
    theme: str | None = None
    variables: list[TemplateVariable] = Field(default_factory=list)
    # Document templates: markdown body with Jinja2 placeholders.
    content: str | None = None
    # Deck templates: SlideSpec-shaped dicts with Jinja2 in string fields.
    slides: list[dict[str, Any]] | None = None
    # Extra document_generate / slides_generate params applied at instantiation
    # (toc, cover, header, footer, aspect, footer_text, background, ...).
    defaults: dict[str, Any] = Field(default_factory=dict)


def _validate_name(name: str) -> str:
    key = str(name).strip().lower()
    if not _NAME_RE.fullmatch(key):
        raise ValueError(
            "Template name must be 2-64 chars of lowercase letters, digits, '-' or '_'."
        )
    return key


# ---------------------------------------------------------------------------
# Rendering (Jinja2 over strings, structure-preserving for decks)
# ---------------------------------------------------------------------------


def _jinja_env() -> Any:
    from jinja2 import StrictUndefined
    from jinja2.sandbox import SandboxedEnvironment

    return SandboxedEnvironment(
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _resolve_variables(
    template: DocTemplate, variables: dict[str, Any] | None
) -> dict[str, Any]:
    supplied = dict(variables or {})
    resolved: dict[str, Any] = {}
    missing: list[str] = []
    for var in template.variables:
        if var.name in supplied:
            resolved[var.name] = supplied.pop(var.name)
        elif var.default is not None:
            resolved[var.name] = var.default
        elif var.required:
            missing.append(var.name)
        else:
            resolved[var.name] = ""
    if missing:
        raise ValueError(
            f"Missing required template variables: {', '.join(sorted(missing))}"
        )
    # Undeclared extras are still available to the template.
    resolved.update(supplied)
    return resolved


def _render_value(env: Any, value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, str):
        if "{{" in value or "{%" in value:
            return env.from_string(value).render(**variables)
        return value
    if isinstance(value, dict):
        return {k: _render_value(env, v, variables) for k, v in value.items()}
    if isinstance(value, list):
        return [_render_value(env, v, variables) for v in value]
    return value


def render_template(
    template: DocTemplate, variables: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Instantiate a template into a generation payload.

    Returns ``{"kind", "theme", "content" | "slides", **defaults}`` — the
    exact inputs ``document_generate`` / ``slides_generate`` accept.
    """
    from jinja2 import TemplateError

    env = _jinja_env()
    resolved = _resolve_variables(template, variables)

    payload: dict[str, Any] = dict(template.defaults)
    payload["kind"] = template.kind
    if template.theme is not None:
        payload["theme"] = template.theme

    try:
        if template.kind == "deck":
            if not template.slides:
                raise ValueError("Deck template has no slides.")
            payload["slides"] = _render_value(env, template.slides, resolved)
        else:
            if not template.content or not template.content.strip():
                raise ValueError("Document template has no content.")
            payload["content"] = env.from_string(template.content).render(**resolved)
    except TemplateError as exc:
        raise ValueError(f"Template rendering failed: {exc}") from exc
    return payload


def _validate_render(template: DocTemplate) -> None:
    """Test-render with defaults/placeholders and validate against the IR."""
    from leagent.docgen.markdown import parse_markdown_blocks
    from leagent.docgen.model import DeckSpec

    placeholders = {
        var.name: (var.default if var.default is not None else f"<{var.name}>")
        for var in template.variables
    }
    payload = render_template(template, placeholders)
    if template.kind == "deck":
        DeckSpec.model_validate({"slides": payload["slides"]})
    else:
        blocks = parse_markdown_blocks(payload["content"])
        if not blocks:
            raise ValueError("Document template renders to empty content.")


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


def save_template(template: DocTemplate, *, overwrite: bool = True) -> dict[str, Any]:
    """Validate + persist a template; returns name/path/variables summary."""
    import yaml

    key = _validate_name(template.name)
    template = template.model_copy(update={"name": key})
    _validate_render(template)

    directory = templates_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{key}.yaml"
    if path.exists() and not overwrite:
        raise ValueError(f"Template '{key}' already exists (pass overwrite to replace).")

    path.write_text(
        yaml.safe_dump(
            template.model_dump(exclude_none=True), allow_unicode=True, sort_keys=False
        ),
        encoding="utf-8",
    )
    logger.info("docgen_template_saved", name=key, kind=template.kind, path=str(path))
    return {
        "name": key,
        "kind": template.kind,
        "path": str(path),
        "variables": [v.model_dump(exclude_none=True) for v in template.variables],
    }


def load_template(name: str) -> DocTemplate | None:
    """Load a template by name, or None when absent/invalid."""
    import yaml

    directory = templates_dir()
    for ext in (".yaml", ".yml"):
        path = directory / f"{name}{ext}"
        if not path.is_file():
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            logger.exception("docgen_template_load_failed", path=str(path))
            return None
        if not isinstance(raw, dict):
            return None
        raw.setdefault("name", name)
        try:
            return DocTemplate.model_validate(raw)
        except Exception:  # noqa: BLE001
            logger.exception("docgen_template_invalid", path=str(path))
            return None
    return None


def list_templates() -> list[dict[str, Any]]:
    """Summaries of stored templates (name, kind, description, variables)."""
    out: list[dict[str, Any]] = []
    directory = templates_dir()
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.y*ml")):
        tpl = load_template(path.stem)
        if tpl is None:
            continue
        out.append(
            {
                "name": tpl.name,
                "kind": tpl.kind,
                "description": tpl.description,
                "variables": [v.model_dump(exclude_none=True) for v in tpl.variables],
            }
        )
    return out


def delete_template(name: str) -> bool:
    """Delete a stored template; returns whether anything was removed."""
    key = _validate_name(name)
    removed = False
    directory = templates_dir()
    for ext in (".yaml", ".yml"):
        path = directory / f"{key}{ext}"
        if path.is_file():
            path.unlink()
            removed = True
    if removed:
        logger.info("docgen_template_deleted", name=key)
    return removed
