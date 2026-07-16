"""Tests for canvas companion SSE events and generative UI schema validation."""

import json
from pathlib import Path
from uuid import uuid4

import pytest

from leagent.api.v1 import chat as chat_mod
from jsonschema.exceptions import ValidationError

from leagent.services.gen_ui.schema import (
    normalize_ui_tree,
    validate_ui_patch,
    validate_ui_tree,
)
from leagent.tools.executor import normalize_tool_parameters
from leagent.services.canvas.service import (
    build_preview_html,
    mint_preview_token,
    preview_query_path,
    sanitize_html,
)
from leagent.config.settings import CanvasSettings, Settings
from leagent.db.models.canvas import CanvasContentType, CanvasDocument
from leagent.tools.base import ToolContext
from leagent.tools.canvas.canvas_publish import CanvasPublishTool
from leagent.tools.canvas.genui_guide import GetGenuiGuideTool
from leagent.tools.canvas.html_guide import GetHtmlCanvasGuideTool
from leagent.tools.canvas.ui_components import EmitUiPatchTool, EmitUiTreeTool


def test_canvas_publish_params_accepts_html_blob_id() -> None:
    tool = CanvasPublishTool()
    ok, err = tool.validate_params(
        {
            "title": "Page",
            "mode": "html",
            "session_id": "current",
            "html_blob_id": "a" * 32,
        },
    )
    assert ok, err


def test_canvas_publish_params_accepts_current_and_omitted_session_id():
    """JSON schema must allow 'current' (7 chars) and optional session_id; models use both."""
    tool = CanvasPublishTool()
    ok, err = tool.validate_params(
        {
            "title": "Dashboard",
            "mode": "html",
            "session_id": "current",
            "html": "<div>ok</div>",
        },
    )
    assert ok, err
    ok2, err2 = tool.validate_params(
        {
            "title": "Dashboard",
            "mode": "html",
            "html": "<div>ok</div>",
        },
    )
    assert ok2, err2


def test_companion_canvas_event():
    out = chat_mod._companion_sse_events(
        "tool_result",
        {
            "name": "canvas_publish",
            "success": True,
            "data": {
                "canvas_id": str(uuid4()),
                "revision": 1,
                "preview_path": "/api/v1/canvas/preview?token=abc",
                "title": "T",
                "content_type": "html",
                "trust": "hosted",
                "open_in_panel": True,
            },
        },
    )
    assert len(out) == 1
    assert out[0][0] == "canvas"
    assert "preview_path" in out[0][1]


def test_companion_emit_ui():
    out = chat_mod._companion_sse_events(
        "tool_result",
        {
            "name": "emit_ui_tree",
            "success": True,
            "data": {
                "tree": {
                    "schemaVersion": "1",
                    "root": {"nodeId": "1", "kind": "Text", "props": {"value": "x"}},
                }
            },
        },
    )
    assert any(x[0] == "ui_tree" for x in out)


def test_companion_emit_ui_legacy_payload_wrapper():
    """SSE still unwraps pre-flatten tool results stored as `{payload: {tree}}`."""
    out = chat_mod._companion_sse_events(
        "tool_result",
        {
            "name": "emit_ui_tree",
            "success": True,
            "data": {
                "payload": {
                    "tree": {
                        "schemaVersion": "1",
                        "root": {"nodeId": "1", "kind": "Text", "props": {"value": "x"}},
                    }
                }
            },
        },
    )
    assert any(x[0] == "ui_tree" for x in out)


def test_companion_includes_tool_call_id():
    tid = "call_abc123"
    out = chat_mod._companion_sse_events(
        "tool_result",
        {
            "tool_call_id": tid,
            "name": "emit_ui_tree",
            "success": True,
            "data": {
                "tree": {
                    "schemaVersion": "1",
                    "root": {"nodeId": "1", "kind": "Text", "props": {"value": "x"}},
                }
            },
        },
    )
    ui = next(x for x in out if x[0] == "ui_tree")
    assert ui[1].get("tool_call_id") == tid


def test_validate_root_ui_slot():
    tree = {
        "schemaVersion": "1",
        "root": {
            "nodeId": "1",
            "kind": "Stack",
            "props": {"uiSlot": "weather"},
            "children": [{"nodeId": "2", "kind": "Text", "props": {"value": "hi"}}],
        },
    }
    validate_ui_tree(tree, max_depth=10, max_nodes=20)


def test_validate_root_ui_slot_rejects_invalid():
    tree = {
        "schemaVersion": "1",
        "root": {"nodeId": "1", "kind": "Stack", "props": {"uiSlot": "nope"}, "children": []},
    }
    with pytest.raises(Exception):
        validate_ui_tree(tree, max_depth=10, max_nodes=20)


def test_validate_poster_media_layout_kinds():
    """AspectBox, DesignSurface, LiveCamera, and extended Image validate as schema v1."""
    tree = {
        "schemaVersion": "1",
        "root": {
            "nodeId": "root",
            "kind": "DesignSurface",
            "props": {"preset": "slide", "padding": "md"},
            "children": [
                {
                    "nodeId": "ab",
                    "kind": "AspectBox",
                    "props": {"ratio": "16:9", "rounded": True},
                    "children": [
                        {
                            "nodeId": "cam",
                            "kind": "LiveCamera",
                            "props": {"facingMode": "user", "mirrored": True},
                            "children": [],
                        },
                        {
                            "nodeId": "img",
                            "kind": "Image",
                            "props": {
                                "src": "https://example.com/p.png",
                                "alt": "x",
                                "fit": "cover",
                                "lightbox": True,
                            },
                            "children": [],
                        },
                    ],
                }
            ],
        },
    }
    out = validate_ui_tree(tree, max_depth=12, max_nodes=30)
    assert out["root"]["kind"] == "DesignSurface"
    assert out["root"]["children"][0]["kind"] == "AspectBox"
    assert out["root"]["children"][0]["children"][0]["kind"] == "LiveCamera"


