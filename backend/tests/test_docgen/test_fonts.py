"""FontManager resolution-order and download-integrity tests (network mocked)."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from leagent.docgen import fonts as fonts_mod
from leagent.docgen.fonts import FONT_MANIFEST, FontManager


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("LEAGENT_CJK_FONT", raising=False)
    monkeypatch.delenv("LEAGENT_CJK_FONT_BOLD", raising=False)
    monkeypatch.delenv("LEAGENT_FONT_AUTO_DOWNLOAD", raising=False)


def _no_system_fonts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fonts_mod, "discover_cjk_font_file", lambda *, is_bold: None
    )


def test_env_override_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    font = tmp_path / "custom.ttf"
    font.write_bytes(b"x")
    monkeypatch.setenv("LEAGENT_CJK_FONT", str(font))

    resolved = FontManager(fonts_dir=tmp_path / "managed").resolve(allow_download=False)
    assert resolved.source == "env"
    assert resolved.regular_path == str(font)


def test_env_override_missing_file_warns_and_falls_through(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("LEAGENT_CJK_FONT", str(tmp_path / "missing.ttf"))
    _no_system_fonts(monkeypatch)

    resolved = FontManager(fonts_dir=tmp_path / "managed").resolve(allow_download=False)
    assert resolved.source == "none"
    assert any("missing file" in w for w in resolved.warnings)


def test_managed_dir_preferred_over_system(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    managed_dir = tmp_path / "managed"
    managed_dir.mkdir()
    managed = managed_dir / FONT_MANIFEST["regular"].filename
    managed.write_bytes(b"x")
    monkeypatch.setattr(
        fonts_mod, "discover_cjk_font_file", lambda *, is_bold: "/sys/font.ttf"
    )

    resolved = FontManager(fonts_dir=managed_dir).resolve(allow_download=False)
    assert resolved.source == "managed"
    assert resolved.regular_path == str(managed)


def test_system_scan_used_when_no_managed(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    sys_font = tmp_path / "NotoSansSC-Regular.ttf"
    sys_font.write_bytes(b"x")
    monkeypatch.setattr(
        fonts_mod,
        "discover_cjk_font_file",
        lambda *, is_bold: None if is_bold else str(sys_font),
    )

    resolved = FontManager(fonts_dir=tmp_path / "managed").resolve(allow_download=False)
    assert resolved.source == "system"
    assert resolved.regular_path == str(sys_font)
    assert resolved.bold_path is None


def test_auto_download_last_resort(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _no_system_fonts(monkeypatch)
    managed_dir = tmp_path / "managed"
    mgr = FontManager(fonts_dir=managed_dir)

    def fake_download(asset, *, warnings):
        managed_dir.mkdir(parents=True, exist_ok=True)
        target = managed_dir / asset.filename
        target.write_bytes(b"fake-font")
        return str(target)

    monkeypatch.setattr(mgr, "_download_asset", fake_download)

    resolved = mgr.resolve(allow_download=True)
    assert resolved.source == "downloaded"
    assert resolved.regular_path == str(managed_dir / FONT_MANIFEST["regular"].filename)
    assert resolved.bold_path == str(managed_dir / FONT_MANIFEST["bold"].filename)


def test_auto_download_disabled_warns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _no_system_fonts(monkeypatch)
    monkeypatch.setenv("LEAGENT_FONT_AUTO_DOWNLOAD", "0")

    resolved = FontManager(fonts_dir=tmp_path / "managed").resolve(allow_download=True)
    assert resolved.source == "none"
    assert any("auto-download is disabled" in w for w in resolved.warnings)


def test_download_sha256_mismatch_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-the-pinned-bytes")

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client

    def patched_client(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=transport, **kwargs)

    monkeypatch.setattr(httpx, "Client", patched_client)

    mgr = FontManager(fonts_dir=tmp_path / "managed")
    warnings: list[str] = []
    path = mgr._download_asset(FONT_MANIFEST["regular"], warnings=warnings)
    assert path is None
    assert any("integrity" in w or "download" in w for w in warnings)
    assert not (tmp_path / "managed" / FONT_MANIFEST["regular"].filename).exists()


def test_download_sha256_match_accepted(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import httpx

    from leagent.docgen.fonts import FontAsset

    body = b"pinned-font-bytes"
    asset = FontAsset(
        filename="Fake-Regular.ttf",
        urls=("https://example.invalid/fake.ttf",),
        sha256=hashlib.sha256(body).hexdigest(),
        size_bytes=len(body),
    )

    transport = httpx.MockTransport(lambda req: httpx.Response(200, content=body))
    real_client = httpx.Client
    monkeypatch.setattr(
        httpx, "Client", lambda **kw: real_client(transport=transport, **kw)
    )

    mgr = FontManager(fonts_dir=tmp_path / "managed")
    warnings: list[str] = []
    path = mgr._download_asset(asset, warnings=warnings)
    assert path is not None
    assert Path(path).read_bytes() == body
    assert warnings == []


def test_resolve_caches_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    font = tmp_path / "custom.ttf"
    font.write_bytes(b"x")
    monkeypatch.setenv("LEAGENT_CJK_FONT", str(font))

    mgr = FontManager(fonts_dir=tmp_path / "managed")
    first = mgr.resolve(allow_download=False)
    monkeypatch.delenv("LEAGENT_CJK_FONT")
    second = mgr.resolve(allow_download=False)
    assert second is first
    assert mgr.resolve(allow_download=False, refresh=True).source != "env"


def test_office_east_asia_font_name() -> None:
    assert FontManager.office_east_asia_font() == "Microsoft YaHei"
