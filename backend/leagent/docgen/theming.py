"""Theme generation + customization for the docgen subsystem.

Turns a brand seed (primary color, optional accent, light/dark mode, font
picks) into a complete, contrast-safe :class:`~leagent.docgen.themes.Theme`
payload, lints any theme for WCAG contrast problems, and manages the custom
theme store (YAML files under the styles directory) that
:func:`~leagent.docgen.themes.get_theme` resolves by name.

The generated payload is a plain dict in the exact shape the theme YAML
files use, so ``derive_theme_payload() -> save_custom_theme()`` produces a
theme any ``document_generate`` / ``slides_generate`` call can select.
"""

from __future__ import annotations

import colorsys
import re
from typing import Any, Literal

import structlog

from leagent.docgen.slides import relative_luminance
from leagent.docgen.themes import (
    BUILTIN_THEMES,
    Theme,
    get_theme,
    invalidate_custom_theme_cache,
    styles_dir,
)

logger = structlog.get_logger(__name__)

__all__ = [
    "contrast_ratio",
    "delete_custom_theme",
    "derive_theme_payload",
    "lint_theme",
    "list_custom_themes",
    "load_custom_theme_payload",
    "save_custom_theme",
]

_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


# ---------------------------------------------------------------------------
# Color math
# ---------------------------------------------------------------------------


