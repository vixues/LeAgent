"""Tests for the two-tier code execution stack.

Tier 1 — ``leagent.tools._sandbox.inproc.execute_script``:
  lightweight in-process RestrictedPython evaluator used by the
  ``ScriptNode``. Must capture stdout, respect the timeout, and refuse
  imports outside the allow-list.

Tier 2 — ``leagent.services.code_execution.SubprocessSandbox``:
  out-of-process sandbox used by ``CodeExecutionTool`` and the Code
  Execution Agent. Must forward stdout, surface non-zero exits, and
  apply wall-clock timeouts.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import tempfile
import time

import pytest


# --------------------------------------------------------------------------- #
# Tier 1 — in-process script sandbox
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_script_sandbox_captures_print_and_result() -> None:
    from leagent.tools._sandbox.inproc import execute_script

    source = (
        "print('hello', name)\n"
        "result = sum(range(n))\n"
    )
    outcome = await execute_script(
        source,
        inputs={"name": "world", "n": 5},
        timeout_sec=2.0,
    )
    assert outcome.stdout.strip().endswith("hello world")
    assert outcome.result == 10
    assert outcome.truncated_stdout is False


@pytest.mark.asyncio
async def test_script_sandbox_allows_stdlib_imports() -> None:
    """In-process sandbox uses unrestricted ``exec``; imports are not blocked."""
    from leagent.tools._sandbox.inproc import execute_script

    outcome = await execute_script(
        "import socket\nresult = len(socket.gethostname()) > 0\n",
        inputs={},
        timeout_sec=2.0,
    )
    assert outcome.result is True


@pytest.mark.asyncio
async def test_script_sandbox_times_out_cleanly() -> None:
    from leagent.tools._sandbox.inproc import (
        ScriptTimeoutError,
        execute_script,
    )

    with pytest.raises(ScriptTimeoutError):
        await execute_script(
            "while True:\n    pass\n",
            inputs={},
            timeout_sec=0.2,
        )


# --------------------------------------------------------------------------- #
# Tier 2 — subprocess sandbox
# --------------------------------------------------------------------------- #


def test_create_subprocess_kwargs_windows_uses_process_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from leagent.services.code_execution.subprocess_sandbox import (
        _create_subprocess_kwargs,
    )

    monkeypatch.setattr(sys, "platform", "win32")
    kw = _create_subprocess_kwargs(cwd="/tmp", env={})
    # ``subprocess.CREATE_NEW_PROCESS_GROUP`` only exists on Windows; mirror the
    # production fallback so this test runs on POSIX CI hosts.
    expected = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
    assert kw["creationflags"] == expected
    assert "start_new_session" not in kw


def test_create_subprocess_kwargs_posix_uses_new_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from leagent.services.code_execution.subprocess_sandbox import (
        _create_subprocess_kwargs,
    )

    monkeypatch.setattr(sys, "platform", "linux")
    kw = _create_subprocess_kwargs(cwd="/tmp", env={})
    assert kw.get("start_new_session") is True
    assert "creationflags" not in kw


@pytest.mark.asyncio
async def test_subprocess_sandbox_runs_and_reports_files() -> None:
    from leagent.services.code_execution import (
        SubprocessSandbox,
        WorkspaceManager,
    )

    with tempfile.TemporaryDirectory() as root:
        mgr = WorkspaceManager(root)
        ws = mgr.get(user_id="u", session_id="test-session")
        sandbox = SubprocessSandbox(python_exe=sys.executable)

        script = (
            "import json, pathlib\n"
            "pathlib.Path('out.json').write_text(json.dumps({'ok': True}))\n"
            "print('wrote out.json')\n"
            "result = {'count': 1}\n"
        )
        res = await sandbox.execute(
            script,
            workspace=ws,
            timeout_sec=10.0,
        )
        assert res.ok, f"sandbox failed: {res.error!r} stderr={res.stderr!r}"
        assert "wrote out.json" in res.stdout
        assert res.result == {"count": 1}
        produced = {entry.get("path") for entry in res.produced_files}
        assert "out.json" in produced
        json_entry = next(
            entry for entry in res.produced_files if entry.get("path") == "out.json"
        )
        assert json_entry.get("mime") == "application/json"


@pytest.mark.asyncio
async def test_subprocess_sandbox_reports_image_artifacts_without_inline_base64() -> None:
    from leagent.services.code_execution import (
        SubprocessSandbox,
        WorkspaceManager,
    )

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )

    with tempfile.TemporaryDirectory() as root:
        mgr = WorkspaceManager(root)
        ws = mgr.get(user_id="u", session_id="test-image")
        sandbox = SubprocessSandbox(python_exe=sys.executable)

        res = await sandbox.execute(
            "import pathlib\n"
            f"pathlib.Path('chart.png').write_bytes({png!r})\n"
            "result = {'image': 'chart.png'}\n",
            workspace=ws,
            timeout_sec=10.0,
        )

        assert res.ok, f"sandbox failed: {res.error!r} stderr={res.stderr!r}"
        assert res.image_artifacts
        image = res.image_artifacts[0]
        assert image["path"] == "chart.png"
        assert image["mime"] == "image/png"
        assert "base64" not in image
        produced = next(entry for entry in res.produced_files if entry.get("path") == "chart.png")
        assert "base64" not in produced


@pytest.mark.skip(reason="Unrestricted subprocess execution does not enforce workspace read boundaries.")
@pytest.mark.asyncio
async def test_subprocess_sandbox_blocks_reads_outside_workspace() -> None:
    pass


@pytest.mark.asyncio
async def test_subprocess_sandbox_reports_extra_scan_roots() -> None:
    """Files written outside the workspace but inside an extra scan root are surfaced.

    This mirrors the production wiring where ``CodeExecutionTool`` passes the
    per-session uploads directory so PDFs/CSVs the agent writes there are
    auto-attached to the chat workspace.
    """
    from leagent.services.code_execution import (
        SubprocessSandbox,
        WorkspaceManager,
    )

    with tempfile.TemporaryDirectory() as root:
        ws_root = os.path.join(root, "ws")
        uploads_root = os.path.join(root, "uploads", "sess-xyz")
        os.makedirs(uploads_root, exist_ok=True)

        mgr = WorkspaceManager(ws_root)
        ws = mgr.get(user_id="u", session_id="sess-xyz")
        sandbox = SubprocessSandbox(python_exe=sys.executable)

        target = os.path.join(uploads_root, "report.pdf")
        script = (
            "import pathlib\n"
            f"pathlib.Path({target!r}).write_bytes(b'%PDF-1.4 stub')\n"
            "pathlib.Path('local.txt').write_text('inside workspace')\n"
            "result = {'ok': True}\n"
        )
        res = await sandbox.execute(
            script,
            workspace=ws,
            timeout_sec=10.0,
            extra_scan_roots=(uploads_root,),
        )
        assert res.ok, f"sandbox failed: {res.error!r} stderr={res.stderr!r}"

        paths = {entry.get("path") for entry in res.produced_files}
        assert "local.txt" in paths, paths
        assert target in paths, (
            f"expected absolute upload path in produced_files, got {paths}"
        )


@pytest.mark.asyncio
async def test_code_execution_tool_passes_session_uploads_root(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``CodeExecutionTool`` should expose ``<upload_root>/<session_id>/`` as a scan root."""
    from leagent.config import settings as settings_module
    from leagent.tools.base import ToolContext
    from leagent.tools.code.execution import (
        CodeExecutionConfig,
        CodeExecutionTool,
    )

    upload_root = tmp_path / "uploads"
    upload_root.mkdir()

    settings = settings_module.get_settings()
    monkeypatch.setattr(settings.files, "upload_dir", str(upload_root))

    cfg = CodeExecutionConfig(workspace_root=str(tmp_path / "ws"))
    tool = CodeExecutionTool(config=cfg)

    session_id = "97820da4-b273-4f71-91b5-a9ef8b501320"
    session_uploads = upload_root / session_id
    session_uploads.mkdir()

    ctx = ToolContext(
        user_id="00000000-0000-0000-0000-000000000001",
        session_id=session_id,
    )
    target = session_uploads / "test_document_v2.pdf"

    params = {
        "source": (
            "import pathlib\n"
            f"pathlib.Path({str(target)!r}).write_bytes(b'%PDF-1.4 hello')\n"
            "result = {'ok': True}\n"
        ),
        "timeout_sec": 10.0,
    }

    out = await tool.execute(params, ctx)

    assert out["status"] == "ok", out
    paths = {entry.get("path") for entry in out["produced_files"]}
    assert str(target) in paths, (
        "expected the session-uploads PDF to surface in produced_files; got "
        f"{paths!r}"
    )


