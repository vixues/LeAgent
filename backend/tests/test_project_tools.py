"""Smoke tests for the ``project_*`` coding-agent toolbox.

Each tool is exercised against a fresh temp project so we verify the
end-to-end path: ``project_path`` → sandbox allow-listing →
``ProjectFS`` resolution → tool execution.

The tests stay deliberately narrow: they confirm the tools work on
happy-path inputs and that the sandbox refuses obvious escapes
(``../`` traversal, paths outside the configured root). Heavy
behavioural tests live closer to ``_fs.py`` and the diff applicator
internals.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from leagent.tools.base import ToolContext, ToolResult


def _ctx(project: Path) -> ToolContext:
    """Build a tool context that authorises the temp project root."""
    return ToolContext(
        user_id="u1",
        session_id="s1",
        extra={"project_roots": [str(project)]},
    )


async def _run(tool: Any, params: dict[str, Any], ctx: ToolContext) -> ToolResult:
    return await tool.run(params, ctx)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Scaffold a tiny project with a Python module + tests folder."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "def greet(name: str) -> str:\n    return f\"hello {name}\"\n",
        encoding="utf-8",
    )
    (tmp_path / "src" / "util.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a + b\n",
        encoding="utf-8",
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text(
        "from src.app import greet\n\n"
        "def test_greet():\n    assert greet(\"world\") == \"hello world\"\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# Demo project\n", encoding="utf-8",
    )
    (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__/\n", encoding="utf-8")
    return tmp_path


@pytest.mark.asyncio
async def test_project_read_returns_line_numbered_content(project: Path) -> None:
    from leagent.tools.project.read import ProjectReadTool

    tool = ProjectReadTool()
    result = await _run(tool, {"path": "src/app.py"}, _ctx(project))
    assert result.success, result.error
    data = result.data
    assert data["path"] == "src/app.py"
    assert "1|def greet" in data["content"]
    assert data["total_lines"] == 2
    assert data["start_line"] == 1
    assert data["end_line"] == 2


@pytest.mark.asyncio
async def test_project_read_rejects_escape(project: Path) -> None:
    from leagent.tools.project.read import ProjectReadTool

    outside = project.parent / "outside.txt"
    outside.write_text("nope", encoding="utf-8")
    tool = ProjectReadTool()
    result = await _run(tool, {"path": "../outside.txt"}, _ctx(project))
    assert not result.success
    assert "outside" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_project_write_then_edit_then_read(project: Path) -> None:
    from leagent.tools.project.edit import ProjectEditTool
    from leagent.tools.project.read import ProjectReadTool
    from leagent.tools.project.write import ProjectWriteTool

    write = ProjectWriteTool()
    edit = ProjectEditTool()
    read = ProjectReadTool()

    res = await _run(write, {
        "path": "src/feature.py",
        "content": "VALUE = 1\n",
    }, _ctx(project))
    assert res.success, res.error
    assert (project / "src" / "feature.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert res.data["created"] is True

    res2 = await _run(write, {
        "path": "src/feature.py",
        "content": "VALUE = 2\n",
    }, _ctx(project))
    assert res2.success
    assert "already exists" in (res2.data.get("error") or "")

    res3 = await _run(edit, {
        "path": "src/feature.py",
        "old_string": "VALUE = 1",
        "new_string": "VALUE = 42",
    }, _ctx(project))
    assert res3.success, res3.error
    assert res3.data["replacements"] == 1
    assert (project / "src" / "feature.py").read_text(encoding="utf-8").startswith("VALUE = 42")

    res4 = await _run(read, {"path": "src/feature.py"}, _ctx(project))
    assert res4.success
    assert "VALUE = 42" in res4.data["content"]


@pytest.mark.asyncio
async def test_project_edit_requires_uniqueness(project: Path) -> None:
    """Multiple matches without ``replace_all`` must fail loudly."""
    from leagent.tools.project.edit import ProjectEditTool
    from leagent.tools.project.write import ProjectWriteTool

    await _run(
        ProjectWriteTool(),
        {"path": "dup.txt", "content": "x\nx\n"},
        _ctx(project),
    )
    res = await _run(
        ProjectEditTool(),
        {"path": "dup.txt", "old_string": "x", "new_string": "y"},
        _ctx(project),
    )
    assert res.success  # tool-level success: returns structured error
    assert "occurs 2 times" in (res.data.get("error") or "")

    res2 = await _run(
        ProjectEditTool(),
        {
            "path": "dup.txt",
            "old_string": "x",
            "new_string": "y",
            "replace_all": True,
        },
        _ctx(project),
    )
    assert res2.success and res2.data.get("replacements") == 2


@pytest.mark.asyncio
async def test_project_grep_finds_match(project: Path) -> None:
    from leagent.tools.project.grep import ProjectGrepTool

    tool = ProjectGrepTool()
    result = await _run(tool, {"pattern": "def greet"}, _ctx(project))
    assert result.success, result.error
    matches = result.data.get("matches") or []
    files = result.data.get("files_with_matches") or []
    # Either ripgrep or python backend is fine; both should locate the
    # symbol in src/app.py.
    if matches:
        assert any(m["path"] == "src/app.py" for m in matches)
    assert "src/app.py" in files


@pytest.mark.asyncio
async def test_project_glob_lists_python_files(project: Path) -> None:
    from leagent.tools.project.glob import ProjectGlobTool

    result = await _run(
        ProjectGlobTool(),
        {"pattern": "**/*.py"},
        _ctx(project),
    )
    assert result.success, result.error
    files = [f["path"] for f in result.data["files"]]
    assert "src/app.py" in files
    assert "src/util.py" in files
    assert "tests/test_app.py" in files


@pytest.mark.asyncio
async def test_project_tree_renders_layout(project: Path) -> None:
    from leagent.tools.project.tree import ProjectTreeTool

    result = await _run(ProjectTreeTool(), {"max_depth": 3}, _ctx(project))
    assert result.success, result.error
    tree = result.data["tree"]
    assert "src/" in tree
    assert "tests/" in tree
    assert "README.md" in tree


@pytest.mark.asyncio
async def test_project_tree_missing_root_is_not_retried() -> None:
    from leagent.tools.project.tree import ProjectTreeTool

    result = await _run(
        ProjectTreeTool(),
        {"max_depth": 3},
        ToolContext(user_id="u1", session_id="s1"),
    )

    assert not result.success
    assert "No project root configured" in (result.error or "")
    assert result.metadata.get("attempts") == 1


@pytest.mark.asyncio
async def test_project_apply_patch_creates_and_modifies(project: Path) -> None:
    from leagent.tools.project.patch import ProjectApplyPatchTool

    diff = (
        "--- /dev/null\n"
        "+++ b/src/new_module.py\n"
        "@@ -0,0 +1,2 @@\n"
        "+CONST = 7\n"
        "+other = 8\n"
    )
    result = await _run(
        ProjectApplyPatchTool(),
        {"diff": diff},
        _ctx(project),
    )
    assert result.success, result.error
    files = result.data["files"]
    assert files == [
        {"path": "src/new_module.py", "is_new": True, "is_deleted": False}
    ]
    assert (project / "src" / "new_module.py").read_text(encoding="utf-8").startswith(
        "CONST = 7"
    )


@pytest.mark.asyncio
async def test_project_shell_runs_python(project: Path) -> None:
    """Curated shell can execute ``python -c`` inside the project root."""
    from leagent.tools.project.shell import ProjectShellTool

    result = await _run(
        ProjectShellTool(),
        {
            "argv": ["python", "-c", "print('ok'); import os; print(os.getcwd())"],
            "timeout_sec": 30,
        },
        _ctx(project),
    )
    assert result.success, result.error
    data = result.data
    assert data["returncode"] == 0
    assert "ok" in data["stdout"]
    # cwd line must reside inside the project root.
    cwd_line = data["stdout"].strip().splitlines()[-1]
    assert str(project) in cwd_line or cwd_line == str(project)


@pytest.mark.asyncio
async def test_project_shell_blocks_unknown_binary(
    project: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Curated argv rejects unknown binaries when free-shell mode is off."""
    monkeypatch.setenv("LEAGENT_CODING_AGENT_FREE_SHELL", "0")
    from leagent.tools.project.shell import ProjectShellTool

    result = await _run(
        ProjectShellTool(),
        {"argv": ["definitely_not_real_42"]},
        _ctx(project),
    )
    assert not result.success
    assert result.data is not None
    assert "whitelist" in (result.error or "").lower() or "whitelist" in str(
        result.data.get("error") or ""
    ).lower()


