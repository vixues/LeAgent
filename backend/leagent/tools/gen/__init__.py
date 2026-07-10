"""Document generation tools for LeAgent.

Document generation is powered by the ``leagent.docgen`` subsystem: one
typed document model, a guaranteed pan-Unicode font pipeline, one theme
system, and per-format renderers.

Tools:
    DocumentGenerateTool: PDF / DOCX / HTML / Markdown documents from markdown
        or typed blocks (``document_generate``)
    SlidesGenerateTool: PPTX presentations with themed layouts
        (``slides_generate``)
    ThemeDesignerTool: derive/save/manage custom docgen themes
        (``theme_designer``)
    DocumentTemplateTool: reusable parameterized document/deck templates
        (``document_template``)
    ChecklistGeneratorTool: status-tracked checklists to md/json/html/pdf/docx
        (``checklist_generate``)
    ExcelGeneratorTool: .xlsx files with sheets, formatting, and charts
    TemplateFillerTool: Fill templates using the Jinja2 engine

Dependencies:
    - reportlab: PDF rendering
    - python-docx: Word rendering
    - python-pptx: PowerPoint rendering
    - openpyxl: Excel generation
    - markdown-it-py: markdown parsing
    - jinja2: template rendering
"""

from leagent.tools.gen.checklist_tool import ChecklistGeneratorTool
from leagent.tools.gen.document_tool import DocumentGenerateTool
from leagent.tools.gen.excel_generator import ExcelGeneratorTool
from leagent.tools.gen.slides_tool import SlidesGenerateTool
from leagent.tools.gen.template_filler import TemplateFillerTool
from leagent.tools.gen.template_tool import DocumentTemplateTool
from leagent.tools.gen.theme_tool import ThemeDesignerTool

__all__ = [
    "DocumentGenerateTool",
    "SlidesGenerateTool",
    "ThemeDesignerTool",
    "DocumentTemplateTool",
    "ChecklistGeneratorTool",
    "ExcelGeneratorTool",
    "TemplateFillerTool",
]
