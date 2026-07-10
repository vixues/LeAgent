"""Tests for the OS-level sandbox wrapper (bwrap / Seatbelt / degrade)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from leagent.services.execution import os_sandbox
from leagent.services.execution.os_sandbox import (
    MODE_NONE,
    MODE_READ_ONLY,
    MODE_WORKSPACE_WRITE,
    SandboxSpec,
    default_writable_roots,
    resolve_sandbox_mode,
    wrap_argv,
)


@pytest.fixture(autouse=True)
def _reset_probes():
    os_sandbox.reset_probe_cache()
    yield
    os_sandbox.reset_probe_cache()


# ---------------------------------------------------------------------------
# Mode resolution
# ---------------------------------------------------------------------------


def test_resolve_mode_explicit_wins(monkeypatch):
    monkeypatch.setenv("LEAGENT_SANDBOX_MODE", "read-only")
    assert resolve_sandbox_mode("workspace-write") == MODE_WORKSPACE_WRITE


def test_resolve_mode_env_fallback(monkeypatch):
    monkeypatch.setenv("LEAGENT_SANDBOX_MODE", "workspace-write")
    assert resolve_sandbox_mode(None) == MODE_WORKSPACE_WRITE
    assert resolve_sandbox_mode("auto") == MODE_WORKSPACE_WRITE


def test_resolve_mode_legacy_aliases(monkeypatch):
    monkeypatch.delenv("LEAGENT_SANDBOX_MODE", raising=False)
    assert resolve_sandbox_mode("bwrap") == MODE_WORKSPACE_WRITE
    assert resolve_sandbox_mode("ro") == MODE_READ_ONLY
    assert resolve_sandbox_mode("none") == MODE_NONE


def test_resolve_mode_unknown_falls_back(monkeypatch):
    monkeypatch.delenv("LEAGENT_SANDBOX_MODE", raising=False)
    assert resolve_sandbox_mode("martian") == MODE_NONE


def test_spec_rejects_unknown_mode():
    with pytest.raises(ValueError):
        SandboxSpec(mode="martian")


def test_default_writable_roots(tmp_path):
    roots = default_writable_roots(str(tmp_path))
    assert str(tmp_path.resolve()) in roots
    assert len(roots) >= 2  # workspace + tempdir


# ---------------------------------------------------------------------------
# Wrapping / degradation
# ---------------------------------------------------------------------------


def test_wrap_noop_for_mode_none(tmp_path):
    spec = SandboxSpec(mode=MODE_NONE)
    app = wrap_argv(["/bin/echo", "hi"], spec, cwd=str(tmp_path))
    assert app.argv == ["/bin/echo", "hi"]
    assert not app.applied


def test_wrap_degrades_when_bwrap_missing(tmp_path, monkeypatch):
    if not sys.platform.startswith("linux"):
        pytest.skip("linux-only")
    monkeypatch.setattr(os_sandbox, "bwrap_path", lambda: None)
    spec = SandboxSpec(mode=MODE_WORKSPACE_WRITE, writable_roots=(str(tmp_path),))
    app = wrap_argv(["/bin/echo"], spec, cwd=str(tmp_path))
    assert not app.applied
    assert app.argv == ["/bin/echo"]
    assert app.degraded_reasons


def test_wrap_builds_bwrap_argv(tmp_path, monkeypatch):
    if not sys.platform.startswith("linux"):
        pytest.skip("linux-only")
    monkeypatch.setattr(os_sandbox, "bwrap_path", lambda: "/usr/bin/bwrap")
    monkeypatch.setattr(os_sandbox, "probe_bwrap_basic", lambda: True)
    monkeypatch.setattr(os_sandbox, "probe_bwrap_network_isolation", lambda: True)
    spec = SandboxSpec(
        mode=MODE_WORKSPACE_WRITE,
        writable_roots=(str(tmp_path),),
        network_access=False,
    )
    app = wrap_argv(["/bin/echo", "hi"], spec, cwd=str(tmp_path))
    assert app.applied and app.backend == "bwrap"
    assert app.argv[0] == "/usr/bin/bwrap"
    assert "--unshare-net" in app.argv
    assert app.network_isolated
    # writable workspace bound rw
    bind_idx = app.argv.index("--bind")
    assert app.argv[bind_idx + 1] == str(tmp_path)
    # inner command preserved after "--"
    sep = app.argv.index("--")
    assert app.argv[sep + 1:] == ["/bin/echo", "hi"]


def test_wrap_read_only_has_no_workspace_bind(tmp_path, monkeypatch):
    if not sys.platform.startswith("linux"):
        pytest.skip("linux-only")
    monkeypatch.setattr(os_sandbox, "bwrap_path", lambda: "/usr/bin/bwrap")
    monkeypatch.setattr(os_sandbox, "probe_bwrap_basic", lambda: True)
    spec = SandboxSpec(mode=MODE_READ_ONLY, writable_roots=(str(tmp_path),))
    app = wrap_argv(["/bin/true"], spec, cwd=str(tmp_path))
    assert app.applied
    assert "--bind" not in app.argv


def test_wrap_degrades_network_isolation(tmp_path, monkeypatch):
    if not sys.platform.startswith("linux"):
        pytest.skip("linux-only")
    monkeypatch.setattr(os_sandbox, "bwrap_path", lambda: "/usr/bin/bwrap")
    monkeypatch.setattr(os_sandbox, "probe_bwrap_basic", lambda: True)
    monkeypatch.setattr(os_sandbox, "probe_bwrap_network_isolation", lambda: False)
    spec = SandboxSpec(
        mode=MODE_WORKSPACE_WRITE,
        writable_roots=(str(tmp_path),),
        network_access=False,
    )
    app = wrap_argv(["/bin/true"], spec, cwd=str(tmp_path))
    assert app.applied
    assert "--unshare-net" not in app.argv
    assert not app.network_isolated
    assert any("network isolation" in r for r in app.degraded_reasons)


def test_git_dir_stays_read_only(tmp_path, monkeypatch):
    if not sys.platform.startswith("linux"):
        pytest.skip("linux-only")
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(os_sandbox, "bwrap_path", lambda: "/usr/bin/bwrap")
    monkeypatch.setattr(os_sandbox, "probe_bwrap_basic", lambda: True)
    spec = SandboxSpec(mode=MODE_WORKSPACE_WRITE, writable_roots=(str(tmp_path),))
    app = wrap_argv(["/bin/true"], spec, cwd=str(tmp_path))
    git = str(tmp_path / ".git")
    ro_pairs = [
        (app.argv[i + 1], app.argv[i + 2])
        for i, tok in enumerate(app.argv)
        if tok == "--ro-bind"
    ]
    assert (git, git) in ro_pairs


# ---------------------------------------------------------------------------
# Live enforcement (only when bwrap actually works on this host)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="linux-only")
def test_live_bwrap_blocks_out_of_workspace_write(tmp_path):
    if not os_sandbox.probe_bwrap_basic():
        pytest.skip("bwrap unusable on this host")
    import subprocess

    workspace = tmp_path / "ws"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    spec = SandboxSpec(mode=MODE_WORKSPACE_WRITE, writable_roots=(str(workspace),))

    # write inside workspace succeeds
    app = wrap_argv(
        ["/bin/sh", "-c", f"echo ok > {workspace}/f.txt"], spec, cwd=str(workspace),
    )
    assert app.applied
    assert subprocess.run(app.argv, capture_output=True).returncode == 0
    assert (workspace / "f.txt").read_text().strip() == "ok"

    # write outside workspace is blocked by the kernel
    app2 = wrap_argv(
        ["/bin/sh", "-c", f"echo bad > {outside}/f.txt"], spec, cwd=str(workspace),
    )
    assert subprocess.run(app2.argv, capture_output=True).returncode != 0
    assert not (outside / "f.txt").exists()
