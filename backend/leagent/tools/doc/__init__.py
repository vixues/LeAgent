"""Document processing tools for LeAgent.

This module provides tools for reading and processing various document formats:
- PDF files (PyMuPDF)
- Word documents (python-docx)
- Excel spreadsheets (openpyxl)
- Image OCR (PaddleOCR)
- Document classification (rule-based and LLM)
- CSV/TSV processing
- Markdown parsing and conversion
- HTML extraction and conversion
- Config files (JSON/YAML/TOML)
- Archive management (zip/tar)
- Text file processing with encoding detection
"""

from leagent.tools.doc.archive_manager import ArchiveManagerTool
from leagent.tools.doc.config_file_tool import ConfigFileTool
from leagent.tools.doc.csv_processor import CSVProcessorTool
from leagent.tools.doc.doc_classifier import DocClassifierTool
from leagent.tools.doc.excel_reader import ExcelReaderTool
from leagent.tools.doc.html_processor import HTMLProcessorTool
from leagent.tools.doc.image_ocr import ImageOCRTool
from leagent.tools.doc.markdown_processor import MarkdownProcessorTool
from leagent.tools.doc.pdf_reader import PDFReaderTool
from leagent.tools.doc.pdf_research import (
    CitationExtractorTool,
    PDFStructureTool,
    PDFTranslateTool,
    SectionSummarizerTool,
)
from leagent.tools.doc.text_processor import TextFileProcessorTool
from leagent.tools.doc.word_reader import WordReaderTool

__all__ = [
    "PDFReaderTool",
    "PDFStructureTool",
    "CitationExtractorTool",
    "SectionSummarizerTool",
    "PDFTranslateTool",
    "WordReaderTool",
    "ExcelReaderTool",
    "ImageOCRTool",
    "DocClassifierTool",
    "CSVProcessorTool",
    "MarkdownProcessorTool",
    "HTMLProcessorTool",
    "ConfigFileTool",
    "ArchiveManagerTool",
    "TextFileProcessorTool",
]
