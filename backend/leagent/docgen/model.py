"""Typed document / deck intermediate representation (IR).

Every generation path (markdown input or raw block JSON from the agent)
normalises into these Pydantic models before rendering. Text fields accept
markdown *inline* syntax (``**bold**``, `` `code` ``, ``[link](url)``);
renderers parse it via :func:`leagent.docgen.markdown.parse_inline` so rich
text works identically in PDF, DOCX, PPTX, and HTML output.

Models are deliberately tolerant (``extra="ignore"``) — LLM-produced JSON
often carries stray keys.
"""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Shared config
# ---------------------------------------------------------------------------


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


def _coerce_date_str(value: Any) -> str | None:
    """Normalize YAML/front-matter date values to ISO date strings."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value)


Alignment = Literal["left", "center", "right", "justify"]


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


class HeadingBlock(_Model):
    type: Literal["heading"] = "heading"
    text: str
    level: int = Field(default=1, ge=1, le=6)


class ParagraphBlock(_Model):
    type: Literal["paragraph"] = "paragraph"
    text: str
    alignment: Alignment | None = None


class ListItem(_Model):
    text: str
    checked: bool | None = None  # task-list state; None = plain item
    children: list[ListItem] = Field(default_factory=list)


class ListBlock(_Model):
    type: Literal["list"] = "list"
    ordered: bool = False
    items: list[ListItem] = Field(default_factory=list)

    @field_validator("items", mode="before")
    @classmethod
    def _coerce_items(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [
                {"text": str(x)} if not isinstance(x, (dict, BaseModel)) else x
                for x in v
            ]
        return v


class TableBlock(_Model):
    type: Literal["table"] = "table"
    columns: list[str] | None = None  # header row; None = first data row is header
    rows: list[list[str]] = Field(default_factory=list)
    align: list[Alignment] | None = None  # per-column alignment (auto by data type when omitted)
    caption: str | None = None
    style: Literal["default", "minimal", "grid"] = "default"
    # Enterprise-table options (processed by leagent.docgen.tables):
    number_format: bool = True        # thousands separators for bare integers
    total_row: bool | None = None     # None = auto-detect 合计/总计/Total labels
    zebra: bool | None = None         # None = theme default
    widths: list[float] | None = None  # explicit per-column width weights/percents

    @field_validator("rows", mode="before")
    @classmethod
    def _coerce_rows(cls, v: Any) -> Any:
        if isinstance(v, list):
            out = []
            for row in v:
                if isinstance(row, (list, tuple)):
                    out.append(["" if c is None else str(c) for c in row])
                else:
                    out.append([str(row)])
            return out
        return v

    @field_validator("columns", mode="before")
    @classmethod
    def _coerce_columns(cls, v: Any) -> Any:
        if isinstance(v, list):
            return [str(c) for c in v]
        return v

    def effective_header_and_body(self) -> tuple[list[str], list[list[str]]]:
        if self.columns:
            return list(self.columns), [list(r) for r in self.rows]
        if self.rows:
            return list(self.rows[0]), [list(r) for r in self.rows[1:]]
        return [], []


class ImageBlock(_Model):
    type: Literal["image"] = "image"
    path: str | None = None
    url: str | None = None
    base64_data: str | None = None
    caption: str | None = None
    width_pct: float | None = Field(default=None, gt=0, le=100)
    alignment: Alignment | None = "center"


class CodeBlock(_Model):
    type: Literal["code"] = "code"
    code: str
    language: str | None = None
    caption: str | None = None


class QuoteBlock(_Model):
    type: Literal["quote"] = "quote"
    text: str
    attribution: str | None = None


CalloutVariant = Literal["info", "note", "tip", "success", "warning", "danger"]


class CalloutBlock(_Model):
    type: Literal["callout"] = "callout"
    variant: CalloutVariant = "info"
    title: str | None = None
    text: str = ""


class ChartSeries(_Model):
    name: str | None = None
    values: list[float] = Field(default_factory=list)


class ChartBlock(_Model):
    type: Literal["chart"] = "chart"
    chart_type: Literal["bar", "line", "pie", "scatter", "area", "barh"] = "bar"
    title: str | None = None
    categories: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)
    x_label: str | None = None
    y_label: str | None = None
    caption: str | None = None
    width_pct: float | None = Field(default=None, gt=0, le=100)

    @field_validator("series", mode="before")
    @classmethod
    def _coerce_series(cls, v: Any) -> Any:
        # Accept a bare list of numbers as a single unnamed series.
        if isinstance(v, list) and v and all(
            isinstance(x, (int, float)) and not isinstance(x, bool) for x in v
        ):
            return [{"values": list(v)}]
        return v


class MetricItem(_Model):
    label: str
    value: str
    delta: str | None = None  # e.g. "+12%" — rendered green/red by sign
    note: str | None = None


class MetricsBlock(_Model):
    type: Literal["metrics"] = "metrics"
    items: list[MetricItem] = Field(default_factory=list)


class DividerBlock(_Model):
    type: Literal["divider"] = "divider"


class PageBreakBlock(_Model):
    type: Literal["page_break"] = "page_break"


class SpacerBlock(_Model):
    type: Literal["spacer"] = "spacer"
    height_pt: float = 12.0


class TocBlock(_Model):
    """Explicit table-of-contents placement marker."""

    type: Literal["toc"] = "toc"
    title: str | None = None


class MathBlock(_Model):
    """Display math (LaTeX). Rendered via matplotlib mathtext — no TeX
    install needed. Multi-line AMS environments (align/gather/cases) are
    split into stacked rows."""

    type: Literal["math"] = "math"
    latex: str
    caption: str | None = None


class DefinitionItem(_Model):
    term: str
    definitions: list[str] = Field(default_factory=list)

    @field_validator("definitions", mode="before")
    @classmethod
    def _coerce_definitions(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [v]
        return v


class DefinitionListBlock(_Model):
    """Definition list (markdown ``Term`` / ``: definition`` syntax)."""

    type: Literal["definition_list"] = "definition_list"
    items: list[DefinitionItem] = Field(default_factory=list)


class FootnoteItem(_Model):
    label: str  # rendered marker, e.g. "1"
    text: str


class FootnotesBlock(_Model):
    """Collected footnote definitions (``[^1]`` references render as
    superscript markers in text)."""

    type: Literal["footnotes"] = "footnotes"
    items: list[FootnoteItem] = Field(default_factory=list)


class ColumnsBlock(_Model):
    """Side-by-side column layout (2-3 columns of nested blocks).

    PDF renders true columns; DOCX/Markdown degrade to sequential content;
    HTML uses a flex row.
    """

    type: Literal["columns"] = "columns"
    columns: list[list[Block]] = Field(default_factory=list)
    widths: list[float] | None = None  # relative weights, default equal
    gap_pt: float = 18.0


ChecklistStatus = Literal[
    "pending", "in_progress", "completed", "blocked", "skipped"
]
ChecklistPriority = Literal["low", "medium", "high", "critical"]


class ChecklistItem(_Model):
    """One checklist entry with status tracking and optional metadata."""

    text: str
    id: str | None = None
    status: ChecklistStatus = "pending"
    priority: ChecklistPriority | None = None
    due_date: str | None = None
    assignee: str | None = None
    notes: str | None = None
    sub_items: list[ChecklistItem] = Field(default_factory=list)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> Any:
        if v is None or v == "":
            return "pending"
        if isinstance(v, str):
            return v.strip().lower().replace(" ", "_").replace("-", "_")
        return v

    @field_validator("priority", mode="before")
    @classmethod
    def _coerce_priority(cls, v: Any) -> Any:
        if isinstance(v, str):
            v = v.strip().lower()
            return v or None
        return v


class ChecklistGroup(_Model):
    """A named section of checklist items."""

    name: str | None = None
    description: str | None = None
    items: list[ChecklistItem] = Field(default_factory=list)


class ChecklistBlock(_Model):
    """Status-tracked checklist with groups, priorities, and progress.

    Supersedes the legacy ``checklist_generator``: grouped or flat items,
    per-item status/priority/assignee/due-date/notes, nested sub-items, an
    optional progress summary and status legend. Rendered professionally in
    PDF/DOCX/HTML and as GFM task lists in Markdown.
    """

    type: Literal["checklist"] = "checklist"
    title: str | None = None
    description: str | None = None
    groups: list[ChecklistGroup] = Field(default_factory=list)
    items: list[ChecklistItem] = Field(default_factory=list)  # flat alternative
    show_progress: bool = True
    show_legend: bool = True

    def normalized_groups(self) -> list[ChecklistGroup]:
        """Return groups, wrapping any flat ``items`` into a leading group."""
        groups: list[ChecklistGroup] = []
        if self.items:
            groups.append(ChecklistGroup(items=list(self.items)))
        groups.extend(self.groups)
        return groups


Block = Annotated[
    HeadingBlock | ParagraphBlock | ListBlock | TableBlock | ImageBlock | CodeBlock | QuoteBlock | CalloutBlock | ChartBlock | MetricsBlock | DividerBlock | PageBreakBlock | SpacerBlock | TocBlock | MathBlock | DefinitionListBlock | FootnotesBlock | ChecklistBlock | ColumnsBlock,
    Field(discriminator="type"),
]

ChecklistItem.model_rebuild()
ColumnsBlock.model_rebuild()


# ---------------------------------------------------------------------------
# Document-level configuration
# ---------------------------------------------------------------------------


class PageMargins(_Model):
    top: float = 64.0
    bottom: float = 56.0
    left: float = 64.0
    right: float = 64.0


class PageSetup(_Model):
    size: Literal["A4", "LETTER", "LEGAL", "A3", "A5"] = "A4"
    orientation: Literal["portrait", "landscape"] = "portrait"
    margins: PageMargins = Field(default_factory=PageMargins)


class HeaderFooter(_Model):
    """Running header/footer.

    ``text`` supports placeholders resolved at render time (PDF):
    ``{page}``, ``{pages}``, ``{title}``, ``{author}``, ``{date}``, and
    ``{section}`` (the current H1 on that page).
    """

    text: str | None = None
    show_page_number: bool = False
    alignment: Alignment = "center"


class Watermark(_Model):
    text: str
    color: str = "CCCCCC"  # hex, no leading '#'
    opacity: float = Field(default=0.08, ge=0.0, le=1.0)
    angle: float = 45.0
    font_size: int = 64


class Encryption(_Model):
    user_password: str
    owner_password: str | None = None


class CoverSpec(_Model):
    """Cover page; unset fields fall back to document metadata."""

    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    date: str | None = None
    organization: str | None = None
    logo_path: str | None = None

    @field_validator("date", mode="before")
    @classmethod
    def _normalize_date(cls, value: Any) -> str | None:
        return _coerce_date_str(value)


class DocumentSpec(_Model):
    """Complete specification of a generated document."""

    title: str = ""
    subtitle: str | None = None
    author: str | None = None
    date: str | None = None
    subject: str | None = None
    keywords: list[str] = Field(default_factory=list)
    theme: str = "professional"
    page: PageSetup = Field(default_factory=PageSetup)
    header: HeaderFooter | None = None
    footer: HeaderFooter | None = None
    watermark: Watermark | None = None
    cover: CoverSpec | bool = False
    toc: bool = False
    numbered_headings: bool = False
    # Precision formatting (PDF-first; other renderers degrade gracefully):
    justify: bool = False           # justified body text (formal reports)
    numbered_figures: bool = False  # auto 图/表/Figure/Table N caption numbering
    section_pages: bool = False     # every H1 starts a new page as a section divider
    encryption: Encryption | None = None
    merge_sources: list[str] = Field(default_factory=list)
    blocks: list[Block] = Field(default_factory=list)

    @field_validator("date", mode="before")
    @classmethod
    def _normalize_date(cls, value: Any) -> str | None:
        return _coerce_date_str(value)

    def cover_spec(self) -> CoverSpec | None:
        """Effective cover spec, or None when disabled."""
        if self.cover is False or self.cover is None:
            return None
        base = self.cover if isinstance(self.cover, CoverSpec) else CoverSpec()
        return CoverSpec(
            title=base.title or self.title,
            subtitle=base.subtitle or self.subtitle,
            author=base.author or self.author,
            date=base.date or self.date,
            organization=base.organization,
            logo_path=base.logo_path,
        )


# ---------------------------------------------------------------------------
# Decks (presentations)
# ---------------------------------------------------------------------------

SlideLayout = Literal[
    "title",       # deck opener: big title + subtitle
    "section",     # section divider: accent background
    "content",     # title + body (markdown -> bullets/paragraphs)
    "two_column",  # title + left/right markdown columns
    "columns",     # title + 2-4 headed columns (comparison / framework)
    "image",       # title + image with configurable text placement
    "table",       # title + table
    "chart",       # title + chart (+ optional body)
    "quote",       # large centered quotation
    "closing",     # thank-you / call-to-action
]

ImagePosition = Literal["right", "left", "top", "full", "background"]


class SlideImage(_Model):
    path: str | None = None
    url: str | None = None
    base64_data: str | None = None
    caption: str | None = None
    position: ImagePosition = "full"
    # Share of the content area the image occupies for split positions
    # (left/right/top). Clamped to 0.2-0.8 at render time.
    ratio: float = 0.5


class SlideBackground(_Model):
    """Per-slide (or deck-default) background configuration.

    Exactly one of ``color`` / ``gradient`` / image source should be set;
    when an image is used, ``overlay`` dims it for text legibility.
    """

    color: str | None = None                 # "#RRGGBB"
    gradient: list[str] | None = None        # 2 hex stops
    gradient_angle: float = 90.0             # degrees, 90 = top->bottom
    image_path: str | None = None
    image_url: str | None = None
    image_base64: str | None = None
    overlay: float = 0.0                     # 0-1 scrim opacity over image
    overlay_color: str = "#000000"


class SlideColumn(_Model):
    """One column of a `columns` layout (framework / comparison slides)."""

    heading: str | None = None
    body: str | None = None                  # markdown
    image: SlideImage | None = None
    emphasis: bool = False                   # card-style surface fill
    width: float | None = None               # relative weight (default equal)


class SlideSpec(_Model):
    layout: SlideLayout = "content"
    title: str | None = None
    kicker: str | None = None    # eyebrow label above the title
    subtitle: str | None = None
    body: str | None = None   # markdown (bullets, paragraphs, nested lists)
    left: str | None = None   # two_column layouts
    right: str | None = None
    columns: list[SlideColumn] | None = None  # `columns` layout
    image: SlideImage | None = None
    table: TableBlock | None = None
    chart: ChartBlock | None = None
    quote: str | None = None
    attribution: str | None = None
    takeaway: str | None = None  # bottom "so-what" bar (consulting style)
    background: SlideBackground | None = None
    notes: str | None = None  # speaker notes


class DeckSpec(_Model):
    """Complete specification of a generated presentation."""

    title: str = ""
    subtitle: str | None = None
    author: str | None = None
    date: str | None = None
    theme: str = "executive_light"
    aspect: Literal["16:9", "4:3"] = "16:9"
    show_slide_numbers: bool = True
    footer_text: str | None = None
    background: SlideBackground | None = None  # deck-wide default
    slides: list[SlideSpec] = Field(default_factory=list)

    @field_validator("date", mode="before")
    @classmethod
    def _normalize_date(cls, value: Any) -> str | None:
        return _coerce_date_str(value)
