"""Extension pack install should invoke Playwright CLI for the browser pack."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture()
def isolated_extensions(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    reg = tmp_path / "official_registry.json"
    reg.write_text(
        """{
  "version": 1,
  "packs": [
    {
      "id": "browser",
      "name": "Browser automation",
      "description": "test",
      "extras": ["browser"],
      "uninstall_packages": ["playwright"],
      "playwright_install": ["chromium"],
      "playwright_install_deps": false
    }
  ]
}""",
        encoding="utf-8",
    )
    monkeypatch.setattr("leagent.extensions.manager._REGISTRY_PATH", reg)
    monkeypatch.setattr("leagent.extensions.manager._INSTALLED_PATH", tmp_path / "installed.json")
    return tmp_path


def test_browser_pack_triggers_playwright_install(monkeypatch: pytest.MonkeyPatch, isolated_extensions: Path) -> None:
    from leagent.extensions import manager as mgr_mod

    calls: list[list[str]] = []

    def fake_run(cmd: list[str], **kwargs: object) -> MagicMock:
        calls.append(list(cmd))
        m = MagicMock()
        m.returncode = 0
        m.stdout = "ok\n"
        m.stderr = ""
        return m

    monkeypatch.setattr(mgr_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(mgr_mod.shutil, "which", lambda _: "/fake/uv")

    mgr = mgr_mod.ExtensionManager()
    out = mgr.install_pack("browser")

    assert out.get("ok") is True
    assert out.get("playwright_install_ok") is True
    assert out.get("needs_backend_restart") is False
    assert any("playwright" in c and "install" in c for c in calls), calls


def test_normalize_focus_arxiv_id() -> None:
    from leagent.tools.web.web_search.core import _normalize_focus

    assert _normalize_focus("2401.12345", "auto") == "arxiv"
    assert _normalize_focus("arxiv:2401.12345", "auto") == "arxiv"
    assert _normalize_focus("machine learning survey", "auto") == "general"
    assert _normalize_focus("anything", "wikipedia") == "wikipedia"
