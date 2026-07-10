"""Doc-template store, Jinja2 instantiation, and end-to-end generation tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from leagent.docgen.templates import (
    DocTemplate,
    delete_template,
    list_templates,
    load_template,
    render_template,
    save_template,
)


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LEAGENT_HOME", str(tmp_path))
    yield


_DOC_TPL = DocTemplate(
    name="quarterly-report",
    kind="document",
    description="季度经营报告模板",
    theme="professional",
    variables=[
        {"name": "quarter", "description": "如 2026Q2", "required": True},
        {"name": "author", "default": "经营分析组"},
        {"name": "highlights", "default": []},
    ],
    content=(
        "# {{ quarter }} 经营报告\n\n"
        "作者：{{ author }}\n\n"
        "## 亮点\n\n"
        "{% for item in highlights %}- {{ item }}\n{% endfor %}\n"
    ),
    defaults={"toc": True, "cover": True},
)

_DECK_TPL = DocTemplate(
    name="board-update",
    kind="deck",
    theme="midnight_executive",
    variables=[{"name": "month", "required": True, "default": "1月"}],
    slides=[
        {"layout": "title", "title": "{{ month }} 董事会汇报"},
        {
            "layout": "content",
            "kicker": "MONTHLY UPDATE",
            "title": "{{ month }} 关键进展",
            "body": "- 进展 A\n- 进展 B",
            "takeaway": "{{ month }} 目标达成",
        },
    ],
    defaults={"footer_text": "Confidential"},
)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_render_document_template_with_loop() -> None:
    payload = render_template(
        _DOC_TPL,
        {"quarter": "2026Q2", "highlights": ["收入 +23%", "毛利率 40%"]},
    )
    assert payload["kind"] == "document"
    assert payload["toc"] is True and payload["cover"] is True
    assert payload["theme"] == "professional"
    assert "# 2026Q2 经营报告" in payload["content"]
    assert "- 收入 +23%" in payload["content"]
    assert "经营分析组" in payload["content"]  # default filled


def test_render_deck_template_renders_nested_strings() -> None:
    payload = render_template(_DECK_TPL, {"month": "7月"})
    assert payload["kind"] == "deck"
    assert payload["footer_text"] == "Confidential"
    assert payload["slides"][0]["title"] == "7月 董事会汇报"
    assert payload["slides"][1]["takeaway"] == "7月 目标达成"
    # Non-templated fields pass through untouched.
    assert payload["slides"][1]["kicker"] == "MONTHLY UPDATE"


def test_render_missing_required_variable_raises() -> None:
    tpl = _DOC_TPL.model_copy()
    with pytest.raises(ValueError, match="quarter"):
        render_template(tpl, {})


def test_render_undefined_variable_in_body_raises() -> None:
    tpl = DocTemplate(
        name="broken", kind="document", content="Hello {{ nobody_declared_me }}"
    )
    with pytest.raises(ValueError, match="rendering failed"):
        render_template(tpl, {})


# ---------------------------------------------------------------------------
# Store round trip
# ---------------------------------------------------------------------------


def test_save_load_list_delete_round_trip() -> None:
    saved = save_template(_DOC_TPL)
    assert saved["name"] == "quarterly-report"

    loaded = load_template("quarterly-report")
    assert loaded is not None
    assert loaded.kind == "document"
    assert loaded.defaults == {"toc": True, "cover": True}
    assert [v.name for v in loaded.variables] == ["quarter", "author", "highlights"]

    summaries = list_templates()
    assert any(t["name"] == "quarterly-report" for t in summaries)

    assert delete_template("quarterly-report") is True
    assert load_template("quarterly-report") is None


def test_save_validates_render_up_front() -> None:
    broken = DocTemplate(
        name="broken", kind="document", content="{% for x in %}oops{% endfor %}"
    )
    with pytest.raises(ValueError):
        save_template(broken)

    empty_deck = DocTemplate(name="empty-deck", kind="deck", slides=[])
    with pytest.raises(ValueError, match="no slides"):
        save_template(empty_deck)


def test_save_no_overwrite_guard() -> None:
    save_template(_DOC_TPL)
    with pytest.raises(ValueError, match="already exists"):
        save_template(_DOC_TPL, overwrite=False)


# ---------------------------------------------------------------------------
# Tool surface (save -> preview -> generate)
# ---------------------------------------------------------------------------


def _ctx():
    from leagent.tools.base import ToolContext

    return ToolContext(user_id="u", session_id="s")


def test_document_template_tool_end_to_end(tmp_path: Path) -> None:
    from leagent.tools.gen.template_tool import DocumentTemplateTool

    tool = DocumentTemplateTool()
    saved = tool.execute_sync(
        {
            "action": "save",
            "name": "weekly-brief",
            "kind": "document",
            "content": "# {{ week }} 周报\n\n{{ summary }}\n",
            "variables": [
                {"name": "week", "required": True},
                {"name": "summary", "default": "本周无重大事项。"},
            ],
            "defaults": {"toc": False},
        },
        _ctx(),
    )
    assert saved["success"] is True

    preview = tool.execute_sync(
        {"action": "preview", "name": "weekly-brief", "values": {"week": "W28"}},
        _ctx(),
    )
    assert "# W28 周报" in preview["rendered"]["content"]

    out = tmp_path / "brief.md"
    result = tool.execute_sync(
        {
            "action": "generate",
            "name": "weekly-brief",
            "values": {"week": "W28"},
            "output_path": str(out),
            "format": "markdown",
        },
        _ctx(),
    )
    assert result["success"] is True
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "W28 周报" in text and "本周无重大事项" in text


def test_document_template_tool_deck_generate(tmp_path: Path) -> None:
    pptx = pytest.importorskip("pptx")
    from leagent.tools.gen.template_tool import DocumentTemplateTool

    tool = DocumentTemplateTool()
    tool.execute_sync(
        {
            "action": "save",
            "name": "board-update",
            "kind": "deck",
            "slides": [s for s in _DECK_TPL.slides or []],
            "theme": "midnight_executive",
            "variables": [{"name": "month", "required": True}],
        },
        _ctx(),
    )
    out = tmp_path / "board.pptx"
    result = tool.execute_sync(
        {
            "action": "generate",
            "name": "board-update",
            "values": {"month": "7月"},
            "output_path": str(out),
        },
        _ctx(),
    )
    assert result["success"] is True
    assert out.is_file()

    prs = pptx.Presentation(str(out))
    texts = [
        shape.text_frame.text
        for slide in prs.slides
        for shape in slide.shapes
        if shape.has_text_frame
    ]
    joined = "\n".join(texts)
    assert "7月 董事会汇报" in joined
    assert "7月 目标达成" in joined


def test_document_template_tool_unknown_template() -> None:
    from leagent.tools.gen.template_tool import DocumentTemplateTool

    with pytest.raises(ValueError, match="not found"):
        DocumentTemplateTool().execute_sync(
            {"action": "preview", "name": "nope", "values": {}}, _ctx()
        )