@pytest.mark.asyncio
async def test_project_outline_single_file(project: Path) -> None:
    from leagent.tools.project.outline import ProjectOutlineTool

    result = await _run(
        ProjectOutlineTool(),
        {"path": "src/app.py"},
        _ctx(project),
    )
    assert result.success, result.error
    files = result.data["files"]
    assert len(files) == 1
    f0 = files[0]
    assert f0["path"] == "src/app.py"
    assert f0["language"] == "python"
    names = {s["name"] for s in f0["symbols"]}
    assert "greet" in names


@pytest.mark.asyncio
async def test_project_outline_syntax_error(project: Path) -> None:
    from leagent.tools.project.outline import ProjectOutlineTool

    (project / "broken.py").write_text("def x(\n", encoding="utf-8")
    result = await _run(
        ProjectOutlineTool(),
        {"path": "broken.py"},
        _ctx(project),
    )
    assert result.success, result.error
    f0 = result.data["files"][0]
    assert f0.get("parse_error")


@pytest.mark.asyncio
async def test_project_outline_root_glob(project: Path) -> None:
    from leagent.tools.project.outline import ProjectOutlineTool

    result = await _run(
        ProjectOutlineTool(),
        {"glob": "**/*.py", "max_files": 10},
        _ctx(project),
    )
    assert result.success, result.error
    paths = {f["path"] for f in result.data["files"]}
    assert "src/app.py" in paths
    assert "tests/test_app.py" in paths