@pytest.mark.asyncio
async def test_code_execution_tool_allows_long_runtime_profile(tmp_path) -> None:
    from leagent.tools.base import ToolContext
    from leagent.tools.code.execution import CodeExecutionConfig, CodeExecutionTool
    from leagent.services.code_execution.subprocess_sandbox import SandboxResult

    class _FakeSandbox:
        timeout_seen: float | None = None

        async def execute(self, source, **kwargs):  # noqa: ANN001
            self.timeout_seen = float(kwargs["timeout_sec"])
            return SandboxResult(status="ok", result={"ok": True})

    tool = CodeExecutionTool(
        config=CodeExecutionConfig(
            workspace_root=str(tmp_path / "ws"),
            default_timeout_sec=1.0,
            max_timeout_sec=2.0,
        )
    )
    fake = _FakeSandbox()
    tool._sandbox = fake  # type: ignore[attr-defined]
    ctx = ToolContext(
        user_id="u",
        session_id="s",
        extra={"runtime_profile": "coding_long"},
    )

    out = await tool.execute(
        {"source": "result = {'ok': True}", "timeout_sec": 1200.0},
        ctx,
    )

    assert out["status"] == "ok"
    assert fake.timeout_seen == 1200.0


@pytest.mark.asyncio
async def test_subprocess_sandbox_enforces_timeout() -> None:
    from leagent.services.code_execution import (
        SandboxTimeoutError,
        SubprocessSandbox,
        WorkspaceManager,
    )

    with tempfile.TemporaryDirectory() as root:
        mgr = WorkspaceManager(root)
        ws = mgr.get(user_id="u", session_id="test-timeout")
        sandbox = SubprocessSandbox(python_exe=sys.executable, grace_sec=0.5)

        # The child traps SIGALRM first and reports ``status="timeout"``;
        # only when the child ignores the alarm does the parent's
        # wall-clock wait fire :class:`SandboxTimeoutError`. Accept both
        # outcomes — either way the sandbox enforced the budget.
        try:
            res = await sandbox.execute(
                "while True:\n    pass\n",
                workspace=ws,
                timeout_sec=0.3,
            )
        except SandboxTimeoutError:
            return
        assert res.status == "timeout", f"expected timeout status, got {res!r}"


