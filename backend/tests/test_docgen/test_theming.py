"""Theme generation, contrast lint, and custom-theme store tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from leagent.docgen.themes import (
    Theme,
    get_theme,
    invalidate_custom_theme_cache,
    list_theme_names,
)
from leagent.docgen.theming import (
    contrast_ratio,
    delete_custom_theme,
    derive_theme_payload,
    lint_theme,
    list_custom_themes,
    load_custom_theme_payload,
    save_custom_theme,
)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEAGENT_HOME", str(tmp_path))
    invalidate_custom_theme_cache()
    yield
    invalidate_custom_theme_cache()


# ---------------------------------------------------------------------------
# Color math + derivation
# ---------------------------------------------------------------------------


def test_contrast_ratio_extremes() -> None:
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.1)
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0, abs=0.01)


@pytest.mark.parametrize("primary", ["#1F4E79", "#990011", "#0B5FFF", "#2C5F2D"])
def test_derive_light_theme_is_contrast_safe(primary: str) -> None:
    payload = derive_theme_payload(kind="document", primary=primary, mode="light")
    colors = payload["colors"]
    assert colors["background"] == "#FFFFFF"
    assert contrast_ratio(colors["text"], colors["background"]) >= 4.5
    assert contrast_ratio(colors["text_light"], colors["background"]) >= 3.0
    assert contrast_ratio(colors["primary"], colors["background"]) >= 3.0
    # Full payload resolves through the real theme machinery without lint.
    theme = get_theme(payload, kind="document")
    assert lint_theme(theme) == []


def test_derive_dark_deck_theme() -> None:
    payload = derive_theme_payload(kind="deck", primary="#1E2761", mode="dark")
    assert payload["deck"] == {"dark": True}
    colors = payload["colors"]
    assert colors["text"] == "#FFFFFF"
    assert contrast_ratio(colors["text"], colors["background"]) >= 4.5
    theme = get_theme(payload, kind="deck")
    assert lint_theme(theme) == []


def test_derive_respects_explicit_accent_and_fonts() -> None:
    payload = derive_theme_payload(
        kind="deck",
        primary="#1E2761",
        accent="#F9E795",
        mode="dark",
        heading_font="Georgia",
        east_asia_font="SimHei",
    )
    assert payload["fonts"] == {"heading": "Georgia", "east_asia": "SimHei"}
    # Accent survives (possibly contrast-nudged; hue must be preserved-ish).
    assert payload["colors"]["accent"].startswith("#")


def test_derive_rejects_bad_color() -> None:
    with pytest.raises(ValueError, match="Invalid hex color"):
        derive_theme_payload(kind="document", primary="not-a-color")


def test_lint_flags_bad_theme() -> None:
    bad = Theme.model_validate(
        {
            "name": "bad",
            "colors": {
                "text": "#DDDDDD",  # light gray on white: unreadable
                "background": "#FFFFFF",
                "primary": "#EEEEEE",
            },
        }
    )
    warnings = lint_theme(bad)
    assert any("body text" in w for w in warnings)
    assert any("headings" in w for w in warnings)


# ---------------------------------------------------------------------------
# Store round trip
# ---------------------------------------------------------------------------


def test_save_resolve_delete_custom_theme() -> None:
    payload = derive_theme_payload(kind="document", primary="#1F4E79")
    saved = save_custom_theme("acme_brand", payload, kind="document")
    assert saved["lint_warnings"] == []

    # Resolves by name through the standard resolver + appears in listings.
    theme = get_theme("acme_brand", kind="document")
    assert theme.name == "acme_brand"
    assert theme.colors.primary == payload["colors"]["primary"]
    assert "acme_brand" in list_theme_names()
    assert any(t["name"] == "acme_brand" for t in list_custom_themes())
    assert load_custom_theme_payload("acme_brand")["colors"] == payload["colors"]

    assert delete_custom_theme("acme_brand") is True
    assert get_theme("acme_brand", kind="document").name == "professional"  # fallback


def test_save_rewrites_cached_theme() -> None:
    save_custom_theme("brand2", {"colors": {"primary": "#111111"}})
    assert get_theme("brand2").colors.primary == "#111111"
    save_custom_theme("brand2", {"colors": {"primary": "#222222"}})
    assert get_theme("brand2").colors.primary == "#222222"  # cache invalidated


def test_save_rejects_builtin_and_bad_names() -> None:
    with pytest.raises(ValueError, match="built-in"):
        save_custom_theme("professional", {"colors": {"primary": "#111111"}})
    with pytest.raises(ValueError, match="name"):
        save_custom_theme("Bad Name!", {"colors": {"primary": "#111111"}})


def test_save_no_overwrite_guard() -> None:
    save_custom_theme("once", {"colors": {"primary": "#111111"}})
    with pytest.raises(ValueError, match="already exists"):
        save_custom_theme("once", {"colors": {"primary": "#222222"}}, overwrite=False)


# ---------------------------------------------------------------------------
# Tool surface
# ---------------------------------------------------------------------------


def _ctx():
    from leagent.tools.base import ToolContext

    return ToolContext(user_id="u", session_id="s")


def test_theme_designer_tool_create_and_get(tmp_path: Path) -> None:
    from leagent.tools.gen.theme_tool import ThemeDesignerTool

    tool = ThemeDesignerTool()
    result = tool.execute_sync(
        {
            "action": "create",
            "name": "board_deck",
            "kind": "deck",
            "primary": "#1E2761",
            "mode": "dark",
            "overrides": {"deck": {"body_size": 18}},
        },
        _ctx(),
    )
    assert result["success"] is True and result["saved"] is True
    assert result["lint_warnings"] == []
    assert result["payload"]["deck"]["body_size"] == 18

    got = tool.execute_sync({"action": "get", "name": "board_deck", "kind": "deck"}, _ctx())
    assert got["resolved"]["deck"]["dark"] is True
    listed = tool.execute_sync({"action": "list"}, _ctx())
    names = [t["name"] for t in listed["themes"]]
    assert "board_deck" in names and "professional" in names

    deleted = tool.execute_sync({"action": "delete", "name": "board_deck"}, _ctx())
    assert deleted["deleted"] is True


def test_theme_designer_tool_dry_run_saves_nothing() -> None:
    from leagent.tools.gen.theme_tool import ThemeDesignerTool

    result = ThemeDesignerTool().execute_sync(
        {"action": "create", "name": "ghost", "primary": "#0B5FFF", "dry_run": True},
        _ctx(),
    )
    assert result["saved"] is False
    assert load_custom_theme_payload("ghost") is None


def test_theme_designer_tool_save_invalid_payload_rejected() -> None:
    from leagent.tools.gen.theme_tool import ThemeDesignerTool

    with pytest.raises(ValueError):
        ThemeDesignerTool().execute_sync(
            {"action": "save", "name": "broken", "payload": {"colors": "nope"}},
            _ctx(),
        )