@pytest.mark.asyncio
async def test_project_write_content_blob_id(project: Path) -> None:
    from leagent.tools.project.write import ProjectWriteTool
    from leagent.tools.util.tool_argument_blob import ToolArgumentBlobTool

    ctx = _ctx(project)
    blob_tool = ToolArgumentBlobTool()
    created = await _run(blob_tool, {"action": "create"}, ctx)
    assert created.success, created.error
    bid = created.data["blob_id"]
    assert isinstance(bid, str) and bid
    await _run(
        blob_tool,
        {"action": "append", "blob_id": bid, "chunk": "alpha\nbeta\n"},
        ctx,
    )
    fin = await _run(blob_tool, {"action": "finalize", "blob_id": bid}, ctx)
    assert fin.data.get("ok") is True

    write = ProjectWriteTool()
    res = await _run(
        write,
        {"path": "staged.txt", "content_blob_id": bid},
        ctx,
    )
    assert res.success, res.error
    assert (project / "staged.txt").read_text(encoding="utf-8") == "alpha\nbeta\n"


@pytest.mark.asyncio
async def test_project_edit_old_string_blob_id(project: Path) -> None:
    from leagent.tools.project.edit import ProjectEditTool
    from leagent.tools.util.tool_argument_blob import ToolArgumentBlobTool

    ctx = _ctx(project)
    blob_tool = ToolArgumentBlobTool()
    bid = (await _run(blob_tool, {"action": "create"}, ctx)).data["blob_id"]
    await _run(
        blob_tool,
        {"action": "append", "blob_id": bid, "chunk": "def greet(name: str) -> str:"},
        ctx,
    )
    await _run(blob_tool, {"action": "finalize", "blob_id": bid}, ctx)

    edit = ProjectEditTool()
    res = await _run(
        edit,
        {
            "path": "src/app.py",
            "old_string_blob_id": bid,
            "new_string": "def greet(name: str) -> str:  #patched",
        },
        ctx,
    )
    assert res.success, res.error
    text = (project / "src" / "app.py").read_text(encoding="utf-8")
    assert "#patched" in text


