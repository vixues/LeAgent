"""Document generation tools for LeAgent.

This module provides tools for generating various document formats including
Word documents, Excel spreadsheets, PDFs, PowerPoint presentations, reports,
checklists, and filled templates.

Tools:
    WordGeneratorTool: Create .docx documents with headings, tables, and styling
    ExcelGeneratorTool: Create .xlsx files with sheets, formatting, and charts
    PDFGeneratorTool: Create PDF documents with reportlab
    PptxGeneratorTool: Create .pptx presentations with slides, charts, and images
    ReportGeneratorTool: Generate data-driven reports in multiple formats
    ChecklistGeneratorTool: Generate checklists from workflows/rules
    TemplateFillerTool: Fill templates using Jinja2 engine

Dependencies:
    - python-docx: Word document generation
    - openpyxl: Excel file generation
    - reportlab: PDF generation
    - python-pptx: PowerPoint generation
    - jinja2: Template rendering
    - pyyaml: YAML parsing (optional)
"""

from leagent.tools.gen.checklist_generator import ChecklistGeneratorTool
from leagent.tools.gen.excel_generator import ExcelGeneratorTool
from leagent.tools.gen.pdf_generator import PDFGeneratorTool
from leagent.tools.gen.pptx_generator import PptxGeneratorTool
from leagent.tools.gen.report_generator import ReportGeneratorTool
from leagent.tools.gen.style_registry import StyleRegistry, get_style_registry
from leagent.tools.gen.template_filler import TemplateFillerTool
from leagent.tools.gen.word_generator import WordGeneratorTool

__all__ = [
    "WordGeneratorTool",
    "ExcelGeneratorTool",
    "PDFGeneratorTool",
    "PptxGeneratorTool",
    "ReportGeneratorTool",
    "ChecklistGeneratorTool",
    "TemplateFillerTool",
    "StyleRegistry",
    "get_style_registry",
]
