from __future__ import annotations

from leagent.context.strategies.deepseek import (
    DeepSeekContextStrategy,
    V4_CONTEXT_WINDOW,
    estimate_tokens,
)


def test_estimate_tokens_uses_tokenizer_for_cjk_text() -> None:
    text = "你好，世界"

    assert estimate_tokens(text) > len(text) // 4


def test_chunk_for_retrieval_uses_token_budget() -> None:
    strategy = DeepSeekContextStrategy()
    messages = [
        {"role": "user", "content": "alpha " * 20},
        {"role": "assistant", "content": "beta " * 20},
        {"role": "user", "content": "gamma " * 20},
    ]

    chunks = strategy.chunk_for_retrieval(messages, max_chunk_tokens=10)

    assert len(chunks) == 3
    assert chunks[0][0]["content"].startswith("alpha")


def test_v4_context_window_constant() -> None:
    assert V4_CONTEXT_WINDOW == 1_000_000


def test_default_budget_is_conservative() -> None:
    strategy = DeepSeekContextStrategy()
    budgets = strategy.compute_budgets()
    total = sum(budgets.values())
    assert total <= 32_000


def test_budget_scales_with_context_window() -> None:
    strategy = DeepSeekContextStrategy()
    budgets = strategy.compute_budgets(model_context_window=V4_CONTEXT_WINDOW)
    total = sum(budgets.values())
    assert total == V4_CONTEXT_WINDOW


def test_order_blocks_places_stable_content_in_middle() -> None:
    from leagent.context.strategies.deepseek import ContextBlock

    blocks = [
        ContextBlock(name="task", content="current task", priority=0.9, stability=0.1, position_hint="start"),
        ContextBlock(name="persona", content="system persona", priority=0.3, stability=0.9, position_hint="middle"),
        ContextBlock(name="history", content="recent turns", priority=0.5, stability=0.2, position_hint="end"),
    ]

    strategy = DeepSeekContextStrategy()
    ordered = strategy.order_blocks(blocks)

    assert ordered[0].name == "task"
    assert ordered[1].name == "persona"
    assert ordered[2].name == "history"
