"""Shared packing logic for ``load_skill`` — inline skill resources and script sources.

Progressive disclosure Level 2: combine SKILL.md body with optional bundled text under
budget caps. Binary assets are not base64-inlined here; use ``read_skill_resource``.
Scripts are inlined as UTF-8 source only; execution remains ``run_skill_script``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from leagent.skills.base import Skill

# Align with loader script discovery — text-like extensions we inline as source.
_TEXT_SCRIPT_EXTENSIONS = frozenset({".py", ".js", ".sh", ".ps1", ".cs", ".csx"})

# When inlining bundled files, reserve up to this fraction of max_total_chars (capped)
# for resources/scripts so a very long SKILL.md never squeezes the bundle to zero.
_BUNDLE_RESERVE_FRACTION = 0.45
_BUNDLE_RESERVE_CAP_CHARS = 90_000

# Default per-file cap when reading resource/script text into the bundle.
DEFAULT_MAX_PER_FILE_CHARS = 50_000
# Whole-bundle char budget aligned with ``SkillTool.max_result_size_chars`` / progressive disclosure.
DEFAULT_SKILL_BUNDLE_TOTAL_CHARS = 200_000

# Backward-compatible alias (legacy imports).
_DEFAULT_MAX_PER_FILE_CHARS = DEFAULT_MAX_PER_FILE_CHARS


def skill_metadata_bundle_on_load(skill: Skill) -> bool:
    """Return True when SKILL.md requests bundle-on-load via metadata."""
    meta = skill.manifest.metadata.get("leagent") if skill.manifest.metadata else None
    if not isinstance(meta, dict):
        return False
    val = meta.get("bundle_on_load")
    if val is None:
        return False
    return bool(val)


def _try_read_utf8_text(path: Path, max_bytes: int) -> tuple[str | None, bool, str]:
    """Try to read *path* as UTF-8 text up to *max_bytes*.

    Returns:
        (text, is_binary_or_omit, detail) — text None means omit from inline bundle.
    """
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, True, f"read_error:{exc}"

    cap = max(0, min(len(raw), max_bytes))
    chunk = raw[:cap]
    try:
        text = chunk.decode("utf-8")
        truncated = len(raw) > cap
        return text, False, "truncated" if truncated else ""
    except UnicodeDecodeError:
        return None, True, "binary"


def _reserved_chars_for_bundle(max_total: int) -> int:
    """Characters to reserve for inlined resources/scripts when bundling is requested."""
    return min(int(max_total * _BUNDLE_RESERVE_FRACTION), _BUNDLE_RESERVE_CAP_CHARS, max_total - 512)


def build_bundle_payload(
    skill: Skill,
    *,
    skill_body: str,
    max_total_chars: int,
    include_resources: bool,
    include_scripts: bool,
    max_per_file_chars: int = DEFAULT_MAX_PER_FILE_CHARS,
) -> tuple[str, dict[str, Any]]:
    """Build ``content`` string and structured bundle metadata within ``max_total_chars``.

    When ``include_resources`` or ``include_scripts`` is true, the SKILL.md body may be
    truncated early so a minimum budget remains for bundled UTF-8 files — avoiding the
    case where a huge body leaves no room for any inlined script or reference text.
    """
    notes: list[str] = []
    bytes_omitted = 0

    skill_body = skill_body or ""
    max_total = max(1024, int(max_total_chars))

    inline_bundle = include_resources or include_scripts

    if inline_bundle:
        reserved = _reserved_chars_for_bundle(max_total)
        body_cap = max(512, max_total - reserved)
        if len(skill_body) > body_cap:
            body_out = skill_body[:body_cap]
            notes.append(
                f"SKILL.md body truncated to {body_cap} chars to reserve space for "
                f"bundled files (~{reserved} chars budget)."
            )
        else:
            body_out = skill_body
    else:
        if len(skill_body) > max_total:
            body_out = skill_body[:max_total]
            notes.append(f"SKILL.md body truncated to {max_total} chars (max_total_chars cap).")
        else:
            body_out = skill_body

    remaining = max_total - len(body_out)

    bundled_resources: list[dict[str, Any]] = []
    bundled_scripts: list[dict[str, Any]] = []

    max_bytes_file = max(256, min(max_per_file_chars * 4, max(remaining, 1) * 4))

    if include_resources and skill.manifest.resources:
        for res in sorted(skill.manifest.resources, key=lambda r: r.relative_path):
            if remaining <= 0:
                notes.append(
                    f"Omitted remaining resources starting with '{res.relative_path}' "
                    "(budget exhausted); use read_skill_resource."
                )
                break
            text, is_bin, detail = _try_read_utf8_text(res.absolute_path, max_bytes_file)
            if is_bin or text is None:
                bytes_omitted += max(res.size, 0)
                bundled_resources.append(
                    {
                        "path": res.relative_path,
                        "kind": res.kind.value,
                        "content": None,
                        "omitted": "binary" if detail == "binary" else "error",
                        "size": res.size,
                        "hint": "Non-UTF-8 or binary — use read_skill_resource for full bytes/base64.",
                    }
                )
                continue
            cap = min(len(text), remaining, max_per_file_chars)
            slice_ = text[:cap]
            entry: dict[str, Any] = {
                "path": res.relative_path,
                "kind": res.kind.value,
                "content": slice_,
                "truncated": len(text) > cap or detail == "truncated",
            }
            bundled_resources.append(entry)
            remaining -= len(slice_)
            if len(text) > cap:
                notes.append(f"Truncated resource '{res.relative_path}' to fit bundle budget.")

    if include_scripts and skill.manifest.scripts:
        for scr in sorted(skill.manifest.scripts, key=lambda s: s.relative_path):
            if remaining <= 0:
                notes.append(
                    f"Omitted remaining scripts starting with '{scr.relative_path}' "
                    "(budget exhausted); use read_skill_resource or run_skill_script."
                )
                break
            ext = scr.extension.lower()
            if ext not in _TEXT_SCRIPT_EXTENSIONS:
                bundled_scripts.append(
                    {
                        "path": scr.relative_path,
                        "content": None,
                        "omitted": "unsupported_extension",
                        "hint": "Inline source not bundled for this extension; use run_skill_script.",
                    }
                )
                continue
            text, is_bin, detail = _try_read_utf8_text(scr.absolute_path, max_bytes_file)
            if is_bin or text is None:
                bundled_scripts.append(
                    {
                        "path": scr.relative_path,
                        "content": None,
                        "omitted": detail or "binary",
                        "hint": "Could not read as UTF-8; use run_skill_script.",
                    }
                )
                continue
            cap = min(len(text), remaining, max_per_file_chars)
            slice_ = text[:cap]
            bundled_scripts.append(
                {
                    "path": scr.relative_path,
                    "content": slice_,
                    "truncated": len(text) > cap or detail == "truncated",
                }
            )
            remaining -= len(slice_)
            if len(text) > cap:
                notes.append(f"Truncated script '{scr.relative_path}' to fit bundle budget.")

    extra = {
        "bundled_resources": bundled_resources,
        "bundled_scripts": bundled_scripts,
        "truncation_notes": notes,
        "bytes_omitted": bytes_omitted,
    }
    return body_out, extra


def _markdown_lines_for_bundled_entries(
    section_title: str,
    entries: list[dict[str, Any]],
) -> list[str]:
    """Shared markdown for ``bundled_resources`` / ``bundled_scripts`` list entries."""
    if not entries:
        return []
    lines: list[str] = [section_title]
    for entry in entries:
        path = entry.get("path", "")
        content = entry.get("content")
        if content is None:
            hint = entry.get("hint") or entry.get("omitted") or ""
            lines.append(f"- `{path}` _(omitted: {hint})_")
            continue
        truncated = entry.get("truncated")
        suf = " _(truncated)_" if truncated else ""
        lines.append(f"#### `{path}`{suf}")
        lines.append("```")
        lines.append(content)
        lines.append("```")
        lines.append("")
    return lines


def format_bundle_payload_markdown(
    skill_name: str,
    body: str,
    bundle_extra: dict[str, Any],
    *,
    skill_section_title: str | None = None,
) -> str:
    """Render ``build_bundle_payload`` output as markdown (prompts, logs, @skill injection).

    *skill_section_title* defaults to a heading that includes *skill_name*.
    """
    title = skill_section_title or f"### Skill `{skill_name}`"
    lines: list[str] = [
        title,
        "",
        "## SKILL.md body",
        "",
        body,
        "",
    ]
    notes = bundle_extra.get("truncation_notes") or []
    if notes:
        lines.append("### Bundle notes")
        for n in notes:
            lines.append(f"- {n}")
        lines.append("")

    lines.extend(
        _markdown_lines_for_bundled_entries(
            "### Bundled references / assets (UTF-8 text)",
            bundle_extra.get("bundled_resources") or [],
        )
    )
    lines.extend(
        _markdown_lines_for_bundled_entries(
            "### Bundled scripts (source text)",
            bundle_extra.get("bundled_scripts") or [],
        )
    )
    return "\n".join(lines).rstrip()
