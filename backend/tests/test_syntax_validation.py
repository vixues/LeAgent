from __future__ import annotations

from pathlib import Path

from leagent.services.syntax_validation import detect_language, validate_syntax
from leagent.tools.base import ToolContext
from leagent.code.syntax import SyntaxValidatorTool


def test_validate_json_reports_line_column_and_patch_frame() -> None:
    result = validate_syntax('{"name": "Ada",\n "age": }', language="json")

    assert result.valid is False
    assert result.language == "json"
    diag = result.diagnostics[0]
    assert diag.line == 2
    assert diag.column > 0
    assert diag.code == "json_syntax_error"
    assert diag.frame
    assert diag.caret.strip() == "^"


def test_validate_json_accepts_valid_document() -> None:
    result = validate_syntax('{"items": [1, 2, 3]}', language="json")

    assert result.valid is True
    assert result.diagnostics == []


def test_validate_python_reports_syntax_error_context() -> None:
    result = validate_syntax("def f():\n    return (\n", language="python")

    assert result.valid is False
    diag = result.diagnostics[0]
    assert diag.line >= 1
    assert diag.code == "python_syntax_error"
    assert diag.frame


def test_detect_language_uses_filename_and_content() -> None:
    assert detect_language(content="print('x')", filename="app.py") == "python"
    assert detect_language(content="{}", filename=None) == "json"
    assert detect_language(content="[project]", filename="pyproject.toml") == "toml"


def test_validate_toml_reports_invalid_document() -> None:
    result = validate_syntax("a =", language="toml")
    assert result.valid is False
    assert result.language == "toml"
    assert result.diagnostics


def test_validate_toml_accepts_valid_document() -> None:
    result = validate_syntax('[tool]\nname = "x"\n', language="toml")
    assert result.valid is True


def test_validate_yaml_reports_error() -> None:
    result = validate_syntax("key: [", language="yaml")
    assert result.valid is False
    assert result.language == "yaml"
    assert result.diagnostics[0].code == "yaml_syntax_error"


def test_validate_yaml_accepts_document() -> None:
    result = validate_syntax("a: 1\nb: [2, 3]\n", language="yaml")
    assert result.valid is True


def test_validate_jsonc_accepts_trailing_comma() -> None:
    result = validate_syntax('{"a": 1,}', language="jsonc")
    assert result.valid is True


def test_validate_jsonc_accepts_line_comment() -> None:
    body = "// header\n{\n  \"x\": 1\n}\n"
    result = validate_syntax(body, language="jsonc")
    assert result.valid is True


def test_validate_json_rejects_trailing_comma() -> None:
    result = validate_syntax('{"a": 1,}', language="json")
    assert result.valid is False


def test_detect_language_yaml_by_extension() -> None:
    assert detect_language(content="x: 1", filename="helm/values.yaml") == "yaml"


def test_detect_language_jsonc_extension() -> None:
    assert detect_language(content="{}", filename="tsconfig.jsonc") == "jsonc"


def test_syntax_validator_tool_validates_inline_content() -> None:
    tool = SyntaxValidatorTool()
    context = ToolContext(user_id=None, session_id=None)

    result = tool.execute_sync(
        {"language": "python", "content": "x = [1, 2\n", "context_lines": 1},
        context,
    )

    assert result["valid"] is False
    assert result["language"] == "python"
    assert result["primary_error"]["line"] >= 1
    assert result["patch_hint"]["start_line"] >= 1
    assert result["patch_hint"]["replacement_target"]


def test_syntax_validator_tool_validates_file(tmp_path: Path) -> None:
    target = tmp_path / "data.json"
    target.write_text('{"ok": true,}', encoding="utf-8")
    tool = SyntaxValidatorTool()
    context = ToolContext(user_id=None, session_id=None)

    result = tool.execute_sync(
        {"language": "auto", "file_path": str(target), "context_lines": 1},
        context,
    )

    assert result["valid"] is False
    assert result["language"] == "json"
    assert result["source"]["kind"] == "file"
    assert result["source"]["file_path"] == str(target)


def test_syntax_validator_hint_filename_steers_yaml(tmp_path: Path) -> None:
    tool = SyntaxValidatorTool()
    context = ToolContext(user_id=None, session_id=None)
    result = tool.execute_sync(
        {
            "language": "auto",
            "content": "version: '3'\nservices:\n  web: {",
            "hint_filename": "compose.yaml",
            "context_lines": 1,
        },
        context,
    )
    assert result["valid"] is False
    assert result["language"] == "yaml"


def test_syntax_validator_rejects_oversized_content() -> None:
    tool = SyntaxValidatorTool()
    context = ToolContext(user_id=None, session_id=None)
    result = tool.execute_sync(
        {
            "language": "python",
            "content": "x" * 5000,
            "max_content_chars": 100,
        },
        context,
    )
    assert result["valid"] is False
    assert result["diagnostics"][0]["code"] == "input_too_large"
