"""Per-format renderers for the document generation subsystem.

Each renderer consumes a validated :class:`~leagent.docgen.model.DocumentSpec`
or :class:`~leagent.docgen.model.DeckSpec` plus a resolved theme and writes a
file, returning a result dict with stats and font/embedding warnings.

Imports are lazy so a missing optional dependency for one format never breaks
the others.
"""

from typing import Any

__all__ = ["render_pdf", "render_docx", "render_pptx", "render_html", "render_markdown"]


def __getattr__(name: str) -> Any:
    if name == "render_pdf":
        from leagent.docgen.renderers.pdf import render_pdf

        return render_pdf
    if name == "render_docx":
        from leagent.docgen.renderers.docx import render_docx

        return render_docx
    if name == "render_pptx":
        from leagent.docgen.renderers.pptx import render_pptx

        return render_pptx
    if name in ("render_html", "render_markdown"):
        from leagent.docgen.renderers import html as _html

        return getattr(_html, name)
    raise AttributeError(name)
