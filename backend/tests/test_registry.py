"""Tests for ToolRegistry: registration, aliases, categories, schemas, discover."""

from __future__ import annotations

from typing import Any

import pytest

from leagent.tools.base import BaseTool, SyncTool, ToolCategory, ToolContext, ToolResult
from leagent.tools.registry import (
    ToolNotFoundError,
    ToolRegistrationError,
    ToolRegistry,
)


# ---------------------------------------------------------------------------
# Minimal tool stubs for testing
# ---------------------------------------------------------------------------


class _SimpleTool(SyncTool):
    name = "simple_tool"
    description = "A simple test tool"
    category = ToolCategory.UTIL
    version = "1.0.0"
    aliases = ["simple", "st"]

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
        }

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult.ok({"result": params.get("value", "")})


class _DocTool(SyncTool):
    name = "doc_tool"
    description = "A doc-category test tool"
    category = ToolCategory.DOC
    version = "1.0.0"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"path": {"type": "string"}}}

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult.ok({"path": params.get("path", "")})


class _WebTool(SyncTool):
    name = "web_tool"
    description = "A web-category test tool"
    category = ToolCategory.WEB
    version = "1.0.0"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"url": {"type": "string"}}}

    def execute_sync(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
        return ToolResult.ok({})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegistration:
    def test_register_tool(self) -> None:
        reg = ToolRegistry()
        tool = _SimpleTool()
        reg.register(tool)
        assert reg.has("simple_tool")

    def test_register_alias_resolution(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        retrieved = reg.get("simple")
        assert retrieved.name == "simple_tool"
        retrieved2 = reg.get("st")
        assert retrieved2.name == "simple_tool"

    def test_register_duplicate_raises(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        with pytest.raises(ToolRegistrationError):
            reg.register(_SimpleTool())

    def test_register_replace(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        reg.register(_SimpleTool(), replace=True)
        assert reg.has("simple_tool")

    def test_unregister_tool(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        assert reg.unregister("simple_tool") is True
        assert not reg.has("simple_tool")

    def test_unregister_cleans_aliases(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        assert reg.has("simple")
        reg.unregister("simple_tool")
        assert not reg.has("simple")
        assert not reg.has("st")

    def test_unregister_nonexistent(self) -> None:
        reg = ToolRegistry()
        assert reg.unregister("nonexistent") is False

    def test_get_nonexistent_raises(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(ToolNotFoundError):
            reg.get("nonexistent_tool")

    def test_get_optional_returns_none(self) -> None:
        reg = ToolRegistry()
        assert reg.get_optional("nonexistent_tool") is None

    def test_list_all(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        reg.register(_DocTool())
        names = {t.name for t in reg.list_all()}
        assert "simple_tool" in names
        assert "doc_tool" in names

    def test_list_names(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        assert "simple_tool" in reg.list_names()


class TestCategories:
    def test_list_by_category(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        reg.register(_DocTool())
        reg.register(_WebTool())

        doc_tools = reg.list_by_category(ToolCategory.DOC)
        assert any(t.name == "doc_tool" for t in doc_tools)

        util_tools = reg.list_by_category(ToolCategory.UTIL)
        assert any(t.name == "simple_tool" for t in util_tools)

    def test_get_categories_counts(self) -> None:
        reg = ToolRegistry()
        reg.register(_DocTool())
        counts = reg.get_categories()
        assert counts[ToolCategory.DOC] == 1
        assert counts[ToolCategory.UTIL] == 0


class TestSchemas:
    def test_openai_schema_structure(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        schemas = reg.get_schemas("openai")
        assert len(schemas) == 1
        schema = schemas[0]
        assert schema["type"] == "function"
        assert "function" in schema
        func = schema["function"]
        assert func["name"] == "simple_tool"
        assert "description" in func
        assert "parameters" in func

    def test_anthropic_schema_structure(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        schemas = reg.get_schemas("anthropic")
        assert len(schemas) == 1
        schema = schemas[0]
        assert "name" in schema
        assert schema["name"] == "simple_tool"

    def test_generic_schema_structure(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        schemas = reg.get_schemas("generic")
        assert len(schemas) == 1

    def test_schema_for_specific_tools(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        reg.register(_DocTool())
        schemas = reg.get_schemas("openai", tool_names=["doc_tool"])
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "doc_tool"

    def test_schema_resolves_alias(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        schemas = reg.get_schemas("openai", tool_names=["simple"])
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "simple_tool"

    def test_schema_unknown_tool_raises(self) -> None:
        reg = ToolRegistry()
        with pytest.raises(ToolNotFoundError):
            reg.get_schemas("openai", tool_names=["missing_tool"])


class TestSearch:
    def test_search_by_keyword(self) -> None:
        reg = ToolRegistry()
        reg.register(_DocTool())
        reg.register(_WebTool())
        # search_tools requires a list_all + search_hint matching
        results = reg.search_tools("doc")
        assert any(t.name == "doc_tool" for t in results)

    def test_has_with_alias(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        assert reg.has("simple")
        assert not reg.has("nonexistent_alias")


class TestSelection:
    class _FillerTool(SyncTool):
        description = "irrelevant filler"
        category = ToolCategory.UTIL
        version = "1.0.0"

        def __init__(self, name: str) -> None:
            self.name = name

        @property
        def parameters(self) -> dict[str, Any]:
            return {"type": "object", "properties": {}}

        def execute_sync(self, params: dict[str, Any], context: ToolContext) -> ToolResult:
            return ToolResult.ok({})

    def test_genui_selection_keeps_component_catalog_companion(self) -> None:
        from leagent.tools.canvas.genui_guide import GetGenuiGuideTool
        from leagent.tools.canvas.ui_components import EmitUiTreeTool, ListUiComponentsTool

        reg = ToolRegistry()
        reg.register(EmitUiTreeTool())
        reg.register(GetGenuiGuideTool())
        reg.register(ListUiComponentsTool())

        schemas = reg.get_tools_for_llm(
            provider_format="openai",
            context_hint="dashboard",
            max_tools=1,
        )
        names = {schema["function"]["name"] for schema in schemas}

        assert "emit_ui_tree" in names
        assert "get_genui_guide" in names
        assert "list_ui_components" in names

    def test_chinese_genui_hint_forces_component_catalog_tools(self) -> None:
        from leagent.tools.canvas.genui_guide import GetGenuiGuideTool
        from leagent.tools.canvas.ui_components import EmitUiTreeTool, ListUiComponentsTool

        reg = ToolRegistry()
        for idx in range(30):
            reg.register(self._FillerTool(f"aaa_filler_{idx:02d}"))
        reg.register(EmitUiTreeTool())
        reg.register(GetGenuiGuideTool())
        reg.register(ListUiComponentsTool())

        schemas = reg.get_tools_for_llm(
            provider_format="openai",
            context_hint=(
                "请用 GenUI（聊天里的可视化组件）帮我搭一版中文简历展示稿："
                "分区块（个人信息、教育/工作经历、项目与技能）。"
            ),
            max_tools=5,
        )
        names = {schema["function"]["name"] for schema in schemas}

        assert "emit_ui_tree" in names
        assert "get_genui_guide" in names
        assert "list_ui_components" in names

    def test_canvas_publish_selection_keeps_html_guide_companion(self) -> None:
        from leagent.tools.canvas.canvas_publish import CanvasPublishTool
        from leagent.tools.canvas.html_guide import GetHtmlCanvasGuideTool

        reg = ToolRegistry()
        reg.register(CanvasPublishTool())
        reg.register(GetHtmlCanvasGuideTool())

        schemas = reg.get_tools_for_llm(
            provider_format="openai",
            context_hint="canvas_publish",
            max_tools=1,
        )
        names = {schema["function"]["name"] for schema in schemas}

        assert "canvas_publish" in names
        assert "get_html_canvas_guide" in names

    def test_webpage_hint_forces_publish_and_html_guide(self) -> None:
        from leagent.tools.canvas.canvas_publish import CanvasPublishTool
        from leagent.tools.canvas.html_guide import GetHtmlCanvasGuideTool

        reg = ToolRegistry()
        for idx in range(30):
            reg.register(self._FillerTool(f"aaa_filler_{idx:02d}"))
        reg.register(CanvasPublishTool())
        reg.register(GetHtmlCanvasGuideTool())

        schemas = reg.get_tools_for_llm(
            provider_format="openai",
            context_hint="请生成一个专业的产品落地页，并发布到网页画布。",
            max_tools=5,
        )
        names = {schema["function"]["name"] for schema in schemas}

        assert "canvas_publish" in names
        assert "get_html_canvas_guide" in names

    def test_emit_pet_bubble_always_survives_max_tools_prune(self) -> None:
        """Mascot bubble tool is core — must stay callable under pruning."""
        from leagent.tools.util.pet_bubble import EmitPetBubbleTool

        reg = ToolRegistry()
        for idx in range(40):
            reg.register(self._FillerTool(f"aaa_filler_{idx:02d}"))
        reg.register(EmitPetBubbleTool())

        schemas = reg.get_tools_for_llm(
            provider_format="openai",
            context_hint="帮我写封催款邮件",
            max_tools=8,
        )
        names = {schema["function"]["name"] for schema in schemas}
        assert "emit_pet_bubble" in names


class TestValidation:
    def test_empty_name_raises(self) -> None:
        class _BadTool(SyncTool):
            name = ""
            description = "bad"
            category = ToolCategory.UTIL
            version = "1.0.0"

            @property
            def parameters(self) -> dict[str, Any]:
                return {"type": "object", "properties": {}}

            def execute_sync(self, params: dict, context: ToolContext) -> ToolResult:
                return ToolResult.ok({})

        reg = ToolRegistry()
        with pytest.raises(ToolRegistrationError):
            reg.register(_BadTool())

    def test_empty_description_raises(self) -> None:
        class _BadTool(SyncTool):
            name = "bad_tool"
            description = ""
            category = ToolCategory.UTIL
            version = "1.0.0"

            @property
            def parameters(self) -> dict[str, Any]:
                return {"type": "object", "properties": {}}

            def execute_sync(self, params: dict, context: ToolContext) -> ToolResult:
                return ToolResult.ok({})

        reg = ToolRegistry()
        with pytest.raises(ToolRegistrationError):
            reg.register(_BadTool())

    def test_non_object_schema_raises(self) -> None:
        class _BadTool(SyncTool):
            name = "bad_schema_tool"
            description = "has bad schema"
            category = ToolCategory.UTIL
            version = "1.0.0"

            @property
            def parameters(self) -> dict[str, Any]:
                return {"type": "array"}  # must be "object"

            def execute_sync(self, params: dict, context: ToolContext) -> ToolResult:
                return ToolResult.ok({})

        reg = ToolRegistry()
        with pytest.raises(ToolRegistrationError):
            reg.register(_BadTool())


class TestGetToolsForLlm:
    def test_get_tools_for_llm(self) -> None:
        reg = ToolRegistry()
        reg.register(_SimpleTool())
        reg.register(_DocTool())
        schemas = reg.get_tools_for_llm()
        assert isinstance(schemas, list)
        assert len(schemas) >= 1

    def test_disabled_tool_excluded(self) -> None:
        reg = ToolRegistry()
        tool = _SimpleTool()
        tool.is_enabled = False  # type: ignore[assignment]
        reg.register(tool)
        schemas = reg.get_tools_for_llm()
        names = [s.get("function", {}).get("name", s.get("name", "")) for s in schemas]
        assert "simple_tool" not in names
