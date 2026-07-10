"""Tests for toolchain-aware verification_gap detection."""

from __future__ import annotations

from leagent.agent.subagent import (
    _expected_verify_tokens,
    assess_verification_gap,
)


def test_expected_tokens_for_python():
    tokens = _expected_verify_tokens({"src/foo.py", "README.md"})
    assert "pytest" in tokens
    assert "ruff" in tokens


def test_expected_tokens_for_typescript():
    tokens = _expected_verify_tokens({"app/Button.tsx"})
    assert "vitest" in tokens or "npm test" in tokens


def test_expected_tokens_for_rust():
    tokens = _expected_verify_tokens({"src/lib.rs"})
    assert "cargo test" in tokens


def test_gap_when_no_shell():
    gap = assess_verification_gap(
        changed_paths={"a.py"},
        shell_blobs=[],
        enforce=True,
        partial=False,
        error=None,
    )
    assert gap is not None
    assert "project_shell was not run" in gap
    assert "pytest" in gap


def test_gap_when_shell_unrelated():
    gap = assess_verification_gap(
        changed_paths={"a.py"},
        shell_blobs=["git status"],
        enforce=True,
        partial=False,
        error=None,
    )
    assert gap is not None
    assert "no command matched" in gap


def test_no_gap_when_pytest_ran():
    gap = assess_verification_gap(
        changed_paths={"a.py", "b.py"},
        shell_blobs=["pytest tests/ -q"],
        enforce=True,
        partial=False,
        error=None,
    )
    assert gap is None


def test_no_gap_when_enforce_off():
    gap = assess_verification_gap(
        changed_paths={"a.py"},
        shell_blobs=[],
        enforce=False,
        partial=False,
        error=None,
    )
    assert gap is None


def test_unknown_ext_any_shell_counts():
    gap = assess_verification_gap(
        changed_paths={"notes.txt"},
        shell_blobs=["echo ok"],
        enforce=True,
        partial=False,
        error=None,
    )
    assert gap is None
