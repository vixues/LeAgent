"""Path resolution smoke tests for unrestricted desktop mode.

Strict sandbox denial tests live in ``test_path_sandbox.py`` (skipped); local
builds use ``PathSandbox.resolve_safe`` without deny-lists.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Iterator

import pytest

from leagent.tools._sandbox.paths import PathSandbox, reset_roots
from leagent.tools.base import ToolContext


@pytest.fixture(autouse=True)
def _restore_sandbox_env() -> Iterator[None]:
    saved = {
        key: os.environ.get(key)
        for key in (
            "LEAGENT_TOOL_FILE_ROOTS",
            "LEAGENT_FILES_UPLOAD_DIR",
            "FILES_UPLOAD_DIR",
            "OPENCLAW_HOME",
            "HOME",
        )
    }
    try:
        yield
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        reset_roots()


def _ctx(session_id: str = "s-desktop") -> ToolContext:
    return ToolContext(user_id="u1", session_id=session_id)


def test_empty_path_rejected() -> None:
    with pytest.raises(PermissionError, match="Empty path"):
        PathSandbox.resolve_safe("  ", context=_ctx())


def test_dot_resolves_to_directory() -> None:
    """``'.'`` may resolve via upload/session layout; must be an absolute directory."""
    p = PathSandbox.resolve_safe(".", context=_ctx())
    assert p.is_absolute() and p.is_dir()


def test_absolute_existing_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEAGENT_TOOL_FILE_ROOTS", str(tmp_path))
    reset_roots()
    f = tmp_path / "x.txt"
    f.write_text("ok", encoding="utf-8")
    got = PathSandbox.resolve_safe(str(f), context=_ctx())
    assert got == f.resolve()


def test_is_safe_true_for_readable_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEAGENT_TOOL_FILE_ROOTS", str(tmp_path))
    reset_roots()
    f = tmp_path / "y.txt"
    f.write_text("y", encoding="utf-8")
    assert PathSandbox.is_safe(str(f), context=_ctx())


def test_openclaw_home_is_supported_local_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LEAGENT_TOOL_FILE_ROOTS", raising=False)
    openclaw_home = tmp_path / ".openclaw"
    monkeypatch.setenv("OPENCLAW_HOME", str(openclaw_home))
    reset_roots()
    config = openclaw_home / "openclaw.json"
    config.parent.mkdir(parents=True)
    config.write_text('{"skills":{"entries":{}}}', encoding="utf-8")

    got = PathSandbox.resolve_safe(str(config), context=_ctx())

    assert got == config.resolve()


def test_tilde_openclaw_path_uses_home_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root = tmp_path / "allowed"
    upload_root = tmp_path / "uploads"
    home = tmp_path / "home"
    config = home / ".openclaw" / "openclaw.json"
    allowed_root.mkdir()
    config.parent.mkdir(parents=True)
    config.write_text('{"skills":{"entries":{}}}', encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("OPENCLAW_HOME", raising=False)
    monkeypatch.setenv("LEAGENT_TOOL_FILE_ROOTS", str(allowed_root))
    monkeypatch.setenv("LEAGENT_FILES_UPLOAD_DIR", str(upload_root))
    reset_roots()

    got = PathSandbox.resolve_safe(
        "~/.openclaw/openclaw.json",
        context=_ctx("s-openclaw"),
        allow_create=False,
    )

    assert got == config.resolve()
    assert upload_root.resolve() not in got.parents


def test_allow_create_relative_does_not_reuse_attachment_alias(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEAGENT_TOOL_FILE_ROOTS", str(tmp_path))
    monkeypatch.setenv("LEAGENT_FILES_UPLOAD_DIR", str(tmp_path))
    reset_roots()
    session_id = "s-copy"
    session_dir = tmp_path / session_id
    session_dir.mkdir()
    existing = session_dir / "1f60b93c-1aa4-4466-8139-a9a0f81154bd_sine_wave_animation.gif"
    existing.write_text("existing", encoding="utf-8")
    ctx = _ctx(session_id=session_id)
    ctx.extra["attachments"] = [str(existing)]
    ctx.extra["attachment_lookup"] = {
        "by_name": {"sinewaveanimationgif": str(existing)},
    }

    got = PathSandbox.resolve_safe(
        "sine_wave_animation.gif",
        context=ctx,
        allow_create=True,
    )

    assert got.name == "sine_wave_animation.gif"
    assert got.parent.name == session_id
    assert got != existing.resolve()


@pytest.mark.parametrize(
    "filename",
    [
        "test_presentation.pptx",
        "test_document.pdf",
        "test_document.docx",
        "test_workbook.xlsx",
    ],
)
def test_temp_output_path_reroutes_to_session_workspace(
    filename: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root = tmp_path / "allowed"
    upload_root = tmp_path / "uploads"
    allowed_root.mkdir()
    monkeypatch.setenv("LEAGENT_TOOL_FILE_ROOTS", str(allowed_root))
    monkeypatch.setenv("LEAGENT_FILES_UPLOAD_DIR", str(upload_root))
    reset_roots()

    session_id = "s-generated"
    raw_output = str(Path(tempfile.gettempdir()) / filename)

    got = PathSandbox.resolve_safe(
        raw_output,
        context=_ctx(session_id=session_id),
        allow_create=True,
    )

    assert got == (upload_root / session_id / filename).resolve()
    assert got.parent.is_dir()


def test_bare_output_filename_resolves_to_session_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root = tmp_path / "allowed"
    upload_root = tmp_path / "uploads"
    allowed_root.mkdir()
    monkeypatch.setenv("LEAGENT_TOOL_FILE_ROOTS", str(allowed_root))
    monkeypatch.setenv("LEAGENT_FILES_UPLOAD_DIR", str(upload_root))
    reset_roots()

    got = PathSandbox.resolve_safe(
        "report.docx",
        context=_ctx(session_id="s-bare-output"),
        allow_create=True,
    )

    assert got == (upload_root / "s-bare-output" / "report.docx").resolve()


def test_unsafe_absolute_output_path_still_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    allowed_root = tmp_path / "allowed"
    upload_root = tmp_path / "uploads"
    allowed_root.mkdir()
    monkeypatch.setenv("LEAGENT_TOOL_FILE_ROOTS", str(allowed_root))
    monkeypatch.setenv("LEAGENT_FILES_UPLOAD_DIR", str(upload_root))
    reset_roots()

    with pytest.raises(PermissionError, match="outside the allowed sandbox"):
        PathSandbox.resolve_safe(
            "/etc/test_document.pdf",
            context=_ctx(session_id="s-reject"),
            allow_create=True,
        )
