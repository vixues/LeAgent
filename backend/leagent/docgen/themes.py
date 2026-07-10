"""Theme system for the document generation subsystem.

One named theme drives typography, palette, spacing, and per-format font
choices for every renderer (PDF / DOCX / PPTX / HTML). Consolidates the old
``tools/gen/style_registry.py`` presets and the ``pptx_generator`` palettes.

Custom themes: YAML files in ``~/.leagent/templates/styles/`` deep-merge over
the ``professional`` base (document) or ``executive_light`` base (deck).
"""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Literal

import structlog
from pydantic import BaseModel, ConfigDict, Field

logger = structlog.get_logger(__name__)


def styles_dir() -> Path:
    """Custom-theme YAML directory (honors ``LEAGENT_HOME``)."""
    home = Path(os.getenv("LEAGENT_HOME", str(Path.home() / ".leagent")))
    return home / "templates" / "styles"


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ThemeFonts(_Model):
    """Font names for Office formats; PDF always embeds the managed face."""

    heading: str = "Calibri"
    body: str = "Calibri"
    mono: str = "Consolas"
    east_asia: str = "Microsoft YaHei"


class ThemeSizes(_Model):
    """Point sizes. Heading levels derive from h1/h2/h3 with a decay."""

    title: float = 30.0
    h1: float = 20.0
    h2: float = 16.0
    h3: float = 13.0
    body: float = 10.5
    small: float = 8.5
    code: float = 9.0

    def heading(self, level: int) -> float:
        if level <= 1:
            return self.h1
        if level == 2:
            return self.h2
        if level == 3:
            return self.h3
        return max(self.body + 0.5, self.h3 - 1.5 * (level - 3))


class ThemeColors(_Model):
    """Hex colors including leading ``#``."""

    primary: str = "#1F4E79"
    secondary: str = "#2E75B6"
    accent: str = "#ED7D31"
    text: str = "#333333"
    text_light: str = "#666666"
    background: str = "#FFFFFF"
    surface: str = "#F5F7FA"  # code blocks, callout fills, zebra rows
    border: str = "#D9D9D9"


class ThemeSpacing(_Model):
    line_spacing: float = 1.4       # body leading multiplier
    paragraph_spacing: float = 7.0  # pt after body paragraphs


class DeckStyle(_Model):
    """Presentation-specific styling on top of the shared palette."""

    dark: bool = False              # dark background decks use light text
    title_size: float = 40.0
    slide_title_size: float = 28.0
    body_size: float = 16.0


class Theme(_Model):
    name: str = "professional"
    kind: Literal["document", "deck"] = "document"
    fonts: ThemeFonts = Field(default_factory=ThemeFonts)
    sizes: ThemeSizes = Field(default_factory=ThemeSizes)
    colors: ThemeColors = Field(default_factory=ThemeColors)
    spacing: ThemeSpacing = Field(default_factory=ThemeSpacing)
    deck: DeckStyle = Field(default_factory=DeckStyle)
    zebra_tables: bool = True


# Fixed per-variant callout hues (fill, bar, title) — consistent across themes.
CALLOUT_COLORS: dict[str, tuple[str, str]] = {
    "info": ("#EAF2FB", "#2E75B6"),
    "note": ("#F0F0F5", "#6B6B8D"),
    "tip": ("#EAF7EF", "#2F9E5B"),
    "success": ("#EAF7EF", "#2F9E5B"),
    "warning": ("#FDF3E3", "#D97706"),
    "danger": ("#FBEAEA", "#C0392B"),
}


def _doc_theme(name: str, **overrides: Any) -> Theme:
    return Theme.model_validate({"name": name, "kind": "document", **overrides})


def _deck_theme(name: str, **overrides: Any) -> Theme:
    return Theme.model_validate({"name": name, "kind": "deck", **overrides})


