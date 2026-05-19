"""Text Splitter Tool - Text chunking and splitting.

Provides operations for splitting text by characters, tokens, sentences,
with overlap support and smart splitting that preserves structure.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

from leagent.tools.base import SyncTool, ToolCategory, ToolContext

logger = structlog.get_logger(__name__)


class TextSplitterTool(SyncTool):
    """Split and chunk text content.

    Features:
    - Split by character count with overlap
    - Split by token count (approximate)
    - Split by sentences or paragraphs
    - Smart splitting preserving structure
    - Configurable separators
    - Metadata tracking for chunks
    """

    name = "text_splitter"
    description = (
        "Split text into chunks by characters, tokens, sentences, or paragraphs "
        "with configurable overlap and smart splitting to preserve structure."
    )
    category = ToolCategory.UTIL
    version = "1.0.0"
    timeout_sec = 60
    aliases = ["splitter", "chunk", "text_chunk"]
    search_hint = "text split chunk characters tokens sentences paragraphs overlap"
    is_concurrency_safe = True
    is_read_only = True
    interrupt_behavior = "cancel"
    max_result_size_chars = 200_000

    def get_activity_description(self, params: dict[str, Any] | None = None) -> str | None:
        method = (params or {}).get("method", "characters")
        return f"Splitting text ({method})"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": [
                        "split_chars",
                        "split_tokens",
                        "split_sentences",
                        "split_paragraphs",
                        "split_lines",
                        "split_regex",
                        "smart_split",
                    ],
                    "description": "Splitting operation to perform.",
                    "default": "split_chars",
                },
                "text": {
                    "type": "string",
                    "description": "Text content to split.",
                },
                "chunk_size": {
                    "type": "integer",
                    "description": "Maximum size of each chunk.",
                    "minimum": 1,
                    "default": 1000,
                },
                "chunk_overlap": {
                    "type": "integer",
                    "description": "Number of characters/tokens to overlap between chunks.",
                    "minimum": 0,
                    "default": 0,
                },
                "separators": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Custom separators for splitting (tried in order).",
                },
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern for split_regex operation.",
                },
                "keep_separator": {
                    "type": "boolean",
                    "description": "Keep separators in output chunks.",
                    "default": False,
                },
                "strip_chunks": {
                    "type": "boolean",
                    "description": "Strip whitespace from chunks.",
                    "default": True,
                },
                "min_chunk_size": {
                    "type": "integer",
                    "description": "Minimum chunk size (smaller chunks are merged).",
                    "minimum": 0,
                    "default": 0,
                },
                "max_chunks": {
                    "type": "integer",
                    "description": "Maximum number of chunks to return.",
                    "minimum": 1,
                },
                "include_metadata": {
                    "type": "boolean",
                    "description": "Include metadata (position, index) for each chunk.",
                    "default": True,
                },
                "preserve_words": {
                    "type": "boolean",
                    "description": "Avoid splitting in the middle of words.",
                    "default": True,
                },
                "encoding": {
                    "type": "string",
                    "description": "Token encoding model for token-based splitting.",
                    "default": "cl100k_base",
                },
            },
            "required": ["text"],
            "additionalProperties": False,
        }

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> dict[str, Any]:
        """Execute text splitting operation.

        Args:
            params: Tool parameters including text and splitting options.
            context: Execution context.

        Returns:
            Dictionary containing split chunks and metadata.

        Raises:
            ValueError: If parameters are invalid.
        """
        operation = params.get("operation", "split_chars")
        text = params.get("text", "")

        if not text:
            return {
                "chunks": [],
                "count": 0,
                "total_length": 0,
            }

        logger.info("Executing text split", operation=operation, text_length=len(text))

        operations = {
            "split_chars": self._split_by_chars,
            "split_tokens": self._split_by_tokens,
            "split_sentences": self._split_by_sentences,
            "split_paragraphs": self._split_by_paragraphs,
            "split_lines": self._split_by_lines,
            "split_regex": self._split_by_regex,
            "smart_split": self._smart_split,
        }

        if operation not in operations:
            raise ValueError(f"Unknown operation: {operation}")

        chunks = operations[operation](text, params)

        max_chunks = params.get("max_chunks")
        if max_chunks and len(chunks) > max_chunks:
            chunks = chunks[:max_chunks]

        include_metadata = params.get("include_metadata", True)
        if not include_metadata:
            chunks = [c["text"] if isinstance(c, dict) else c for c in chunks]

        result = {
            "chunks": chunks,
            "count": len(chunks),
            "total_length": len(text),
        }

        if include_metadata and chunks:
            result["statistics"] = {
                "avg_chunk_size": sum(len(c["text"]) if isinstance(c, dict) else len(c) for c in chunks) // len(chunks),
                "min_chunk_size": min(len(c["text"]) if isinstance(c, dict) else len(c) for c in chunks),
                "max_chunk_size": max(len(c["text"]) if isinstance(c, dict) else len(c) for c in chunks),
            }

        logger.info("Text split complete", chunks=len(chunks))
        return result

    def _split_by_chars(self, text: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Split text by character count."""
        chunk_size = params.get("chunk_size", 1000)
        overlap = params.get("chunk_overlap", 0)
        preserve_words = params.get("preserve_words", True)
        strip_chunks = params.get("strip_chunks", True)
        min_chunk_size = params.get("min_chunk_size", 0)

        if overlap >= chunk_size:
            raise ValueError("Overlap must be less than chunk size")

        chunks: list[dict[str, Any]] = []
        start = 0
        index = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))

            if preserve_words and end < len(text):
                word_boundary = text.rfind(" ", start, end)
                if word_boundary > start:
                    end = word_boundary

            chunk_text = text[start:end]
            if strip_chunks:
                chunk_text = chunk_text.strip()

            if len(chunk_text) >= min_chunk_size:
                chunks.append({
                    "text": chunk_text,
                    "index": index,
                    "start": start,
                    "end": end,
                    "length": len(chunk_text),
                })
                index += 1

            start = end - overlap if overlap > 0 else end
            if start >= end:
                start = end

        return chunks

    def _split_by_tokens(self, text: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Split text by approximate token count."""
        chunk_size = params.get("chunk_size", 500)
        overlap = params.get("chunk_overlap", 0)
        strip_chunks = params.get("strip_chunks", True)
        encoding = params.get("encoding", "cl100k_base")

        try:
            import tiktoken
            enc = tiktoken.get_encoding(encoding)
            tokens = enc.encode(text)
        except ImportError:
            avg_token_len = 4
            char_chunk_size = chunk_size * avg_token_len
            char_overlap = overlap * avg_token_len
            return self._split_by_chars(text, {
                **params,
                "chunk_size": char_chunk_size,
                "chunk_overlap": char_overlap,
            })

        chunks: list[dict[str, Any]] = []
        start = 0
        index = 0

        while start < len(tokens):
            end = min(start + chunk_size, len(tokens))
            chunk_tokens = tokens[start:end]
            chunk_text = enc.decode(chunk_tokens)

            if strip_chunks:
                chunk_text = chunk_text.strip()

            if chunk_text:
                chunks.append({
                    "text": chunk_text,
                    "index": index,
                    "token_start": start,
                    "token_end": end,
                    "token_count": len(chunk_tokens),
                    "length": len(chunk_text),
                })
                index += 1

            start = end - overlap if overlap > 0 else end

        return chunks

    def _split_by_sentences(self, text: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Split text by sentences."""
        chunk_size = params.get("chunk_size", 3)
        overlap = params.get("chunk_overlap", 0)
        strip_chunks = params.get("strip_chunks", True)

        sentence_pattern = r"(?<=[.!?])\s+(?=[A-Z])"
        sentences = re.split(sentence_pattern, text)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            return []

        chunks: list[dict[str, Any]] = []
        index = 0
        char_pos = 0

        for i in range(0, len(sentences), max(1, chunk_size - overlap)):
            end_idx = min(i + chunk_size, len(sentences))
            chunk_sentences = sentences[i:end_idx]
            chunk_text = " ".join(chunk_sentences)

            if strip_chunks:
                chunk_text = chunk_text.strip()

            if chunk_text:
                chunks.append({
                    "text": chunk_text,
                    "index": index,
                    "sentence_start": i,
                    "sentence_end": end_idx,
                    "sentence_count": len(chunk_sentences),
                    "length": len(chunk_text),
                })
                index += 1
                char_pos += len(chunk_text)

        return chunks

    def _split_by_paragraphs(self, text: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Split text by paragraphs."""
        chunk_size = params.get("chunk_size", 1)
        overlap = params.get("chunk_overlap", 0)
        strip_chunks = params.get("strip_chunks", True)
        min_chunk_size = params.get("min_chunk_size", 0)

        paragraphs = re.split(r"\n\s*\n", text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        if not paragraphs:
            return []

        chunks: list[dict[str, Any]] = []
        index = 0

        for i in range(0, len(paragraphs), max(1, chunk_size - overlap)):
            end_idx = min(i + chunk_size, len(paragraphs))
            chunk_paras = paragraphs[i:end_idx]
            chunk_text = "\n\n".join(chunk_paras)

            if strip_chunks:
                chunk_text = chunk_text.strip()

            if len(chunk_text) >= min_chunk_size:
                chunks.append({
                    "text": chunk_text,
                    "index": index,
                    "paragraph_start": i,
                    "paragraph_end": end_idx,
                    "paragraph_count": len(chunk_paras),
                    "length": len(chunk_text),
                })
                index += 1

        return chunks

    def _split_by_lines(self, text: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Split text by lines."""
        chunk_size = params.get("chunk_size", 10)
        overlap = params.get("chunk_overlap", 0)
        strip_chunks = params.get("strip_chunks", True)
        min_chunk_size = params.get("min_chunk_size", 0)

        lines = text.split("\n")

        chunks: list[dict[str, Any]] = []
        index = 0

        for i in range(0, len(lines), max(1, chunk_size - overlap)):
            end_idx = min(i + chunk_size, len(lines))
            chunk_lines = lines[i:end_idx]
            chunk_text = "\n".join(chunk_lines)

            if strip_chunks:
                chunk_text = chunk_text.strip()

            if len(chunk_text) >= min_chunk_size:
                chunks.append({
                    "text": chunk_text,
                    "index": index,
                    "line_start": i,
                    "line_end": end_idx,
                    "line_count": len(chunk_lines),
                    "length": len(chunk_text),
                })
                index += 1

        return chunks

    def _split_by_regex(self, text: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Split text by regex pattern."""
        pattern = params.get("pattern")
        keep_separator = params.get("keep_separator", False)
        strip_chunks = params.get("strip_chunks", True)
        min_chunk_size = params.get("min_chunk_size", 0)

        if not pattern:
            raise ValueError("Pattern is required for split_regex operation")

        if keep_separator:
            parts = re.split(f"({pattern})", text)
        else:
            parts = re.split(pattern, text)

        chunks: list[dict[str, Any]] = []
        index = 0

        for part in parts:
            chunk_text = part.strip() if strip_chunks else part

            if len(chunk_text) >= min_chunk_size:
                chunks.append({
                    "text": chunk_text,
                    "index": index,
                    "length": len(chunk_text),
                })
                index += 1

        return chunks

    def _smart_split(self, text: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        """Smart split that preserves document structure."""
        chunk_size = params.get("chunk_size", 1000)
        overlap = params.get("chunk_overlap", 0)
        strip_chunks = params.get("strip_chunks", True)
        min_chunk_size = params.get("min_chunk_size", 0)

        default_separators = [
            "\n## ",
            "\n### ",
            "\n#### ",
            "\n\n",
            "\n",
            ". ",
            "? ",
            "! ",
            "; ",
            ", ",
            " ",
        ]
        separators = params.get("separators", default_separators)
        keep_separator = params.get("keep_separator", False)

        def split_recursive(text: str, seps: list[str], depth: int = 0) -> list[str]:
            if not text or len(text) <= chunk_size:
                return [text] if text else []

            if depth >= len(seps):
                return [text[i : i + chunk_size] for i in range(0, len(text), chunk_size - overlap)]

            sep = seps[depth]
            if sep not in text:
                return split_recursive(text, seps, depth + 1)

            if keep_separator:
                parts = []
                last_end = 0
                for match in re.finditer(re.escape(sep), text):
                    if last_end < match.start():
                        parts.append(text[last_end : match.start()])
                    parts.append(sep)
                    last_end = match.end()
                if last_end < len(text):
                    parts.append(text[last_end:])
            else:
                parts = text.split(sep)

            result: list[str] = []
            current_chunk = ""

            for part in parts:
                test_chunk = current_chunk + (sep if current_chunk and not keep_separator else "") + part

                if len(test_chunk) <= chunk_size:
                    current_chunk = test_chunk
                else:
                    if current_chunk:
                        result.append(current_chunk)

                    if len(part) > chunk_size:
                        sub_chunks = split_recursive(part, seps, depth + 1)
                        result.extend(sub_chunks)
                        current_chunk = ""
                    else:
                        current_chunk = part

            if current_chunk:
                result.append(current_chunk)

            return result

        raw_chunks = split_recursive(text, separators)

        chunks: list[dict[str, Any]] = []
        char_pos = 0

        for i, chunk_text in enumerate(raw_chunks):
            if strip_chunks:
                chunk_text = chunk_text.strip()

            if len(chunk_text) >= min_chunk_size:
                chunks.append({
                    "text": chunk_text,
                    "index": len(chunks),
                    "start": char_pos,
                    "length": len(chunk_text),
                })

            char_pos += len(raw_chunks[i])

        return chunks