def _hex_to_rgb(hex_color: str) -> tuple[float, float, float]:
    raw = hex_color.lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if not re.fullmatch(r"[0-9a-fA-F]{6}", raw):
        raise ValueError(f"Invalid hex color: {hex_color!r}")
    return tuple(int(raw[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def _rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255):02X}" for c in rgb)


def _with_hls(
    hex_color: str,
    *,
    h: float | None = None,
    l: float | None = None,  # noqa: E741 - HLS convention
    s: float | None = None,
) -> str:
    ch, cl, cs = colorsys.rgb_to_hls(*_hex_to_rgb(hex_color))
    return _rgb_to_hex(
        colorsys.hls_to_rgb(
            (ch if h is None else h % 1.0),
            max(0.0, min(1.0, cl if l is None else l)),
            max(0.0, min(1.0, cs if s is None else s)),
        )
    )


def _mix(a: str, b: str, t: float) -> str:
    """Blend ``a`` toward ``b`` by ``t`` (0 = pure a, 1 = pure b)."""
    ra = _hex_to_rgb(a)
    rb = _hex_to_rgb(b)
    return _rgb_to_hex(tuple(ca + (cb - ca) * t for ca, cb in zip(ra, rb, strict=True)))  # type: ignore[arg-type]


def contrast_ratio(a: str, b: str) -> float:
    """WCAG contrast ratio between two hex colors (1.0 - 21.0)."""
    la = relative_luminance(a)
    lb = relative_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _ensure_contrast(color: str, against: str, minimum: float, *, darken: bool) -> str:
    """Nudge ``color`` lightness until it clears ``minimum`` vs ``against``."""
    out = color
    for _ in range(20):
        if contrast_ratio(out, against) >= minimum:
            return out
        h, l, s = colorsys.rgb_to_hls(*_hex_to_rgb(out))  # noqa: E741
        l = max(0.02, l - 0.05) if darken else min(0.98, l + 0.05)  # noqa: E741
        out = _rgb_to_hex(colorsys.hls_to_rgb(h, l, s))
    return out


def _derive_accent(primary: str, *, dark: bool) -> str:
    """Hue-rotated companion color with enough saturation to read as accent."""
    h, _, s = colorsys.rgb_to_hls(*_hex_to_rgb(primary))
    return _with_hls(
        primary,
        h=h + 165.0 / 360.0,
        l=0.62 if dark else 0.48,
        s=max(0.5, s),
    )


# ---------------------------------------------------------------------------
# Theme derivation
# ---------------------------------------------------------------------------


def derive_theme_payload(
    *,
    kind: Literal["document", "deck"] = "document",
    primary: str,
    accent: str | None = None,
    mode: Literal["light", "dark"] | None = None,
    heading_font: str | None = None,
    body_font: str | None = None,
    east_asia_font: str | None = None,
) -> dict[str, Any]:
    """Derive a complete theme payload from a brand seed.

    Returns a dict in custom-theme YAML shape (deep-merged over the kind's
    base theme by :func:`get_theme` at resolve time). Colors are derived
    with contrast guarantees: body text vs background >= 4.5:1 and the
    primary/heading tone vs background >= 3:1.
    """
    _hex_to_rgb(primary)  # validate early
    if accent is not None:
        _hex_to_rgb(accent)
    dark = (mode or "light") == "dark"

    if dark:
        background = _with_hls(primary, l=0.13, s=None)
        surface = _with_hls(primary, l=0.20)
        border = _with_hls(primary, l=0.36, s=0.35)
        text = "#FFFFFF"
        text_light = _with_hls(primary, l=0.80, s=0.30)
        secondary = _with_hls(primary, l=0.72, s=0.45)
        acc = accent or _derive_accent(primary, dark=True)
        acc = _ensure_contrast(acc, background, 2.5, darken=False)
        colors = {
            "primary": background,  # dark decks: primary ≈ background canvas
            "secondary": secondary,
            "accent": acc,
            "text": text,
            "text_light": text_light,
            "background": background,
            "surface": surface,
            "border": border,
        }
    else:
        background = "#FFFFFF"
        prim = _ensure_contrast(primary, background, 3.0, darken=True)
        surface = _mix(prim, background, 0.92)
        border = _mix(prim, background, 0.72)
        text = _ensure_contrast(_mix("#1F2933", prim, 0.15), background, 7.0, darken=True)
        text_light = _mix(text, background, 0.35)
        text_light = _ensure_contrast(text_light, background, 4.0, darken=True)
        acc = accent or _derive_accent(prim, dark=False)
        acc = _ensure_contrast(acc, background, 2.5, darken=True)
        # Secondary: a lighter sibling of primary.
        h, l, s = colorsys.rgb_to_hls(*_hex_to_rgb(prim))  # noqa: E741
        secondary = _rgb_to_hex(colorsys.hls_to_rgb(h, min(0.9, l + 0.18), s))
        colors = {
            "primary": prim,
            "secondary": secondary,
            "accent": acc,
            "text": text,
            "text_light": text_light,
            "background": background,
            "surface": surface,
            "border": border,
        }

    payload: dict[str, Any] = {"colors": colors}

    fonts: dict[str, str] = {}
    if heading_font:
        fonts["heading"] = heading_font
    if body_font:
        fonts["body"] = body_font
    if east_asia_font:
        fonts["east_asia"] = east_asia_font
    if fonts:
        payload["fonts"] = fonts

    if kind == "deck":
        payload["deck"] = {"dark": dark}
    return payload


# ---------------------------------------------------------------------------
# Contrast lint
# ---------------------------------------------------------------------------

_LINT_RULES: tuple[tuple[str, str, float, str], ...] = (
    # (foreground role, background role, minimum ratio, human label)
    ("text", "background", 4.5, "body text"),
    ("text_light", "background", 3.0, "secondary text"),
    ("accent", "background", 2.0, "accent marks"),
    ("text", "surface", 3.5, "text on surface fills (cards, callouts)"),
)


def lint_theme(theme: Theme) -> list[str]:
    """Return human-readable contrast warnings for a resolved theme."""
    warnings: list[str] = []
    colors = theme.colors
    for fg_role, bg_role, minimum, label in _LINT_RULES:
        fg = getattr(colors, fg_role)
        bg = getattr(colors, bg_role)
        ratio = contrast_ratio(fg, bg)
        if ratio < minimum:
            warnings.append(
                f"{label}: {fg} on {bg} has contrast {ratio:.1f}:1 (< {minimum}:1)"
            )

    # Headings: dark decks draw headings in `text`, everything else in `primary`.
    heading = colors.text if (theme.kind == "deck" and theme.deck.dark) else colors.primary
    ratio = contrast_ratio(heading, colors.background)
    if ratio < 3.0:
        warnings.append(
            f"headings: {heading} on {colors.background} has contrast "
            f"{ratio:.1f}:1 (< 3.0:1)"
        )

    # Table headers / section slides put white-ish text on primary fills.
    if not (theme.kind == "deck" and theme.deck.dark):
        ratio = contrast_ratio("#FFFFFF", colors.primary)
        if ratio < 3.0:
            warnings.append(
                f"on-primary text: #FFFFFF on {colors.primary} has contrast "
                f"{ratio:.1f}:1 (< 3.0:1) — table headers/section slides may be hard to read"
            )
    return warnings


# ---------------------------------------------------------------------------
# Custom theme store
# ---------------------------------------------------------------------------


def _validate_name(name: str) -> str:
    key = str(name).strip().lower()
    if not _NAME_RE.fullmatch(key):
        raise ValueError(
            "Theme name must be 2-64 chars of lowercase letters, digits, '-' or '_'."
        )
    if key in BUILTIN_THEMES:
        raise ValueError(f"'{key}' is a built-in theme and cannot be modified.")
    return key


def save_custom_theme(
    name: str,
    payload: dict[str, Any],
    *,
    kind: Literal["document", "deck"] = "document",
    overwrite: bool = True,
) -> dict[str, Any]:
    """Validate + persist a custom theme; returns path, resolved theme, lint.

    The payload is stored as YAML and deep-merges over the kind's base theme
    when resolved, so partial payloads (colors only) are fine.
    """
    import yaml

    key = _validate_name(name)
    if not isinstance(payload, dict) or not payload:
        raise ValueError("Theme payload must be a non-empty object.")

    # Resolve through the real merge path to catch invalid shapes now.
    merged = get_theme({**payload, "name": key}, kind=kind)
    if merged.name != key:
        raise ValueError("Theme payload failed validation against the theme schema.")
    warnings = lint_theme(merged)

    directory = styles_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{key}.yaml"
    if path.exists() and not overwrite:
        raise ValueError(f"Theme '{key}' already exists (pass overwrite to replace).")

    stored = dict(payload)
    stored.setdefault("kind", kind)
    path.write_text(
        yaml.safe_dump(stored, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    invalidate_custom_theme_cache(key)
    logger.info("docgen_theme_saved", name=key, path=str(path), warnings=len(warnings))
    return {"name": key, "path": str(path), "kind": kind, "lint_warnings": warnings}


def load_custom_theme_payload(name: str) -> dict[str, Any] | None:
    """Raw YAML payload of a custom theme, or None."""
    import yaml

    directory = styles_dir()
    for ext in (".yaml", ".yml"):
        path = directory / f"{name}{ext}"
        if path.is_file():
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else None
    return None


def list_custom_themes() -> list[dict[str, Any]]:
    """Names + declared kinds of on-disk custom themes."""
    out: list[dict[str, Any]] = []
    directory = styles_dir()
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.y*ml")):
        payload = load_custom_theme_payload(path.stem) or {}
        out.append({"name": path.stem, "kind": payload.get("kind", "document")})
    return out


def delete_custom_theme(name: str) -> bool:
    """Delete a custom theme file; returns whether anything was removed."""
    key = _validate_name(name)
    removed = False
    directory = styles_dir()
    for ext in (".yaml", ".yml"):
        path = directory / f"{key}{ext}"
        if path.is_file():
            path.unlink()
            removed = True
    if removed:
        invalidate_custom_theme_cache(key)
        logger.info("docgen_theme_deleted", name=key)
    return removed
