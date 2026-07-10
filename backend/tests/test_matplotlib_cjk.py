"""Tests for matplotlib CJK auto-configuration in code_execution."""

from __future__ import annotations

import time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def test_resolve_cjk_regular_path_env_priority(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from leagent.utils import cjk_font_discovery as mod

    p = tmp_path / "custom.otf"
    p.write_bytes(b"x")
    monkeypatch.delenv("LEAGENT_CJK_FONT", raising=False)
    assert mod.resolve_cjk_regular_path(explicit=str(p)) == str(p)


def test_discover_cjk_font_file_caches_result(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from leagent.utils import cjk_font_discovery as mod

    mod.clear_cjk_font_discovery_cache()
    font_dir = tmp_path / "fonts" / "noto"
    font_dir.mkdir(parents=True)
    font_path = font_dir / "NotoSansSC-Regular.otf"
    font_path.write_bytes(b"x")
    monkeypatch.setattr(mod, "cjk_font_search_roots", lambda: [str(tmp_path / "fonts")])

    assert mod.discover_cjk_font_file(is_bold=False) == str(font_path)
    font_path.unlink()
    assert mod.discover_cjk_font_file(is_bold=False) == str(font_path)

    mod.clear_cjk_font_discovery_cache()
    assert mod.discover_cjk_font_file(is_bold=False) is None


def test_build_cjk_generation_turn_extra_for_document_tool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from leagent.utils import cjk_font_discovery as mod

    class Tools:
        def __init__(self, names: set[str]) -> None:
            self.names = names

        def has(self, name: str) -> bool:
            return name in self.names

    regular = tmp_path / "regular.otf"
    regular.write_bytes(b"x")
    monkeypatch.setattr(mod, "resolve_cjk_regular_path", lambda **_: str(regular))
    monkeypatch.setattr(mod, "resolve_cjk_bold_path", lambda **_: None)

    assert mod.build_cjk_generation_turn_extra(tools=Tools(set())) == ""
    # document_generate / slides_generate handle fonts internally — no hint.
    assert mod.build_cjk_generation_turn_extra(tools=Tools({"document_generate"})) == ""
    extra = mod.build_cjk_generation_turn_extra(tools=Tools({"chart_generator"}))
    assert str(regular) in extra
    assert "python-docx/python-pptx" in extra
    assert "document_generate" in extra


@pytest.mark.asyncio
async def test_subprocess_sandbox_passes_resolved_cjk_font_env(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    from leagent.code import sandbox as mod
    from leagent.code.workspace import Workspace

    font_path = tmp_path / "NotoSansSC-Regular.otf"
    font_path.write_bytes(b"x")
    captured: dict[str, object] = {}

    class Engine:
        async def python_sandbox(self, *args, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                produced_files=[],
                status="ok",
                stdout="",
                stderr="",
                metadata={},
                error=None,
                duration_ms=1,
                returncode=0,
            )

    monkeypatch.setattr(mod, "resolve_cjk_regular_path", lambda **_: str(font_path))
    monkeypatch.setattr(mod, "get_execution_engine", lambda: Engine())

    sandbox = mod.SubprocessSandbox()
    workspace = Workspace(root=tmp_path / "workspace", session_id="s1", created_at=time.time())
    result = await sandbox.execute("result = 1", workspace=workspace)

    assert result.ok is True
    policy = captured["policy"]
    env = policy.sanitized_env()  # type: ignore[attr-defined]
    assert env["LEAGENT_CJK_FONT"] == str(font_path)


def test_configure_matplotlib_cjk_no_font_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from leagent.code import matplotlib_cjk as mpl_cjk

    mpl_cjk.reset_matplotlib_cjk_configured_for_tests()
    # Patch where used: matplotlib_cjk binds resolve_cjk_regular_path at import time.
    monkeypatch.setattr(mpl_cjk, "resolve_cjk_regular_path", lambda **_: None)
    assert mpl_cjk.configure_matplotlib_cjk() is False


def test_configure_matplotlib_cjk_sets_rcparams(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    from leagent.code import matplotlib_cjk as mpl_cjk

    mpl_cjk.reset_matplotlib_cjk_configured_for_tests()
    font_path = tmp_path / "fake.otf"
    font_path.write_bytes(b"\0" * 16)
    monkeypatch.setattr(
        mpl_cjk,
        "resolve_cjk_regular_path",
        lambda **_: str(font_path),
    )

    import matplotlib

    matplotlib.use("Agg", force=True)

    with patch("matplotlib.font_manager.fontManager.addfont") as addfont_mock:
        with patch("matplotlib.font_manager.FontProperties") as fp_cls:
            fp_inst = MagicMock()
            fp_inst.get_name.return_value = "Noto Sans SC"
            fp_cls.return_value = fp_inst
            assert mpl_cjk.configure_matplotlib_cjk() is True
            addfont_mock.assert_called_once_with(str(font_path))

    import matplotlib.pyplot as plt

    assert plt.rcParams["axes.unicode_minus"] is False
    assert plt.rcParams["font.sans-serif"][0] == "Noto Sans SC"

    assert mpl_cjk.configure_matplotlib_cjk() is True
    mpl_cjk.reset_matplotlib_cjk_configured_for_tests()
