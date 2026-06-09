"""Invariant enforcement tests for the unified file/code/project layers.

These tests hard-enforce the architectural invariants from the service-layer &
persistence migration:

INV-1: No direct ``open(…, 'wb'/'w')``, ``write_bytes()`` or ``write_text()`` in
       blob-layer code. Managed blobs must flow through ``FileService.register``
       (which delegates to a ``StorageBackend``). The only permitted direct
       writes are non-managed-blob writes (CLI output, app/provider/cron config,
       workflow-definition serialization, and Tier-B sandbox/output-path tool
       writes governed by the path sandbox) — each justified in
       ``_INV1_ALLOWLIST`` / covered by ``_INV1_ALLOWED_PREFIXES``.
INV-5: ``leagent/project/`` never imports ``FileService`` or ``FileRef``.
INV-7: Path-containment checks delegate to ``primitives.is_path_inside`` rather
       than inline ``is_relative_to`` / ``commonpath``.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent / "leagent"

# Tier B packages own their workspaces (project scaffolds, code sandboxes,
# skill bundles) and are exempt from the managed-blob ingress rule entirely.
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
    """Return (path, relative_str) pairs for blob-layer Python files."""
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
    """Blob-layer code must not write managed blobs directly.

    Every entry below is a *non-managed-blob* write (CLI artifacts, config
    files, durable job/extension registries, workflow-definition exports, or
    Tier-B sandbox/output-path tool writes that the path sandbox governs and the
    artifact pipeline promotes). Adding a new entry requires a written
    justification here and CODEOWNERS review.
    """

    # StorageBackend implementations are the canonical write surface.
    _SKIP_FILES = {
        "file/storage/local.py",
        "file/storage/backend.py",
    }

    # Files that legitimately perform non-managed-blob writes, with rationale.
    _INV1_ALLOWLIST: dict[str, str] = {
        # App / provider / migration config files (not session blobs).
        "config/config.py": "writes the user app-config file",
        "config/migrate_v2.py": "rewrites config during v1->v2 migration",
        "llm/provider_config.py": "persists the LLM provider config file",
        # Durable operational registries with their own file formats.
        "cron/repository.py": "atomic write of the cron jobs registry file",
        "extensions/manager.py": "persists the installed-extensions registry",
        # Workflow definitions are documents, not managed blobs.
        "workflow/io/serializer.py": "serializes workflow definitions to yaml/json",
        # Tier-B tool writes: sandbox-validated output_path / config / temp / auth.
        "tools/_data/records.py": "writes to sandbox-validated output path",
        "tools/doc/config_file_tool.py": "edits config files at sandbox paths",
        "tools/doc/csv_processor.py": "writes transformed CSV to output_path",
        "tools/doc/html_processor.py": "writes processed HTML to output_path",
        "tools/doc/markdown_processor.py": "writes processed Markdown to output_path",
        "tools/doc/text_processor.py": "writes processed text to output_path",
        "tools/gen/checklist_generator.py": "writes generated checklist to output_path",
        "tools/gen/report_generator.py": "writes generated report to output_path",
        "tools/gen/template_filler.py": "writes rendered template to output_path",
        "tools/skills/package_skill.py": "packages a skill bundle artifact",
        "tools/util/tool_argument_blob.py": "stages large tool args to sandbox-temp",
        "tools/web/login.py": "persists a browser auth-session file in the sandbox",
    }

    # CLI commands write user-facing artifacts (exports, scaffolds, env files).
    _INV1_ALLOWED_PREFIXES = ("cli/",)

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
            if rel in self._INV1_ALLOWLIST:
                continue
            if any(rel.startswith(p) for p in self._INV1_ALLOWED_PREFIXES):
                continue
            for i, line in enumerate(py.read_text().splitlines(), 1):
                stripped = line.lstrip()
                if stripped.startswith("#") or stripped.startswith('"""'):
                    continue
                if self._WRITE_PAT.search(line):
                    violations.append(f"{rel}:{i}: {stripped}")

        assert not violations, (
            "Direct managed-blob writes found in blob-layer code. Route them "
            "through FileService.register, or (if genuinely non-managed) add a "
            "justified entry to _INV1_ALLOWLIST:\n" + "\n".join(violations)
        )


class TestINV5_ProjectNeverImportsFileService:
    """leagent/project/ must never import FileService or FileRef."""

    def test_no_file_service_imports(self):
        project_dir = BACKEND_ROOT / "project"
        if not project_dir.exists():
            return

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
    """Blob-layer containment checks must delegate to primitives.is_path_inside,
    not use raw is_relative_to/commonpath for security decisions."""

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

        assert not violations, (
            "Inline path-containment found in blob-layer code outside "
            "primitives.py. Use leagent.file.primitives.is_path_inside:\n"
            + "\n".join(violations)
        )
