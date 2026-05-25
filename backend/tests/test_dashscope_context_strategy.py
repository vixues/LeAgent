"""Tests for DashScopeContextStrategy."""

from __future__ import annotations

import pytest

from leagent.context.strategies.dashscope import (
    QWEN_DEFAULT_CONTEXT_WINDOW,
    QWEN_LONG_CONTEXT_WINDOW,
    ContextBlock,
    DashScopeContextStrategy,
    estimate_tokens,
)


class TestDashScopeContextStrategyBudgets:
    def test_default_budgets_sum_correctly(self) -> None:
        s = DashScopeContextStrategy()
        budgets = s.compute_budgets()
        total = sum(budgets.values())
        assert total <= s._total_budget
        assert "system" in budgets
        assert "memory" in budgets
        assert "conversation" in budgets
        assert "output_reserve" in budgets

    def test_budgets_scale_with_model_window(self) -> None:
        s = DashScopeContextStrategy()
        default_b = s.compute_budgets()
        large_b = s.compute_budgets(model_context_window=QWEN_DEFAULT_CONTEXT_WINDOW)
        assert large_b["conversation"] > default_b["conversation"]

    def test_long_context_budget(self) -> None:
        s = DashScopeContextStrategy()
        b = s.compute_budgets(model_context_window=QWEN_LONG_CONTEXT_WINDOW)
        assert b["conversation"] > 100_000

    def test_adapt_budgets_for_file_query(self) -> None:
        s = DashScopeContextStrategy()
        base = s.compute_budgets()
        adapted = s.adapt_budgets_for_query("read the file main.py", base)
        assert adapted["conversation"] >= base["conversation"]

    def test_adapt_budgets_for_recall_query(self) -> None:
        s = DashScopeContextStrategy()
        base = s.compute_budgets()
        adapted = s.adapt_budgets_for_query("remember what we discussed earlier", base)
        assert adapted["memory"] >= base["memory"]

    def test_adapt_budgets_neutral_query(self) -> None:
        s = DashScopeContextStrategy()
        base = s.compute_budgets()
        adapted = s.adapt_budgets_for_query("hello world", base)
        assert adapted == base


class TestDashScopeContextStrategyBlockOrdering:
    def test_high_priority_blocks_at_start(self) -> None:
        s = DashScopeContextStrategy()
        blocks = [
            ContextBlock(name="low", content="...", priority=0.3, position_hint="middle"),
            ContextBlock(name="high", content="...", priority=0.9, position_hint="start"),
            ContextBlock(name="end", content="...", priority=0.5, position_hint="end"),
        ]
        ordered = s.order_blocks(blocks)
        assert ordered[0].name == "high"
        assert ordered[-1].name == "end"

    def test_stable_blocks_in_middle(self) -> None:
        s = DashScopeContextStrategy()
        blocks = [
            ContextBlock(name="stable", content="...", stability=0.9, position_hint="middle"),
            ContextBlock(name="volatile", content="...", stability=0.1, position_hint="middle"),
            ContextBlock(name="task", content="...", priority=0.9, position_hint="start"),
        ]
        ordered = s.order_blocks(blocks)
        names = [b.name for b in ordered]
        assert names.index("stable") < names.index("volatile")

    def test_empty_blocks_list(self) -> None:
        s = DashScopeContextStrategy()
        assert s.order_blocks([]) == []


class TestDashScopeContextStrategyChunking:
    def test_basic_chunking(self) -> None:
        s = DashScopeContextStrategy()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]
        chunks = s.chunk_for_retrieval(messages, max_chunk_tokens=10)
        assert len(chunks) >= 1
        total_messages = sum(len(c) for c in chunks)
        assert total_messages == 3

    def test_tool_messages_not_split(self) -> None:
        s = DashScopeContextStrategy()
        messages = [
            {"role": "assistant", "content": "Let me check.", "tool_calls": [{"id": "c1"}]},
            {"role": "tool", "content": "result", "tool_call_id": "c1"},
            {"role": "user", "content": "Thanks"},
        ]
        chunks = s.chunk_for_retrieval(messages, max_chunk_tokens=5)
        for chunk in chunks:
            roles = [m["role"] for m in chunk]
            if "tool" in roles:
                assert "assistant" in roles or chunk[0]["role"] == "tool"

    def test_empty_messages(self) -> None:
        s = DashScopeContextStrategy()
        chunks = s.chunk_for_retrieval([])
        assert chunks == []


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        assert estimate_tokens("") == 0

    def test_nonempty_string(self) -> None:
        result = estimate_tokens("Hello, world!")
        assert result > 0

    def test_long_string(self) -> None:
        text = "word " * 1000
        result = estimate_tokens(text)
        assert result > 100
