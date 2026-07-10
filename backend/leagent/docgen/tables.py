"""Shared table-processing engine for all document renderers.

One pipeline turns a raw :class:`~leagent.docgen.model.TableBlock` into a
fully analysed :class:`ProcessedTable` that every renderer (PDF / DOCX /
PPTX / HTML / Markdown) consumes, so tabular content behaves identically
across formats while each renderer stays free to draw it natively.

What the engine does (consulting-grade table hygiene):

- **Normalization** — header/body split, uniform column count, trimmed cells.
- **Column intelligence** — per-column kind inference (text / number /
  percent / currency / delta / date-ish). Numeric columns auto right-align;
  explicit ``TableBlock.align`` always wins.
- **Number polish** — bare integers/decimals gain thousands separators
  (``1234567`` → ``1,234,567``); disable with ``number_format=false``.
- **Semantic rows/cells** — total/summary rows (合计 / 总计 / Total / …)
  are detected (or forced via ``total_row=true``) and emphasised; delta
  cells (``+8%``, ``-3.2``, ``▲``, ``(1,200)``) carry a polarity so
  renderers color them consistently (green up, red down).
- **Column widths** — CJK-aware content weighting shared by PDF, PPTX,
  and HTML; ``widths`` on the block overrides with explicit percents.
- **Style resolution** — :func:`resolve_table_style` maps the block's
  ``style`` variant (``default`` banded / ``minimal`` open rules /
  ``grid``) plus the theme palette (light or dark deck) to concrete hex
  colors and rule weights, so all formats share one visual contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from leagent.docgen.model import TableBlock
    from leagent.docgen.themes import Theme

__all__ = [
    "CellPolarity",
    "ColumnKind",
    "ProcessedCell",
    "ProcessedColumn",
    "ProcessedTable",
    "TableStyleSpec",
    "process_table",
    "resolve_table_style",
]

ColumnKind = Literal["text", "number", "percent", "currency", "delta", "date"]
CellPolarity = Literal["positive", "negative"]

# ---------------------------------------------------------------------------
# Cell classification
# ---------------------------------------------------------------------------

_CURRENCY_SIGNS = "¥$€£₩₹"
_BARE_NUMBER_RE = re.compile(r"^[+\-−]?\d{1,3}(,\d{3})*(\.\d+)?$|^[+\-−]?\d+(\.\d+)?$")
_PERCENT_RE = re.compile(r"^[+\-−]?\d[\d,]*(\.\d+)?\s*%$")
_CURRENCY_RE = re.compile(
    rf"^[+\-−]?\s*(US\$|HK\$|RMB|[{_CURRENCY_SIGNS}])\s*\d[\d,]*(\.\d+)?\s*"
    r"([KMBkmb]|万|亿|千|百万)?$"
)
_NUMBER_SUFFIX_RE = re.compile(r"^[+\-−]?\d[\d,]*(\.\d+)?\s*([KMBkmb]|万|亿|千|百万|bps|pp|x)$")
_DATE_RE = re.compile(
    r"^(\d{4}[-/年.]\d{1,2}([-/月.]\d{1,2}日?)?|\d{1,2}/\d{1,2}/\d{2,4}|"
    r"(19|20)\d{2}|Q[1-4](\s*['’]?\d{2,4})?|FY\s?\d{2,4}|\d{4}[Hh][12])$"
)
_DELTA_PREFIX_RE = re.compile(r"^[+↑▲△]\s*\d|^[-−↓▼▽]\s*\d")
_PAREN_NEGATIVE_RE = re.compile(r"^\(\s*\d[\d,]*(\.\d+)?\s*%?\s*\)$")
_ARROW_ONLY_RE = re.compile(r"^[↑▲△↗]$|^[↓▼▽↘]$")
_INT_NO_SEP_RE = re.compile(r"^([+\-−]?)(\d{5,})(\.\d+)?$")

_TOTAL_LABELS = frozenset(
    {
        "total",
        "totals",
        "sum",
        "grand total",
        "overall",
        "合计",
        "总计",
        "小计",
        "总额",
        "总和",
        "汇总",
        "合 计",
        "总 计",
    }
)

_POSITIVE_LEADS = "+↑▲△↗"
_NEGATIVE_LEADS = "-−↓▼▽↘"


def _classify_cell(text: str) -> ColumnKind | None:
    """Best-effort kind for one trimmed cell; ``None`` for empty/unknown."""
    if not text:
        return None
    if _PERCENT_RE.match(text) or _PAREN_NEGATIVE_RE.match(text):
        return "percent" if "%" in text else "number"
    if _CURRENCY_RE.match(text):
        return "currency"
    if _BARE_NUMBER_RE.match(text) or _NUMBER_SUFFIX_RE.match(text):
        return "number"
    if _DATE_RE.match(text):
        return "date"
    if _DELTA_PREFIX_RE.match(text) or _ARROW_ONLY_RE.match(text):
        return "delta"
    return None


def _cell_polarity(text: str) -> CellPolarity | None:
    """Sign of a delta-style cell (``+8%`` / ``▼3.2`` / ``(1,200)``)."""
    if not text:
        return None
    if _PAREN_NEGATIVE_RE.match(text):
        return "negative"
    lead = text[0]
    body_is_delta = bool(
        _DELTA_PREFIX_RE.match(text) or _ARROW_ONLY_RE.match(text)
    )
    if not body_is_delta:
        return None
    if lead in _POSITIVE_LEADS:
        return "positive"
    if lead in _NEGATIVE_LEADS:
        return "negative"
    return None


def _format_number(text: str) -> str:
    """Insert thousands separators into bare, separator-less integers."""
    m = _INT_NO_SEP_RE.match(text)
    if not m:
        return text
    sign, int_part, frac = m.group(1), m.group(2), m.group(3) or ""
    grouped = f"{int(int_part):,}"
    return f"{sign}{grouped}{frac}"


def _display_width(text: str) -> float:
    """Approximate rendered width; CJK glyphs count double."""
    return sum(2.0 if "\u2e80" <= ch <= "\u9fff" or "\uff00" <= ch <= "\uffef" else 1.0 for ch in text)


# ---------------------------------------------------------------------------
# Processed structures
# ---------------------------------------------------------------------------


@dataclass
class ProcessedCell:
    """One analysed cell, ready for format-specific rich-text rendering."""

    text: str
    align: Literal["left", "center", "right"]
    polarity: CellPolarity | None = None
    bold: bool = False


@dataclass
class ProcessedColumn:
    index: int
    kind: ColumnKind
    align: Literal["left", "center", "right"]
    weight: float  # normalised width fraction; sums to 1.0 across columns


@dataclass
class ProcessedTable:
    """Renderer-agnostic table: uniform grid + column/row semantics."""

    columns: list[ProcessedColumn]
    header: list[ProcessedCell]  # empty when the table has no header row
    body: list[list[ProcessedCell]]
    total_row_index: int | None  # index into body
    caption: str | None
    style: str  # default | minimal | grid
    zebra: bool

    @property
    def has_header(self) -> bool:
        return bool(self.header)

    @property
    def col_count(self) -> int:
        return len(self.columns)

    def width_fractions(self) -> list[float]:
        return [c.weight for c in self.columns]


# ---------------------------------------------------------------------------
# Style resolution
# ---------------------------------------------------------------------------


@dataclass
class TableStyleSpec:
    """Concrete visual contract (hex colors, pt rules) shared by renderers."""

    header_fill: str | None       # None = open header (no band)
    header_text: str
    header_rule: str              # rule under the header
    header_rule_width: float      # pt
    row_rule: str | None          # hairline between body rows (None = none)
    row_rule_width: float
    outer_rule: str | None        # top/bottom frame rules (minimal style)
    outer_rule_width: float
    grid: bool                    # full cell grid
    zebra_fill: str | None
    total_fill: str | None
    total_text: str
    total_rule: str               # rule above the total row
    total_rule_width: float
    body_text: str
    positive: str
    negative: str
    caption_text: str

    # Cell paddings in points (renderers translate to their own units).
    pad_v: float = 5.0
    pad_h: float = 6.0


def resolve_table_style(
    theme: Theme,
    style: str,
    *,
    dark: bool = False,
) -> TableStyleSpec:
    """Map a style variant + theme palette to concrete colors.

    ``dark`` is set by deck renderers whose background makes ``primary``
    unusable as a header band; headers then use the accent color with the
    background color as text.
    """
    c = theme.colors
    if dark:
        header_fill = c.accent
        header_text = c.background
        body_text = c.text
        zebra = c.surface
        rule = c.border
        positive, negative = "#5FD68A", "#FF8A7A"
        caption = c.text_light
    else:
        header_fill = c.primary
        header_text = "#FFFFFF"
        body_text = c.text
        zebra = c.surface
        rule = c.border
        positive, negative = "#1E8449", "#C0392B"
        caption = c.text_light

    if style == "minimal":
        # Open, rule-only table (classic consulting deck exhibit).
        return TableStyleSpec(
            header_fill=None,
            header_text=c.text,
            header_rule=c.primary if not dark else c.accent,
            header_rule_width=1.1,
            row_rule=rule,
            row_rule_width=0.35,
            outer_rule=c.primary if not dark else c.accent,
            outer_rule_width=1.1,
            grid=False,
            zebra_fill=None,
            total_fill=None,
            total_text=body_text,
            total_rule=c.primary if not dark else c.accent,
            total_rule_width=0.9,
            body_text=body_text,
            positive=positive,
            negative=negative,
            caption_text=caption,
        )
    if style == "grid":
        return TableStyleSpec(
            header_fill=header_fill,
            header_text=header_text,
            header_rule=header_fill,
            header_rule_width=0.8,
            row_rule=None,
            row_rule_width=0.0,
            outer_rule=None,
            outer_rule_width=0.0,
            grid=True,
            zebra_fill=zebra if theme.zebra_tables else None,
            total_fill=zebra,
            total_text=body_text,
            total_rule=header_fill,
            total_rule_width=0.9,
            body_text=body_text,
            positive=positive,
            negative=negative,
            caption_text=caption,
        )
    # default — banded header, hairline rows.
    return TableStyleSpec(
        header_fill=header_fill,
        header_text=header_text,
        header_rule=header_fill,
        header_rule_width=0.8,
        row_rule=rule,
        row_rule_width=0.4,
        outer_rule=None,
        outer_rule_width=0.0,
        grid=False,
        zebra_fill=zebra if theme.zebra_tables else None,
        total_fill=zebra,
        total_text=body_text,
        total_rule=header_fill,
        total_rule_width=0.9,
        body_text=body_text,
        positive=positive,
        negative=negative,
        caption_text=caption,
    )


# ---------------------------------------------------------------------------
# Processing pipeline
# ---------------------------------------------------------------------------

_NUMERIC_KINDS: frozenset[str] = frozenset({"number", "percent", "currency", "delta"})


def _infer_column_kind(cells: list[str]) -> ColumnKind:
    """Dominant kind across non-empty cells (>=60% agreement required)."""
    kinds = [k for k in (_classify_cell(c) for c in cells if c) if k is not None]
    non_empty = sum(1 for c in cells if c)
    if not kinds or non_empty == 0:
        return "text"
    counts: dict[str, int] = {}
    for k in kinds:
        counts[k] = counts.get(k, 0) + 1
    # Numeric-family kinds reinforce each other (a revenue column may mix
    # currency and bare numbers).
    numeric_hits = sum(v for k, v in counts.items() if k in _NUMERIC_KINDS)
    if numeric_hits / non_empty >= 0.6:
        dominant = max(
            (k for k in counts if k in _NUMERIC_KINDS),
            key=lambda k: counts[k],
        )
        return dominant  # type: ignore[return-value]
    if counts.get("date", 0) / non_empty >= 0.6:
        return "date"
    return "text"


def _detect_total_row(body: list[list[str]]) -> int | None:
    if len(body) < 2:
        return None
    label = (body[-1][0] if body[-1] else "").strip().lower()
    if label in _TOTAL_LABELS:
        return len(body) - 1
    return None


def process_table(block: TableBlock, *, theme: Theme | None = None) -> ProcessedTable:
    """Analyse a table block into a renderer-agnostic :class:`ProcessedTable`."""
    header_raw, body_raw = block.effective_header_and_body()
    col_count = max(1, len(header_raw), *(len(r) for r in body_raw))

    def _pad(row: list[str]) -> list[str]:
        cells = [str(c).strip() for c in row]
        return (cells + [""] * col_count)[:col_count]

    header_txt = _pad(header_raw) if header_raw else []
    body_txt = [_pad(r) for r in body_raw]

    # Number polish (bare separator-less integers only).
    if getattr(block, "number_format", True):
        body_txt = [[_format_number(c) for c in row] for row in body_txt]

    # Total row: explicit flag wins, else label detection.
    forced_total = getattr(block, "total_row", None)
    if forced_total is True and body_txt:
        total_idx: int | None = len(body_txt) - 1
    elif forced_total is False:
        total_idx = None
    else:
        total_idx = _detect_total_row(body_txt)

    # Column kinds are inferred from body cells excluding the total row
    # (its label cell would otherwise poison the first column).
    sample_rows = [r for i, r in enumerate(body_txt) if i != total_idx]
    kinds: list[ColumnKind] = [
        _infer_column_kind([r[i] for r in sample_rows]) for i in range(col_count)
    ]

    explicit_align = list(block.align or [])
    aligns: list[Literal["left", "center", "right"]] = []
    for i in range(col_count):
        if i < len(explicit_align) and explicit_align[i] in ("left", "center", "right"):
            aligns.append(explicit_align[i])  # type: ignore[arg-type]
        elif kinds[i] in _NUMERIC_KINDS:
            aligns.append("right")
        elif kinds[i] == "date":
            aligns.append("center")
        else:
            aligns.append("left")

    # Width weights: explicit percents win; otherwise CJK-aware content fit.
    explicit_widths = getattr(block, "widths", None)
    if explicit_widths and len(explicit_widths) == col_count and all(
        w > 0 for w in explicit_widths
    ):
        total_w = float(sum(explicit_widths))
        weights = [float(w) / total_w for w in explicit_widths]
    else:
        raw: list[float] = []
        for i in range(col_count):
            samples = [
                _display_width(r[i]) for r in ([header_txt] if header_txt else []) + body_txt
            ]
            longest = max(samples or [1.0])
            avg = sum(samples) / len(samples) if samples else 1.0
            raw.append(min(40.0, max(4.0, 0.55 * longest + 0.45 * avg)))
        total_raw = sum(raw) or float(col_count)
        weights = [w / total_raw for w in raw]

    columns = [
        ProcessedColumn(index=i, kind=kinds[i], align=aligns[i], weight=weights[i])
        for i in range(col_count)
    ]

    header_cells = [
        ProcessedCell(text=t, align=aligns[i], bold=True)
        for i, t in enumerate(header_txt)
    ]
    body_cells: list[list[ProcessedCell]] = []
    for r_idx, row in enumerate(body_txt):
        is_total = r_idx == total_idx
        cells: list[ProcessedCell] = []
        for c_idx, txt in enumerate(row):
            cells.append(
                ProcessedCell(
                    text=txt,
                    align=aligns[c_idx],
                    polarity=_cell_polarity(txt),
                    bold=is_total,
                )
            )
        body_cells.append(cells)

    zebra_override = getattr(block, "zebra", None)
    if zebra_override is not None:
        zebra = bool(zebra_override)
    else:
        zebra = bool(theme.zebra_tables) if theme is not None else True

    return ProcessedTable(
        columns=columns,
        header=header_cells,
        body=body_cells,
        total_row_index=total_idx,
        caption=block.caption,
        style=block.style,
        zebra=zebra and block.style != "minimal",
    )