def test_validate_ui_tree_accepts_chart_node():
    tree = {
        "schemaVersion": "1",
        "root": {
            "nodeId": "chart-root",
            "kind": "Chart",
            "props": {
                "chart": "line",
                "title": "Revenue",
                "categories": ["A", "B", "C"],
                "series": [{"name": "Q", "values": [10, 20, 30]}],
                "height": 260,
                "showGrid": True,
            },
        },
    }
    out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
    assert out["root"]["kind"] == "Chart"


def test_print_renderer_chart_table_fallback():
    from leagent.services.gen_ui.print_renderer import render_pages_html

    tree = {
        "schemaVersion": "1",
        "root": {
            "nodeId": "chart-root",
            "kind": "Chart",
            "props": {
                "chart": "bar",
                "title": "Sales",
                "categories": ["Jan", "Feb"],
                "series": [{"name": "Units", "values": [5, 7]}],
            },
        },
    }
    norm = validate_ui_tree(tree, max_depth=10, max_nodes=20)
    html = render_pages_html(norm, mode="document")
    assert "Sales" in html
    assert "<table" in html


def test_validate_gen_ui():
    t = {
        "schemaVersion": "1",
        "root": {"nodeId": "1", "kind": "Stack", "children": []},
    }
    out = validate_ui_tree(t, max_depth=10, max_nodes=20)
    assert out["schemaVersion"] == "1"
    assert out["root"]["nodeId"] == "1"
    validate_ui_patch(
        {
            "patches": [{"op": "replace", "path": "/root", "value": {"nodeId": "1", "kind": "Text"}}]
        }
    )


def test_validate_gen_ui_normalizes_missing_schema_and_node_ids():
    partial = {"root": {"kind": "Text", "props": {"value": "x"}}}
    out = validate_ui_tree(partial, max_depth=10, max_nodes=20)
    assert out["schemaVersion"] == "1"
    assert out["root"]["kind"] == "Text"
    assert out["root"]["nodeId"]
    assert len(out["root"]["nodeId"]) >= 1


def test_validate_coerces_legacy_type_to_kind():
    """LLM output often uses ``type`` like React; schema and frontend use ``kind``."""
    tree = {
        "root": {
            "type": "Stack",
            "props": {"spacing": "lg"},
            "children": [{"type": "Text", "props": {"value": "hi"}}],
        },
    }
    out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
    assert out["root"]["kind"] == "Stack"
    assert out["root"]["children"][0]["kind"] == "Text"
    assert "type" not in out["root"]
    assert "type" not in out["root"]["children"][0]


def test_validate_wraps_bare_root_node_with_type():
    """Some models pass the root Stack/Grid as the top-level object (no schemaVersion/root)."""
    tree = {
        "type": "Stack",
        "props": {"gap": "lg"},
        "children": [{"type": "Text", "props": {"value": "x"}}],
    }
    out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
    assert out["schemaVersion"] == "1"
    assert out["root"]["kind"] == "Stack"
    assert out["root"]["children"][0]["kind"] == "Text"


def test_validate_normalizes_common_model_prop_aliases():
    tree = {
        "type": "Stack",
        "props": {"gap": "lg", "padding": "12px"},
        "children": [
            {
                "type": "Row",
                "props": {"gap": "sm", "alignment": "start"},
                "children": [
                    {"type": "Badge", "props": {"text": "回顾性研究", "variant": "info"}},
                    {"type": "Text", "props": {"content": "摘要"}},
                    {"type": "Image", "props": {"imageUrl": "https://example.com/a.png"}},
                ],
            }
        ],
    }
    out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
    root = out["root"]
    row = root["children"][0]
    assert root["props"]["gap"] == 16
    assert root["props"]["padding"] == 12
    assert row["props"]["gap"] == 8
    assert row["props"]["align"] == "start"
    assert row["children"][0]["props"]["value"] == "回顾性研究"
    assert row["children"][1]["props"]["value"] == "摘要"
    assert row["children"][2]["props"]["src"] == "https://example.com/a.png"


def test_normalize_slide_deck_expands_props_slides():
    tree = {
        "schemaVersion": "1",
        "root": {
            "kind": "SlideDeck",
            "props": {
                "title": "Deck",
                "slides": [
                    {
                        "title": "Cover",
                        "subtitle": "Sub",
                        "content": "Body",
                        "variant": "cover",
                    },
                    {
                        "title": "Inner",
                        "variant": "content",
                        "children": [{"kind": "Text", "props": {"value": "hello"}}],
                    },
                ],
            },
        },
    }
    out = validate_ui_tree(tree, max_depth=30, max_nodes=300)
    root = out["root"]
    assert root["kind"] == "SlideDeck"
    assert "slides" not in (root.get("props") or {})
    ch = root["children"]
    assert len(ch) == 2
    assert ch[0]["kind"] == "Slide"
    assert ch[0]["props"]["title"] == "Cover"
    assert ch[0]["props"]["layout"] == "cover"
    kinds0 = [n.get("kind") for n in ch[0]["children"]]
    assert "Text" in kinds0
    assert ch[1]["kind"] == "Slide"
    assert ch[1]["children"][0]["props"]["value"] == "hello"