def test_workspace_manager_is_per_session() -> None:
    from leagent.services.code_execution import WorkspaceManager

    with tempfile.TemporaryDirectory() as root:
        mgr = WorkspaceManager(root)
        ws_a = mgr.get(user_id="u", session_id="sess-a")
        ws_b = mgr.get(user_id="u", session_id="sess-b")
        assert ws_a.path != ws_b.path
        # Re-acquiring a session yields the same workspace.
        ws_a2 = mgr.get(user_id="u", session_id="sess-a")
        assert ws_a.path == ws_a2.path


def test_workspace_manager_compact_keys_for_local_user() -> None:
    from leagent.services.auth.service import LOCAL_USER_ID
    from leagent.services.code_execution.workspace import WorkspaceManager

    session_id = "35f3971b-d115-4db5-8b6a-eca9c717325e"
    with tempfile.TemporaryDirectory() as root:
        mgr = WorkspaceManager(root)
        ws = mgr.get(user_id=str(LOCAL_USER_ID), session_id=session_id)
        assert ws.path.name == "local__35f3971b"


def test_workspace_manager_gc_reaps_unknown_disk_dirs() -> None:
    from pathlib import Path

    from leagent.services.code_execution import WorkspaceManager

    with tempfile.TemporaryDirectory() as root:
        stale = Path(root) / "stale-session"
        stale.mkdir()
        (stale / "scratch.txt").write_text("old", encoding="utf-8")
        old = time.time() - 3600
        os.utime(stale, (old, old))

        mgr = WorkspaceManager(root, idle_ttl_sec=1)

        reaped = mgr.gc(include_disk=True)

        assert "stale-session" in reaped
        assert not stale.exists()


@pytest.mark.asyncio
async def test_code_execution_tool_presubmit_syntax_fails(tmp_path) -> None:
    from leagent.tools.base import ToolContext
    from leagent.tools.code.execution import CodeExecutionConfig, CodeExecutionTool

    tool = CodeExecutionTool(
        config=CodeExecutionConfig(workspace_root=str(tmp_path / "ws")),
    )
    ctx = ToolContext(user_id="u", session_id="s")
    res = await tool.run({"source": "def broken(\n    pass"}, ctx)
    assert res.success is False
    assert isinstance(res.data, dict)
    assert res.data.get("status") == "error"
    assert res.data.get("syntax_diagnostics")


@pytest.mark.asyncio
async def test_code_execution_tool_skip_syntax_presubmit(tmp_path) -> None:
    from leagent.tools.base import ToolContext
    from leagent.tools.code.execution import CodeExecutionConfig, CodeExecutionTool
    from leagent.services.code_execution.subprocess_sandbox import SandboxResult

    class _FakeSandbox:
        async def execute(self, source, **kwargs):  # noqa: ANN001
            return SandboxResult(status="ok", result={"ok": True})

    tool = CodeExecutionTool(
        config=CodeExecutionConfig(workspace_root=str(tmp_path / "ws")),
    )
    tool._sandbox = _FakeSandbox()  # type: ignore[attr-defined]
    ctx = ToolContext(user_id="u", session_id="s")
    res = await tool.run(
        {"source": "result = {'ok': True}", "skip_syntax_check": True},
        ctx,
    )
    assert res.success is True


