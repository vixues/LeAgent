"""Parse common linter / typechecker CLI output into structured diagnostics.

Shapes mirror :class:`leagent.services.syntax_validation.Diagnostic` dict
form so agents can reuse the same mental model as ``syntax_validator``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# Ruff: path:line:column: CODE message
_RUFF_RE = re.compile(
    r"^(?P<file>[^\s:]+?):(?P<line>\d+):(?P<col>\d+): (?P<code>\S+)\s+(?P<message>.+)$"
)

# TypeScript: path(line,col): error TSxxxx: message
_TSC_RE = re.compile(
    r"^(?P<file>.+?)\((?P<line>\d+),(?P<col>\d+)\):\s+"
    r"(?P<sev>error|warning)\s+(?P<code>TS\d+):\s*(?P<message>.+)$"
)


def _binary_basename(arg0: str) -> str:
    leaf = Path(arg0).name.lower()
    if leaf.endswith((".exe", ".cmd", ".bat", ".ps1")):
        leaf = leaf.rsplit(".", 1)[0]
    return leaf


def _argv_invokes(argv: list[str], name: str) -> bool:
    return any(_binary_basename(a) == name for a in argv if isinstance(a, str))


def _diagnostic_dict(
    *,
    file: str,
    line: int,
    column: int,
    code: str,
    message: str,
    severity: str,
) -> dict[str, Any]:
    return {
        "message": message.strip(),
        "severity": severity,
        "line": line,
        "column": column,
        "end_line": None,
        "end_column": None,
        "offset": None,
        "code": code,
        "source_line": "",
        "frame": [],
        "caret": "",
        "file": file,
    }


def parse_ruff_output(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        m = _RUFF_RE.match(line.strip())
        if not m:
            continue
        sev = "error"
        code = m.group("code")
        if code.lower().startswith("w"):
            sev = "warning"
        try:
            ln = int(m.group("line"))
            col = int(m.group("col"))
        except ValueError:
            continue
        out.append(
            _diagnostic_dict(
                file=m.group("file").strip(),
                line=ln,
                column=col,
                code=code,
                message=m.group("message"),
                severity=sev,
            )
        )
    return out


def parse_tsc_output(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in text.splitlines():
        m = _TSC_RE.match(line.strip())
        if not m:
            continue
        sev = m.group("sev").lower()
        try:
            ln = int(m.group("line"))
            col = int(m.group("col"))
        except ValueError:
            continue
        out.append(
            _diagnostic_dict(
                file=m.group("file").strip(),
                line=ln,
                column=col,
                code=m.group("code"),
                message=m.group("message"),
                severity=sev,
            )
        )
    return out


def extract_shell_diagnostics(
    argv: list[str],
    stdout: str,
    stderr: str,
) -> tuple[str | None, list[dict[str, Any]]]:
    """Return ``(source_label, diagnostics)`` for supported tools."""
    if not argv:
        return None, []
    combined = f"{stdout}\n{stderr}"
    if _argv_invokes(argv, "ruff"):
        diags = parse_ruff_output(combined)
        return ("ruff", diags) if diags else (None, [])
    if _argv_invokes(argv, "tsc"):
        diags = parse_tsc_output(combined)
        return ("tsc", diags) if diags else (None, [])
    return None, []
