"""Optional live DeepSeek tests: repo editing via ``project_*`` tools.

Skipped when ``DEEPSEEK_API_KEY`` is unset. Offline coverage lives in
``test_edit_repair_offline.py``.

    uv run pytest tests/integration/test_deepseek_project_edit.py -m live -v
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

from tests.integration.conftest import (
    drive_query_engine,
    requires_live_deepseek,
)
from tests.integration.test_edit_repair_offline import _write_calc_project

pytestmark = [pytest.mark.integration, pytest.mark.live, requires_live_deepseek]


PROJECT_EDIT_PROMPT = """\
The project root is the current working directory. It contains ``calc.py``.

Task: change ``multiply`` so it **adds** numbers instead of multiplying.
Rename the function to ``add`` and update ``main()`` to call ``add(6, 7)``.
Use ``project_read`` first, then ``project_edit`` (one edit is enough).
Do not rewrite the whole file with ``project_write``.

When done, stop calling tools and state the value that ``main()`` would print.
"""


PROJECT_MULTIEDIT_PROMPT = """\
The project has ``constants.py`` with VERSION and BUILD.

Use ``project_read`` on ``constants.py``, then apply **one** ``project_multiedit``
call with two edits in the ``edits`` array:
- change VERSION from 1.0.0 to 2.0.0
- change BUILD from 100 to 200

Do not use ``project_write``. When finished, summarize the new VERSION and BUILD.
"""


PROJECT_PATCH_PROMPT = """\
Read ``calc.py`` with ``project_read``.

Then call ``project_apply_patch`` once with a unified diff that inserts this
docstring as the **first line** of the file (before ``def multiply``):

\"\"\"Calculator helpers.\"\"\"

Use exact file content from ``project_read`` for context lines. Do not use
``project_write``. After the patch succeeds, confirm the docstring is present.
"""


@pytest.fixture()
def calc_project(tmp_path: Path) -> Path:
    project = tmp_path / "mini_calc"
    project.mkdir()
    _write_calc_project(project)
    return project


@pytest.mark.asyncio
async def test_live_deepseek_project_edit_add_function(
    deepseek_llm,
    full_tool_registry,
    calc_project: Path,
) -> None:
    from leagent.agent.coding_agent import build_coding_agent_engine

    engine = build_coding_agent_engine(
        llm=deepseek_llm,
        tools=full_tool_registry,
        project_path=str(calc_project),
        max_turns=10,
        max_tool_calls_per_turn=5,
        temperature=0.1,
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )

    trace = await drive_query_engine(engine, PROJECT_EDIT_PROMPT, timeout=300.0)

    assert trace.final_reason == "completed", (
        f"reason={trace.final_reason}, tools={trace.tool_uses}"
    )
    assert trace.used_tool("project_read")
    assert trace.used_tool("project_edit")

    text = (calc_project / "calc.py").read_text(encoding="utf-8")
    assert "def add(" in text
    assert "multiply" not in text
    assert "add(6, 7)" in text
    assert "13" in trace.final_text.lower()


@pytest.mark.asyncio
async def test_live_deepseek_project_multiedit_constants(
    deepseek_llm,
    full_tool_registry,
    calc_project: Path,
) -> None:
    from leagent.agent.coding_agent import (
        DEFAULT_CODING_AGENT_TOOLS,
        build_coding_agent_engine,
    )

    allowed = tuple(
        n for n in DEFAULT_CODING_AGENT_TOOLS
        if n in {
            "project_read", "project_multiedit", "project_edit",
            "project_write", "project_grep", "project_tree",
        }
    )
    engine = build_coding_agent_engine(
        llm=deepseek_llm,
        tools=full_tool_registry,
        project_path=str(calc_project),
        allowed_tools=allowed,
        max_turns=8,
        max_tool_calls_per_turn=4,
        temperature=0.1,
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )

    trace = await drive_query_engine(
        engine, PROJECT_MULTIEDIT_PROMPT, timeout=240.0,
    )

    assert trace.final_reason == "completed", (
        f"reason={trace.final_reason}, tools={trace.tool_uses}"
    )
    assert trace.used_tool("project_multiedit")

    text = (calc_project / "constants.py").read_text(encoding="utf-8")
    assert 'VERSION = "2.0.0"' in text or "VERSION = '2.0.0'" in text
    assert "BUILD = 200" in text


@pytest.mark.asyncio
async def test_live_deepseek_project_apply_patch_docstring(
    deepseek_llm,
    full_tool_registry,
    calc_project: Path,
) -> None:
    from leagent.agent.coding_agent import build_coding_agent_engine

    engine = build_coding_agent_engine(
        llm=deepseek_llm,
        tools=full_tool_registry,
        project_path=str(calc_project),
        max_turns=8,
        max_tool_calls_per_turn=4,
        temperature=0.1,
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )

    trace = await drive_query_engine(engine, PROJECT_PATCH_PROMPT, timeout=240.0)

    assert trace.final_reason == "completed", (
        f"reason={trace.final_reason}, tools={trace.tool_uses}"
    )
    assert trace.used_tool("project_read")
    assert trace.used_tool("project_apply_patch")

    text = (calc_project / "calc.py").read_text(encoding="utf-8")
    assert text.startswith('"""Calculator helpers."""')
