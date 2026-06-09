"""Shared helpers for the ``project_*`` coding tools.

Why a shared module? Each tool needs the same handful of primitives:

* Pick the active project root from ``ToolContext.extra["project_roots"]``.
* Resolve a user-supplied relative path under that root, refusing
  anything that escapes via ``..`` or symlinks.
* Read text files with encoding detection (so ``project_read`` doesn't
  trip on UTF-16 lock files / Windows-1252 legacy code).
* Apply ignore rules (``.gitignore``, plus a hardcoded list of caches
  like ``node_modules``, ``__pycache__``, ``.venv``) when walking the
  tree so grep / glob / tree don't drown in noise.
* Apply a unified diff (``project_apply_patch``) using only the standard
  library — no external ``patch`` binary required.

Putting these in one place keeps each tool implementation small and
makes it easy to harden the security boundary in a single review.
"""

from __future__ import annotations

import fnmatch
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator

import structlog

from leagent.file.sandbox import get_project_roots
from leagent.tools.base import NonRetryableToolError, ToolContext

logger = structlog.get_logger(__name__)


#: Directory and file names that are skipped by the gitignore-aware
#: walkers regardless of whether the project ships a ``.gitignore``.
#: Keeps grep/glob/tree useful out-of-the-box on Python and Node repos.
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset({
    ".git",
    ".hg",
    ".svn",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".tox",
    ".nox",
    ".venv",
    "venv",
    "env",
    "node_modules",
    ".next",
    ".nuxt",
    "dist",
    "build",
    "out",
    ".turbo",
    ".cache",
    ".parcel-cache",
    "target",
    ".gradle",
    ".idea",
    ".vscode",
    ".DS_Store",
})

DEFAULT_IGNORE_GLOBS: tuple[str, ...] = (
    "*.pyc",
    "*.pyo",
    "*.so",
    "*.dll",
    "*.dylib",
    "*.class",
    "*.jar",
    "*.war",
    "*.lock",
    "*.log",
    "*.tsbuildinfo",
)

#: Hard cap for in-memory file reads inside the project tools. Files
#: larger than this should be inspected through ``project_grep`` or
#: ``code_execution`` so the LLM context isn't blown up.
MAX_TEXT_FILE_BYTES: int = 4 * 1024 * 1024  # 4 MiB

#: Cap on file size considered "text" by a binary heuristic — we only
#: peek at the first slice for the NUL test.
_BINARY_PEEK_BYTES: int = 8 * 1024


class ProjectRootError(NonRetryableToolError, ValueError):
    """Raised when the active project root cannot be determined."""


class ProjectPathError(PermissionError):
    """Raised when a relative path would escape the active project root."""


@dataclass(frozen=True)
class ResolvedFile:
    """A path resolved inside the active project root."""

    root: Path
    abs_path: Path
    rel_path: str  # always forward-slash, relative to ``root``


def select_project_root(
    context: ToolContext,
    *,
    explicit: str | None = None,
) -> Path:
    """Pick the active project root for this request.

    Order of resolution:

    1. ``explicit`` argument (when a tool param overrides it).
    2. The first entry of ``context.extra["project_roots"]`` (set by
       :class:`leagent.agent.coding_agent.CodingAgentTool` when it
       forks the child engine).

    Raises :class:`ProjectRootError` when none of those produce a real
    directory. The path sandbox in
    :mod:`leagent.tools._sandbox.paths` already validates and folds
    these roots into the allow-list, but tools still call this helper
    so they get a friendly error message instead of a generic
    ``PermissionError`` from the deeper sandbox.
    """
    candidate: Path | None = None
    if explicit:
        try:
            candidate = Path(explicit).expanduser().resolve()
        except (OSError, RuntimeError, ValueError) as exc:
            raise ProjectRootError(
                f"Could not resolve project_path={explicit!r}: {exc}"
            ) from exc

    if candidate is None:
        roots = get_project_roots(context)
        if roots:
            candidate = roots[0]

    if candidate is None:
        raise ProjectRootError(
            "No project root configured. Pass `project_path` (absolute) "
            "or invoke the tool through the coding_agent which stamps "
            "context.extra['project_roots']."
        )

    if not candidate.exists() or not candidate.is_dir():
        raise ProjectRootError(
            f"Project root {str(candidate)!r} does not exist or is not a directory."
        )
    return candidate


