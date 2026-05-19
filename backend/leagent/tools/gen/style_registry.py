"""StyleRegistry — reusable style definitions for document generation tools.

Loads YAML style definitions from ``~/.leagent/templates/styles/`` and provides
built-in presets for professional document generation across PDF, Word, and PPTX.

Includes 10 curated PPTX presentation palettes derived from the pptx skill:
  midnight_executive, forest_moss, coral_energy, warm_terracotta,
  ocean_gradient, charcoal_minimal, teal_trust, berry_cream,
  sage_calm, cherry_bold.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import structlog
import yaml

logger = structlog.get_logger(__name__)

_DEFAULT_STYLES_DIR = Path.home() / ".leagent" / "templates" / "styles"


BUILTIN_PRESETS: dict[str, dict[str, Any]] = {
    "professional": {
        "fonts": {
            "heading": "Calibri",
            "body": "Calibri",
            "mono": "Consolas",
        },
        "font_sizes": {
            "title": 28,
            "h1": 24,
            "h2": 20,
            "h3": 16,
            "body": 11,
            "small": 9,
        },
        "colors": {
            "primary": "#1F4E79",
            "secondary": "#2E75B6",
            "accent": "#ED7D31",
            "text": "#333333",
            "text_light": "#666666",
            "background": "#FFFFFF",
            "border": "#D9D9D9",
        },
        "spacing": {
            "margin_top": 1.0,
            "margin_bottom": 1.0,
            "margin_left": 1.0,
            "margin_right": 1.0,
            "line_spacing": 1.15,
            "paragraph_spacing": 6,
        },
        "header_footer": {
            "header_font_size": 9,
            "footer_font_size": 8,
            "separator_line": True,
        },
    },
    "minimal": {
        "fonts": {
            "heading": "Helvetica",
            "body": "Helvetica",
            "mono": "Courier",
        },
        "font_sizes": {
            "title": 32,
            "h1": 24,
            "h2": 18,
            "h3": 14,
            "body": 10,
            "small": 8,
        },
        "colors": {
            "primary": "#111111",
            "secondary": "#444444",
            "accent": "#0066CC",
            "text": "#111111",
            "text_light": "#888888",
            "background": "#FFFFFF",
            "border": "#EEEEEE",
        },
        "spacing": {
            "margin_top": 0.75,
            "margin_bottom": 0.75,
            "margin_left": 0.75,
            "margin_right": 0.75,
            "line_spacing": 1.3,
            "paragraph_spacing": 4,
        },
        "header_footer": {
            "header_font_size": 8,
            "footer_font_size": 7,
            "separator_line": False,
        },
    },
    "corporate": {
        "fonts": {
            "heading": "Arial",
            "body": "Arial",
            "mono": "Courier New",
        },
        "font_sizes": {
            "title": 26,
            "h1": 22,
            "h2": 18,
            "h3": 14,
            "body": 11,
            "small": 9,
        },
        "colors": {
            "primary": "#003366",
            "secondary": "#336699",
            "accent": "#CC6600",
            "text": "#222222",
            "text_light": "#555555",
            "background": "#FFFFFF",
            "border": "#CCCCCC",
        },
        "spacing": {
            "margin_top": 1.0,
            "margin_bottom": 1.0,
            "margin_left": 1.25,
            "margin_right": 1.0,
            "line_spacing": 1.2,
            "paragraph_spacing": 6,
        },
        "header_footer": {
            "header_font_size": 9,
            "footer_font_size": 8,
            "separator_line": True,
        },
    },
    "academic": {
        "fonts": {
            "heading": "Times New Roman",
            "body": "Times New Roman",
            "mono": "Courier New",
        },
        "font_sizes": {
            "title": 24,
            "h1": 18,
            "h2": 16,
            "h3": 14,
            "body": 12,
            "small": 10,
        },
        "colors": {
            "primary": "#000000",
            "secondary": "#333333",
            "accent": "#8B0000",
            "text": "#000000",
            "text_light": "#444444",
            "background": "#FFFFFF",
            "border": "#999999",
        },
        "spacing": {
            "margin_top": 1.0,
            "margin_bottom": 1.0,
            "margin_left": 1.5,
            "margin_right": 1.0,
            "line_spacing": 2.0,
            "paragraph_spacing": 0,
        },
        "header_footer": {
            "header_font_size": 10,
            "footer_font_size": 10,
            "separator_line": False,
        },
    },
    # ------------------------------------------------------------------
    # PPTX presentation palettes (from pptx skill design guide)
    # ------------------------------------------------------------------
    "midnight_executive": {
        "fonts": {"heading": "Georgia", "body": "Calibri", "mono": "Consolas"},
        "font_sizes": {"title": 36, "h1": 24, "h2": 20, "h3": 16, "body": 16, "small": 11},
        "colors": {
            "primary": "#1E2761",
            "secondary": "#CADCFC",
            "accent": "#FFFFFF",
            "text": "#FFFFFF",
            "text_light": "#CADCFC",
            "background": "#1E2761",
            "border": "#CADCFC",
        },
        "spacing": {"margin_top": 0.5, "margin_bottom": 0.5, "margin_left": 0.5, "margin_right": 0.5, "line_spacing": 1.2, "paragraph_spacing": 6},
        "header_footer": {"header_font_size": 9, "footer_font_size": 8, "separator_line": False},
    },
    "forest_moss": {
        "fonts": {"heading": "Cambria", "body": "Calibri", "mono": "Consolas"},
        "font_sizes": {"title": 36, "h1": 24, "h2": 20, "h3": 16, "body": 16, "small": 11},
        "colors": {
            "primary": "#2C5F2D",
            "secondary": "#97BC62",
            "accent": "#F5F5F5",
            "text": "#2C5F2D",
            "text_light": "#5A7D5B",
            "background": "#F5F5F5",
            "border": "#97BC62",
        },
        "spacing": {"margin_top": 0.5, "margin_bottom": 0.5, "margin_left": 0.5, "margin_right": 0.5, "line_spacing": 1.2, "paragraph_spacing": 6},
        "header_footer": {"header_font_size": 9, "footer_font_size": 8, "separator_line": False},
    },
    "coral_energy": {
        "fonts": {"heading": "Arial Black", "body": "Arial", "mono": "Consolas"},
        "font_sizes": {"title": 36, "h1": 24, "h2": 20, "h3": 16, "body": 16, "small": 11},
        "colors": {
            "primary": "#F96167",
            "secondary": "#F9E795",
            "accent": "#2F3C7E",
            "text": "#2F3C7E",
            "text_light": "#F96167",
            "background": "#FFFFFF",
            "border": "#F9E795",
        },
        "spacing": {"margin_top": 0.5, "margin_bottom": 0.5, "margin_left": 0.5, "margin_right": 0.5, "line_spacing": 1.2, "paragraph_spacing": 6},
        "header_footer": {"header_font_size": 9, "footer_font_size": 8, "separator_line": False},
    },
    "warm_terracotta": {
        "fonts": {"heading": "Palatino", "body": "Calibri", "mono": "Consolas"},
        "font_sizes": {"title": 36, "h1": 24, "h2": 20, "h3": 16, "body": 16, "small": 11},
        "colors": {
            "primary": "#B85042",
            "secondary": "#E7E8D1",
            "accent": "#A7BEAE",
            "text": "#B85042",
            "text_light": "#A7BEAE",
            "background": "#E7E8D1",
            "border": "#B85042",
        },
        "spacing": {"margin_top": 0.5, "margin_bottom": 0.5, "margin_left": 0.5, "margin_right": 0.5, "line_spacing": 1.2, "paragraph_spacing": 6},
        "header_footer": {"header_font_size": 9, "footer_font_size": 8, "separator_line": False},
    },
    "ocean_gradient": {
        "fonts": {"heading": "Trebuchet MS", "body": "Calibri", "mono": "Consolas"},
        "font_sizes": {"title": 36, "h1": 24, "h2": 20, "h3": 16, "body": 16, "small": 11},
        "colors": {
            "primary": "#065A82",
            "secondary": "#1C7293",
            "accent": "#21295C",
            "text": "#FFFFFF",
            "text_light": "#B0D0E0",
            "background": "#065A82",
            "border": "#1C7293",
        },
        "spacing": {"margin_top": 0.5, "margin_bottom": 0.5, "margin_left": 0.5, "margin_right": 0.5, "line_spacing": 1.2, "paragraph_spacing": 6},
        "header_footer": {"header_font_size": 9, "footer_font_size": 8, "separator_line": False},
    },
    "charcoal_minimal": {
        "fonts": {"heading": "Calibri", "body": "Calibri Light", "mono": "Consolas"},
        "font_sizes": {"title": 36, "h1": 24, "h2": 20, "h3": 16, "body": 16, "small": 11},
        "colors": {
            "primary": "#36454F",
            "secondary": "#F2F2F2",
            "accent": "#212121",
            "text": "#212121",
            "text_light": "#666666",
            "background": "#F2F2F2",
            "border": "#36454F",
        },
        "spacing": {"margin_top": 0.5, "margin_bottom": 0.5, "margin_left": 0.5, "margin_right": 0.5, "line_spacing": 1.2, "paragraph_spacing": 6},
        "header_footer": {"header_font_size": 9, "footer_font_size": 8, "separator_line": False},
    },
    "teal_trust": {
        "fonts": {"heading": "Georgia", "body": "Calibri", "mono": "Consolas"},
        "font_sizes": {"title": 36, "h1": 24, "h2": 20, "h3": 16, "body": 16, "small": 11},
        "colors": {
            "primary": "#028090",
            "secondary": "#00A896",
            "accent": "#02C39A",
            "text": "#FFFFFF",
            "text_light": "#B0E0D6",
            "background": "#028090",
            "border": "#02C39A",
        },
        "spacing": {"margin_top": 0.5, "margin_bottom": 0.5, "margin_left": 0.5, "margin_right": 0.5, "line_spacing": 1.2, "paragraph_spacing": 6},
        "header_footer": {"header_font_size": 9, "footer_font_size": 8, "separator_line": False},
    },
    "berry_cream": {
        "fonts": {"heading": "Palatino", "body": "Calibri", "mono": "Consolas"},
        "font_sizes": {"title": 36, "h1": 24, "h2": 20, "h3": 16, "body": 16, "small": 11},
        "colors": {
            "primary": "#6D2E46",
            "secondary": "#A26769",
            "accent": "#ECE2D0",
            "text": "#6D2E46",
            "text_light": "#A26769",
            "background": "#ECE2D0",
            "border": "#6D2E46",
        },
        "spacing": {"margin_top": 0.5, "margin_bottom": 0.5, "margin_left": 0.5, "margin_right": 0.5, "line_spacing": 1.2, "paragraph_spacing": 6},
        "header_footer": {"header_font_size": 9, "footer_font_size": 8, "separator_line": False},
    },
    "sage_calm": {
        "fonts": {"heading": "Georgia", "body": "Calibri", "mono": "Consolas"},
        "font_sizes": {"title": 36, "h1": 24, "h2": 20, "h3": 16, "body": 16, "small": 11},
        "colors": {
            "primary": "#84B59F",
            "secondary": "#69A297",
            "accent": "#50808E",
            "text": "#2D4A3E",
            "text_light": "#69A297",
            "background": "#F5F9F7",
            "border": "#84B59F",
        },
        "spacing": {"margin_top": 0.5, "margin_bottom": 0.5, "margin_left": 0.5, "margin_right": 0.5, "line_spacing": 1.2, "paragraph_spacing": 6},
        "header_footer": {"header_font_size": 9, "footer_font_size": 8, "separator_line": False},
    },
    "cherry_bold": {
        "fonts": {"heading": "Impact", "body": "Arial", "mono": "Consolas"},
        "font_sizes": {"title": 36, "h1": 24, "h2": 20, "h3": 16, "body": 16, "small": 11},
        "colors": {
            "primary": "#990011",
            "secondary": "#FCF6F5",
            "accent": "#2F3C7E",
            "text": "#990011",
            "text_light": "#2F3C7E",
            "background": "#FCF6F5",
            "border": "#990011",
        },
        "spacing": {"margin_top": 0.5, "margin_bottom": 0.5, "margin_left": 0.5, "margin_right": 0.5, "line_spacing": 1.2, "paragraph_spacing": 6},
        "header_footer": {"header_font_size": 9, "footer_font_size": 8, "separator_line": False},
    },
}


class StyleRegistry:
    """Load and resolve style definitions for document generation."""

    def __init__(self, *, styles_dir: Path | str | None = None) -> None:
        self._styles_dir = Path(styles_dir) if styles_dir else _DEFAULT_STYLES_DIR
        self._custom_cache: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def resolve(self, style: str | dict[str, Any] | None) -> dict[str, Any]:
        """Resolve a style name or inline dict to a full style definition.

        - None → returns the ``professional`` preset
        - str → looks up built-in presets, then custom YAML files
        - dict → merges the dict on top of ``professional`` defaults
        """
        if style is None:
            return dict(BUILTIN_PRESETS["professional"])

        if isinstance(style, dict):
            base = dict(BUILTIN_PRESETS["professional"])
            _deep_merge(base, style)
            return base

        if style in BUILTIN_PRESETS:
            return dict(BUILTIN_PRESETS[style])

        custom = self._load_custom(style)
        if custom is not None:
            return custom

        logger.warning("style_not_found_using_default", requested=style)
        return dict(BUILTIN_PRESETS["professional"])

    def list_available(self) -> list[str]:
        """Return names of all available styles (builtins + custom)."""
        names = list(BUILTIN_PRESETS.keys())
        if self._styles_dir.is_dir():
            for f in self._styles_dir.glob("*.yaml"):
                names.append(f.stem)
            for f in self._styles_dir.glob("*.yml"):
                names.append(f.stem)
        return sorted(set(names))

    def _load_custom(self, name: str) -> dict[str, Any] | None:
        with self._lock:
            if name in self._custom_cache:
                return dict(self._custom_cache[name])

        if not self._styles_dir.is_dir():
            return None

        for ext in (".yaml", ".yml"):
            path = self._styles_dir / f"{name}{ext}"
            if path.is_file():
                try:
                    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        base = dict(BUILTIN_PRESETS.get("professional", {}))
                        _deep_merge(base, raw)
                        with self._lock:
                            self._custom_cache[name] = base
                        return dict(base)
                except Exception:
                    logger.exception("style_load_failed", path=str(path))
        return None


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """Recursively merge override into base (mutates base)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


_singleton: StyleRegistry | None = None
_singleton_lock = threading.Lock()


def get_style_registry(*, styles_dir: Path | str | None = None) -> StyleRegistry:
    """Return the process-wide StyleRegistry singleton."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = StyleRegistry(styles_dir=styles_dir)
        return _singleton
