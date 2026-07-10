"""Shared CJK font path discovery for PDF, matplotlib, and other generators.

Pan-Unicode fonts only; avoid Latin-stripped supplemental fallbacks as sole body font.
Discovery is cached for the process lifetime; restart to pick up fonts installed later.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


_DISCOVERY_CACHE: dict[bool, str | None] = {}
# Tools that write CJK text into rendered artifacts through user-authored
# code (charts, scripts). document_generate / slides_generate are NOT listed:
# their font handling is fully automatic via leagent.docgen.fonts.
_REGULAR_GENERATION_TOOLS: frozenset[str] = frozenset(
    {
        "code_execution",
        "script_agent",
        "coding_agent",
        "chart_generator",
    }
)


def cjk_font_search_roots() -> list[str]:
    """Directory roots scanned for known CJK filenames (rglob)."""
    home = str(Path.home())
    roots: list[str | None] = [
        str(Path(os.environ.get("XDG_DATA_HOME", "")).expanduser() / "fonts")
        if os.environ.get("XDG_DATA_HOME")
        else None,
        f"{home}/.local/share/fonts",
        f"{home}/.fonts",
        "/usr/local/share/fonts",
        "/usr/share/fonts",
    ]
    if sys.platform == "darwin":
        roots.extend(
            [
                f"{home}/Library/Fonts",
                "/Library/Fonts",
                "/System/Library/Fonts/Supplemental",
                "/System/Library/Fonts",
            ]
        )
    windir = (os.environ.get("WINDIR") or os.environ.get("SystemRoot") or "").strip()
    if windir:
        win_fonts = str(Path(windir) / "Fonts")
        if Path(win_fonts).is_dir():
            roots.append(win_fonts)
    out: list[str] = []
    seen: set[str] = set()
    for raw in roots:
        if not raw:
            continue
        path = str(Path(raw).expanduser())
        if path not in seen:
            seen.add(path)
            out.append(path)
    return out


def _candidate_names(*, is_bold: bool) -> tuple[str, ...]:
    """Known pan-Unicode CJK font filenames, ordered by preference."""
    common = (
        "PingFang.ttc",
        "STHeiti Medium.ttc",
        "STHeiti Light.ttc",
        "wqy-microhei.ttc",
        "wqy-zenhei.ttc",
    )
    if is_bold:
        return (
            "NotoSansSC-Bold.ttf",
            "NotoSansSC-Bold.otf",
            "NotoSansCJKSC-Bold.otf",
            "NotoSansCJK-Bold.ttc",
            "SourceHanSansSC-Bold.otf",
            "SourceHanSansCN-Bold.otf",
            "SourceHanSans-Bold.ttc",
            "msyhbd.ttc",
            *common,
        )
    return (
        "NotoSansSC-Regular.ttf",
        "NotoSansSC-Regular.otf",
        "NotoSansCJKSC-Regular.otf",
        "NotoSansCJK-Regular.ttc",
        "SourceHanSansSC-Regular.otf",
        "SourceHanSansCN-Regular.otf",
        "SourceHanSans-Regular.ttc",
        "Microsoft YaHei.ttf",
        "msyh.ttc",
        *common,
    )


def discover_cjk_font_file(*, is_bold: bool) -> str | None:
    """Search common CJK file names under system font trees."""
    if is_bold in _DISCOVERY_CACHE:
        return _DISCOVERY_CACHE[is_bold]

    names = _candidate_names(is_bold=is_bold)
    for base in cjk_font_search_roots():
        root = Path(base)
        if not root.is_dir():
            continue
        for n in names:
            direct = root / n
            if direct.is_file():
                _DISCOVERY_CACHE[is_bold] = str(direct)
                return str(direct)
            try:
                matches = root.rglob(n)
                for p in matches:
                    if p.is_file():
                        _DISCOVERY_CACHE[is_bold] = str(p)
                        return str(p)
            except OSError:
                continue
    _DISCOVERY_CACHE[is_bold] = None
    return None


def clear_cjk_font_discovery_cache() -> None:
    """Clear discovery cache for tests."""
    _DISCOVERY_CACHE.clear()


def _managed_font_path(*, is_bold: bool) -> str | None:
    """Font previously auto-downloaded by ``leagent.docgen.fonts.FontManager``.

    Checked here directly (filename convention, no download) to avoid a
    circular import — docgen builds on this module.
    """
    try:
        from leagent.config.constants import LEAGENT_HOME
    except Exception:  # noqa: BLE001 - constants must never break discovery
        return None
    name = "NotoSansSC-Bold.ttf" if is_bold else "NotoSansSC-Regular.ttf"
    path = LEAGENT_HOME / "fonts" / name
    if path.is_file() and path.stat().st_size > 0:
        return str(path)
    return None


def resolve_cjk_regular_path(*, explicit: str | None = None) -> str | None:
    """First existing regular CJK font: explicit, LEAGENT_CJK_FONT, managed dir, scan."""
    for raw in (explicit, os.environ.get("LEAGENT_CJK_FONT", "").strip() or None):
        if not raw:
            continue
        p = Path(raw)
        if p.is_file():
            return str(p)
    managed = _managed_font_path(is_bold=False)
    if managed:
        return managed
    return discover_cjk_font_file(is_bold=False)


def resolve_cjk_bold_path(*, explicit: str | None = None) -> str | None:
    """First existing bold CJK font: explicit, LEAGENT_CJK_FONT_BOLD, managed dir, scan."""
    for raw in (explicit, os.environ.get("LEAGENT_CJK_FONT_BOLD", "").strip() or None):
        if not raw:
            continue
        p = Path(raw)
        if p.is_file():
            return str(p)
    managed = _managed_font_path(is_bold=True)
    if managed:
        return managed
    return discover_cjk_font_file(is_bold=True)


def build_cjk_generation_turn_extra(*, tools: Any | None) -> str:
    """Return a short prompt hint for CJK-capable generation tools."""
    if tools is None:
        return ""

    def _has(name: str) -> bool:
        has = getattr(tools, "has", None)
        if not callable(has):
            return False
        try:
            return bool(has(name))
        except Exception:  # noqa: BLE001 - prompt hints must never break a turn
            return False

    active = [name for name in _REGULAR_GENERATION_TOOLS if _has(name)]
    if not active:
        return ""

    regular = resolve_cjk_regular_path()
    bold = resolve_cjk_bold_path()
    active_tools = ", ".join(sorted(active))
    lines = [
        "### CJK Font Guidance for Generated Artifacts",
        f"Active generation tools: {active_tools}.",
        "For Chinese or mixed Chinese/Latin charts, PDF, DOCX, or PPTX output, use a pan-Unicode CJK font and avoid relying on guessed OS paths.",
    ]
    if regular:
        lines.append(f"Resolved regular CJK font path: `{regular}`.")
        lines.append(
            "Use this path for ReportLab `TTFont`, python-docx/python-pptx font setup, and matplotlib `font_manager` when writing custom scripts. "
            "(`document_generate` / `slides_generate` handle fonts automatically — no path needed there.)"
        )
    if bold and bold != regular:
        lines.append(f"Resolved bold CJK font path: `{bold}`.")
    if regular:
        lines.append(
            "`code_execution` also receives `LEAGENT_CJK_FONT` and auto-configures matplotlib when source imports/uses matplotlib, pyplot, plt., mpl., pylab, or font_manager."
        )
    else:
        lines.append(
            "No local CJK font path was discovered; prefer asking the user to install `fonts-noto-cjk` or `fonts-wqy-microhei`, or set `LEAGENT_CJK_FONT` to an absolute .otf/.ttf/.ttc path."
        )
    lines.append("中文生成任务优先使用上面的真实字体路径，避免凭空编造字体路径。")
    return "\n".join(lines)
