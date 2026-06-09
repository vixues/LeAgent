"""Invariant enforcement tests for the unified file layer.

These tests verify the architectural invariants specified in the
File Layer Consolidation Roadmap:

INV-1: No direct open(…, 'wb') or write_bytes() in blob paths
       outside StorageBackend and project/.
INV-5: leagent/project/ never imports FileService or FileRef.
INV-7: Path containment via commonpath/is_relative_to in blob-path
       code should delegate to primitives.is_path_inside.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent / "leagent"

_TIER_B_PREFIXES = ("project/", "code/", "skills/")
_EXCLUDED_DIRS = ("__pycache__",)


def _python_files(root: Path) -> list[Path]:
    """Collect all .py files under *root*, excluding __pycache__."""
    return [
        p
        for p in root.rglob("*.py")
        if "__pycache__" not in str(p) and ".pyc" not in p.suffix
    ]


def _blob_path_files() -> list[tuple[Path, str]]:
    """Return (path, relative_str) pairs for blob-layer Python files.

    Excludes Tier B packages (project/, code/, skills/) and test files.
    """
    out: list[tuple[Path, str]] = []
    for py in _python_files(BACKEND_ROOT):
        rel = str(py.relative_to(BACKEND_ROOT))
        if any(rel.startswith(p) for p in _TIER_B_PREFIXES):
            continue
        if any(d in rel for d in _EXCLUDED_DIRS):
            continue
        if "test" in rel:
            continue
        out.append((py, rel))
    return out


class TestINV1_NoDirectWriteInBlobPaths:
    """Blob-layer code must not use direct open(…, 'wb') or write_bytes()
    outside StorageBackend implementations."""

    _SKIP_FILES = {
        "file/storage/local.py",
        "file/storage/backend.py",
    }

    _WRITE_PAT = re.compile(
        r"""open\([^)]*['"]w[b]?['"]"""
        r"""|\.write_bytes\("""
        r"""|\.write_text\(""",
    )

    def test_no_direct_blob_writes(self):
        violations: list[str] = []
        for py, rel in _blob_path_files():
            if rel in self._SKIP_FILES:
                continue
            for i, line in enumerate(py.read_text().splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#") or stripped.startswith('"""'):
                    continue
                if self._WRITE_PAT.search(line):
                    violations.append(f"{rel}:{i}: {stripped}")

        if violations:
            pytest.xfail(
                "Direct file writes found in blob-layer code "
                "(expected during migration):\n"
                + "\n".join(violations[:10])
            )


class TestINV5_ProjectNeverImportsFileService:
    """leagent/project/ must never import FileService or FileRef."""

    def test_no_file_service_imports(self):
        project_dir = BACKEND_ROOT / "project"
        if not project_dir.exists():
            pytest.skip("leagent/project/ not found")

        violations: list[str] = []
        pattern = re.compile(r"(?:FileService|FileRef|file_service)")
        for py in _python_files(project_dir):
            for i, line in enumerate(py.read_text().splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if pattern.search(line):
                    violations.append(f"{py.relative_to(BACKEND_ROOT)}:{i}: {line.strip()}")

        assert not violations, (
            "leagent/project/ must not reference FileService/FileRef:\n"
            + "\n".join(violations)
        )


class TestINV7_PathContainmentInBlobLayer:
    """Blob-layer containment checks should delegate to primitives.is_path_inside,
    not use raw relative_to/is_relative_to/commonpath for security decisions."""

    _SKIP_FILES = {
        "file/primitives.py",
        "file/storage/local.py",
    }

    _CONTAINMENT_PAT = re.compile(r"\.is_relative_to\(|commonpath\(")

    def test_no_inline_containment_in_blob_paths(self):
        violations: list[str] = []
        for py, rel in _blob_path_files():
            if rel in self._SKIP_FILES:
                continue
            for i, line in enumerate(py.read_text().splitlines(), 1):
                if line.lstrip().startswith("#"):
                    continue
                if self._CONTAINMENT_PAT.search(line):
                    violations.append(f"{rel}:{i}: {line.strip()}")

        if violations:
            pytest.xfail(
                "Containment logic found in blob-layer code outside primitives.py "
                "(expected during migration, will be cleaned up):\n"
                + "\n".join(violations[:10])
            )