@pytest.mark.asyncio
async def test_project_apply_patch_diff_blob_id(project: Path) -> None:
    from leagent.tools.project.patch import ProjectApplyPatchTool
    from leagent.tools.util.tool_argument_blob import ToolArgumentBlobTool

    diff = (
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1,2 +1,2 @@\n"
        "-def greet(name: str) -> str:\n"
        "+def greet(name: str) -> str:  #via_blob_patch\n"
        "     return f\"hello {name}\"\n"
    )
    ctx = _ctx(project)
    blob_tool = ToolArgumentBlobTool()
    bid = (await _run(blob_tool, {"action": "create"}, ctx)).data["blob_id"]
    await _run(blob_tool, {"action": "append", "blob_id": bid, "chunk": diff}, ctx)
    await _run(blob_tool, {"action": "finalize", "blob_id": bid}, ctx)

    patch = ProjectApplyPatchTool()
    res = await _run(patch, {"diff_blob_id": bid}, ctx)
    assert res.success, res.error
    assert "#via_blob_patch" in (project / "src" / "app.py").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_tool_argument_blob_append_chunk_base64_html(project: Path) -> None:
    import base64

    from leagent.tools.project.write import ProjectWriteTool
    from leagent.tools.util.tool_argument_blob import ToolArgumentBlobTool

    ctx = _ctx(project)
    blob_tool = ToolArgumentBlobTool()
    bid = (await _run(blob_tool, {"action": "create"}, ctx)).data["blob_id"]
    html = '<!DOCTYPE html><html lang="zh-CN"><body id="q">a"b\'c</body></html>'
    b64 = base64.standard_b64encode(html.encode("utf-8")).decode("ascii")
    res = await _run(
        blob_tool,
        {"action": "append", "blob_id": bid, "chunk_base64": b64},
        ctx,
    )
    assert res.success and res.data.get("ok") is True
    await _run(blob_tool, {"action": "finalize", "blob_id": bid}, ctx)
    wr = await _run(
        ProjectWriteTool(),
        {"path": "page.html", "content_blob_id": bid},
        ctx,
    )
    assert wr.success, wr.error
    assert (project / "page.html").read_text(encoding="utf-8") == html


@pytest.mark.asyncio
async def test_tool_argument_blob_chunk_base64_wins_over_chunk(project: Path) -> None:
    import base64

    from leagent.tools.project.write import ProjectWriteTool
    from leagent.tools.util.tool_argument_blob import ToolArgumentBlobTool

    ctx = _ctx(project)
    blob_tool = ToolArgumentBlobTool()
    bid = (await _run(blob_tool, {"action": "create"}, ctx)).data["blob_id"]
    want = "from-base64-layer"
    b64 = base64.standard_b64encode(want.encode()).decode("ascii")
    res = await _run(
        blob_tool,
        {
            "action": "append",
            "blob_id": bid,
            "chunk": "plain-wrong",
            "chunk_base64": b64,
        },
        ctx,
    )
    assert res.success and res.data.get("ok") is True
    await _run(blob_tool, {"action": "finalize", "blob_id": bid}, ctx)
    wr = await _run(
        ProjectWriteTool(),
        {"path": "winner.txt", "content_blob_id": bid},
        ctx,
    )
    assert wr.success, wr.error
    assert (project / "winner.txt").read_text(encoding="utf-8") == want