def resolve_in_project(
    root: Path,
    rel_or_abs: str,
    *,
    must_exist: bool = True,
) -> ResolvedFile:
    """Resolve ``rel_or_abs`` to an absolute path inside ``root``.

    The input may be either a path relative to ``root`` (preferred) or
    an absolute path that already sits inside it. Symlink targets are
    materialised so ``../`` traversal cannot smuggle the resolved path
    out of the root.

    When ``must_exist`` is ``True`` (the default for read tools) the
    resolved file must already exist on disk. Write tools pass ``False``
    so they can create new files.
    """
    if not rel_or_abs or not rel_or_abs.strip():
        raise ProjectPathError("Path is empty.")

    raw = rel_or_abs.replace("\\", "/").strip()
    candidate_path = Path(raw)
    try:
        if candidate_path.is_absolute():
            abs_path = candidate_path.expanduser().resolve()
        else:
            abs_path = (root / raw).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ProjectPathError(
            f"Cannot resolve path {raw!r} under {root}: {exc}"
        ) from exc

    try:
        abs_path.relative_to(root)
    except ValueError as exc:
        raise ProjectPathError(
            f"Path {raw!r} is outside the project root {root}."
        ) from exc

    if must_exist and not abs_path.exists():
        raise FileNotFoundError(f"File not found: {raw}")

    rel = PurePosixPath(abs_path.relative_to(root).as_posix()).as_posix()
    return ResolvedFile(root=root, abs_path=abs_path, rel_path=rel)


# ---------------------------------------------------------------------------
# Ignore rules
# ---------------------------------------------------------------------------


class IgnoreMatcher:
    """Combined gitignore + sensible defaults matcher.

    The implementation is intentionally lean — it understands the most
    common ``.gitignore`` patterns (one per line, ``#`` comments, ``!``
    re-include, leading ``/`` for root-anchored, trailing ``/`` for
    directories, ``**`` recursion). It does not attempt to be a fully
    bug-compatible reimplementation of ``git check-ignore``; for that
    level of precision a project should rely on ``git`` via
    ``project_shell``.
    """

    def __init__(
        self,
        root: Path,
        *,
        extra_ignores: Iterable[str] = (),
        respect_gitignore: bool = True,
    ) -> None:
        self._root = root
        self._patterns: list[tuple[str, bool, bool]] = []  # (pattern, negate, dir_only)
        if respect_gitignore:
            self._load_gitignores(root)
        for pat in extra_ignores:
            self._compile(pat)

    def _load_gitignores(self, root: Path) -> None:
        gi_root = root / ".gitignore"
        if gi_root.is_file():
            try:
                for line in gi_root.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines():
                    self._compile(line)
            except OSError:
                pass

    def _compile(self, raw: str) -> None:
        line = raw.strip()
        if not line or line.startswith("#"):
            return
        negate = False
        if line.startswith("!"):
            negate = True
            line = line[1:]
        dir_only = line.endswith("/")
        if dir_only:
            line = line[:-1]
        if line.startswith("/"):
            line = line[1:]
        if not line:
            return
        self._patterns.append((line, negate, dir_only))

    def is_ignored(self, abs_path: Path, *, is_dir: bool | None = None) -> bool:
        """Return True if ``abs_path`` should be skipped by walkers."""
        try:
            rel = abs_path.relative_to(self._root).as_posix()
        except ValueError:
            return True

        if is_dir is None:
            try:
                is_dir = abs_path.is_dir()
            except OSError:
                is_dir = False

        name = abs_path.name
        if name in DEFAULT_IGNORE_DIRS:
            return True
        for glob in DEFAULT_IGNORE_GLOBS:
            if fnmatch.fnmatchcase(name, glob):
                return True

        ignored = False
        for pattern, negate, dir_only in self._patterns:
            if dir_only and not is_dir:
                continue
            if _gitignore_match(pattern, rel, name):
                ignored = not negate
        return ignored


