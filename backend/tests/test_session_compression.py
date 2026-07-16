"""Tests for session transcript compression helpers."""

from __future__ import annotations

import json
from uuid import uuid4

import pytest

from leagent.context.compression import (
    CompressionConfig,
    ProgressiveCompressor,
    compress_tool_result,
)
from leagent.context.session_compression import (
    merge_compressed_with_session_tail,
    run_session_compression_pipeline,
)
from leagent.memory.compact import _approximate_tokens
from leagent.services.session.state import SessionMessage


def test_apply_progressive_transcript_compress_smoke() -> None:
    from leagent.config.settings import Settings

    from leagent.context.session_compression import apply_progressive_transcript_compress

    settings = Settings()
    huge = "x" * 50_000
    msgs = [{"role": "tool", "content": huge, "tool_call_id": "t1"}]
    for i in range(20):
        msgs.append({"role": "user", "content": f"u{i}"})
        msgs.append({"role": "assistant", "content": f"a{i}" * 120})
    out = apply_progressive_transcript_compress(
        msgs, settings=settings, budget_tokens=2_000
    )
    assert len(out) == len(msgs)
    assert out[0].get("tool_call_id") == "t1"
    assert len(out[0].get("content", "")) < len(huge)


def test_approximate_tokens_includes_vision_blocks() -> None:
    msgs = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "describe this"},
                {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
            ],
        },
    ]
    assert _approximate_tokens(msgs) >= 500


def test_approximate_tokens_skips_vision_for_assistant_multimodal() -> None:
    """Code/model-generated image parts on assistant turns must not add vision budget."""
    msgs = [
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "here is the chart"},
                {"type": "image_url", "image_url": {"url": "https://example.com/out.png"}},
            ],
        },
    ]
    assert _approximate_tokens(msgs) < 200


def test_compress_turn_accepts_multimodal_list() -> None:
    from leagent.context.compression import compress_turn

    long_text = "x" * 400
    out = compress_turn(
        "user",
        [
            {"type": "text", "text": long_text},
            {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
        ],
        max_chars=300,
    )
    assert out.startswith("[user intent]")


def test_merge_compressed_preserves_tail_session_ids() -> None:
    u1 = SessionMessage(role="user", content="hello", id=uuid4())
    a1 = SessionMessage(role="assistant", content="hi", id=uuid4())
    orig = [u1, a1]
    final_dicts = [
        {"role": "system", "content": "<compacted_history>\nx\n</compacted_history>"},
        {"role": "user", "content": "hello", "id": str(u1.id)},
        {"role": "assistant", "content": "hi", "id": str(a1.id)},
    ]
    out = merge_compressed_with_session_tail(orig, final_dicts)
    assert len(out) == 3
    assert out[0].role == "system"
    assert "<compacted_history>" in out[0].content
    assert out[1].id == u1.id
    assert out[2].id == a1.id


def test_merge_compressed_overlay_preserves_attachment_ids() -> None:
    uid = uuid4()
    u1 = SessionMessage(
        role="user",
        content="hello",
        id=uid,
        attachment_ids=["att-1"],
    )
    orig = [u1]
    final_dicts = [
        {
            "role": "user",
            "content": "hello [trimmed]",
            "id": str(uid),
            "attachment_ids": ["should-not-replace"],
        },
    ]
    out = merge_compressed_with_session_tail(orig, final_dicts)
    assert len(out) == 1
    assert out[0].id == uid
    assert out[0].content == "hello [trimmed]"
    assert out[0].attachment_ids == ["att-1"]


def test_compress_tool_result_preserves_changed_files_for_subagent_json() -> None:
    paths = [f"/proj/src/module_{i}.py" for i in range(40)]
    payload = {
        "success": True,
        "partial": False,
        "text": "x" * 50_000,
        "steps_count": 12,
        "changed_files": paths,
        "activity": [{"tool": "project_edit", "path": p} for p in paths[:5]],
    }
    raw = json.dumps(payload)
    out = compress_tool_result(raw, max_chars=200)
    parsed = json.loads(out)
    assert parsed["success"] is True
    assert len(parsed["changed_files"]) == 40
    assert all("/proj/src/module_" in p for p in parsed["changed_files"])
    assert "text" in parsed
    assert len(parsed["text"]) < len(payload["text"])


def test_compress_tool_result_engineering_respects_budget_in_compressor() -> None:
    cfg = CompressionConfig(tool_result_max_chars=200, min_recent_turns=4)
    huge = json.dumps(
        {
            "success": True,
            "text": "y" * 30_000,
            "steps_count": 3,
            "changed_files": [f"/x/{i}.ts" for i in range(100)],
        }
    )
    msgs: list[dict[str, str]] = [{"role": "tool", "content": huge}]
    msgs += [
        pair
        for _ in range(15)
        for pair in (
            {"role": "user", "content": "ping"},
            {"role": "assistant", "content": "pong"},
        )
    ]
    pc = ProgressiveCompressor(cfg)
    out = pc.compress(msgs, budget_tokens=800)
    tool_msgs = [m for m in out if m.role == "tool"]
    assert tool_msgs
    parsed = json.loads(tool_msgs[0].content)
    assert "changed_files" in parsed
    assert len(parsed["changed_files"]) >= 24


@pytest.mark.asyncio
async def test_compact_pipeline_merge_preserves_message_ids() -> None:
    """Microtruncate must not break merge: ids round-trip via overlay."""
    from leagent.config.settings import Settings

    from leagent.context.session_compression import (
        merge_compressed_with_session_tail,
        run_session_compression_pipeline,
        session_messages_to_compact_llm_dicts,
    )

    settings = Settings()
    uid = uuid4()
    aid = uuid4()
    tid = uuid4()
    huge = "z" * 50_000
    orig = [
        SessionMessage(role="user", content="q", id=uid),
        SessionMessage(
            role="assistant",
            content="",
            id=aid,
            tool_calls=[
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "x", "arguments": "{}"},
                }
            ],
        ),
        SessionMessage(role="tool", content=huge, id=tid, tool_call_id="c1"),
    ]
    llm_msgs = session_messages_to_compact_llm_dicts(orig)
    result = await run_session_compression_pipeline(
        llm_msgs,
        settings=settings,
        llm=None,
        force_llm=False,
        budget_tokens=500_000,
    )
    merged = merge_compressed_with_session_tail(orig, result.messages)
    by_id = {str(m.id): m for m in merged}
    assert by_id[str(uid)].content == "q"
    assert by_id[str(aid)].tool_calls
    assert str(tid) in by_id
    assert "truncated" in by_id[str(tid)].content or len(by_id[str(tid)].content) < len(huge)


