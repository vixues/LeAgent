"""Tests for webpage-write policy on code_execution."""

from __future__ import annotations

from uuid import uuid4

import pytest

from leagent.code.markup_guard import (
    WEBPAGE_NEXT_STEP,
    attach_webpage_block,
    source_writes_webpage,
    webpage_paths_in_produced,
)
from leagent.tools.base import ToolContext


@pytest.mark.parametrize(
    ("source", "blocked"),
    [
        ('open("dashboard.html", "w").write(html)', True),
        ("open('page.htm', 'w')", True),
        ('Path("out.html").write_text(body)', True),
        ('open("dashboard.html").read()', False),
        ('open("data.csv", "w").write("a,b")', False),
        ('html = "<!DOCTYPE html><html></html>"\nprint(len(html))', False),
    ],
)
def test_source_writes_webpage(source: str, blocked: bool) -> None:
    assert source_writes_webpage(source) is blocked


def test_webpage_paths_in_produced() -> None:
    assert webpage_paths_in_produced(
        [
            {"path": "stats.json"},
            {"file_path": "dashboard.html"},
            {"path": "chart.png"},
            {"path": "dashboard.html"},
        ]
    ) == ["dashboard.html"]


def test_attach_webpage_block() -> None:
    out = attach_webpage_block({"status": "ok"}, paths=["a.html"])
    assert out["status"] == "error"
    assert out["error_type"] == "validation"
    assert out["blocked_webpage_files"] == ["a.html"]
    assert out["next_step"] == WEBPAGE_NEXT_STEP


@pytest.mark.asyncio
async def test_code_execution_blocks_html_write_source() -> None:
    from leagent.code.execution import CodeExecutionTool

    tool = CodeExecutionTool()
    ctx = ToolContext(user_id=str(uuid4()), session_id=str(uuid4()))
    out = await tool.execute(
        {
            "source": (
                'html = "<!DOCTYPE html><html><body>x</body></html>"\n'
                'open("page.html", "w").write(html)\n'
            ),
        },
        ctx,
    )
    assert out["status"] == "error"
    assert out["error_type"] == "validation"
    assert out["next_step"] == WEBPAGE_NEXT_STEP


@pytest.mark.asyncio
async def test_code_execution_blocks_produced_html() -> None:
    from leagent.code.execution import CodeExecutionTool

    tool = CodeExecutionTool()
    ctx = ToolContext(user_id=str(uuid4()), session_id=str(uuid4()))
    out = await tool.execute(
        {
            "source": (
                "from pathlib import Path\n"
                "p = Path('report').with_suffix('.html')\n"
                "p.write_text('<html><body>ok</body></html>', encoding='utf-8')\n"
            ),
        },
        ctx,
    )
    assert out["status"] == "error"
    assert out["error_type"] == "validation"
    assert out.get("blocked_webpage_files")
    assert out["next_step"] == WEBPAGE_NEXT_STEP