def test_normalize_slide_deck_keeps_explicit_slide_children_over_props_slides():
    tree = {
        "schemaVersion": "1",
        "root": {
            "kind": "SlideDeck",
            "props": {"slides": [{"title": "From slides array"}]},
            "children": [{"kind": "Slide", "props": {"title": "Explicit"}}],
        },
    }
    out = validate_ui_tree(tree, max_depth=20, max_nodes=50)
    root = out["root"]
    assert len(root["children"]) == 1
    assert root["children"][0]["props"]["title"] == "Explicit"


@pytest.mark.asyncio
async def test_emit_ui_tree_accepts_tree_as_json_string():
    """Some providers serialize the whole tree as a JSON string; schema allows oneOf object|string."""
    tool = EmitUiTreeTool()
    raw = '{"schemaVersion":"1","root":{"nodeId":"1","kind":"Stack","children":[]}}'
    ok, err = tool.validate_params({"tree": raw})
    assert ok, err
    result = await tool.execute({"tree": raw}, ToolContext(user_id="u1", session_id="s1"))
    assert result["tree"]["schemaVersion"] == "1"


@pytest.mark.asyncio
async def test_emit_ui_tree_returns_normalized_payload_for_sse():
    result = await EmitUiTreeTool().execute(
        {"tree": {"type": "Badge", "props": {"text": "Ready", "variant": "success"}}},
        ToolContext(user_id="u1", session_id="s1"),
    )
    tree = result["tree"]
    assert tree["root"]["kind"] == "Badge"
    assert tree["root"]["props"]["value"] == "Ready"

    out = chat_mod._companion_sse_events(
        "tool_result",
        {"name": "emit_ui_tree", "success": True, "data": result},
    )
    assert out == [("ui_tree", {"tree": tree})]


def test_normalize_lifts_known_flat_card_props():
    """Catalog-documented flat keys (title/subtitle/padding/variant) lift into props."""
    tree = {
        "kind": "Card",
        "title": "X",
        "subtitle": "Y",
        "padding": "lg",
        "variant": "elevated",
        "children": [{"kind": "Text", "value": "hi"}],
    }
    out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
    root_props = out["root"]["props"]
    assert root_props["title"] == "X"
    assert root_props["subtitle"] == "Y"
    assert root_props["padding"] == "lg"
    assert root_props["variant"] == "elevated"
    # Flat keys are gone from the node level after lifting.
    for key in ("title", "subtitle", "padding", "variant"):
        assert key not in out["root"]
    assert out["root"]["children"][0]["props"]["value"] == "hi"


def test_normalize_lifts_flat_props_recursively():
    """Mirrors the reported failure: nested Tabs > TabItem > MetricCard flat shape."""
    tree = {
        "kind": "Stack",
        "gap": 12,
        "children": [
            {
                "kind": "Tabs",
                "defaultTab": "A",
                "children": [
                    {
                        "kind": "TabItem",
                        "label": "A",
                        "children": [
                            {
                                "kind": "MetricCard",
                                "title": "Users",
                                "value": "100",
                                "delta": "+5%",
                                "trend": "up",
                            },
                        ],
                    },
                ],
            },
        ],
    }
    out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
    root = out["root"]
    tabs = root["children"][0]
    tab_item = tabs["children"][0]
    metric = tab_item["children"][0]
    assert root["props"]["gap"] == 12
    assert tabs["props"]["defaultTab"] == "A"
    assert tab_item["props"]["label"] == "A"
    assert metric["props"]["title"] == "Users"
    assert metric["props"]["value"] == "100"
    assert metric["props"]["delta"] == "+5%"
    assert metric["props"]["trend"] == "up"


def test_normalize_keeps_unknown_flat_keys_failing():
    """Unknown flat keys are NOT silently absorbed — schema raises a real error."""
    tree = {"kind": "Card", "banana": "yes"}
    with pytest.raises(ValidationError):
        validate_ui_tree(tree, max_depth=10, max_nodes=20)


def test_normalize_caller_props_win_over_flat():
    """Explicit props.<key> takes precedence over a duplicate flat key."""
    tree = {
        "kind": "Card",
        "title": "flat",
        "props": {"title": "explicit"},
    }
    out = normalize_ui_tree(tree)
    assert out["root"]["props"]["title"] == "explicit"
    assert "title" not in out["root"]


@pytest.mark.asyncio
async def test_emit_ui_tree_repairs_malformed_json_string():
    """Structural JSON issues (e.g. superfluous ``}``) are repaired like outer tool-arg recovery."""
    raw = (Path(__file__).parent / "fixtures" / "emit_ui_tree_malformed_llm.json").read_text(
        encoding="utf-8",
    )
    result = await EmitUiTreeTool().execute(
        {"tree": raw}, ToolContext(user_id="u1", session_id="s1")
    )
    root = result["tree"]["root"]
    assert root["kind"] == "Stack"
    kinds = [c.get("kind") for c in root.get("children", [])]
    assert "Alert" in kinds


@pytest.mark.asyncio
async def test_emit_ui_tree_invalid_json_string_includes_decode_hint():
    """Irrecoverable nested JSON string surfaces byte position so the model can fix it."""
    # Escape-repair can salvage unescaped quotes; use token garbage that stays invalid.
    bad = '{"root": NOT_JSON}'
    with pytest.raises(ValueError) as excinfo:
        await EmitUiTreeTool().execute(
            {"tree": bad}, ToolContext(user_id="u1", session_id="s1")
        )
    msg = str(excinfo.value)
    assert "tree is not valid JSON" in msg
    assert "byte" in msg
    assert "Near:" in msg


