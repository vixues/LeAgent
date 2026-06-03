"""Offline integration: edit / repair workflows without any LLM API key.

These tests drive the real ``QueryEngine`` tool dispatch path with a
scripted ``call_model`` that emits deterministic tool calls. They validate
the same interfaces exercised by optional ``live`` tests in sibling files.
"""

from __future__ import annotations

import textwrap
import uuid
from pathlib import Path

import pytest

from tests.integration.conftest import (
    EngineTrace,
    drive_query_engine,
    make_scripted_deps,
    scripted_text_turn,
    scripted_turn,
)

pytestmark = pytest.mark.integration

BROKEN_SOURCE = (
    "def add_values():\n"
    "    return 17 + 25\n"
    "\n"
    "print(add_values()\n"
)


@pytest.fixture()
def calc_project(tmp_path: Path) -> Path:
    project = tmp_path / "mini_calc"
    project.mkdir()
    _write_calc_project(project)
    return project


@pytest.mark.asyncio
async def test_offline_script_repair_via_workspace_edit(
    full_tool_registry,
    tmp_path: Path,
) -> None:
    from leagent.agent.script_agent import build_script_agent_engine

    script = [
        scripted_turn(
            {
                "id": "ce_fail",
                "name": "code_execution",
                "arguments": {"source": BROKEN_SOURCE},
            },
        ),
        scripted_turn(
            {
                "id": "cw_fix",
                "name": "code_workspace_edit",
                "arguments": {
                    "path": "__last_source__.py",
                    "old_string": "print(add_values()",
                    "new_string": "print(add_values())",
                },
            },
        ),
        scripted_turn(
            {
                "id": "ce_ok",
                "name": "code_execution",
                "arguments": {
                    "workspace_file": "__last_source__.py",
                    "timeout_sec": 15.0,
                },
            },
        ),
        scripted_text_turn("The printed result is 42."),
    ]

    engine = build_script_agent_engine(
        llm=None,
        tools=full_tool_registry,
        cwd=str(tmp_path),
        max_turns=8,
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        deps=make_scripted_deps(script),
    )

    trace = await drive_query_engine(engine, "repair the broken script", timeout=60.0)
    _assert_script_repair_trace(trace)


@pytest.mark.asyncio
async def test_offline_project_edit_add_function(
    full_tool_registry,
    calc_project: Path,
) -> None:
    from leagent.agent.coding_agent import build_coding_agent_engine

    old_block = (
        "def multiply(a, b):\n"
        "    return a * b\n"
        "\n"
        "\n"
        "def main():\n"
        "    print(multiply(6, 7))"
    )
    new_block = (
        "def add(a, b):\n"
        "    return a + b\n"
        "\n"
        "\n"
        "def main():\n"
        "    print(add(6, 7))"
    )

    script = [
        scripted_turn(
            {"id": "read1", "name": "project_read", "arguments": {"path": "calc.py"}},
        ),
        scripted_turn(
            {
                "id": "edit1",
                "name": "project_edit",
                "arguments": {
                    "path": "calc.py",
                    "old_string": old_block,
                    "new_string": new_block,
                },
            },
        ),
        scripted_text_turn("After the edit, main() prints 13."),
    ]

    engine = build_coding_agent_engine(
        llm=None,
        tools=full_tool_registry,
        project_path=str(calc_project),
        max_turns=6,
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        deps=make_scripted_deps(script),
    )

    trace = await drive_query_engine(engine, "refactor multiply to add", timeout=60.0)

    assert trace.final_reason == "completed"
    assert trace.tool_use_count("project_edit") == 1
    text = (calc_project / "calc.py").read_text(encoding="utf-8")
    assert "def add(" in text and "multiply" not in text
    assert "13" in trace.final_text


@pytest.mark.asyncio
async def test_offline_project_multiedit_constants(
    full_tool_registry,
    calc_project: Path,
) -> None:
    from leagent.agent.coding_agent import build_coding_agent_engine

    script = [
        scripted_turn(
            {
                "id": "read_c",
                "name": "project_read",
                "arguments": {"path": "constants.py"},
            },
        ),
        scripted_turn(
            {
                "id": "me1",
                "name": "project_multiedit",
                "arguments": {
                    "path": "constants.py",
                    "edits": [
                        {
                            "old_string": 'VERSION = "1.0.0"',
                            "new_string": 'VERSION = "2.0.0"',
                        },
                        {
                            "old_string": "BUILD = 100",
                            "new_string": "BUILD = 200",
                        },
                    ],
                },
            },
        ),
        scripted_text_turn("VERSION is 2.0.0 and BUILD is 200."),
    ]

    engine = build_coding_agent_engine(
        llm=None,
        tools=full_tool_registry,
        project_path=str(calc_project),
        max_turns=6,
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        deps=make_scripted_deps(script),
    )

    trace = await drive_query_engine(engine, "bump version constants", timeout=60.0)

    assert trace.final_reason == "completed"
    assert trace.used_tool("project_multiedit")
    text = (calc_project / "constants.py").read_text(encoding="utf-8")
    assert 'VERSION = "2.0.0"' in text
    assert "BUILD = 200" in text


@pytest.mark.asyncio
async def test_offline_project_apply_patch_docstring(
    full_tool_registry,
    calc_project: Path,
) -> None:
    from leagent.agent.coding_agent import build_coding_agent_engine

    patch_diff = (
        "--- a/calc.py\n"
        "+++ b/calc.py\n"
        "@@ -1,0 +1,1 @@\n"
        '+"""Calculator helpers."""\n'
        " def multiply(a, b):\n"
    )

    script = [
        scripted_turn(
            {"id": "read_p", "name": "project_read", "arguments": {"path": "calc.py"}},
        ),
        scripted_turn(
            {
                "id": "patch1",
                "name": "project_apply_patch",
                "arguments": {"diff": patch_diff},
            },
        ),
        scripted_text_turn('Added docstring """Calculator helpers."""'),
    ]

    engine = build_coding_agent_engine(
        llm=None,
        tools=full_tool_registry,
        project_path=str(calc_project),
        max_turns=6,
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        deps=make_scripted_deps(script),
    )

    trace = await drive_query_engine(engine, "add module docstring", timeout=60.0)

    assert trace.final_reason == "completed"
    assert trace.used_tool("project_apply_patch")
    text = (calc_project / "calc.py").read_text(encoding="utf-8")
    assert text.startswith('"""Calculator helpers."""')


def _write_calc_project(project: Path) -> None:
    (project / "calc.py").write_text(
        textwrap.dedent(
            """\
            def multiply(a, b):
                return a * b


            def main():
                print(multiply(6, 7))


            if __name__ == "__main__":
                main()
            """
        ),
        encoding="utf-8",
    )
    (project / "constants.py").write_text(
        'VERSION = "1.0.0"\nBUILD = 100\n',
        encoding="utf-8",
    )


def _assert_script_repair_trace(trace: EngineTrace) -> None:
    assert trace.final_reason == "completed", (
        f"expected completed, got {trace.final_reason!r}; tools={trace.tool_uses}"
    )
    assert trace.tool_use_count("code_execution") >= 2
    assert trace.used_tool("code_workspace_edit")
    assert "42" in trace.final_text.lower()
