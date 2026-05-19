"""Read-only filesystem + git introspection for coding project roots.

Paths are always resolved under ``project.root_path`` via :func:`safe_join`.
"""

from __future__ import annotations

import mimetypes
import shutil
from pathlib import Path
from typing import Any, Literal

SKIP_DIR_NAMES = frozenset(
    {
        "node_modules",
        ".venv",
        "venv",
        "dist",
        "build",
        ".turbo",
        "__pycache__",
        ".git",
        ".idea",
        ".vscode",
    }
)

# Treat as text when extension unknown but sniff says text/* below max bytes.
TEXT_EXTENSIONS = frozenset(
    {
        ".txt",
        ".md",
        ".markdown",
        ".html",
        ".htm",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".js",
        ".jsx",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".json",
        ".jsonc",
        ".yaml",
        ".yml",
        ".toml",
        ".xml",
        ".svg",
        ".env",
        ".gitignore",
        ".gitattributes",
        ".editorconfig",
        ".py",
        ".pyi",
        ".pyw",
        ".rs",
        ".go",
        ".java",
        ".kt",
        ".kts",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".cs",
        ".rb",
        ".php",
        ".sql",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".bat",
        ".cmd",
        ".dockerfile",
        ".vue",
        ".svelte",
    }
)

DEFAULT_MAX_TREE_DEPTH = 8
DEFAULT_MAX_TREE_ENTRIES = 500
DEFAULT_MAX_CHILDREN_PER_DIR = 200
DEFAULT_MAX_FILE_BYTES = 512 * 1024


class UnsafePathError(ValueError):
    """Relative path escapes the project root."""


def safe_join(project_root: Path, rel: str) -> Path:
    """Resolve ``rel`` under ``project_root``; reject traversal."""
    if rel is None:
        raise UnsafePathError("path is required.")
    raw = str(rel).strip()
    if not raw or raw == ".":
        return project_root.resolve()
    # Normalize separators from URL/query (Windows accepts /).
    rel_path = Path(raw)
    if rel_path.is_absolute():
        raise UnsafePathError("path must be relative.")
    for part in rel_path.parts:
        if part == "..":
            raise UnsafePathError("path must not contain '..'.")
        if part in ("/", "\\") or ":" in part:
            raise UnsafePathError("invalid path segment.")

    root = project_root.resolve()
    candidate = (root / rel_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise UnsafePathError("path escapes project root.") from exc
    return candidate


def _tree_node(
    name: str,
    path_posix: str,
    kind: Literal["file", "dir"],
    *,
    children: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    node: dict[str, Any] = {
        "name": name,
        "path": path_posix,
        "type": kind,
    }
    if children is not None:
        node["children"] = children
    return node


def build_tree(
    project_root: Path,
    *,
    max_depth: int = DEFAULT_MAX_TREE_DEPTH,
    max_entries: int = DEFAULT_MAX_TREE_ENTRIES,
    max_children_per_dir: int = DEFAULT_MAX_CHILDREN_PER_DIR,
) -> dict[str, Any]:
    """Return a nested tree dict plus ``truncated`` when limits hit."""
    root = project_root.resolve()
    if not root.is_dir():
        return {"root": _tree_node(".", "", "dir", children=[]), "truncated": False}

    count = 0
    truncated = False

    def bump() -> bool:
        nonlocal count, truncated
        if count >= max_entries:
            truncated = True
            return False
        count += 1
        return True

    def walk(rel: Path, depth: int) -> dict[str, Any]:
        nonlocal truncated
        abs_dir = root / rel
        name = "." if rel == Path("") else rel.name
        posix_parent = "" if rel == Path("") else rel.as_posix()

        try:
            entries = sorted(abs_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except OSError:
            return _tree_node(name, posix_parent, "dir", children=[])

        if not bump():
            return _tree_node(name, posix_parent, "dir", children=[])

        children: list[dict[str, Any]] = []
        lim = min(len(entries), max_children_per_dir)
        if len(entries) > max_children_per_dir:
            truncated = True

        for p in entries[:lim]:
            if count >= max_entries:
                truncated = True
                break
            rel_child = p.relative_to(root)
            posix = rel_child.as_posix()

            if p.is_dir():
                if p.name in SKIP_DIR_NAMES:
                    continue
                if depth >= max_depth:
                    if not bump():
                        break
                    children.append(_tree_node(p.name, posix, "dir", children=[]))
                    continue
                children.append(walk(rel_child, depth + 1))
            elif p.is_file():
                if not bump():
                    break
                try:
                    st = p.stat()
                    size = int(st.st_size)
                except OSError:
                    size = None
                node = _tree_node(p.name, posix, "file")
                node["size"] = size
                children.append(node)

        return _tree_node(name, posix_parent, "dir", children=children)

    tree = walk(Path(""), 0)
    return {"root": tree, "truncated": truncated}


def is_probably_text_file(path: Path) -> bool:
    ext = path.suffix.lower()
    if ext in TEXT_EXTENSIONS:
        return True
    if not ext and path.name in ("Dockerfile", "Makefile", "LICENSE", "README"):
        return True
    mime, _ = mimetypes.guess_type(str(path))
    if mime and mime.startswith("text/"):
        return True
    return False


def read_text_file(
    project_root: Path,
    rel: str,
    *,
    max_bytes: int = DEFAULT_MAX_FILE_BYTES,
) -> dict[str, Any]:
    """Read a text file under the project; returns content + truncated flag."""
    full = safe_join(project_root, rel)
    if not full.is_file():
        raise FileNotFoundError(str(rel))
    if not is_probably_text_file(full):
        raise ValueError("file is not a supported text type for preview.")
    try:
        raw = full.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read file: {exc}") from exc

    truncated = len(raw) > max_bytes
    data = raw[:max_bytes]
    text = data.decode("utf-8", errors="replace")
    return {
        "path": rel.strip().replace("\\", "/"),
        "content": text,
        "truncated": truncated,
        "size": len(raw),
    }


async def git_snapshot(project_root: Path) -> dict[str, Any]:
    """Return branch, head, and porcelain status lines; cheap when not a repo.

    Delegates subprocess and porcelain parsing to :mod:`leagent.services.coding_projects.git`
    so behaviour matches folder-based project Git APIs.
    """
    from leagent.services.coding_projects.git import (
        git_status_porcelain,
        is_git_repo,
        run_git,
    )

    root = project_root.resolve()
    if not root.is_dir():
        return {
            "is_git": False,
            "git_available": bool(shutil.which("git")),
            "error": "project root is not a directory",
        }

    if shutil.which("git") is None:
        return {"is_git": False, "git_available": False, "error": "git is not installed"}

    if not await is_git_repo(root):
        return {"is_git": False, "git_available": True}

    # Match older workspace behaviour: tolerate dubious ownership on shared roots.
    _c = ("-c", "safe.directory=*")

    _, br_out, _ = await run_git(root, (*_c, "branch", "--show-current"), check=False)
    branch = (br_out or "").strip() or None

    rc_hd, hd_out, _ = await run_git(root, (*_c, "rev-parse", "HEAD"), check=False)
    head_full = (hd_out or "").strip() if rc_hd == 0 else None
    head_short = head_full[:7] if head_full else None

    entries = await git_status_porcelain(root)
    lines = [
        {
            "status": e.status_code.strip(),
            "xy": e.status_code,
            "path": e.path,
        }
        for e in entries
    ]

    return {
        "is_git": True,
        "git_available": True,
        "branch": branch,
        "head": head_short,
        "head_full": head_full,
        "lines": lines,
        "error": None,
    }