@pytest.mark.asyncio
async def test_emit_ui_tree_repairs_superfluous_closing_brackets():
    """LLM over-closes nested arrays/objects before the next sibling node."""
    valid = {
        "schemaVersion": "1",
        "root": {
            "kind": "Stack",
            "props": {"gap": 12},
            "children": [
                {
                    "kind": "Grid",
                    "props": {"columns": 2},
                    "children": [
                        {
                            "kind": "Select",
                            "props": {
                                "options": [
                                    {"label": "IF/ELSE 逻辑"},
                                    {"label": "触发器", "value": "Cron / Webhook"},
                                ],
                            },
                        },
                    ],
                },
                {
                    "kind": "Card",
                    "props": {"title": "运行指标", "padding": 12},
                },
            ],
        },
    }
    bad = json.dumps(valid, ensure_ascii=False)
    bad = bad.replace(
        "Cron / Webhook\"}}]},",
        "Cron / Webhook\"}}]}]}]},",
        1,
    )
    result = await EmitUiTreeTool().execute(
        {"tree": bad}, ToolContext(user_id="u1", session_id="s1")
    )
    root = result["tree"]["root"]
    kinds = [c.get("kind") for c in root.get("children", [])]
    assert "Card" in kinds


def test_emit_ui_tree_recover_raw_args_from_broken_outer_json():
    """``recover_raw_args`` salvages tree when outer tool-call JSON is malformed."""
    inner = {
        "schemaVersion": "1",
        "root": {
            "kind": "Stack",
            "children": [
                {
                    "kind": "Select",
                    "props": {
                        "options": [
                            {"label": "触发器", "value": "Cron / Webhook"},
                        ],
                    },
                },
                {"kind": "Card", "props": {"title": "运行指标"}},
            ],
        },
    }
    inner_bad = json.dumps(inner, ensure_ascii=False)
    inner_bad = inner_bad.replace(
        "Cron / Webhook\"}}]},",
        "Cron / Webhook\"}}]}]}]},",
        1,
    )
    broken_outer = '{"tree":' + inner_bad + '}'
    recovered = EmitUiTreeTool().recover_raw_args(broken_outer)
    assert recovered is not None
    assert isinstance(recovered.get("tree"), dict)
    kinds = [c.get("kind") for c in recovered["tree"]["root"].get("children", [])]
    assert "Card" in kinds


def test_recover_emit_ui_tree_truncated_mid_stream():
    """Truncated provider output (mid-key) should salvage a partial tree."""
    from leagent.tools.executor import _recover_emit_ui_tree_args

    raw = (
        '{"tree": {"root":{"kind":"DesignSurface","props":{"preset":"editorial"},'
        '"children":[{"kind":"Stepper","props":{"steps":[{"title":"Receive",'
        '"status":"completed"},{"t'
    )
    recovered = _recover_emit_ui_tree_args(raw)
    assert recovered is not None
    tree = recovered["tree"]
    root = tree.get("root") or tree
    assert root.get("kind") == "DesignSurface"


def test_recover_emit_ui_patch_truncated_mid_stream():
    from leagent.tools.executor import _recover_emit_ui_patch_args

    raw = (
        '{"patches":[{"op":"add","path":"/root","value":{"kind":"Card","props":'
        '{"title":"Workflow"},"children":[{"kind":"Text","props":{"value":"ok"}'
    )
    recovered = _recover_emit_ui_patch_args(raw)
    assert recovered is not None
    assert isinstance(recovered.get("patches"), list)
    assert recovered["patches"][0]["op"] == "add"


def test_emit_ui_patch_omits_null_canvas_id():
    payload = {"patches": [{"op": "replace", "path": "/root/props/title", "value": "Hi"}]}
    validate_ui_patch(payload)


@pytest.mark.asyncio
async def test_emit_ui_patch_execute_without_canvas_id():
    tool = EmitUiPatchTool()
    patches = [{"op": "replace", "path": "/root/props/title", "value": "LeAgent Workflow 引擎"}]
    result = await tool.execute({"patches": patches, "seq": 1}, ToolContext(user_id="u1", session_id="s1"))
    assert result["patches"] == patches
    assert "canvas_id" not in result
    assert result["seq"] == 1


def test_emit_ui_patch_rejects_payload_key():
    patches = [{"op": "add", "path": "/root/children/-", "value": {"kind": "Text", "props": {"value": "x"}}}]
    ok, err = EmitUiPatchTool().validate_params({"payload": {"patches": patches, "seq": 2}})
    assert not ok
    assert err is not None
    assert "payload" in err
    assert "patches" in err


def test_emit_ui_tree_rejects_payload_key():
    """Args must use ``tree``; unknown ``payload`` gets an actionable hint (no silent rewrite)."""
    node = {"kind": "Image", "props": {"src": "/api/v1/files/x/preview", "alt": "chart"}}
    ok, err = EmitUiTreeTool().validate_params({"payload": node})
    assert not ok
    assert err is not None
    assert "payload" in err
    assert "tree" in err


def test_emit_ui_patch_recovers_top_level_patches_from_raw():
    patches = [{"op": "replace", "path": "/root/props/title", "value": "Title"}]
    raw = json.dumps({"patches": patches, "seq": 1}, ensure_ascii=False)
    tool = EmitUiPatchTool()
    normalized, err = normalize_tool_parameters({"__raw__": raw}, tool=tool)
    assert err is None
    assert normalized["patches"] == patches
    assert normalized["seq"] == 1


