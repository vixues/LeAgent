"""Unit tests for :mod:`leagent.services.diagnostics_parsers.shell_output`."""

from __future__ import annotations

from leagent.services.diagnostics_parsers.shell_output import (
    extract_shell_diagnostics,
    parse_ruff_output,
    parse_tsc_output,
)


def test_parse_ruff_single_line() -> None:
    text = "src/app.py:12:5: F401 `os` imported but unused\n"
    diags = parse_ruff_output(text)
    assert len(diags) == 1
    d = diags[0]
    assert d["file"] == "src/app.py"
    assert d["line"] == 12
    assert d["column"] == 5
    assert d["code"] == "F401"
    assert "unused" in d["message"]


def test_parse_tsc_single_line() -> None:
    text = "src/views.ts(10,3): error TS2322: Type 'string' is not assignable to type 'number'.\n"
    diags = parse_tsc_output(text)
    assert len(diags) == 1
    d = diags[0]
    assert d["file"] == "src/views.ts"
    assert d["line"] == 10
    assert d["column"] == 3
    assert d["code"] == "TS2322"
    assert d["severity"] == "error"


def test_extract_shell_diagnostics_ruff_argv() -> None:
    out = ""
    err = "pkg/mod.py:1:1: E902 The system cannot find the file specified.\n"
    src, diags = extract_shell_diagnostics(["ruff", "check", "."], out, err)
    assert src == "ruff"
    assert len(diags) == 1
    assert diags[0]["code"] == "E902"


def test_extract_shell_diagnostics_npx_tsc() -> None:
    text = "app.tsx(2,1): error TS17004: Cannot use JSX unless the '--jsx' flag is provided.\n"
    src, diags = extract_shell_diagnostics(["npx", "tsc", "--noEmit"], "", text)
    assert src == "tsc"
    assert len(diags) == 1


def test_extract_shell_diagnostics_unknown() -> None:
    src, diags = extract_shell_diagnostics(["pytest", "-q"], "FAILED\n", "")
    assert src is None
    assert diags == []