@pytest.mark.asyncio
async def test_tool_argument_blob_append_invalid_base64(project: Path) -> None:
    from leagent.tools.util.tool_argument_blob import ToolArgumentBlobTool

    ctx = _ctx(project)
    blob_tool = ToolArgumentBlobTool()
    bid = (await _run(blob_tool, {"action": "create"}, ctx)).data["blob_id"]
    res = await _run(
        blob_tool,
        {"action": "append", "blob_id": bid, "chunk_base64": "not-valid-base64!!!"},
        ctx,
    )
    assert res.success
    assert res.data.get("ok") is False
    assert "base64" in (res.data.get("error") or "").lower()


# ---------------------------------------------------------------------------
# services/coding_projects/paths.validate_project_path
# ---------------------------------------------------------------------------


def test_validate_project_path_accepts_existing_dir(project: Path) -> None:
    """A real directory resolves cleanly when no allow-list is set."""
    from leagent.services.coding_projects import validate_project_path

    resolved = validate_project_path(str(project))
    assert resolved == project.resolve()


def test_validate_project_path_rejects_missing(tmp_path: Path) -> None:
    """A path that doesn't exist must not pass."""
    from leagent.services.coding_projects import (
        ProjectPathSafetyError,
        validate_project_path,
    )

    ghost = tmp_path / "does-not-exist"
    with pytest.raises(ProjectPathSafetyError):
        validate_project_path(str(ghost))


def test_validate_project_path_rejects_relative(tmp_path: Path) -> None:
    from leagent.services.coding_projects import (
        ProjectPathSafetyError,
        validate_project_path,
    )

    with pytest.raises(ProjectPathSafetyError):
        validate_project_path("relative/path")


def test_validate_project_path_honours_allowed_roots(
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A path outside ``FILES_PROJECTS_ALLOWED_ROOTS`` is rejected."""
    from leagent.services.coding_projects import paths as safety_mod
    from leagent.services.coding_projects import (
        ProjectPathSafetyError,
        validate_project_path,
    )

    sentinel_root = tmp_path / "sentinel-root"
    sentinel_root.mkdir()
    inner = sentinel_root / "inner"
    inner.mkdir()

    # Stub the live setting so we don't depend on the test env.
    monkeypatch.setattr(
        safety_mod,
        "get_allowed_project_roots",
        lambda: (sentinel_root.resolve(),),
    )

    # Inside the allowed root → ok.
    assert validate_project_path(str(inner)) == inner.resolve()

    # Outside the allowed root → rejected.
    with pytest.raises(ProjectPathSafetyError):
        validate_project_path(str(project))


@pytest.mark.asyncio
async def test_tool_argument_blob_blob_disk_path_and_discard(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    project: Path,
) -> None:
    """Regression: _blob_disk_path must resolve upload_dir; discard always checks disk."""
    from leagent.tools.util.tool_argument_blob import (
        ToolArgumentBlobTool,
        _blob_disk_path,
    )

    fake_files = SimpleNamespace(upload_dir=str(tmp_path))
    fake_settings = SimpleNamespace(files=fake_files)
    monkeypatch.setattr("leagent.config.settings.get_settings", lambda: fake_settings)

    sid = "s-blob-disk"
    bid = "a" * 32
    resolved = _blob_disk_path(sid, bid)
    assert resolved is not None
    assert resolved == (tmp_path / "tool-argument-blobs" / sid / f"{bid}.bin").resolve()

    ctx = _ctx(project)
    tool = ToolArgumentBlobTool()
    created = await _run(tool, {"action": "create"}, ctx)
    assert created.success, created.error
    blob_id = str(created.data["blob_id"])
    discarded = await _run(
        tool,
        {"action": "discard", "blob_id": blob_id},
        ctx,
    )
    assert discarded.success, discarded.error
    assert discarded.data.get("ok") is True