@pytest.mark.asyncio
async def test_emit_ui_tree_accepts_real_failing_payload():
    """Trimmed copy of the user-reported failing tree must validate end-to-end."""
    failing = {
        "root": {
            "kind": "Stack",
            "gap": 24,
            "padding": 16,
            "children": [
                {
                    "kind": "Card",
                    "title": "Canvas demo",
                    "subtitle": "Gen UI shape",
                    "variant": "elevated",
                    "padding": "lg",
                    "children": [
                        {
                            "kind": "Text",
                            "value": "Inline gen UI renders in chat",
                            "size": "base",
                        },
                    ],
                },
                {
                    "kind": "Tabs",
                    "defaultTab": "Dashboard",
                    "children": [
                        {
                            "kind": "TabItem",
                            "label": "Dashboard",
                            "children": [
                                {
                                    "kind": "Grid",
                                    "columns": 3,
                                    "gap": 16,
                                    "children": [
                                        {
                                            "kind": "MetricCard",
                                            "title": "Active users",
                                            "value": "12,847",
                                            "delta": "+12.5%",
                                            "trend": "up",
                                            "period": "vs last month",
                                            "icon": "👥",
                                        },
                                    ],
                                },
                            ],
                        },
                    ],
                },
            ],
        },
    }
    result = await EmitUiTreeTool().execute(
        {"tree": failing}, ToolContext(user_id="u1", session_id="s1")
    )
    tree = result["tree"]
    root = tree["root"]
    assert root["kind"] == "Stack"
    assert root["props"]["gap"] == 24
    card = root["children"][0]
    assert card["kind"] == "Card"
    assert card["props"]["title"] == "Canvas demo"
    assert card["props"]["padding"] == "lg"
    metric = root["children"][1]["children"][0]["children"][0]["children"][0]
    assert metric["kind"] == "MetricCard"
    assert metric["props"]["title"] == "Active users"
    assert metric["props"]["delta"] == "+12.5%"


def _minimal_settings() -> Settings:
    return Settings(
        canvas=CanvasSettings(preview_signing_secret="sign-secret" * 2),
    )


def test_preview_token_and_path():
    s = _minimal_settings()
    uid = uuid4()
    cid = uuid4()
    tok = mint_preview_token(s, canvas_id=cid, revision=1, user_id=uid)
    p = preview_query_path(tok)
    assert "/api/v1/canvas/preview" in p
    assert "token=" in p


def test_build_preview_html_wraps_fragment():
    s = _minimal_settings()
    doc = CanvasDocument(
        id=uuid4(),
        canvas_id=uuid4(),
        revision=1,
        session_id=uuid4(),
        user_id=uuid4(),
        title="x",
        content_type=CanvasContentType.HTML.value,
        html_body="<p>hi</p>",
    )
    html, _m = build_preview_html(doc, s)
    assert "<!DOCTYPE html>" in html
    assert "<p>hi</p>" in html


def test_build_preview_html_professional_shell():
    """Professional HTML shell includes Tailwind CDN, Inter font, and utility classes."""
    s = _minimal_settings()
    doc = CanvasDocument(
        id=uuid4(),
        canvas_id=uuid4(),
        revision=1,
        session_id=uuid4(),
        user_id=uuid4(),
        title="Dashboard",
        content_type=CanvasContentType.HTML.value,
        html_body='<div class="wa-card">Hello</div>',
    )
    html, mime = build_preview_html(doc, s)
    assert "<!DOCTYPE html>" in html
    assert "cdn.tailwindcss.com" in html
    assert "cdn.jsdelivr.net/npm/three@" in html
    assert "three.min.js" in html
    assert "Inter" in html
    assert "wa-card" in html
    assert "wa-gradient" in html
    assert "color-scheme: light" in html
    assert "darkMode: 'class'" in html
    assert "scrollbar-width: none" in html
    assert "text/html" in mime


def test_build_preview_html_injects_tailwind_into_full_document():
    """Full <!DOCTYPE html>… from the agent must still get Tailwind when CDN is absent."""
    s = _minimal_settings()
    full = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/><title>T</title></head>
<body><div class="p-4 text-lg font-semibold text-primary-600">Styled</div></body></html>"""
    doc = CanvasDocument(
        id=uuid4(),
        canvas_id=uuid4(),
        revision=1,
        session_id=uuid4(),
        user_id=uuid4(),
        title="Full",
        content_type=CanvasContentType.HTML.value,
        html_body=full,
    )
    html, _mime = build_preview_html(doc, s)
    assert html.count("cdn.tailwindcss.com") >= 1
    assert "tailwind.config" in html
    assert "Styled" in html


def test_build_preview_html_skips_shell_for_authored_full_document():
    """Authored <style> pages must not get Tailwind Preflight / host body resets."""
    s = _minimal_settings()
    full = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"/>
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:#f8fafc;color:#0f172a;min-height:100vh}
h1{font-size:clamp(28px,5vw,52px);font-weight:700;letter-spacing:-.025em}
h1 span{display:block;background:linear-gradient(135deg,#2563eb,#06b6d4);
-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
.card{background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:20px}
</style>
<title>AI Agent</title></head>
<body><header><h1>AI Agent <span>框架与工具</span></h1></header></body></html>"""
    doc = CanvasDocument(
        id=uuid4(),
        canvas_id=uuid4(),
        revision=1,
        session_id=uuid4(),
        user_id=uuid4(),
        title="Authored",
        content_type=CanvasContentType.HTML.value,
        html_body=full,
    )
    html, _mime = build_preview_html(doc, s)
    assert "cdn.tailwindcss.com" not in html
    assert "tailwind.config" not in html
    assert "three.min.js" not in html
    assert "font-size:clamp(28px,5vw,52px)" in html
    assert "-webkit-background-clip:text" in html
    assert "框架与工具" in html