@pytest.mark.asyncio
async def test_pipeline_progressive_merge_preserves_tool_call_id() -> None:
    """OpenAI-compatible providers require ``tool_call_id`` on every ``role: tool`` message."""
    from leagent.config.settings import Settings

    settings = Settings()
    huge = "x" * 50_000
    llm_msgs: list[dict[str, Any]] = [
        {"role": "tool", "content": huge, "tool_call_id": "tc_keep_me"},
    ]
    for i in range(20):
        llm_msgs.append({"role": "user", "content": f"u{i}"})
        llm_msgs.append({"role": "assistant", "content": f"a{i}" * 120})

    result = await run_session_compression_pipeline(
        llm_msgs,
        settings=settings,
        llm=None,
        force_llm=False,
        budget_tokens=2_000,
    )
    for m in result.messages:
        if m.get("role") == "tool":
            assert m.get("tool_call_id"), f"missing tool_call_id on tool message: {m!r}"


@pytest.mark.asyncio
async def test_pipeline_trims_large_tool_result_without_llm() -> None:
    from leagent.config.settings import Settings

    settings = Settings()
    huge = "x" * 50_000
    llm_msgs = [
        {"role": "user", "content": "ping"},
        {"role": "assistant", "content": "call"},
        {"role": "tool", "content": huge, "tool_call_id": "tc1"},
        {"role": "assistant", "content": "done"},
    ]
    result = await run_session_compression_pipeline(
        llm_msgs,
        settings=settings,
        llm=None,
        force_llm=False,
        budget_tokens=500_000,
    )
    assert result.approx_tokens_after < result.approx_tokens_before
    assert "microcompact" in result.stages_applied
    assert not result.llm_autocompact_applied


def test_compress_tool_result_preserves_source_echo() -> None:
    payload = json.dumps({
        "status": "error",
        "error": "ModuleNotFoundError: No module named 'IPython'",
        "source_echo": "import IPython\nprint('hello')\n",
        "stdout": "",
        "stderr": "traceback...",
    })
    out = compress_tool_result(payload, max_chars=50)
    assert "source_echo=" in out
    assert "import IPython" in out


def test_progressive_rolling_summary_does_not_orphan_tool_rows() -> None:
    """Protected suffix must include the owning assistant when it would start on tool."""
    from leagent.context.compression import CompressionConfig, ProgressiveCompressor
    from leagent.context.session_compression import _progressive_output_dicts

    # Build a long transcript so rolling summary fires; place a tool block
    # just before the naive protected window so an unsnapped split orphans it.
    messages: list[dict[str, Any]] = []
    for i in range(12):
        messages.append({"role": "user", "content": f"u{i} " + ("x" * 400)})
        messages.append({"role": "assistant", "content": f"a{i} " + ("y" * 400)})
    messages.append(
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-keep",
                    "type": "function",
                    "function": {"name": "echo", "arguments": "{}"},
                },
            ],
        }
    )
    messages.append({"role": "tool", "tool_call_id": "call-keep", "content": "z" * 800})
    for i in range(3):
        messages.append({"role": "user", "content": f"follow-{i}"})
        messages.append({"role": "assistant", "content": f"ack-{i}"})
    messages.append({"role": "user", "content": "final"})
    # Naive keep = last 8 → starts at the tool row (owning assistant is older).
    protected = CompressionConfig().min_recent_turns * 2
    assert messages[-protected]["role"] == "tool"

    cfg = CompressionConfig(min_recent_turns=4)
    pc = ProgressiveCompressor(cfg)
    cms = pc.compress(messages, budget_tokens=500)
    out = _progressive_output_dicts(messages, cfg, cms)

    for i, m in enumerate(out):
        if m.get("role") != "tool":
            continue
        assert i > 0, "tool at head of compressed transcript"
        prev = out[i - 1]
        assert prev.get("role") == "assistant", f"tool preceded by {prev.get('role')!r}"
        tcs = prev.get("tool_calls") or []
        ids = {
            (tc.get("id") if isinstance(tc, dict) else None) for tc in tcs
        }
        assert m.get("tool_call_id") in ids
        assert "tool_calls" in prev


@pytest.mark.asyncio
async def test_token_usage_to_api_dict_includes_cache_when_set() -> None:
    from leagent.llm.base import TokenUsage, token_usage_to_api_dict

    u = TokenUsage(
        prompt_tokens=100,
        completion_tokens=10,
        total_tokens=110,
        prompt_cache_hit_tokens=40,
        prompt_cache_miss_tokens=60,
    )
    d = token_usage_to_api_dict(u)
    assert d["prompt_cache_hit_tokens"] == 40
    assert d["prompt_cache_miss_tokens"] == 60
