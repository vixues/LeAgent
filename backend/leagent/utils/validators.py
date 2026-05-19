"""Input validation and sanitisation utilities."""

from __future__ import annotations

import re
from pathlib import Path

from leagent.config.constants import ALL_SUPPORTED_TYPES, MAX_UPLOAD_SIZE_BYTES

_DANGEROUS_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions|prompts)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|your)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*/?script", re.IGNORECASE),
    re.compile(r"javascript\s*:", re.IGNORECASE),
    re.compile(r"on(error|load|click)\s*=", re.IGNORECASE),
    re.compile(r"\{\{.*\}\}", re.IGNORECASE),
    re.compile(r"<\|im_start\|>", re.IGNORECASE),
    re.compile(r"\[INST\]", re.IGNORECASE),
]

_STRIP_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_input(text: str, max_length: int = 100_000) -> str:
    """Strip control characters and enforce a maximum length."""
    text = _STRIP_RE.sub("", text)
    return text[:max_length]


def detect_prompt_injection(text: str) -> tuple[bool, str]:
    """Heuristic check for common prompt-injection patterns.

    Returns:
        (is_suspicious, matched_pattern_description)
    """
    for pattern in _DANGEROUS_PATTERNS:
        match = pattern.search(text)
        if match:
            return True, f"Matched pattern: {pattern.pattern!r} at position {match.start()}"
    return False, ""


def validate_file_type(filename: str, allowed: set[str] | None = None) -> tuple[bool, str]:
    """Validate that the file extension is in the allowed set.

    Returns:
        (is_valid, reason)
    """
    allowed_types = allowed or ALL_SUPPORTED_TYPES
    ext = Path(filename).suffix.lower()
    if not ext:
        return False, "File has no extension"
    if ext not in allowed_types:
        return False, f"File type '{ext}' not supported. Allowed: {sorted(allowed_types)}"
    return True, ""


def validate_file_size(size_bytes: int, max_bytes: int | None = None) -> tuple[bool, str]:
    """Validate that the file size is within limits.

    Returns:
        (is_valid, reason)
    """
    limit = max_bytes or MAX_UPLOAD_SIZE_BYTES
    if size_bytes <= 0:
        return False, "File is empty"
    if size_bytes > limit:
        limit_mb = limit / (1024 * 1024)
        actual_mb = size_bytes / (1024 * 1024)
        return False, f"File size ({actual_mb:.1f} MB) exceeds limit ({limit_mb:.0f} MB)"
    return True, ""


def validate_uuid(value: str) -> bool:
    """Check whether *value* is a valid UUID4 string."""
    import uuid

    try:
        uuid.UUID(value, version=4)
        return True
    except ValueError:
        return False