def test_build_preview_html_skips_shell_for_external_stylesheet():
    """Non-font stylesheet links mark the document as authored."""
    s = _minimal_settings()
    full = """<!DOCTYPE html>
<html><head>
<link rel="stylesheet" href="https://cdn.example.com/app.css"/>
</head><body><h1 class="hero">Hi</h1></body></html>"""
    doc = CanvasDocument(
        id=uuid4(),
        canvas_id=uuid4(),
        revision=1,
        session_id=uuid4(),
        user_id=uuid4(),
        title="LinkedCSS",
        content_type=CanvasContentType.HTML.value,
        html_body=full,
    )
    html, _mime = build_preview_html(doc, s)
    assert "cdn.tailwindcss.com" not in html
    assert "cdn.example.com/app.css" in html


def test_build_preview_html_still_injects_when_only_font_stylesheet():
    """Google Fonts alone must not suppress the host Tailwind shell."""
    s = _minimal_settings()
    full = """<!DOCTYPE html>
<html><head>
<link href="https://fonts.googleapis.com/css2?family=Inter&display=swap" rel="stylesheet"/>
</head><body><div class="p-4">Fonts only</div></body></html>"""
    doc = CanvasDocument(
        id=uuid4(),
        canvas_id=uuid4(),
        revision=1,
        session_id=uuid4(),
        user_id=uuid4(),
        title="FontsOnly",
        content_type=CanvasContentType.HTML.value,
        html_body=full,
    )
    html, _mime = build_preview_html(doc, s)
    assert "cdn.tailwindcss.com" in html
    assert "Fonts only" in html


def test_sanitize_html_fragment_preserves_tailwind_class_svg_and_style():
    """Fragments must keep class/style, inline <style>, and SVG (Tailwind + charts)."""
    frag = (
        '<style>.chart{color:blue}</style>'
        '<div class="p-4 wa-card text-primary-600" style="margin:8px">'
        '<svg viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">'
        '<circle cx="10" cy="10" r="8" fill="currentColor"/>'
        "</svg></div>"
    )
    out = sanitize_html(frag, max_bytes=1024 * 1024)
    assert "wa-card" in out
    assert "text-primary-600" in out
    assert 'style="margin:8px"' in out or "margin:8px" in out
    assert ".chart{color:blue}" in out or "color:blue" in out
    assert "<svg" in out.lower()
    assert "<circle" in out.lower()


def test_sanitize_html_fragment_strips_inline_handlers_and_bad_scripts():
    out = sanitize_html(
        '<div onclick="alert(1)" class="ok">x</div><script>evil()</script>',
        max_bytes=1024 * 1024,
    )
    assert "onclick" not in out.lower()
    assert "evil" not in out
    assert "ok" in out


def test_sanitize_html_full_document_preserves_three_global_src_strips_inline_script():
    full = """<!DOCTYPE html>
<html><head></head>
<body><div class="scene">3D</div>
<script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
<script>initScene()</script>
</body></html>"""
    out = sanitize_html(full, max_bytes=1024 * 1024)
    assert "cdn.jsdelivr.net/npm/three@" in out
    assert "three.min.js" in out
    assert "initScene()" not in out
    assert "scene" in out


def test_sanitize_html_full_document_preserves_style_strips_inline_script():
    full = """<!DOCTYPE html>
<html><head><style>body{color:navy}</style></head>
<body><div class="hero">Hi</div><script>alert(1)</script>
<script src="https://cdn.tailwindcss.com"></script>
</body></html>"""
    out = sanitize_html(full, max_bytes=1024 * 1024)
    assert "color:navy" in out
    assert "hero" in out
    assert "alert(1)" not in out
    assert "cdn.tailwindcss.com" in out


def test_sanitize_html_full_document_strips_javascript_href():
    full = """<!DOCTYPE html><html><body>
<a href="javascript:void(0)" class="link">x</a>
<a href="https://example.com/" class="safe">y</a>
</body></html>"""
    out = sanitize_html(full, max_bytes=1024 * 1024)
    assert "javascript:" not in out.lower()
    assert "example.com" in out
    assert "safe" in out


def test_sanitize_html_allow_js_preserves_scripts_and_handlers():
    raw = '<div onclick="go()" class="ok"><script>run()</script></div>'
    out = sanitize_html(raw, max_bytes=1024 * 1024, allow_js=True)
    assert "onclick" in out.lower()
    assert "run()" in out


def test_build_preview_html_allow_js_toggle():
    s = _minimal_settings()
    raw = '<button onclick="x()">Go</button><script>var a = 1</script>'
    doc = CanvasDocument(
        id=uuid4(),
        canvas_id=uuid4(),
        revision=1,
        session_id=uuid4(),
        user_id=uuid4(),
        title="JsToggle",
        content_type=CanvasContentType.HTML.value,
        html_body=raw,
    )
    html_off, _mime = build_preview_html(doc, s, allow_js=False)
    html_on, _mime2 = build_preview_html(doc, s, allow_js=True)
    assert "onclick" not in html_off.lower()
    assert "var a = 1" not in html_off
    assert "onclick" in html_on.lower()
    assert "var a = 1" in html_on
    assert "__leagentReleaseMedia" in html_on
    assert "__leagentAttachCamera" in html_on
    assert "__leagentPreviewIframeBootstrap" in html_on
    assert "__leagentReleaseMedia" not in html_off


