"""Emoji font resolution + PDF markup switching tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from leagent.docgen.fonts import FONT_MANIFEST, FontManager, PDF_FONT_EMOJI
from leagent.docgen.renderers.pdf import (
    apply_emoji_font,
    spans_to_markup,
    text_contains_emoji,
)


def test_text_contains_emoji() -> None:
    assert text_contains_emoji("hello 😀") is True
    assert text_contains_emoji("✅ done") is True
    assert text_contains_emoji("纯中文与 English") is False
    assert text_contains_emoji("") is False


def test_apply_emoji_font_wraps_runs() -> None:
    out = apply_emoji_font("状态 ✅ 完成 🎉", "LeAgentDocEmoji")
    assert 'face="LeAgentDocEmoji"' in out
    assert "✅" in out and "🎉" in out
    assert out.startswith("状态 ")
    assert apply_emoji_font("😀", None) == "😀"


def test_spans_to_markup_nests_emoji_inside_styles() -> None:
    from leagent.docgen.markdown import parse_inline

    markup = spans_to_markup(
        parse_inline("**重要 🚀** and `code ✅`"),
        mono_font="Mono",
        emoji_font="Emo",
    )
    assert "<b>" in markup and "</b>" in markup
    assert 'face="Emo"' in markup
    assert "🚀" in markup and "✅" in markup


def test_resolve_emoji_env_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    font = tmp_path / "MyEmoji.ttf"
    font.write_bytes(b"x")
    monkeypatch.setenv("LEAGENT_EMOJI_FONT", str(font))

    path, warnings = FontManager(fonts_dir=tmp_path / "managed").resolve_emoji(
        allow_download=False
    )
    assert path == str(font)
    assert warnings == []


def test_resolve_emoji_rejects_color_font(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    color = tmp_path / "NotoColorEmoji.ttf"
    color.write_bytes(b"x")
    monkeypatch.setenv("LEAGENT_EMOJI_FONT", str(color))

    path, warnings = FontManager(fonts_dir=tmp_path / "managed").resolve_emoji(
        allow_download=False
    )
    assert path is None
    assert any("color emoji" in w for w in warnings)


def test_resolve_emoji_managed_dir(tmp_path: Path) -> None:
    managed = tmp_path / "managed"
    managed.mkdir()
    emoji = managed / FONT_MANIFEST["emoji"].filename
    emoji.write_bytes(b"x")

    path, _ = FontManager(fonts_dir=managed).resolve_emoji(allow_download=False)
    assert path == str(emoji)


def test_register_and_render_pdf_emoji(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Emoji face embeds and round-trips through PDF text extraction."""
    fitz = pytest.importorskip("fitz")
    from leagent.docgen.model import DocumentSpec
    from leagent.docgen.renderers import pdf as pdf_mod

    managed = tmp_path / "fonts"
    mgr = FontManager(fonts_dir=managed)
    emoji_path, emoji_warnings = mgr.resolve_emoji(allow_download=True)
    if not emoji_path:
        pytest.skip(f"emoji font unavailable: {emoji_warnings}")

    fonts = mgr.register_pdf_fonts(allow_download=True)
    assert fonts["emoji"] == PDF_FONT_EMOJI
    assert fonts["emoji_embedded"] is True

    monkeypatch.setattr(pdf_mod, "get_font_manager", lambda: mgr)
    monkeypatch.delenv("LEAGENT_EMOJI_FONT", raising=False)

    out = tmp_path / "emoji.pdf"
    result = pdf_mod.render_pdf(
        DocumentSpec.model_validate(
            {
                "title": "Emoji check",
                "blocks": [
                    {
                        "type": "paragraph",
                        "text": "完成 ✅ 庆祝 🎉 启动 🚀",
                    }
                ],
            }
        ),
        out,
    )
    assert result["success"] is True
    assert result["emoji_embedded"] is True

    doc = fitz.open(str(out))
    text = "".join(page.get_text() for page in doc)
    font_names = {f[3] for page in doc for f in page.get_fonts()}
    doc.close()
    assert "完成" in text
    # At least one emoji glyph should survive extraction.
    assert any(ch in text for ch in ("✅", "🎉", "🚀"))
    assert any(
        "Emoji" in name or "emoji" in name.lower() for name in font_names
    )
