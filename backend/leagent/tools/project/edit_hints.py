"""Helpers for edit/patch failure feedback (did-you-mean snippets)."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any


def find_closest_lines(
    text: str,
    needle: str,
    *,
    threshold: float = 0.3,
    context_lines: int = 2,
    top_k: int = 3,
) -> list[dict[str, Any]]:
    """Return up to *top_k* line ranges in *text* most similar to *needle*."""
    if not needle.strip():
        return []

    hay_lines = text.splitlines()
    if not hay_lines:
        return []

    needle_lines = needle.splitlines()
    if len(needle_lines) == 1:
        targets = [(i, hay_lines[i]) for i in range(len(hay_lines))]
        scored: list[tuple[float, int, str]] = []
        for idx, line in targets:
            ratio = SequenceMatcher(None, needle, line).ratio()
            if ratio >= threshold:
                scored.append((ratio, idx, line))
        scored.sort(key=lambda t: t[0], reverse=True)
        out: list[dict[str, Any]] = []
        for ratio, idx, line in scored[:top_k]:
            start = max(0, idx - context_lines)
            end = min(len(hay_lines), idx + context_lines + 1)
            frame = [
                {"line": start + j + 1, "text": hay_lines[start + j]}
                for j in range(end - start)
            ]
            out.append(
                {
                    "score": round(ratio, 3),
                    "line": idx + 1,
                    "source_line": line,
                    "frame": frame,
                }
            )
        return out

    # Multi-line needle: sliding window over haystack.
    window = len(needle_lines)
    scored_multi: list[tuple[float, int]] = []
    for start in range(0, max(1, len(hay_lines) - window + 1)):
        chunk = "\n".join(hay_lines[start : start + window])
        ratio = SequenceMatcher(None, needle, chunk).ratio()
        if ratio >= threshold:
            scored_multi.append((ratio, start))
    scored_multi.sort(key=lambda t: t[0], reverse=True)
    out = []
    seen_starts: set[int] = set()
    for ratio, start in scored_multi:
        if start in seen_starts:
            continue
        seen_starts.add(start)
        end = min(len(hay_lines), start + window + context_lines)
        frame_start = max(0, start - context_lines)
        frame = [
            {"line": frame_start + j + 1, "text": hay_lines[frame_start + j]}
            for j in range(end - frame_start)
        ]
        out.append(
            {
                "score": round(ratio, 3),
                "start_line": start + 1,
                "end_line": start + window,
                "frame": frame,
            }
        )
        if len(out) >= top_k:
            break
    return out


def format_no_match_hint(
    *,
    rel_path: str,
    needle: str,
    file_text: str,
    base_message: str,
) -> dict[str, Any]:
    """Build a patch_hint payload for str_replace / patch failures."""
    closest = find_closest_lines(file_text, needle)
    hint: dict[str, Any] = {
        "path": rel_path,
        "instruction": (
            "The exact match was not found. Compare your old_string or patch "
            "context against the closest sections below, then retry with "
            "correct whitespace and indentation."
        ),
        "closest_matches": closest,
    }
    if closest:
        first = closest[0]
        frame = first.get("frame") or []
        if frame:
            hint["replacement_target"] = "\n".join(
                str(row.get("text", "")) for row in frame
            )
            hint["start_line"] = frame[0].get("line")
            hint["end_line"] = frame[-1].get("line")
    return {
        "error": base_message,
        "path": rel_path,
        "patch_hint": hint,
    }