def test_build_preview_html_skips_duplicate_three_bootstrap():
    s = _minimal_settings()
    raw = (
        '<script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>'
        '<script>console.log(window.THREE)</script>'
    )
    doc = CanvasDocument(
        id=uuid4(),
        canvas_id=uuid4(),
        revision=1,
        session_id=uuid4(),
        user_id=uuid4(),
        title="Three",
        content_type=CanvasContentType.HTML.value,
        html_body=raw,
    )
    html, _mime = build_preview_html(doc, s, allow_js=True)
    assert html.count("three.min.js") == 1


def test_build_preview_html_injects_three_despite_prose_mention():
    """UI copy saying 'Three.js' must not suppress the host CDN bootstrap."""
    s = _minimal_settings()
    raw = """<!DOCTYPE html><html><head></head><body>
<div id="loading">加载中...</div>
<script>
(function () {
  const THREE = window.THREE;
  if (!THREE) {
    document.getElementById('loading').textContent = 'Three.js 未加载，请刷新页面';
    return;
  }
})();
</script>
</body></html>"""
    doc = CanvasDocument(
        id=uuid4(),
        canvas_id=uuid4(),
        revision=1,
        session_id=uuid4(),
        user_id=uuid4(),
        title="Rocket",
        content_type=CanvasContentType.HTML.value,
        html_body=raw,
    )
    html, _mime = build_preview_html(doc, s, allow_js=True)
    assert "three.min.js" in html
    assert html.count("three.min.js") == 1


def test_build_preview_html_uses_sanitized_body_classes():
    """Publish stores raw HTML; preview sanitises unless allow_js."""
    s = _minimal_settings()
    raw = '<div class="rounded-xl p-6 shadow-md bg-slate-100 dark:bg-slate-800">Card</div>'
    doc = CanvasDocument(
        id=uuid4(),
        canvas_id=uuid4(),
        revision=1,
        session_id=uuid4(),
        user_id=uuid4(),
        title="Sanitized",
        content_type=CanvasContentType.HTML.value,
        html_body=raw,
    )
    html, _mime = build_preview_html(doc, s)
    assert "rounded-xl" in html
    assert "dark:bg-slate-800" in html
    assert "Card" in html


@pytest.mark.asyncio
async def test_get_html_canvas_guide_returns_payload():
    data = await GetHtmlCanvasGuideTool().execute({}, ToolContext(user_id="u1", session_id="s1"))
    assert "when_to_call" in data
    assert "design_method" in data
    assert "visual_quality" in data
    assert "responsive_accessibility" in data
    assert "preview_runtime" in data
    assert "surface_matrix" in data
    assert "quality_gate" in data
    assert "wa-card" in data["available_shell_tokens"]["utilities"]
    assert "window.THREE" in data["preview_runtime"]["three_js"]
    assert "API defaults JS off" in data["preview_runtime"]["javascript"]
    assert "does not receive" in data["surface_matrix"]["html_frame"]
    assert "html_paths" in " ".join(data["delivery"])
    assert "<main" in data["reference_template"]
    assert any("not a house style" in line.lower() for line in [data["purpose"]])
    assert any("do not default" in line.lower() for line in data["design_method"])

    doc = CanvasDocument(
        id=uuid4(),
        canvas_id=uuid4(),
        revision=1,
        session_id=uuid4(),
        user_id=uuid4(),
        title="Guide parity",
        content_type=CanvasContentType.HTML.value,
        html_body="<main>Guide parity</main>",
    )
    preview_html, _mime = build_preview_html(doc, _minimal_settings())
    for class_name in data["available_shell_tokens"]["utilities"]:
        assert f".{class_name}" in preview_html


@pytest.mark.asyncio
async def test_get_genui_guide_returns_payload():
    data = await GetGenuiGuideTool().execute({}, ToolContext(user_id="u1", session_id="s1"))
    assert "wire_format_and_syntax" in data
    assert "layout_structure" in data
    assert "emoji_and_icons" in data
    assert "workflow_order" in data
    assert "custom_javascript" in data
    assert any("ThreeJsFrame" in line for line in data["custom_javascript"])


def test_list_component_catalog_returns_singleton_list():
    from leagent.services.gen_ui.schema import list_component_catalog

    a = list_component_catalog()
    b = list_component_catalog()
    assert a is b
    assert len(a) > 0
    design_surface = next(item for item in a if item["kind"] == "DesignSurface")
    assert "geek" in design_surface["props"]["preset"]
    html_frame = next(item for item in a if item["kind"] == "HtmlFrame")
    assert "html" in html_frame["props"]
    three_frame = next(item for item in a if item["kind"] == "ThreeJsFrame")
    assert "geometry" in three_frame["props"]
    assert "sceneScript" in three_frame["props"]


def test_validate_ui_tree_accepts_html_frame_node():
    tree = {
        "schemaVersion": "1",
        "root": {
            "nodeId": "html-root",
            "kind": "HtmlFrame",
            "props": {
                "html": "<div class='p-4'>Hello</div>",
                "height": 280,
                "title": "Demo",
            },
        },
    }
    out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
    assert out["root"]["kind"] == "HtmlFrame"