BUILTIN_THEMES: dict[str, Theme] = {
    # ------------------------------------------------------------------
    # Document themes
    # ------------------------------------------------------------------
    "professional": _doc_theme("professional"),
    "minimal": _doc_theme(
        "minimal",
        fonts={"heading": "Helvetica", "body": "Helvetica", "mono": "Courier New"},
        colors={
            "primary": "#111111",
            "secondary": "#444444",
            "accent": "#0066CC",
            "text": "#111111",
            "text_light": "#888888",
            "surface": "#F7F7F7",
            "border": "#EEEEEE",
        },
        sizes={"title": 28.0, "h1": 19.0, "h2": 15.0, "h3": 12.5, "body": 10.0},
        zebra_tables=False,
    ),
    "corporate": _doc_theme(
        "corporate",
        fonts={"heading": "Arial", "body": "Arial", "mono": "Courier New"},
        colors={
            "primary": "#003366",
            "secondary": "#336699",
            "accent": "#CC6600",
            "text": "#222222",
            "text_light": "#555555",
            "surface": "#EEF3F8",
            "border": "#CCCCCC",
        },
    ),
    "academic": _doc_theme(
        "academic",
        fonts={
            "heading": "Times New Roman",
            "body": "Times New Roman",
            "mono": "Courier New",
            "east_asia": "SimSun",
        },
        colors={
            "primary": "#000000",
            "secondary": "#333333",
            "accent": "#8B0000",
            "text": "#000000",
            "text_light": "#444444",
            "surface": "#F5F5F5",
            "border": "#999999",
        },
        sizes={"title": 24.0, "h1": 18.0, "h2": 15.0, "h3": 13.0, "body": 11.0},
        spacing={"line_spacing": 1.8, "paragraph_spacing": 4.0},
        zebra_tables=False,
    ),
    "modern": _doc_theme(
        "modern",
        colors={
            "primary": "#0B5FFF",
            "secondary": "#3D7BFD",
            "accent": "#00B8A9",
            "text": "#1A1D24",
            "text_light": "#5A6270",
            "surface": "#EAF1FF",
            "border": "#D5E2FB",
        },
    ),
    # ------------------------------------------------------------------
    # Deck themes (from the pptx skill design guide)
    # ------------------------------------------------------------------
    # Default deck theme: a clean, professional light background with a
    # confident blue for titles/section bands and a warm accent.
    "executive_light": _deck_theme(
        "executive_light",
        fonts={"heading": "Calibri", "body": "Calibri"},
        colors={
            "primary": "#1F4E79",
            "secondary": "#2E75B6",
            "accent": "#ED7D31",
            "text": "#1A2733",
            "text_light": "#5A6675",
            "background": "#FFFFFF",
            "surface": "#EEF3F9",
            "border": "#D6E0EA",
        },
        deck={"dark": False},
    ),
    "midnight_executive": _deck_theme(
        "midnight_executive",
        fonts={"heading": "Georgia", "body": "Calibri"},
        colors={
            "primary": "#1E2761",
            "secondary": "#CADCFC",
            "accent": "#7A9CF5",
            "text": "#FFFFFF",
            "text_light": "#CADCFC",
            "background": "#1E2761",
            "surface": "#28347A",
            "border": "#CADCFC",
        },
        deck={"dark": True},
    ),
    "forest_moss": _deck_theme(
        "forest_moss",
        fonts={"heading": "Cambria", "body": "Calibri"},
        colors={
            "primary": "#2C5F2D",
            "secondary": "#97BC62",
            "accent": "#5A8F4E",
            "text": "#233A24",
            "text_light": "#5A7D5B",
            "background": "#F5F5F0",
            "surface": "#E8EFDC",
            "border": "#97BC62",
        },
    ),
    "coral_energy": _deck_theme(
        "coral_energy",
        fonts={"heading": "Arial Black", "body": "Arial"},
        colors={
            "primary": "#F96167",
            "secondary": "#F9E795",
            "accent": "#2F3C7E",
            "text": "#2F3C7E",
            "text_light": "#8A93C4",
            "background": "#FFFFFF",
            "surface": "#FDF6E0",
            "border": "#F9E795",
        },
    ),
    "warm_terracotta": _deck_theme(
        "warm_terracotta",
        fonts={"heading": "Palatino", "body": "Calibri"},
        colors={
            "primary": "#B85042",
            "secondary": "#E7E8D1",
            "accent": "#A7BEAE",
            "text": "#4A2E28",
            "text_light": "#8A6A62",
            "background": "#E7E8D1",
            "surface": "#F2F3E4",
            "border": "#B85042",
        },
    ),
    "ocean_gradient": _deck_theme(
        "ocean_gradient",
        fonts={"heading": "Trebuchet MS", "body": "Calibri"},
        colors={
            "primary": "#065A82",
            "secondary": "#1C7293",
            "accent": "#9EB3C2",
            "text": "#FFFFFF",
            "text_light": "#B0D0E0",
            "background": "#065A82",
            "surface": "#0E6C97",
            "border": "#1C7293",
        },
        deck={"dark": True},
    ),
    "charcoal_minimal": _deck_theme(
        "charcoal_minimal",
        fonts={"heading": "Calibri", "body": "Calibri Light"},
        colors={
            "primary": "#36454F",
            "secondary": "#8A9BA8",
            "accent": "#212121",
            "text": "#212121",
            "text_light": "#666666",
            "background": "#F2F2F2",
            "surface": "#E4E6E8",
            "border": "#36454F",
        },
    ),
    "teal_trust": _deck_theme(
        "teal_trust",
        fonts={"heading": "Georgia", "body": "Calibri"},
        colors={
            "primary": "#028090",
            "secondary": "#00A896",
            "accent": "#02C39A",
            "text": "#FFFFFF",
            "text_light": "#B0E0D6",
            "background": "#028090",
            "surface": "#079AA5",
            "border": "#02C39A",
        },
        deck={"dark": True},
    ),
    "berry_cream": _deck_theme(
        "berry_cream",
        fonts={"heading": "Palatino", "body": "Calibri"},
        colors={
            "primary": "#6D2E46",
            "secondary": "#A26769",
            "accent": "#D5B9B2",
            "text": "#4A1F30",
            "text_light": "#A26769",
            "background": "#ECE2D0",
            "surface": "#F4EDE1",
            "border": "#6D2E46",
        },
    ),
    "sage_calm": _deck_theme(
        "sage_calm",
        fonts={"heading": "Georgia", "body": "Calibri"},
        colors={
            "primary": "#50808E",
            "secondary": "#69A297",
            "accent": "#84B59F",
            "text": "#2D4A3E",
            "text_light": "#69A297",
            "background": "#F5F9F7",
            "surface": "#E6F0EB",
            "border": "#84B59F",
        },
    ),
    "cherry_bold": _deck_theme(
        "cherry_bold",
        fonts={"heading": "Impact", "body": "Arial"},
        colors={
            "primary": "#990011",
            "secondary": "#2F3C7E",
            "accent": "#C33149",
            "text": "#3A0A10",
            "text_light": "#8C5560",
            "background": "#FCF6F5",
            "surface": "#F7E9E7",
            "border": "#990011",
        },
    ),
}


