"""DeepSeek-optimized context construction strategies.

Implements context ordering and structuring techniques aligned with the
DeepSeek V4 model architecture:

- **Automatic disk caching**: V4 caches request prefixes automatically.
  Stable system prompts (layers L0-L4) should stay deterministic across
  turns to maximize cache hits.
- **Sparse attention**: high-priority content placed at context boundaries
  (start/end) gets better attention; stable content in the middle is
  KV-cache friendly.
- **1M token context window**: V4 models support up to 1 000 000 tokens.
  Budgets default to a conservative working set but can scale up.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from leagent.memory.compact import approximate_message_content_tokens

logger = logging.getLogger(__name__)

# V4 context window (both deepseek-v4-flash and deepseek-v4-pro).
V4_CONTEXT_WINDOW = 1_000_000


@dataclass
class ContextBlock:
    """A positioned block of context with priority metadata."""
    name: str
    content: str
    priority: float = 0.5
    stability: float = 0.5
    position_hint: str = "middle"  # "start", "middle", "end"
    token_estimate: int = 0


@lru_cache(maxsize=1)
def _tokenizer() -> Any | None:
    try:
        import tiktoken

        try:
            return tiktoken.encoding_for_model("gpt-4o")
        except KeyError:
            return tiktoken.get_encoding("cl100k_base")
    except Exception as exc:  # noqa: BLE001 - token counting must degrade safely
        logger.debug("tiktoken_unavailable_for_deepseek_context", exc_info=exc)
        return None


def estimate_tokens(text: str) -> int:
    """Estimate token count with the configured tokenizer when available."""
    if not text:
        return 0
    tokenizer = _tokenizer()
    if tokenizer is not None:
        return max(1, len(tokenizer.encode(text)))
    return max(1, len(text) // 4)


class DeepSeekContextStrategy:
    """Optimizes context layout for DeepSeek V4 attention patterns and
    automatic disk-cache prefix matching.

    Key principles:

    1. **Start/end boundaries**: high-priority, dynamic content (current task,
       recent user query, latest conversation turns) — these positions get
       stronger attention in sparse/sliding-window architectures.
    2. **Stable middle**: rarely-changing content (system persona, policies,
       user preferences) — maximizes prefix reuse for DeepSeek's automatic
       disk cache.
    3. **Semantic coherence**: messages are chunked so user-assistant pairs
       and tool-call sequences stay together for retrieval.

    The default ``total_budget`` is set conservatively (32 000 tokens).
    For long-document workflows, pass ``model_context_window=V4_CONTEXT_WINDOW``
    to ``compute_budgets`` to unlock the full 1M window.
    """

    def __init__(
        self,
        *,
        total_budget: int = 32_000,
        system_budget_ratio: float = 0.15,
        memory_budget_ratio: float = 0.20,
        conversation_budget_ratio: float = 0.60,
        output_reserve_ratio: float = 0.05,
    ) -> None:
        self._total_budget = total_budget
        self._system_ratio = system_budget_ratio
        self._memory_ratio = memory_budget_ratio
        self._conversation_ratio = conversation_budget_ratio
        self._output_ratio = output_reserve_ratio

    def compute_budgets(self, model_context_window: int | None = None) -> dict[str, int]:
        """Compute token budgets for each context section.

        When *model_context_window* is provided (e.g.
        :data:`V4_CONTEXT_WINDOW`), budgets scale proportionally.
        """
        total = model_context_window or self._total_budget
        return {
            "system": int(total * self._system_ratio),
            "memory": int(total * self._memory_ratio),
            "conversation": int(total * self._conversation_ratio),
            "output_reserve": int(total * self._output_ratio),
        }

    def order_blocks(self, blocks: list[ContextBlock]) -> list[ContextBlock]:
        """Reorder context blocks for optimal attention and cache behavior.

        Layout:
        - **START**: Current task + recent user query (high attention)
        - **EARLY-MIDDLE**: Stable facts, user preferences (KV cache prefix)
        - **LATE-MIDDLE**: Tool history, working set (moderate attention)
        - **END**: Most recent conversation turns (high attention)

        Keeping stable content in the middle also maximizes DeepSeek's
        automatic disk-cache prefix reuse across requests.
        """
        start_blocks: list[ContextBlock] = []
        middle_blocks: list[ContextBlock] = []
        end_blocks: list[ContextBlock] = []

        for block in blocks:
            if block.position_hint == "start" or block.priority > 0.8:
                start_blocks.append(block)
            elif block.position_hint == "end":
                end_blocks.append(block)
            else:
                middle_blocks.append(block)

        start_blocks.sort(key=lambda b: b.priority, reverse=True)
        middle_blocks.sort(key=lambda b: b.stability, reverse=True)
        end_blocks.sort(key=lambda b: b.priority)

        return start_blocks + middle_blocks + end_blocks

    def adapt_budgets_for_query(
        self,
        query: str,
        base_budgets: dict[str, int],
    ) -> dict[str, int]:
        """Dynamically adjust budget proportions based on query type."""
        budgets = dict(base_budgets)
        query_lower = query.lower()

        file_keywords = {"file", "read", "edit", "write", "code", "function", "class", "import"}
        recall_keywords = {"remember", "earlier", "before", "previous", "last time", "history"}

        file_score = sum(1 for kw in file_keywords if kw in query_lower)
        recall_score = sum(1 for kw in recall_keywords if kw in query_lower)

        if file_score > recall_score and file_score > 0:
            shift = budgets["memory"] // 4
            budgets["conversation"] += shift
            budgets["memory"] -= shift
        elif recall_score > file_score and recall_score > 0:
            shift = budgets["conversation"] // 4
            budgets["memory"] += shift
            budgets["conversation"] -= shift

        return budgets

    def chunk_for_retrieval(
        self,
        messages: list[dict[str, Any]],
        *,
        max_chunk_tokens: int = 500,
    ) -> list[list[dict[str, Any]]]:
        """Group messages into semantically coherent chunks.

        Keeps user-assistant pairs together and avoids splitting
        tool call sequences mid-execution.
        """
        chunks: list[list[dict[str, Any]]] = []
        current_chunk: list[dict[str, Any]] = []
        current_tokens = 0

        for msg in messages:
            raw = msg.get("content", "")
            role_lc = str(msg.get("role") or "").strip().lower()
            msg_tokens = approximate_message_content_tokens(
                raw,
                chars_per_token=4.0,
                message_role=role_lc or None,
            )
            if msg_tokens < 1 and raw not in (None, "", []):
                msg_tokens = 1

            if (
                current_tokens + msg_tokens > max_chunk_tokens
                and current_chunk
                and msg.get("role") != "tool"
            ):
                chunks.append(current_chunk)
                current_chunk = []
                current_tokens = 0

            current_chunk.append(msg)
            current_tokens += msg_tokens

        if current_chunk:
            chunks.append(current_chunk)

        return chunks