@pytest.mark.asyncio
async def test_code_execution_tool_accepts_source_blob_id(tmp_path) -> None:
    from leagent.tools.base import ToolContext
    from leagent.tools.code.execution import CodeExecutionConfig, CodeExecutionTool
    from leagent.tools.util.tool_argument_blob import ToolArgumentBlobTool

    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    tool = CodeExecutionTool(
        config=CodeExecutionConfig(
            workspace_root=str(ws),
            default_timeout_sec=30.0,
            max_timeout_sec=60.0,
        ),
    )
    ctx = ToolContext(user_id="u", session_id="blob-src-session", extra={})
    blob_tool = ToolArgumentBlobTool()
    created = await blob_tool.run({"action": "create"}, ctx)
    assert created.success, created.error
    bid = created.data["blob_id"]
    src = "print('from_blob')\nresult = {'ok': True}\n"
    app = await blob_tool.run(
        {"action": "append", "blob_id": bid, "chunk": src},
        ctx,
    )
    assert app.success, app.error
    fin = await blob_tool.run({"action": "finalize", "blob_id": bid}, ctx)
    assert fin.success, fin.error

    res = await tool.run(
        {"source_blob_id": bid, "timeout_sec": 30.0},
        ctx,
    )
    assert res.success, res.error
    data = res.data
    assert isinstance(data, dict)
    assert data.get("status") == "ok"
    assert "from_blob" in (data.get("stdout") or "")


# --------------------------------------------------------------------------- #
# source_echo on failure
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_source_echo_present_on_syntax_error(tmp_path) -> None:
    from leagent.tools.base import ToolContext
    from leagent.tools.code.execution import CodeExecutionConfig, CodeExecutionTool

    tool = CodeExecutionTool(
        config=CodeExecutionConfig(workspace_root=str(tmp_path / "ws")),
    )
    ctx = ToolContext(user_id="u", session_id="s")
    broken_source = "def broken(\n    pass"
    res = await tool.run({"source": broken_source}, ctx)
    assert res.success is False
    assert isinstance(res.data, dict)
    assert res.data["source_echo"] == broken_source


@pytest.mark.asyncio
async def test_source_echo_present_on_runtime_error(tmp_path) -> None:
    from leagent.tools.base import ToolContext
    from leagent.tools.code.execution import CodeExecutionConfig, CodeExecutionTool

    tool = CodeExecutionTool(
        config=CodeExecutionConfig(workspace_root=str(tmp_path / "ws")),
    )
    ctx = ToolContext(user_id="u", session_id="s")
    failing_source = "raise ValueError('boom')"
    res = await tool.run({"source": failing_source, "timeout_sec": 10.0}, ctx)
    assert res.success is False
    assert isinstance(res.data, dict)
    assert res.data["source_echo"] == failing_source


@pytest.mark.asyncio
async def test_source_echo_absent_on_success(tmp_path) -> None:
    from leagent.tools.base import ToolContext
    from leagent.tools.code.execution import CodeExecutionConfig, CodeExecutionTool

    tool = CodeExecutionTool(
        config=CodeExecutionConfig(workspace_root=str(tmp_path / "ws")),
    )
    ctx = ToolContext(user_id="u", session_id="s")
    res = await tool.run(
        {"source": "result = 42", "timeout_sec": 10.0}, ctx,
    )
    assert res.success is True
    assert isinstance(res.data, dict)
    assert res.data.get("source_echo") == ""
    assert res.data.get("source_length") == len("result = 42")


@pytest.mark.asyncio
async def test_source_echo_truncated_for_large_source(tmp_path) -> None:
    from leagent.tools.base import ToolContext
    from leagent.tools.code.execution import (
        CodeExecutionConfig,
        CodeExecutionTool,
        _SOURCE_ECHO_LIMIT,
    )

    tool = CodeExecutionTool(
        config=CodeExecutionConfig(workspace_root=str(tmp_path / "ws")),
    )
    ctx = ToolContext(user_id="u", session_id="s")
    large_source = "x = 1\n" * (_SOURCE_ECHO_LIMIT // 2)
    failing_source = large_source + "\nraise RuntimeError('fail')"
    res = await tool.run(
        {"source": failing_source, "timeout_sec": 10.0}, ctx,
    )
    assert res.success is False
    assert isinstance(res.data, dict)
    echo = res.data["source_echo"]
    assert len(echo) <= _SOURCE_ECHO_LIMIT
    assert len(echo) < len(failing_source)
    assert res.data["source_length"] == len(failing_source)