_custom_cache: dict[str, Theme] = {}
_cache_lock = threading.Lock()


def invalidate_custom_theme_cache(name: str | None = None) -> None:
    """Drop cached custom themes (one name, or everything when None)."""
    with _cache_lock:
        if name is None:
            _custom_cache.clear()
        else:
            for key in [k for k in _custom_cache if k.split(":", 1)[1] == name]:
                del _custom_cache[key]


def list_theme_names(kind: Literal["document", "deck"] | None = None) -> list[str]:
    """Names of built-in (and on-disk custom) themes, optionally filtered by kind."""
    names = [
        name
        for name, theme in BUILTIN_THEMES.items()
        if kind is None or theme.kind == kind
    ]
    custom_dir = styles_dir()
    if custom_dir.is_dir():
        for f in sorted(custom_dir.glob("*.y*ml")):
            if f.stem not in names:
                names.append(f.stem)
    return names


def get_theme(
    name: str | dict[str, Any] | None,
    *,
    kind: Literal["document", "deck"] = "document",
) -> Theme:
    """Resolve a theme by name / inline dict, falling back to the kind default."""
    default_name = "professional" if kind == "document" else "executive_light"

    if name is None:
        return BUILTIN_THEMES[default_name]

    if isinstance(name, dict):
        base = BUILTIN_THEMES[default_name].model_dump()
        _deep_merge(base, name)
        base["kind"] = kind
        try:
            return Theme.model_validate(base)
        except Exception:  # noqa: BLE001 - inline overrides are best-effort
            logger.warning("docgen_theme_inline_invalid")
            return BUILTIN_THEMES[default_name]

    key = str(name).strip()
    if key in BUILTIN_THEMES:
        return BUILTIN_THEMES[key]

    custom = _load_custom_theme(key, default_name=default_name, kind=kind)
    if custom is not None:
        return custom

    logger.warning("docgen_theme_not_found", requested=key, fallback=default_name)
    return BUILTIN_THEMES[default_name]


def _load_custom_theme(
    name: str, *, default_name: str, kind: Literal["document", "deck"]
) -> Theme | None:
    cache_key = f"{kind}:{name}"
    with _cache_lock:
        if cache_key in _custom_cache:
            return _custom_cache[cache_key]
    custom_dir = styles_dir()
    if not custom_dir.is_dir():
        return None
    import yaml

    for ext in (".yaml", ".yml"):
        path = custom_dir / f"{name}{ext}"
        if not path.is_file():
            continue
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            logger.exception("docgen_theme_load_failed", path=str(path))
            return None
        if not isinstance(raw, dict):
            return None
        base = BUILTIN_THEMES[default_name].model_dump()
        _deep_merge(base, raw)
        base["name"] = name
        base["kind"] = kind
        try:
            theme = Theme.model_validate(base)
        except Exception:  # noqa: BLE001
            logger.exception("docgen_theme_invalid", path=str(path))
            return None
        with _cache_lock:
            _custom_cache[cache_key] = theme
        return theme
    return None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
