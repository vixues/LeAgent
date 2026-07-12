"""Tests for canvas_publish html_paths disk-backed publish."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from leagent.tools.base import ToolContext
from leagent.tools.canvas.canvas_publish import load_html_paths_map


def test_load_html_paths_map_from_project_root(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<!DOCTYPE html><html><body>ok</body></html>",
        encoding="utf-8",
    )
    (tmp_path / "app.js").write_text("console.log(1)", encoding="utf-8")
    ctx = ToolContext(
        user_id=str(uuid4()),
        session_id=str(uuid4()),
        extra={"project_roots": [str(tmp_path)]},
    )
    files = load_html_paths_map(["index.html", "app.js"], ctx)
    assert "ok" in files["index.html"]
    assert files["app.js"] == "console.log(1)"


def test_load_html_paths_map_rejects_missing(tmp_path: Path) -> None:
    ctx = ToolContext(
        user_id=str(uuid4()),
        session_id=str(uuid4()),
        extra={"project_roots": [str(tmp_path)]},
    )
    with pytest.raises(ValueError, match="not found"):
        load_html_paths_map(["missing.html"], ctx)


def test_load_html_paths_map_rejects_traversal(tmp_path: Path) -> None:
    ctx = ToolContext(
        user_id=str(uuid4()),
        session_id=str(uuid4()),
        extra={"project_roots": [str(tmp_path)]},
    )
    with pytest.raises(ValueError, match="Unsafe"):
        load_html_paths_map(["../etc/passwd"], ctx)
