"""Image OCR Tool - Extract text from images using optical character recognition.

Uses PaddleOCR for high-quality Chinese and English text recognition.
Falls back gracefully when PaddleOCR is not installed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)

PADDLEOCR_AVAILABLE = False
_ocr_instance: Any = None

try:
    from paddleocr import PaddleOCR
    PADDLEOCR_AVAILABLE = True
except ImportError:
    pass


def get_ocr_instance(lang: str = "ch", use_gpu: bool = False) -> Any:
    """Get or create a cached PaddleOCR instance.

    PaddleOCR initialization is expensive, so we cache the instance.
    """
    global _ocr_instance
    if _ocr_instance is None:
        _ocr_instance = PaddleOCR(
            use_angle_cls=True,
            lang=lang,
            use_gpu=use_gpu,
            show_log=False,
        )
    return _ocr_instance


class ImageOCRTool(SyncTool):
    """Extract text from images using OCR.

    Features:
    - Chinese and English text recognition
    - Confidence scores for extracted text
    - Bounding box coordinates for text regions
    - Support for various image formats (PNG, JPG, JPEG, BMP, TIFF)
    """

    name = "image_ocr"
    description = (
        "Extract text from images using optical character recognition (OCR). "
        "Supports Chinese and English text with high accuracy."
    )
    category = ToolCategory.DOC
    version = "1.0.0"
    timeout_sec = 180
    requires_gpu = False
    aliases = ["ocr", "image_text", "text_recognition"]
    search_hint = "OCR image text recognition extract Chinese English optical character"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 100_000
    path_params = ("file_path",)

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the image file to process.",
                },
                "language": {
                    "type": "string",
                    "enum": ["ch", "en", "ch_en"],
                    "description": (
                        "OCR language: 'ch' (Chinese+English), 'en' (English only), "
                        "'ch_en' (Chinese+English mixed). Defaults to 'ch'."
                    ),
                    "default": "ch",
                },
                "include_confidence": {
                    "type": "boolean",
                    "description": "Whether to include confidence scores. Defaults to True.",
                    "default": True,
                },
                "include_boxes": {
                    "type": "boolean",
                    "description": "Whether to include bounding box coordinates. Defaults to False.",
                    "default": False,
                },
                "min_confidence": {
                    "type": "number",
                    "description": "Minimum confidence threshold (0-1) for including text. Defaults to 0.5.",
                    "minimum": 0,
                    "maximum": 1,
                    "default": 0.5,
                },
                "use_gpu": {
                    "type": "boolean",
                    "description": "Whether to use GPU for OCR. Defaults to False.",
                    "default": False,
                },
            },
            "required": ["file_path"],
            "additionalProperties": False,
        }

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        return "Extracting text from image (OCR)"

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Extract text from an image using OCR.

        Args:
            params: Tool parameters including file_path and OCR options.
            context: Execution context.

        Returns:
            Dictionary containing extracted text and optional metadata.

        Raises:
            FileNotFoundError: If the image file doesn't exist.
            ValueError: If the file format is not supported.
            RuntimeError: If PaddleOCR is not installed or encounters an error.
        """
        if not PADDLEOCR_AVAILABLE:
            raise RuntimeError(
                "PaddleOCR is not installed. Install with: "
                "pip install paddlepaddle paddleocr\n"
                "For GPU support: pip install paddlepaddle-gpu paddleocr"
            )

        file_path = Path(params["file_path"])
        language = params.get("language", "ch")
        include_confidence = params.get("include_confidence", True)
        include_boxes = params.get("include_boxes", False)
        min_confidence = params.get("min_confidence", 0.5)
        use_gpu = params.get("use_gpu", False)

        supported_formats = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
        if not file_path.exists():
            raise FileNotFoundError(f"Image file not found: {file_path}")

        if file_path.suffix.lower() not in supported_formats:
            raise ValueError(
                f"Unsupported image format: {file_path.suffix}. "
                f"Supported formats: {', '.join(supported_formats)}"
            )

        logger.info(
            "Starting OCR extraction",
            file_path=str(file_path),
            language=language,
            use_gpu=use_gpu,
        )

        try:
            ocr = get_ocr_instance(lang=language, use_gpu=use_gpu)
            result = ocr.ocr(str(file_path), cls=True)
        except Exception as e:
            raise RuntimeError(f"OCR processing failed: {e}") from e

        if not result or not result[0]:
            return {
                "text": "",
                "lines": [],
                "line_count": 0,
                "avg_confidence": 0.0,
                "warning": "No text detected in the image.",
            }

        lines: list[dict[str, Any]] = []
        text_parts: list[str] = []
        total_confidence = 0.0
        filtered_count = 0

        for line in result[0]:
            if not line:
                continue

            box, (text, confidence) = line

            if confidence < min_confidence:
                filtered_count += 1
                continue

            line_data: dict[str, Any] = {"text": text}

            if include_confidence:
                line_data["confidence"] = round(confidence, 4)

            if include_boxes:
                line_data["box"] = [
                    {"x": point[0], "y": point[1]}
                    for point in box
                ]

            lines.append(line_data)
            text_parts.append(text)
            total_confidence += confidence

        full_text = "\n".join(text_parts)
        avg_confidence = total_confidence / len(lines) if lines else 0.0

        output: dict[str, Any] = {
            "text": full_text,
            "lines": lines,
            "line_count": len(lines),
            "total_characters": len(full_text),
        }

        if include_confidence:
            output["avg_confidence"] = round(avg_confidence, 4)

        if filtered_count > 0:
            output["filtered_low_confidence"] = filtered_count

        logger.info(
            "OCR extraction complete",
            file_path=str(file_path),
            lines_detected=len(lines),
            avg_confidence=round(avg_confidence, 4),
        )

        return output