def _gitignore_match(pattern: str, rel: str, name: str) -> bool:
    """Apply a single gitignore-style pattern to a relative path."""
    if "/" not in pattern and "**" not in pattern:
        if fnmatch.fnmatchcase(name, pattern):
            return True
        for part in rel.split("/"):
            if fnmatch.fnmatchcase(part, pattern):
                return True
        return False

    glob = pattern.replace("**/", "*/").replace("/**", "/*")
    if fnmatch.fnmatchcase(rel, glob):
        return True
    if pattern.endswith("/*") or pattern.endswith("/**"):
        prefix = pattern.rstrip("/*").rstrip("/")
        if rel == prefix or rel.startswith(prefix + "/"):
            return True
    return False


def walk_project(
    root: Path,
    *,
    matcher: IgnoreMatcher | None = None,
    max_files: int | None = None,
) -> Iterator[Path]:
    """Yield every non-ignored file path under ``root`` (depth-first).

    Directories are pruned in-place so ``node_modules``/``.git`` are
    never descended into. Iteration stops after ``max_files`` matches
    when the cap is set, which lets callers (grep/glob/tree) implement
    a hard upper bound without spinning forever on monorepos.
    """
    matcher = matcher or IgnoreMatcher(root)
    seen = 0
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        d_abs = Path(dirpath)
        kept_dirs: list[str] = []
        for d in dirnames:
            child = d_abs / d
            if matcher.is_ignored(child, is_dir=True):
                continue
            kept_dirs.append(d)
        dirnames[:] = sorted(kept_dirs)
        for fname in sorted(filenames):
            f_abs = d_abs / fname
            if matcher.is_ignored(f_abs, is_dir=False):
                continue
            yield f_abs
            seen += 1
            if max_files is not None and seen >= max_files:
                return


# ---------------------------------------------------------------------------
# Text reading
# ---------------------------------------------------------------------------


def looks_binary(raw: bytes) -> bool:
    """Cheap binary heuristic — true when sample contains NUL bytes."""
    if not raw:
        return False
    return b"\x00" in raw[:_BINARY_PEEK_BYTES]


