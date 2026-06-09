"""Configure matplotlib for Chinese (and mixed CJK + Latin) text in code_execution."""

from __future__ import annotations

import structlog
from pathlib import Path

from leagent.utils.cjk_font_discovery import resolve_cjk_regular_path

logger = structlog.get_logger(__name__)

_CONFIGURED = False


def configure_matplotlib_cjk(*, explicit_font_path: str | None = None) -> bool:
    """Register a pan-Unicode CJK font and set rcParams for sans-serif + minus sign.

    Safe to call multiple times; only the first successful run mutates global rcParams.

    Returns:
        True if a CJK font was applied, False if none found or matplotlib unavailable.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return True

    try:
        import matplotlib
        from matplotlib import font_manager
        import matplotlib.pyplot as plt
    except Exception as exc:
        logger.debug("matplotlib_cjk_import_failed", error=str(exc))
        return False

    path = resolve_cjk_regular_path(explicit=explicit_font_path)
    if not path:
        logger.debug("matplotlib_cjk_no_font")
        return False

    p = Path(path)
    if not p.is_file():
        return False

    suffix = p.suffix.lower()
    if suffix not in {".otf", ".ttf", ".ttc"}:
        logger.debug("matplotlib_cjk_skip_suffix", path=path, suffix=suffix)
        return False

    try:
        font_manager.fontManager.addfont(str(p))
    except Exception as exc:
        logger.warning("matplotlib_cjk_addfont_failed", path=path, error=str(exc))
        return False

    try:
        fp = font_manager.FontProperties(fname=str(p))
        family = fp.get_name()
    except Exception as exc:
        logger.warning("matplotlib_cjk_fontprops_failed", path=path, error=str(exc))
        return False

    if not family:
        return False

    # Prefer CJK sans first, then Latin fallbacks (theme often uses font.family = 'sans-serif').
    sans_stack = [
        family,
        "DejaVu Sans",
        "Arial",
        "Helvetica",
        "sans-serif",
    ]
    plt.rcParams["font.sans-serif"] = sans_stack
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["axes.unicode_minus"] = False

    _CONFIGURED = True
    logger.info("matplotlib_cjk_configured", family=family, path=path)
    return True


def reset_matplotlib_cjk_configured_for_tests() -> None:
    """Test-only: allow re-running configure_matplotlib_cjk in the same interpreter."""
    global _CONFIGURED
    _CONFIGURED = False
