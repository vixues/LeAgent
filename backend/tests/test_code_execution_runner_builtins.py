"""Sandbox runner builtins — unrestricted mode."""

from __future__ import annotations

from pathlib import Path


def test_sandbox_builtins_has_full_builtins(tmp_path: Path) -> None:
    from leagent.services.code_execution.runner import _sandbox_builtins

    d = _sandbox_builtins(workspace_path=tmp_path)
    assert "open" in d
    assert "eval" in d
    assert "__import__" in d
    assert len(d) > 20


def test_unrestricted_import_allows_os(tmp_path: Path) -> None:
    from leagent.services.code_execution.runner import _sandbox_builtins

    imp = _sandbox_builtins(workspace_path=tmp_path)["__import__"]
    m = imp("os")
    import os
    assert m is os


def test_unrestricted_import_allows_json(tmp_path: Path) -> None:
    import json as json_stdlib

    from leagent.services.code_execution.runner import _sandbox_builtins

    imp = _sandbox_builtins(workspace_path=tmp_path)["__import__"]
    m = imp("json")
    assert m is json_stdlib


def test_open_allows_workspace_write(tmp_path: Path) -> None:
    from leagent.services.code_execution.runner import _sandbox_builtins

    builtins_dict = _sandbox_builtins(workspace_path=tmp_path)
    scoped_open = builtins_dict["open"]
    with scoped_open(tmp_path / "out.txt", "w", encoding="utf-8") as fh:
        fh.write("ok")

    assert (tmp_path / "out.txt").read_text() == "ok"


def test_open_allows_outside_write(tmp_path: Path) -> None:
    from leagent.services.code_execution.runner import _sandbox_builtins

    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    builtins_dict = _sandbox_builtins(workspace_path=tmp_path)
    scoped_open = builtins_dict["open"]
    try:
        with scoped_open(outside, "w", encoding="utf-8") as fh:
            fh.write("unrestricted")
        assert outside.read_text() == "unrestricted"
    finally:
        outside.unlink(missing_ok=True)


def test_open_allows_read_outside_workspace(tmp_path: Path) -> None:
    from leagent.services.code_execution.runner import _sandbox_builtins

    outside = tmp_path.parent / f"{tmp_path.name}-input.txt"
    outside.write_text("readable", encoding="utf-8")
    try:
        builtins_dict = _sandbox_builtins(workspace_path=tmp_path)
        scoped_open = builtins_dict["open"]
        with scoped_open(outside, "r", encoding="utf-8") as fh:
            assert fh.read() == "readable"
    finally:
        outside.unlink(missing_ok=True)