def read_text_with_detection(path: Path) -> tuple[str, str]:
    """Read ``path`` as text, returning ``(content, encoding)``.

    Tries UTF-8 first (the dominant case), then falls back to
    ``utf-8-sig``/``utf-16``/``cp1252`` so legacy files still load
    cleanly. Raises :class:`UnicodeDecodeError` on hopeless inputs so
    the caller can surface a useful error to the LLM rather than
    silently mangling bytes.
    """
    raw = path.read_bytes()
    if looks_binary(raw):
        raise UnicodeDecodeError(
            "binary", raw, 0, min(_BINARY_PEEK_BYTES, len(raw)),
            f"{path} appears to be binary",
        )
    for enc in ("utf-8", "utf-8-sig", "utf-16", "utf-16-le", "utf-16-be", "cp1252"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "utf-8(replace)"


def format_lines_with_numbers(
    text: str,
    *,
    offset: int = 1,
    limit: int | None = None,
    pad_width: int = 6,
) -> tuple[str, int, int]:
    """Render ``text`` as ``LINE_NUM|content`` rows.

    Returns ``(rendered, start_line, end_line)``. ``offset`` is
    1-indexed (the first line of the file is line 1). ``limit`` caps
    the number of rendered rows; when ``None`` the whole file is
    rendered. Padding mirrors the style the agent harness uses
    elsewhere so the LLM sees a consistent format.
    """
    if offset < 1:
        offset = 1
    lines = text.splitlines()
    total = len(lines)
    start = min(offset, total + 1) - 1
    if limit is None:
        end = total
    else:
        end = min(start + max(limit, 0), total)
    out: list[str] = []
    for i in range(start, end):
        out.append(f"{str(i + 1).rjust(pad_width)}|{lines[i]}")
    return "\n".join(out), start + 1, end


# ---------------------------------------------------------------------------
# Surgical string replace
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EditResult:
    rel_path: str
    replacements: int
    new_size: int
    diff: str


def apply_str_replace(
    abs_path: Path,
    rel_path: str,
    *,
    old_string: str,
    new_string: str,
    replace_all: bool,
) -> EditResult:
    """Replace ``old_string`` with ``new_string`` inside the file.

    Behaves like Cursor's ``str_replace`` tool: when ``replace_all`` is
    ``False`` the call fails unless ``old_string`` occurs exactly once
    so the LLM is forced to add context whenever multiple matches
    exist. The returned diff is a unified diff against the file's
    previous contents — useful for telemetry and for showing the user
    what changed.
    """
    import difflib

    if old_string == new_string:
        raise ValueError("old_string and new_string must differ.")
    text, encoding = read_text_with_detection(abs_path)

    occurrences = text.count(old_string)
    if occurrences == 0:
        raise ValueError(
            f"old_string not found in {rel_path}. Provide a snippet that "
            "matches the file exactly (whitespace and indentation matter)."
        )
    if not replace_all and occurrences > 1:
        raise ValueError(
            f"old_string occurs {occurrences} times in {rel_path}. Pass "
            "replace_all=true or extend old_string with surrounding context "
            "until it is unique."
        )

    if replace_all:
        new_text = text.replace(old_string, new_string)
    else:
        new_text = text.replace(old_string, new_string, 1)

    abs_path.write_bytes(new_text.encode(_safe_encoding(encoding)))
    diff = "".join(
        difflib.unified_diff(
            text.splitlines(keepends=True),
            new_text.splitlines(keepends=True),
            fromfile=f"a/{rel_path}",
            tofile=f"b/{rel_path}",
            n=3,
        )
    )
    return EditResult(
        rel_path=rel_path,
        replacements=occurrences if replace_all else 1,
        new_size=len(new_text.encode("utf-8")),
        diff=diff,
    )


class StrReplaceError(ValueError):
    """Raised when str_replace fails; carries optional :attr:`patch_hint`."""

    def __init__(self, message: str, *, patch_hint: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.patch_hint = patch_hint


def perform_str_replace(
    abs_path: Path,
    rel_path: str,
    *,
    old_string: str,
    new_string: str,
    replace_all: bool,
) -> EditResult:
    """Run :func:`apply_str_replace`, enriching no-match errors with did-you-mean hints."""
    from leagent.project.tools.edit_hints import format_no_match_hint

    try:
        return apply_str_replace(
            abs_path,
            rel_path,
            old_string=old_string,
            new_string=new_string,
            replace_all=replace_all,
        )
    except ValueError as exc:
        msg = str(exc)
        if "old_string not found" in msg or "occurs" in msg:
            try:
                file_text = abs_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                raise StrReplaceError(msg) from exc
            payload = format_no_match_hint(
                rel_path=rel_path,
                needle=old_string,
                file_text=file_text,
                base_message=msg,
            )
            raise StrReplaceError(msg, patch_hint=payload.get("patch_hint")) from exc
        raise


def str_replace_result_dict(result: EditResult) -> dict[str, Any]:
    """Normalise a successful :class:`EditResult` to a tool response dict."""
    return {
        "path": result.rel_path,
        "replacements": result.replacements,
        "new_size": result.new_size,
        "diff": result.diff,
    }


def _safe_encoding(detected: str) -> str:
    """Round detected encodings back to a writable codec.

    ``read_text_with_detection`` may report ``utf-8(replace)`` to mark
    a lossy fallback; for writes we always normalise to UTF-8 so the
    file is left in a well-formed state.
    """
    if detected.startswith("utf-8") or detected == "utf-8(replace)":
        return "utf-8"
    if detected.startswith("utf-16"):
        return detected
    return "utf-8"


# ---------------------------------------------------------------------------
# Unified-diff applicator
# ---------------------------------------------------------------------------


_HUNK_HEADER_RE = re.compile(
    r"^@@\s*-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s*@@"
)


@dataclass
class _PatchedFile:
    rel_path: str
    new_content: str | None  # None when file was deleted
    is_new: bool
    is_deleted: bool


def _resolve_context_line(
    collected: list[str],
    cursor: int,
    expected: str,
    *,
    fuzzy: bool,
    rel_path: str,
) -> int:
    """Return the index in *collected* that matches *expected* (context line)."""
    if cursor < len(collected) and collected[cursor] == expected:
        return cursor
    if not fuzzy:
        got = collected[cursor] if cursor < len(collected) else "<EOF>"
        raise ValueError(
            f"Context mismatch in {rel_path} at line {cursor + 1}: "
            f"expected {expected!r} got {got!r}"
        )
    for offset in range(-5, 6):
        idx = cursor + offset
        if 0 <= idx < len(collected) and collected[idx] == expected:
            return idx
    raise ValueError(
        f"Context mismatch in {rel_path} at line {cursor + 1}: "
        f"expected {expected!r} (fuzzy search within ±5 lines failed)"
    )


def apply_unified_diff(
    root: Path,
    diff_text: str,
    *,
    fuzzy: bool = False,
) -> list[_PatchedFile]:
    """Apply a multi-file unified diff in-memory and persist results.

    Supports the subset of unified diff that ``git diff`` and
    ``diff -u`` produce: ``--- a/path``/``+++ b/path`` headers, one or
    more ``@@ ... @@`` hunks, ``-`` removals, ``+`` additions,
    space-context lines. The ``/dev/null`` convention indicates new or
    deleted files.

    The function rebuilds each touched file by walking its lines in
    order; it does **not** attempt fuzzy matching or context-line
    correction. If the source line numbers in a hunk don't agree with
    the file on disk it bails out so the agent can re-read the file
    and try again.
    """
    files: list[_PatchedFile] = []
    lines = diff_text.splitlines()
    i = 0
    n = len(lines)

    while i < n:
        if not lines[i].startswith("--- "):
            i += 1
            continue
        if i + 1 >= n or not lines[i + 1].startswith("+++ "):
            raise ValueError("Malformed diff: '+++' header missing after '---'.")
        old_header = lines[i][4:].strip()
        new_header = lines[i + 1][4:].strip()
        i += 2
        rel_path = _strip_diff_prefix(new_header if new_header != "/dev/null" else old_header)
        is_new = old_header == "/dev/null"
        is_deleted = new_header == "/dev/null"

        if is_deleted:
            target_abs = (root / rel_path).resolve()
            target_abs.relative_to(root)  # raises ValueError on escape
            files.append(_PatchedFile(rel_path=rel_path, new_content=None,
                                       is_new=False, is_deleted=True))
            while i < n and not lines[i].startswith("--- "):
                i += 1
            continue

        if is_new:
            collected: list[str] = []
        else:
            target_abs = (root / rel_path).resolve()
            target_abs.relative_to(root)
            existing = target_abs.read_text(encoding="utf-8")
            collected = existing.splitlines()

        out_lines: list[str] = []
        cursor = 0  # 0-indexed pointer into ``collected``
        while i < n and lines[i].startswith("@@"):
            header = lines[i]
            m = _HUNK_HEADER_RE.match(header)
            if not m:
                raise ValueError(f"Bad hunk header: {header}")
            old_start = int(m.group(1))
            old_count = int(m.group(2) or 1)
            i += 1
            old_idx = max(old_start - 1, 0)
            if not is_new:
                if cursor < old_idx:
                    out_lines.extend(collected[cursor:old_idx])
                    cursor = old_idx
            consumed_old = 0
            while i < n and not lines[i].startswith("@@") and not lines[i].startswith("--- "):
                line = lines[i]
                if line.startswith(" "):
                    if not is_new:
                        if cursor >= len(collected):
                            raise ValueError(
                                f"Patch context past EOF in {rel_path} at line {cursor + 1}"
                            )
                        matched = _resolve_context_line(
                            collected,
                            cursor,
                            line[1:],
                            fuzzy=fuzzy,
                            rel_path=rel_path,
                        )
                        if matched != cursor and fuzzy:
                            out_lines.extend(collected[cursor:matched])
                        out_lines.append(collected[matched])
                        cursor = matched + 1
                    else:
                        out_lines.append(line[1:])
                    consumed_old += 1
                elif line.startswith("-"):
                    if is_new:
                        raise ValueError(
                            f"Removal line in /dev/null hunk for {rel_path}"
                        )
                    if cursor >= len(collected):
                        raise ValueError(
                            f"Patch removal past EOF in {rel_path} at line {cursor + 1}"
                        )
                    if collected[cursor] != line[1:]:
                        raise ValueError(
                            f"Removal mismatch in {rel_path} at line {cursor + 1}"
                        )
                    cursor += 1
                    consumed_old += 1
                elif line.startswith("+"):
                    out_lines.append(line[1:])
                elif line.startswith("\\"):
                    pass  # "\ No newline at end of file"
                else:
                    raise ValueError(f"Unknown diff line: {line!r}")
                i += 1
            if not is_new and consumed_old != old_count:
                # Count mismatches are non-fatal — agents sometimes write
                # the wrong count in the header. Trust the body.
                pass

        if not is_new:
            out_lines.extend(collected[cursor:])

        new_content = "\n".join(out_lines)
        if collected and not is_new:
            existing = "\n".join(collected) + ("\n" if existing.endswith("\n") else "")
        if not new_content.endswith("\n"):
            new_content += "\n"
        files.append(_PatchedFile(
            rel_path=rel_path, new_content=new_content,
            is_new=is_new, is_deleted=False,
        ))

    if not files:
        raise ValueError("Diff contained no '--- /+++' headers.")

    for pf in files:
        target = (root / pf.rel_path).resolve()
        target.relative_to(root)
        if pf.is_deleted:
            if target.exists():
                target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(pf.new_content or "", encoding="utf-8")
    return files


def _strip_diff_prefix(header: str) -> str:
    """Strip the ``a/``/``b/`` prefix and trailing tab metadata."""
    cleaned = header.split("\t", 1)[0].strip()
    if cleaned.startswith(("a/", "b/")):
        cleaned = cleaned[2:]
    return cleaned.lstrip("/")


async def resolve_content(
    params: dict,
    context: "ToolContext",
    *,
    inline_key: str = "content",
    blob_key: str = "content_blob_id",
    allow_empty: bool = False,
) -> str:
    """Resolve a text payload from either an inline param or a staged blob.

    Centralises the duplicated ``*_blob_id`` resolution pattern used by
    ``project_write``, ``project_edit``, ``project_apply_patch``, and
    ``code_execution``.  The blob path delegates to
    :func:`~leagent.tools.util.tool_argument_blob.resolve_blob_text`.

    Raises :class:`ValueError` when neither source provides usable text
    (unless *allow_empty* is set).
    """
    from typing import Any

    blob_raw: Any = params.get(blob_key)
    if isinstance(blob_raw, str) and blob_raw.strip():
        from leagent.tools.util.tool_argument_blob import resolve_blob_text

        return await resolve_blob_text(
            context, blob_raw, allow_empty=allow_empty,
        )

    raw = params.get(inline_key)
    text = raw if isinstance(raw, str) else ""

    if not allow_empty and not text.strip():
        raise ValueError(
            f"Provide non-empty `{inline_key}` or a finalized "
            f"`{blob_key}` (from `tool_argument_blob`)."
        )
    return text


__all__ = [
    "DEFAULT_IGNORE_DIRS",
    "DEFAULT_IGNORE_GLOBS",
    "MAX_TEXT_FILE_BYTES",
    "ProjectRootError",
    "ProjectPathError",
    "ResolvedFile",
    "select_project_root",
    "resolve_in_project",
    "resolve_content",
    "IgnoreMatcher",
    "walk_project",
    "looks_binary",
    "read_text_with_detection",
    "format_lines_with_numbers",
    "EditResult",
    "StrReplaceError",
    "apply_str_replace",
    "perform_str_replace",
    "str_replace_result_dict",
    "apply_unified_diff",
]
