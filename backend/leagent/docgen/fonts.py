"""Guaranteed pan-Unicode font pipeline for document generation.

Resolution order (see ``FontManager.resolve``):

1. ``LEAGENT_CJK_FONT`` / ``LEAGENT_CJK_FONT_BOLD`` env overrides
2. Managed fonts previously downloaded to ``LEAGENT_HOME/fonts/``
3. System font scan (``leagent.utils.cjk_font_discovery``)
4. Auto-download of pinned Noto Sans SC faces (sha256-verified) into the
   managed dir — disable with ``LEAGENT_FONT_AUTO_DOWNLOAD=0`` for offline
   deployments
5. Helvetica fallback with a structured warning surfaced to the caller

Emoji (PDF only) uses a parallel path (``LEAGENT_EMOJI_FONT`` → managed
``NotoEmoji.ttf`` → system Noto Emoji → auto-download). ReportLab cannot
embed Noto *Color* Emoji (CBDT bitmaps); we ship the monochrome Noto Emoji
variable TTF and switch faces per run in paragraph markup.

The manager also owns format-specific registration: ReportLab ``TTFont``
registration (with TTC subfont probing) and ascii+eastAsia font-name pairs
for python-docx / python-pptx.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from leagent.config.constants import LEAGENT_HOME
from leagent.utils.cjk_font_discovery import (
    discover_cjk_font_file,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Pinned download manifest — Noto Sans SC static TTF instances (Google Fonts).
#
# IMPORTANT: the faces MUST have TrueType outlines. ReportLab rejects
# CFF/PostScript outlines ("postscript outlines are not supported"), which
# covers the notofonts release OTFs *and* many distro-packaged Noto CJK TTCs.
# The gstatic TTF instances below are TrueType and register cleanly.
# ---------------------------------------------------------------------------

_GSTATIC_REGULAR = (
    "s/notosanssc/v40/k3kCo84MPvpLmixcA63oeAL7Iqp5IZJF9bmaG9_FnYw.ttf"
)
_GSTATIC_BOLD = (
    "s/notosanssc/v40/k3kCo84MPvpLmixcA63oeAL7Iqp5IZJF9bmaGzjCnYw.ttf"
)

# Monochrome Noto Emoji (variable TTF) — ReportLab-compatible outlines.
# Pinned to a google/fonts commit so sha256 stays stable.
_EMOJI_COMMIT = "b979dba422e445492b0eb9951ac52ee0b4d648c3"
_EMOJI_PATH = "ofl/notoemoji/NotoEmoji%5Bwght%5D.ttf"


@dataclass(frozen=True)
class FontAsset:
    """One downloadable font face with pinned integrity hash."""

    filename: str
    urls: tuple[str, ...]
    sha256: str
    size_bytes: int


FONT_MANIFEST: dict[str, FontAsset] = {
    "regular": FontAsset(
        filename="NotoSansSC-Regular.ttf",
        urls=(
            f"https://fonts.gstatic.com/{_GSTATIC_REGULAR}",
            # gstatic mirror reachable from mainland China.
            f"https://gstatic.loli.net/{_GSTATIC_REGULAR}",
        ),
        sha256="450625c8d46ab3df97b7904ded955ec2746d17ec76740cb1e91d1ba63a0f89af",
        size_bytes=10_540_644,
    ),
    "bold": FontAsset(
        filename="NotoSansSC-Bold.ttf",
        urls=(
            f"https://fonts.gstatic.com/{_GSTATIC_BOLD}",
            f"https://gstatic.loli.net/{_GSTATIC_BOLD}",
        ),
        sha256="0066a522a1ac007c1d72bc4fccb114f80ff7294641c78cead9715bd14d43b9ea",
        size_bytes=10_530_408,
    ),
    "emoji": FontAsset(
        filename="NotoEmoji.ttf",
        urls=(
            f"https://raw.githubusercontent.com/google/fonts/{_EMOJI_COMMIT}/{_EMOJI_PATH}",
            f"https://cdn.jsdelivr.net/gh/google/fonts@{_EMOJI_COMMIT}/{_EMOJI_PATH}",
        ),
        sha256="de6c18832938afc99caf132b39d6a30a19bac7f2e812e28db2535b4608d27551",
        size_bytes=1_982_596,
    ),
}

# ReportLab internal font names registered by this module.
PDF_FONT_REGULAR = "LeAgentDocSans"
PDF_FONT_BOLD = "LeAgentDocSansBold"
PDF_FONT_EMOJI = "LeAgentDocEmoji"
PDF_FONT_FAMILY = "LeAgentDocFamily"

# Common install locations for monochrome Noto Emoji (never Color/CBDT).
_EMOJI_SYSTEM_NAMES = (
    "NotoEmoji-Regular.ttf",
    "NotoEmoji-Medium.ttf",
    "NotoEmoji.ttf",
    "NotoEmoji[wght].ttf",
)
_EMOJI_SYSTEM_DIRS = (
    Path("/usr/share/fonts/truetype/noto"),
    Path("/usr/share/fonts/TTF"),
    Path("/usr/local/share/fonts"),
    Path.home() / ".local/share/fonts",
    Path("/Library/Fonts"),
    Path.home() / "Library/Fonts",
)


@dataclass
class ResolvedFonts:
    """Resolved font file paths plus provenance and warnings."""

    regular_path: str | None = None
    bold_path: str | None = None
    source: str = "none"  # env | managed | system | downloaded | none
    warnings: list[str] = field(default_factory=list)

    @property
    def available(self) -> bool:
        return bool(self.regular_path)


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _auto_download_enabled() -> bool:
    raw = os.environ.get("LEAGENT_FONT_AUTO_DOWNLOAD", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


class FontManager:
    """Process-wide manager for document-generation fonts."""

    def __init__(self, fonts_dir: Path | str | None = None) -> None:
        self._fonts_dir = Path(fonts_dir) if fonts_dir else (LEAGENT_HOME / "fonts")
        self._lock = threading.Lock()
        self._resolved: ResolvedFonts | None = None
        self._pdf_registered: dict[str, str] = {}

    @property
    def fonts_dir(self) -> Path:
        return self._fonts_dir

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------

    def resolve(self, *, allow_download: bool = True, refresh: bool = False) -> ResolvedFonts:
        """Resolve regular/bold font paths using the guaranteed pipeline."""
        with self._lock:
            if (
                self._resolved is not None
                and not refresh
                and (self._resolved.available or not allow_download)
            ):
                return self._resolved
            resolved = self._resolve_locked(allow_download=allow_download)
            self._resolved = resolved
            return resolved

    def _resolve_locked(self, *, allow_download: bool) -> ResolvedFonts:
        out = ResolvedFonts()

        # 1. Env overrides (explicit user intent always wins).
        env_r = os.environ.get("LEAGENT_CJK_FONT", "").strip()
        env_b = os.environ.get("LEAGENT_CJK_FONT_BOLD", "").strip()
        if env_r and Path(env_r).is_file():
            out.regular_path = env_r
            out.bold_path = env_b if env_b and Path(env_b).is_file() else None
            out.source = "env"
            return out
        if env_r:
            out.warnings.append(f"LEAGENT_CJK_FONT points to a missing file: {env_r}")

        # 2. Managed download dir.
        managed_r = self._managed_path("regular")
        if managed_r:
            out.regular_path = managed_r
            out.bold_path = self._managed_path("bold")
            out.source = "managed"
            return out

        # 3. System scan.
        system_r = discover_cjk_font_file(is_bold=False)
        if system_r:
            out.regular_path = system_r
            out.bold_path = discover_cjk_font_file(is_bold=True)
            out.source = "system"
            return out

        # 4. Auto-download pinned Noto faces.
        if allow_download and _auto_download_enabled():
            downloaded = self._download_faces(("regular", "bold"), warnings=out.warnings)
            if downloaded.get("regular"):
                out.regular_path = downloaded["regular"]
                out.bold_path = downloaded.get("bold")
                out.source = "downloaded"
                return out
        elif allow_download:
            out.warnings.append(
                "No CJK font found and auto-download is disabled "
                "(LEAGENT_FONT_AUTO_DOWNLOAD=0)."
            )

        # 5. Nothing available.
        out.warnings.append(
            "No pan-Unicode font available; CJK text will render as boxes. "
            "Install fonts-noto-cjk, set LEAGENT_CJK_FONT, or enable "
            "LEAGENT_FONT_AUTO_DOWNLOAD."
        )
        out.source = "none"
        return out

    def resolve_emoji(self, *, allow_download: bool = True) -> tuple[str | None, list[str]]:
        """Resolve a ReportLab-compatible monochrome emoji font path."""
        warnings: list[str] = []

        env = os.environ.get("LEAGENT_EMOJI_FONT", "").strip()
        if env and Path(env).is_file():
            if _looks_color_emoji(env):
                warnings.append(
                    f"LEAGENT_EMOJI_FONT points to a color emoji font (unsupported "
                    f"by ReportLab): {env}"
                )
            else:
                return env, warnings
        elif env:
            warnings.append(f"LEAGENT_EMOJI_FONT points to a missing file: {env}")

        managed = self._managed_path("emoji")
        if managed:
            return managed, warnings

        system = discover_emoji_font_file()
        if system:
            return system, warnings

        if allow_download and _auto_download_enabled():
            downloaded = self._download_faces(("emoji",), warnings=warnings)
            if downloaded.get("emoji"):
                return downloaded["emoji"], warnings
        elif allow_download:
            warnings.append(
                "No emoji font found and auto-download is disabled "
                "(LEAGENT_FONT_AUTO_DOWNLOAD=0)."
            )

        return None, warnings

    def _managed_path(self, face: str) -> str | None:
        asset = FONT_MANIFEST[face]
        path = self._fonts_dir / asset.filename
        if path.is_file() and path.stat().st_size > 0:
            return str(path)
        return None

    # ------------------------------------------------------------------
    # Download
    # ------------------------------------------------------------------

    def _download_faces(
        self, faces: tuple[str, ...], *, warnings: list[str]
    ) -> dict[str, str]:
        out: dict[str, str] = {}
        for face in faces:
            asset = FONT_MANIFEST[face]
            existing = self._managed_path(face)
            if existing:
                out[face] = existing
                continue
            path = self._download_asset(asset, warnings=warnings)
            if path:
                out[face] = path
        return out

    def _download_asset(self, asset: FontAsset, *, warnings: list[str]) -> str | None:
        try:
            import httpx
        except ImportError:
            warnings.append("httpx not installed; cannot auto-download fonts.")
            return None

        target = self._fonts_dir / asset.filename
        tmp = target.with_suffix(target.suffix + ".part")
        for url in asset.urls:
            try:
                logger.info("docgen_font_download_start", url=url, target=str(target))
                self._fonts_dir.mkdir(parents=True, exist_ok=True)
                with (
                    httpx.Client(timeout=60.0, follow_redirects=True) as client,
                    client.stream("GET", url) as resp,
                ):
                    resp.raise_for_status()
                    digest = hashlib.sha256()
                    with open(tmp, "wb") as fh:
                        for chunk in resp.iter_bytes(1 << 20):
                            digest.update(chunk)
                            fh.write(chunk)
                if digest.hexdigest() != asset.sha256:
                    warnings.append(
                        f"Font download integrity check failed for {asset.filename}."
                    )
                    logger.warning(
                        "docgen_font_sha256_mismatch",
                        url=url,
                        expected=asset.sha256,
                        actual=digest.hexdigest(),
                    )
                    tmp.unlink(missing_ok=True)
                    continue
                tmp.replace(target)
                logger.info("docgen_font_downloaded", path=str(target))
                return str(target)
            except Exception as exc:  # noqa: BLE001 - try the next mirror
                logger.warning("docgen_font_download_failed", url=url, error=str(exc))
                tmp.unlink(missing_ok=True)
                continue
        warnings.append(
            f"Could not download {asset.filename} from any mirror; "
            "check network access or set LEAGENT_CJK_FONT."
        )
        return None

    # ------------------------------------------------------------------
    # ReportLab registration
    # ------------------------------------------------------------------

    def register_pdf_fonts(self, *, allow_download: bool = True) -> dict[str, Any]:
        """Register resolved fonts with ReportLab and return the mapping.

        Returns a dict with keys ``regular`` / ``bold`` / ``mono`` / ``emoji``
        (ReportLab font names — built-ins / ``None`` when embedding failed),
        ``embedded`` / ``emoji_embedded`` (bool), ``source``, and ``warnings``.

        A resolved font can still fail registration — ReportLab rejects CFF
        outlines, which covers many distro Noto CJK OTF/TTCs. In that case we
        fall through to downloading the pinned TrueType faces.
        """
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        resolved = self.resolve(allow_download=allow_download)
        warnings = list(resolved.warnings)
        source = resolved.source

        regular = "Helvetica"
        bold = "Helvetica-Bold"
        embedded = False
        regular_path = resolved.regular_path
        bold_path = resolved.bold_path

        if regular_path and self._register_pdf_face(
            pdfmetrics, TTFont, PDF_FONT_REGULAR, regular_path, is_bold=False
        ):
            regular = PDF_FONT_REGULAR
            embedded = True
        elif regular_path:
            warnings.append(
                f"Font is not ReportLab-compatible (CFF outlines?): {regular_path}"
            )

        if (
            not embedded
            and allow_download
            and _auto_download_enabled()
            and source not in ("managed", "downloaded")
        ):
            downloaded = self._download_faces(("regular", "bold"), warnings=warnings)
            dl_regular = downloaded.get("regular")
            if dl_regular and self._register_pdf_face(
                pdfmetrics, TTFont, PDF_FONT_REGULAR, dl_regular, is_bold=False
            ):
                regular = PDF_FONT_REGULAR
                embedded = True
                source = "downloaded"
                regular_path = dl_regular
                bold_path = downloaded.get("bold")

        if embedded:
            if bold_path and self._register_pdf_face(
                pdfmetrics, TTFont, PDF_FONT_BOLD, bold_path, is_bold=True
            ):
                bold = PDF_FONT_BOLD
            else:
                bold = regular
            # Family registration is best-effort.
            with contextlib.suppress(Exception):
                pdfmetrics.registerFontFamily(
                    PDF_FONT_FAMILY,
                    normal=regular,
                    bold=bold,
                    italic=regular,
                    boldItalic=bold,
                )

        # Code blocks: an embedded pan-Unicode face beats a Latin-only
        # monospace — CJK comments/strings in code must not tofu.
        mono = regular if embedded else "Courier"

        emoji_name: str | None = None
        emoji_path, emoji_warnings = self.resolve_emoji(allow_download=allow_download)
        warnings.extend(emoji_warnings)
        if emoji_path and self._register_pdf_face(
            pdfmetrics, TTFont, PDF_FONT_EMOJI, emoji_path, is_bold=False
        ):
            emoji_name = PDF_FONT_EMOJI
        elif emoji_path:
            warnings.append(
                f"Emoji font is not ReportLab-compatible (color/CBDT?): {emoji_path}"
            )

        if not embedded:
            warnings.append(
                "中文字体未成功嵌入，中文将显示为方框（tofu）。"
                "Set LEAGENT_CJK_FONT or enable font auto-download."
            )
            logger.warning("docgen_pdf_cjk_unavailable", warnings=warnings)

        return {
            "regular": regular,
            "bold": bold,
            "mono": mono,
            "emoji": emoji_name,
            "embedded": embedded,
            "emoji_embedded": emoji_name is not None,
            "source": source,
            "regular_path": regular_path,
            "emoji_path": emoji_path,
            "warnings": warnings,
        }

    def _register_pdf_face(
        self,
        pdfmetrics: Any,
        ttfont_cls: Any,
        internal_name: str,
        path: str,
        *,
        is_bold: bool,
    ) -> bool:
        if not path or not Path(path).is_file():
            return False
        cached = self._pdf_registered.get(internal_name)
        if cached == path:
            return True
        try:
            pdfmetrics.getFont(internal_name)
            self._pdf_registered[internal_name] = path
            return True
        except Exception:  # noqa: BLE001 - not registered yet
            pass
        lower = path.lower()
        if not lower.endswith((".otf", ".ttf", ".ttc")):
            return False
        if not lower.endswith(".ttc"):
            try:
                pdfmetrics.registerFont(ttfont_cls(internal_name, path))
                self._pdf_registered[internal_name] = path
                return True
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "docgen_pdf_font_register_failed", path=path, error=str(exc)
                )
                return False
        # TTC: probe subfonts — wrong index means missing Han glyphs.
        for sub in _ttc_subfont_sequence(path, is_bold):
            try:
                pdfmetrics.registerFont(
                    ttfont_cls(internal_name, path, subfontIndex=sub)  # type: ignore[call-arg]
                )
                logger.info(
                    "docgen_pdf_ttc_subfont",
                    name=internal_name,
                    path=path,
                    subfont=sub,
                )
                self._pdf_registered[internal_name] = path
                return True
            except Exception:  # noqa: BLE001 - try the next subfont
                continue
        return False

    # ------------------------------------------------------------------
    # Office (docx / pptx) font names
    # ------------------------------------------------------------------

    @staticmethod
    def office_east_asia_font() -> str:
        """East-Asian font name for OOXML runs.

        DOCX/PPTX cannot embed fonts via python-docx/pptx; the best portable
        choice is a name resolvable on the viewer's machine. ``Microsoft
        YaHei`` resolves on Windows and modern Office for Mac; LibreOffice
        falls back to an installed CJK face by family metadata.
        """
        return "Microsoft YaHei"


def _ttc_subfont_sequence(path: str, is_bold: bool) -> list[Any]:
    """Subfont candidates for a ``.ttc`` collection: SC/TW/JP names, then indices."""
    p = path.lower()
    w = "Bold" if is_bold else "Regular"
    names: list[Any] = [
        f"NotoSansCJKsc-{w}",
        f"NotoSansCJKtc-{w}",
        f"NotoSansCJKjp-{w}",
    ]
    if "sourcehansans" in p or "source-han" in p or "adobe" in p:
        names = [f"SourceHanSansSC-{w}", *names]
    if "msyh" in p or "microsoft yahei" in p:
        names = [0, "MSYH", "MicrosoftYaHei", "Microsoft YaHei", *names]
    index_probe = list(range(64))
    if any(x in p for x in ("wqy", "droid", "arphic", "ukai", "uming", "microhei", "zenhei")):
        return [0, 1, 2, *names, *index_probe]
    return [*names, *index_probe]


def _looks_color_emoji(path: str) -> bool:
    name = Path(path).name.lower()
    return "color" in name or "colr" in name or "cbdt" in name


def discover_emoji_font_file() -> str | None:
    """Locate a monochrome Noto Emoji TTF on the system (never Color/CBDT)."""
    for directory in _EMOJI_SYSTEM_DIRS:
        if not directory.is_dir():
            continue
        for name in _EMOJI_SYSTEM_NAMES:
            candidate = directory / name
            if candidate.is_file() and not _looks_color_emoji(str(candidate)):
                return str(candidate)
        # Fuzzy: any NotoEmoji*.ttf that isn't color.
        with contextlib.suppress(OSError):
            for candidate in sorted(directory.glob("NotoEmoji*.ttf")):
                if candidate.is_file() and not _looks_color_emoji(str(candidate)):
                    return str(candidate)
    return None


_manager: FontManager | None = None
_manager_lock = threading.Lock()


def get_font_manager() -> FontManager:
    """Return the process-wide FontManager singleton."""
    global _manager
    with _manager_lock:
        if _manager is None:
            _manager = FontManager()
        return _manager


def reset_font_manager() -> None:
    """Reset the singleton (tests only)."""
    global _manager
    with _manager_lock:
        _manager = None
