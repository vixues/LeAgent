"""Slide content infrastructure for professional deck rendering.

Pure-Python (no python-pptx imports) composition layer that the PPTX
renderer consumes. Three concerns live here so the renderer stays a thin
translation onto DrawingML:

- **Typography** — :class:`DeckTypography` derives a complete, consistent
  type scale from a deck theme: display / slide title / kicker / subtitle /
  takeaway / caption roles plus per-level bullet styles (size, weight,
  color role, bullet glyph, indent geometry). All sizes are points.
- **Layout geometry** — :class:`SlideGeometry` computes rectangular
  :class:`Region`\\ s in EMU for the standard slide anatomy (title band,
  content area, image/text splits, N-column grids, bottom takeaway band)
  so every layout shares one margin/gutter system.
- **Content flattening + autofit** — :func:`flatten_body` parses slide
  markdown into a flat list of :class:`BulletPara` (kind + level + text),
  and :func:`fit_body_size` estimates wrapped text height (CJK-aware) to
  shrink the body size until content fits its region — decks never
  overflow their boxes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from leagent.docgen.themes import Theme

__all__ = [
    "EMU_PER_IN",
    "BulletPara",
    "DeckTypography",
    "Region",
    "SlideGeometry",
    "TextStyle",
    "estimate_code_card_height_pt",
    "estimate_text_height_pt",
    "fit_body_size",
    "flatten_body",
    "is_dark_color",
    "segment_body",
]

EMU_PER_IN = 914_400
EMU_PER_PT = 12_700

# ---------------------------------------------------------------------------
# Color helpers
# ---------------------------------------------------------------------------


def relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of a ``#RRGGBB`` color (0 = black, 1 = white)."""
    raw = (hex_color or "#000000").lstrip("#")
    try:
        r, g, b = (int(raw[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
    except (ValueError, IndexError):
        return 0.0

    def _lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def is_dark_color(hex_color: str) -> bool:
    return relative_luminance(hex_color) < 0.35


# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------

ColorRole = Literal["text", "text_light", "heading", "accent", "on_primary"]
FontRole = Literal["heading", "body", "mono"]


@dataclass(frozen=True)
class TextStyle:
    """One typographic role: size in pt plus rendering hints."""

    size: float
    bold: bool = False
    italic: bool = False
    color: ColorRole = "text"
    font: FontRole = "body"
    line_spacing: float = 1.12
    space_before_pt: float = 0.0
    space_after_pt: float = 6.0
    letter_spacing_pt: float = 0.0  # tracking (kickers); 0 = normal
    uppercase: bool = False


@dataclass(frozen=True)
class BulletLevelStyle:
    """Typography + geometry for one bullet nesting level."""

    text: TextStyle
    glyph: str | None  # None = no bullet marker (plain paragraph)
    indent_in: float   # left margin, inches
    hang_in: float     # hanging indent (marker column), inches


@dataclass(frozen=True)
class DeckTypography:
    """Complete deck type scale derived from a theme."""

    display: TextStyle
    slide_title: TextStyle
    kicker: TextStyle
    subtitle: TextStyle
    section: TextStyle
    body: TextStyle
    run_in_heading: TextStyle
    quote: TextStyle
    attribution: TextStyle
    takeaway: TextStyle
    caption: TextStyle
    footer: TextStyle
    code: TextStyle
    levels: tuple[BulletLevelStyle, ...] = field(default_factory=tuple)

    @classmethod
    def from_theme(cls, theme: Theme) -> DeckTypography:
        d = theme.deck
        body = d.body_size

        def _level(i: int) -> BulletLevelStyle:
            sizes = (body, body - 1.5, body - 3.0, body - 4.0, body - 4.0)
            colors: tuple[ColorRole, ...] = (
                "text", "text", "text_light", "text_light", "text_light"
            )
            # Optically balanced markers (• – ◦) — avoid tiny · / ▪ that
            # read smaller than body text even at 100% bullet size.
            glyphs = ("\u2022", "\u2013", "\u25e6", "\u25e6", "\u25e6")
            return BulletLevelStyle(
                text=TextStyle(
                    size=max(10.0, sizes[i]),
                    color=colors[i],
                    space_before_pt=8.0 if i == 0 else 2.0,
                    space_after_pt=4.0,
                ),
                glyph=glyphs[i],
                indent_in=0.02 + 0.32 * i,
                hang_in=0.28,
            )

        return cls(
            display=TextStyle(
                size=d.title_size, bold=True, color="heading", font="heading",
                line_spacing=1.08, space_after_pt=10.0,
            ),
            slide_title=TextStyle(
                size=d.slide_title_size, bold=True, color="heading",
                font="heading", line_spacing=1.1, space_after_pt=4.0,
            ),
            kicker=TextStyle(
                size=11.0, bold=True, color="accent",
                letter_spacing_pt=1.4, uppercase=True, space_after_pt=2.0,
            ),
            subtitle=TextStyle(size=body + 1.0, color="text_light", space_after_pt=6.0),
            section=TextStyle(
                size=d.title_size - 4.0, bold=True, color="on_primary",
                font="heading", line_spacing=1.1,
            ),
            body=TextStyle(size=body, space_after_pt=6.0, line_spacing=1.16),
            run_in_heading=TextStyle(
                size=body + 3.0, bold=True, color="heading", font="heading",
                space_before_pt=10.0, space_after_pt=4.0,
            ),
            quote=TextStyle(
                size=d.slide_title_size - 2.0, color="heading", font="heading",
                line_spacing=1.25,
            ),
            attribution=TextStyle(size=body, color="text_light", space_before_pt=14.0),
            takeaway=TextStyle(size=body + 0.5, bold=True, color="text"),
            caption=TextStyle(size=12.0, color="text_light"),
            footer=TextStyle(size=10.0, color="text_light"),
            code=TextStyle(
                size=max(10.0, body - 2.0),
                color="text",
                font="mono",
                line_spacing=1.28,
                space_before_pt=0.0,
                space_after_pt=1.5,
            ),
            levels=tuple(_level(i) for i in range(5)),
        )

    def level(self, i: int) -> BulletLevelStyle:
        return self.levels[min(max(i, 0), len(self.levels) - 1)]


# ---------------------------------------------------------------------------
# Layout geometry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Region:
    """A rectangle in EMU."""

    left: int
    top: int
    width: int
    height: int

    @property
    def right(self) -> int:
        return self.left + self.width

    @property
    def bottom(self) -> int:
        return self.top + self.height

    def inset(self, dx: int, dy: int | None = None) -> Region:
        dy = dx if dy is None else dy
        return Region(
            self.left + dx, self.top + dy, self.width - 2 * dx, self.height - 2 * dy
        )


def _in(v: float) -> int:
    return int(v * EMU_PER_IN)


@dataclass(frozen=True)
class SlideGeometry:
    """Margin/gutter system + standard slide anatomy in EMU.

    All layouts share these regions, so slides in one deck align perfectly:

    - title band (kicker / title / accent bar / subtitle)
    - content area between title band and footer strip
    - optional bottom takeaway band carved out of the content area
    - image/text splits and N-column grids inside any region
    """

    slide_w: int
    slide_h: int
    margin: int = _in(0.6)
    gutter: int = _in(0.3)
    footer_h: int = _in(0.5)
    takeaway_h: int = _in(0.72)

    @property
    def content_w(self) -> int:
        return self.slide_w - 2 * self.margin

    def full_bleed(self) -> Region:
        return Region(0, 0, self.slide_w, self.slide_h)

    # -- title band -----------------------------------------------------

    def kicker_region(self) -> Region:
        return Region(self.margin, _in(0.38), self.content_w, _in(0.3))

    def title_region(self, *, has_kicker: bool) -> Region:
        top = _in(0.68) if has_kicker else _in(0.45)
        return Region(self.margin, top, self.content_w, _in(0.9))

    def accent_bar_region(self, *, has_kicker: bool) -> Region:
        top = _in(1.52) if has_kicker else _in(1.28)
        return Region(self.margin, top, _in(1.6), int(4 * EMU_PER_PT))

    def subtitle_region(self, *, has_kicker: bool) -> Region:
        top = _in(1.66) if has_kicker else _in(1.42)
        return Region(self.margin, top, self.content_w, _in(0.42))

    def content_top(self, *, has_title: bool, has_kicker: bool, has_subtitle: bool) -> int:
        if not has_title:
            return self.margin
        base = _in(1.52) if has_kicker else _in(1.28)
        base += _in(0.22)  # breathing room under the accent bar
        if has_subtitle:
            base += _in(0.46)
        return base

    # -- content regions --------------------------------------------------

    def content_region(self, top: int, *, has_takeaway: bool = False) -> Region:
        bottom = self.slide_h - self.footer_h
        if has_takeaway:
            bottom -= self.takeaway_h + _in(0.12)
        return Region(self.margin, top, self.content_w, max(0, bottom - top))

    def takeaway_region(self) -> Region:
        return Region(
            self.margin,
            self.slide_h - self.footer_h - self.takeaway_h,
            self.content_w,
            self.takeaway_h,
        )

    def footer_text_region(self) -> Region:
        return Region(self.margin, self.slide_h - _in(0.45), _in(4.0), _in(0.35))

    def slide_number_region(self) -> Region:
        return Region(
            self.slide_w - _in(1.2), self.slide_h - _in(0.45), _in(0.8), _in(0.35)
        )

    # -- composition helpers ----------------------------------------------

    def split(
        self, region: Region, ratio: float, *, side: Literal["left", "right", "top"] = "right"
    ) -> tuple[Region, Region]:
        """Split a region into (text, media) with a gutter.

        ``ratio`` is the media share of the axis (0.2–0.8 clamped);
        ``side`` says where the media half sits.
        """
        ratio = min(0.8, max(0.2, ratio))
        if side == "top":
            media_h = int((region.height - self.gutter) * ratio)
            media = Region(region.left, region.top, region.width, media_h)
            text = Region(
                region.left,
                region.top + media_h + self.gutter,
                region.width,
                region.height - media_h - self.gutter,
            )
            return text, media
        media_w = int((region.width - self.gutter) * ratio)
        text_w = region.width - media_w - self.gutter
        if side == "left":
            media = Region(region.left, region.top, media_w, region.height)
            text = Region(region.left + media_w + self.gutter, region.top, text_w, region.height)
        else:
            text = Region(region.left, region.top, text_w, region.height)
            media = Region(region.left + text_w + self.gutter, region.top, media_w, region.height)
        return text, media

    def columns(self, region: Region, n: int, *, weights: list[float] | None = None) -> list[Region]:
        """Divide a region into ``n`` columns (equal or weighted) with gutters."""
        n = max(1, n)
        usable = region.width - self.gutter * (n - 1)
        if weights and len(weights) == n and all(w > 0 for w in weights):
            total = sum(weights)
            widths = [int(usable * w / total) for w in weights]
        else:
            widths = [usable // n] * n
        out: list[Region] = []
        x = region.left
        for w in widths:
            out.append(Region(x, region.top, w, region.height))
            x += w + self.gutter
        return out


# ---------------------------------------------------------------------------
# Body flattening (markdown -> paragraph plan)
# ---------------------------------------------------------------------------

ParaKind = Literal["para", "bullet", "numbered", "heading", "quote", "code"]


@dataclass
class BulletPara:
    """One paragraph of slide body content."""

    text: str
    kind: ParaKind = "para"
    level: int = 0
    checked: bool | None = None  # task-list state
    number: int | None = None    # 1-based, for numbered items


def flatten_body(markdown_text: str) -> list[BulletPara]:
    """Parse slide markdown into a flat, leveled paragraph plan."""
    from leagent.docgen.markdown import parse_markdown_blocks
    from leagent.docgen.model import (
        CodeBlock,
        HeadingBlock,
        ListBlock,
        ListItem,
        ParagraphBlock,
        QuoteBlock,
    )

    out: list[BulletPara] = []
    if not markdown_text or not markdown_text.strip():
        return out

    def _walk(items: list[ListItem], level: int, *, ordered: bool) -> None:
        for idx, item in enumerate(items, start=1):
            kind: ParaKind = "numbered" if (ordered and level == 0) else "bullet"
            out.append(
                BulletPara(
                    text=item.text,
                    kind=kind,
                    level=level,
                    checked=item.checked,
                    number=idx if kind == "numbered" else None,
                )
            )
            if item.children:
                _walk(item.children, level + 1, ordered=False)

    for block in parse_markdown_blocks(markdown_text):
        if isinstance(block, ListBlock):
            _walk(block.items, 0, ordered=block.ordered)
        elif isinstance(block, HeadingBlock):
            out.append(BulletPara(text=block.text, kind="heading"))
        elif isinstance(block, QuoteBlock):
            out.append(BulletPara(text=block.text, kind="quote"))
        elif isinstance(block, CodeBlock):
            lines = block.code.splitlines() or [""]
            for line in lines:
                out.append(BulletPara(text=line, kind="code"))
        elif isinstance(block, ParagraphBlock):
            out.append(BulletPara(text=block.text, kind="para"))
        # Tables/charts/images inside body markdown are ignored here — they
        # have first-class slide fields with proper layout treatment.
    return out


BodySegmentKind = Literal["text", "code"]

# Vertical chrome around a fenced code surface (padding + outer gap), points.
_CODE_PAD_PT = 10.0
_CODE_GAP_PT = 8.0


def segment_body(
    paras: list[BulletPara],
) -> list[tuple[BodySegmentKind, list[BulletPara]]]:
    """Group consecutive paragraphs into text vs fenced-code segments."""
    segments: list[tuple[BodySegmentKind, list[BulletPara]]] = []
    for para in paras:
        kind: BodySegmentKind = "code" if para.kind == "code" else "text"
        if segments and segments[-1][0] == kind:
            segments[-1][1].append(para)
        else:
            segments.append((kind, [para]))
    return segments


# ---------------------------------------------------------------------------
# Autofit (estimate + shrink)
# ---------------------------------------------------------------------------

_INLINE_MARKS = ("**", "__", "~~", "`")


def _plain_len_pt(text: str, size: float) -> float:
    """Approximate rendered width of ``text`` at ``size`` pt (CJK-aware)."""
    plain = text
    for mark in _INLINE_MARKS:
        plain = plain.replace(mark, "")
    width = 0.0
    for ch in plain:
        if "\u2e80" <= ch <= "\u9fff" or "\uff00" <= ch <= "\uffef":
            width += 1.0
        elif ch in "iljI.,:;'|![]() ":
            width += 0.33
        else:
            width += 0.52
    return width * size


def _para_height_pt(
    para: BulletPara, typo: DeckTypography, width_pt: float, *, scale: float
) -> float:
    if para.kind == "heading":
        style = typo.run_in_heading
        avail = width_pt
    elif para.kind == "quote":
        style = typo.body
        avail = width_pt
    elif para.kind == "code":
        style = typo.code
        # Inner text width accounts for surface padding + accent bar.
        avail = max(36.0, width_pt - 28.0)
    else:
        lvl = typo.level(para.level)
        style = lvl.text
        avail = max(36.0, width_pt - (lvl.indent_in + lvl.hang_in) * 72.0)
    size = style.size * scale
    line_h = size * max(style.line_spacing, 1.0) * 1.08
    text_w = _plain_len_pt(para.text, size)
    lines = max(1, -(-int(text_w) // max(1, int(avail))))
    return lines * line_h + (style.space_before_pt + style.space_after_pt) * scale


def estimate_text_height_pt(
    paras: list[BulletPara], typo: DeckTypography, width_pt: float, *, scale: float = 1.0
) -> float:
    """Estimated rendered height of a paragraph plan at a given size scale."""
    total = 0.0
    for seg_i, (kind, items) in enumerate(segment_body(paras)):
        if kind == "code":
            if seg_i > 0:
                total += _CODE_GAP_PT * scale
            total += estimate_code_card_height_pt(
                items, typo, width_pt, scale=scale
            )
        else:
            total += sum(
                _para_height_pt(p, typo, width_pt, scale=scale) for p in items
            )
    return total


def estimate_code_card_height_pt(
    lines: list[BulletPara],
    typo: DeckTypography,
    width_pt: float,
    *,
    scale: float = 1.0,
) -> float:
    """Height of a fenced-code surface card (lines + inner padding), in points."""
    inner = sum(_para_height_pt(p, typo, width_pt, scale=scale) for p in lines)
    return inner + 2.0 * _CODE_PAD_PT * scale


def fit_body_size(
    paras: list[BulletPara],
    typo: DeckTypography,
    region: Region,
    *,
    min_scale: float = 0.62,
) -> float:
    """Largest scale (≤ 1.0) at which the plan fits the region height."""
    if not paras:
        return 1.0
    width_pt = region.width / EMU_PER_PT
    height_pt = region.height / EMU_PER_PT
    scale = 1.0
    while scale > min_scale:
        if estimate_text_height_pt(paras, typo, width_pt, scale=scale) <= height_pt:
            return scale
        scale -= 0.06
    return min_scale
