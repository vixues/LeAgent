"""LeAgent document generation subsystem.

One document model, one font pipeline, one theme system, N renderers:

- :mod:`leagent.docgen.fonts` — guaranteed pan-Unicode font pipeline
  (env override → managed download dir → system scan → auto-download).
- :mod:`leagent.docgen.model` — typed Document / Deck IR (Pydantic v2).
- :mod:`leagent.docgen.markdown` — markdown → IR parser (markdown-it-py:
  GFM, math, footnotes, definition lists, front matter, callouts).
- :mod:`leagent.docgen.mathtext` — LaTeX math layout (matplotlib mathtext):
  native vector geometry (PDF) + raster fallback + Unicode fallback.
- :mod:`leagent.docgen.omml` — LaTeX → OMML for native, editable Word /
  PowerPoint equations (no rasterisation).
- :mod:`leagent.docgen.themes` — named themes (typography, palette, page geometry).
- :mod:`leagent.docgen.theming` — theme generation (brand seed -> palette),
  WCAG contrast lint, custom theme store.
- :mod:`leagent.docgen.templates` — reusable parameterized document/deck
  templates (Jinja2 placeholders, validated against the IR).
- :mod:`leagent.docgen.tables` — shared table engine (normalization, column
  type inference, number polish, total-row/delta semantics, style contract).
- :mod:`leagent.docgen.slides` — slide composition engine (deck type scale,
  layout regions, multi-level bullet plans, text autofit).
- :mod:`leagent.docgen.charts` — chart blocks rendered to PNG via matplotlib.
- :mod:`leagent.docgen.renderers` — PDF / DOCX / PPTX / HTML / Markdown renderers.

Agent-facing tools (``document_generate`` / ``slides_generate``) live in
``leagent.tools.gen`` and drive this package.
"""

from leagent.docgen.checklist import (
    build_checklist_block,
    checklist_stats,
    checklist_to_dict,
)
from leagent.docgen.fonts import FontManager, ResolvedFonts, get_font_manager
from leagent.docgen.mathtext import (
    MathVector,
    latex_lines,
    latex_to_unicode,
    math_vector_path,
    render_math_png,
)
from leagent.docgen.model import DeckSpec, DocumentSpec, SlideSpec
from leagent.docgen.omml import latex_to_omml_element, latex_to_omml_xml
from leagent.docgen.slides import (
    DeckTypography,
    SlideGeometry,
    fit_body_size,
    flatten_body,
)
from leagent.docgen.tables import (
    ProcessedTable,
    TableStyleSpec,
    process_table,
    resolve_table_style,
)
from leagent.docgen.templates import (
    DocTemplate,
    delete_template,
    list_templates,
    load_template,
    render_template,
    save_template,
)
from leagent.docgen.themes import Theme, get_theme, list_theme_names
from leagent.docgen.theming import (
    derive_theme_payload,
    lint_theme,
    save_custom_theme,
)

__all__ = [
    "FontManager",
    "ResolvedFonts",
    "get_font_manager",
    "DocumentSpec",
    "DeckSpec",
    "SlideSpec",
    "render_math_png",
    "math_vector_path",
    "MathVector",
    "latex_lines",
    "latex_to_unicode",
    "latex_to_omml_xml",
    "latex_to_omml_element",
    "DeckTypography",
    "SlideGeometry",
    "fit_body_size",
    "flatten_body",
    "ProcessedTable",
    "TableStyleSpec",
    "process_table",
    "resolve_table_style",
    "DocTemplate",
    "save_template",
    "load_template",
    "list_templates",
    "delete_template",
    "render_template",
    "Theme",
    "get_theme",
    "list_theme_names",
    "derive_theme_payload",
    "lint_theme",
    "save_custom_theme",
    "checklist_stats",
    "checklist_to_dict",
    "build_checklist_block",
]
