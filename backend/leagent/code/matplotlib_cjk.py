"""Configure matplotlib for Chinese (and mixed CJK + Latin) text in code_execution.

Agent scripts often reset ``font.sans-serif`` to Windows/macOS family names
(``SimHei``, ``Microsoft YaHei``, …) that are absent on Linux. Registration
aliases those names to the resolved pan-Unicode face so overrides keep working.
``configure_matplotlib_cjk`` is idempotent for font registration and always
re-applies rcParams so a later call (e.g. before ``savefig``) can restore CJK
after a script wiped the stack down to DejaVu-only.
"""

from __future__ import annotations

import structlog
from pathlib import Path

from leagent.utils.cjk_font_discovery import resolve_cjk_regular_path

logger = structlog.get_logger(__name__)

# Family names LLMs commonly put in rcParams / FontProperties on non-Windows hosts.
_CJK_FAMILY_ALIASES: tuple[str, ...] = (
    "SimHei",
    "SimSun",
    "Microsoft YaHei",
    "Microsoft YaHei UI",
    "PingFang SC",
    "PingFang HK",
    "STHeiti",
    "Heiti SC",
    "WenQuanYi Micro Hei",
    "WenQuanYi Zen Hei",
    "Noto Sans CJK SC",
    "Noto Sans CJK",
    "Source Han Sans SC",
    "Source Han Sans CN",
)

_REGISTERED_PATH: str | None = None
_FAMILY: str | None = None


def configure_matplotlib_cjk(*, explicit_font_path: str | None = None) -> bool:
    """Register a pan-Unicode CJK font (once) and (re)apply sans-serif rcParams.

    Returns:
        True if a CJK font was applied, False if none found or matplotlib unavailable.
    """
    global _REGISTERED_PATH, _FAMILY

    try:
        from matplotlib import font_manager
        import matplotlib.pyplot as plt
    except Exception as exc:
        logger.debug("matplotlib_cjk_import_failed", error=str(exc))
        return False

    if _REGISTERED_PATH and _FAMILY:
        _apply_rcparams(plt, _FAMILY)
        return True

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

    _register_family_aliases(font_manager, path=str(p), real_family=family)
    _apply_rcparams(plt, family)

    _REGISTERED_PATH = str(p)
    _FAMILY = family
    logger.info("matplotlib_cjk_configured", family=family, path=path)
    return True


def _register_family_aliases(
    font_manager: object,
    *,
    path: str,
    real_family: str,
) -> None:
    """Map common Windows/macOS CJK names onto the same file as ``real_family``.

    Replaces any prior alias entries for those names so a stale path from an
    earlier configure (or a failed probe font) cannot win ``findfont``.
    """
    fm = font_manager.fontManager  # type: ignore[attr-defined]
    FontEntry = font_manager.FontEntry  # type: ignore[attr-defined]
    try:
        path_resolved = str(Path(path).resolve())
    except OSError:
        path_resolved = path

    kept: list[object] = []
    for entry in list(getattr(fm, "ttflist", ())):
        name = getattr(entry, "name", "") or ""
        if name in _CJK_FAMILY_ALIASES and name != real_family:
            fname = str(getattr(entry, "fname", "") or "")
            try:
                if fname and str(Path(fname).resolve()) == path_resolved:
                    kept.append(entry)
            except OSError:
                pass
            continue
        kept.append(entry)
    fm.ttflist = kept  # type: ignore[assignment]

    existing = {getattr(e, "name", "") for e in fm.ttflist}
    for alias in _CJK_FAMILY_ALIASES:
        if not alias or alias == real_family or alias in existing:
            continue
        try:
            fm.ttflist.append(
                FontEntry(
                    fname=path,
                    name=alias,
                    style="normal",
                    variant="normal",
                    weight="normal",
                    stretch="normal",
                    size="scalable",
                )
            )
            existing.add(alias)
        except Exception as exc:
            logger.debug(
                "matplotlib_cjk_alias_failed",
                alias=alias,
                error=str(exc),
            )


def _apply_rcparams(plt: object, family: str) -> None:
    """Put ``family`` first on the sans-serif stack; keep axes.unicode_minus off."""
    rc = plt.rcParams  # type: ignore[attr-defined]
    prior = [str(x) for x in (rc.get("font.sans-serif") or []) if x]
    rest = [name for name in prior if name != family]
    # Prefer CJK sans first, then whatever the script already chose, then Latin.
    latin_fallback = ("DejaVu Sans", "Arial", "Helvetica", "sans-serif")
    for name in latin_fallback:
        if name not in rest and name != family:
            rest.append(name)
    rc["font.sans-serif"] = [family, *rest]
    rc["font.family"] = "sans-serif"
    rc["axes.unicode_minus"] = False


def reset_matplotlib_cjk_configured_for_tests() -> None:
    """Test-only: allow re-running full registration in the same interpreter."""
    global _REGISTERED_PATH, _FAMILY
    _REGISTERED_PATH = None
    _FAMILY = None