def test_validate_ui_tree_accepts_three_js_frame_node():
    tree = {
        "schemaVersion": "1",
        "root": {
            "nodeId": "three-root",
            "kind": "ThreeJsFrame",
            "props": {
                "title": "Spinning cube",
                "height": 400,
                "background": "#0f172a",
                "geometry": "icosahedron",
                "particles": 320,
                "orbiters": 8,
                "quality": "high",
                "cameraZ": 6,
                "sceneScript": (
                    "const geo = new THREE.BoxGeometry(1, 1, 1);"
                    "const mat = new THREE.MeshNormalMaterial();"
                    "const mesh = new THREE.Mesh(geo, mat);"
                    "scene.add(mesh);"
                    "onFrame = () => { mesh.rotation.y += 0.02; };"
                ),
            },
        },
    }
    out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
    assert out["root"]["kind"] == "ThreeJsFrame"
    assert out["root"]["props"]["geometry"] == "icosahedron"
    assert "BoxGeometry" in out["root"]["props"]["sceneScript"]


def test_validate_weather_card_tree():
    """WeatherCard with forecast validates correctly."""
    tree = {
        "root": {
            "kind": "WeatherCard",
            "props": {
                "location": "Beijing",
                "temperature": "23°C",
                "condition": "Partly Cloudy",
                "icon": "⛅",
                "humidity": "65%",
                "wind": "12 km/h",
                "forecast": [
                    {"day": "Mon", "high": "25°C", "low": "18°C", "icon": "☀️"},
                    {"day": "Tue", "high": "22°C", "low": "16°C", "icon": "🌧️"},
                ],
            },
        }
    }
    out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
    assert out["schemaVersion"] == "1"
    assert out["root"]["kind"] == "WeatherCard"
    assert out["root"]["props"]["location"] == "Beijing"
    assert out["root"]["nodeId"]


def test_validate_metric_card_tree():
    tree = {
        "root": {
            "kind": "MetricCard",
            "props": {
                "title": "Revenue",
                "value": "$1.2M",
                "delta": "+5.2%",
                "trend": "up",
                "period": "vs last week",
                "icon": "💰",
            },
        }
    }
    out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
    assert out["root"]["kind"] == "MetricCard"
    assert out["root"]["props"]["delta"] == "+5.2%"


def test_validate_interactive_button_tree():
    tree = {
        "root": {
            "kind": "InteractiveButton",
            "props": {
                "label": "Submit",
                "actionId": "submit-form",
                "icon": "🚀",
                "variant": "primary",
                "size": "md",
                "tooltip": "Click to submit",
                "disabled": False,
            },
        }
    }
    out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
    assert out["root"]["kind"] == "InteractiveButton"
    assert out["root"]["props"]["actionId"] == "submit-form"


def test_validate_new_layout_components():
    """Grid, Row, Tabs, Accordion all validate as valid kinds."""
    for kind in ["Grid", "Row", "Tabs", "Accordion", "ScrollArea", "Spacer"]:
        tree = {"root": {"kind": kind}}
        out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
        assert out["root"]["kind"] == kind


def test_validate_data_display_components():
    """Badge, Tag, Stat, Progress, Table, etc. all validate."""
    for kind in [
        "Badge", "Tag", "Stat", "Progress", "Avatar", "Image",
        "Icon", "Table", "List", "CodeBlock", "Markdown",
    ]:
        tree = {"root": {"kind": kind}}
        out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
        assert out["root"]["kind"] == kind


def test_validate_rich_card_components():
    """All rich card kinds validate."""
    for kind in [
        "WeatherCard", "DataCard", "MetricCard", "ProfileCard",
        "MediaCard", "AlertCard", "TimelineCard",
    ]:
        tree = {"root": {"kind": kind}}
        out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
        assert out["root"]["kind"] == kind


def test_validate_feedback_components():
    for kind in ["Alert", "Callout"]:
        tree = {
            "root": {
                "kind": kind,
                "props": {"title": "Note", "message": "Hello", "severity": "info"},
            }
        }
        out = validate_ui_tree(tree, max_depth=10, max_nodes=20)
        assert out["root"]["kind"] == kind


def test_validate_complex_dashboard_tree():
    """A realistic dashboard tree with Grid, MetricCards, and a Table."""
    tree = {
        "root": {
            "kind": "Stack",
            "children": [
                {"kind": "Heading", "props": {"level": 1, "value": "Dashboard"}},
                {
                    "kind": "Grid",
                    "props": {"columns": 3, "gap": 16},
                    "children": [
                        {"kind": "MetricCard", "props": {"title": "Users", "value": "1,234", "delta": "+12%", "trend": "up"}},
                        {"kind": "MetricCard", "props": {"title": "Revenue", "value": "$45K", "delta": "-3%", "trend": "down"}},
                        {"kind": "MetricCard", "props": {"title": "Orders", "value": "567", "delta": "+8%", "trend": "up"}},
                    ],
                },
                {
                    "kind": "Table",
                    "props": {"headers": ["Name", "Status", "Amount"], "striped": True},
                    "children": [
                        {
                            "kind": "TableRow",
                            "children": [
                                {"kind": "TableCell", "props": {"value": "Alice"}},
                                {"kind": "TableCell", "props": {"value": "Active"}},
                                {"kind": "TableCell", "props": {"value": "$1,200", "align": "right", "bold": True}},
                            ],
                        },
                    ],
                },
            ],
        }
    }
    out = validate_ui_tree(tree, max_depth=10, max_nodes=50)
    assert out["root"]["kind"] == "Stack"
    grid = out["root"]["children"][1]
    assert grid["kind"] == "Grid"
    assert len(grid["children"]) == 3
