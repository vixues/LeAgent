"""CompactService: Coordinates three-layer context compression.

Layer 1 — autoCompact: Triggered when token count exceeds a threshold.
          Summarises old messages via an LLM call.
Layer 2 — snipCompact: Removes zombie / stale messages.
Layer 3 — contextCollapse: Restructures context for efficiency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from leagent.agent.base import ConversationContext
    from leagent.llm.service import LLMService

logger = structlog.get_logger(__name__)

# Token thresholds
AUTO_COMPACT_TRIGGER = 12_000   # trigger auto-summarise above this
AUTO_COMPACT_TARGET = 6_000     # target after compaction
SNIP_COMPACT_TRIGGER = 8_000    # remove stale markers above this


class CompactService:
    """Coordinates context window compression strategies.

    Usage:
        compact_svc = CompactService(llm_service=llm)
        await compact_svc.maybe_compact(conversation)
    """

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self.llm = llm_service

    def _count_tokens(self, conversation: ConversationContext) -> int:
        """Estimate token count for a conversation.

        Uses character-based approximation (1 token ≈ 3 chars).
        """
        return conversation.token_estimate

    async def maybe_compact(self, conversation: ConversationContext) -> bool:
        """Run all compaction layers if necessary.

        Returns True if any compaction was applied.
        """
        changed = False
        tokens = self._count_tokens(conversation)

        if tokens > AUTO_COMPACT_TRIGGER:
            changed = await self._auto_compact(conversation) or changed

        if tokens > SNIP_COMPACT_TRIGGER:
            changed = self._snip_compact(conversation) or changed

        return changed

    async def _auto_compact(self, conversation: ConversationContext) -> bool:
        """Summarise old turns via LLM to reclaim context budget.

        The oldest half of the conversation is summarised into a single
        system-level summary message, then truncated.  Messages that
        contain the original user intent for artifact generation are
        preserved so that regeneration attempts have access to the
        original specification.
        """
        messages = conversation.messages
        if len(messages) < 4:
            return False

        split = len(messages) // 2
        to_summarise = messages[:split]
        to_keep = messages[split:]

        preserved = self._extract_artifact_intent_messages(to_summarise)
        if preserved:
            to_summarise = [m for m in to_summarise if m not in preserved]

        if not self.llm:
            conversation.messages = preserved + list(to_keep)
            logger.info(
                "auto_compact_trim",
                kept=len(to_keep),
                removed=split - len(preserved),
                preserved_intent=len(preserved),
            )
            return True

        try:
            summary_prompt = (
                "Summarise the following conversation history concisely, "
                "preserving all important facts, decisions, and context:\n\n"
                + "\n".join(
                    f"{m.role}: {m.content[:500]}"
                    for m in to_summarise
                    if m.content
                )
            )
            resp = await self.llm.chat(
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.0,
                task="compression",
            )
            summary_text = resp.get("content", "")

            from leagent.agent.base import ConversationMessage
            summary_msg = ConversationMessage(
                role="system",
                content=f"[Summary of earlier conversation]\n{summary_text}",
            )
            conversation.messages = [summary_msg] + preserved + list(to_keep)
            logger.info(
                "auto_compact_summarised",
                removed=split - len(preserved),
                kept=len(to_keep),
                preserved_intent=len(preserved),
                summary_len=len(summary_text),
            )
            return True
        except Exception as e:
            logger.warning("auto_compact_failed", error=str(e))
            conversation.messages = preserved + list(to_keep)
            return True

    @staticmethod
    def _extract_artifact_intent_messages(
        messages: list[Any],
    ) -> list[Any]:
        """Find user messages that precede artifact-producing tool calls.

        These carry the original generation intent and should survive
        compaction so the agent can regenerate from scratch if needed.
        """
        _ARTIFACT_TOOLS = {
            "emit_ui_tree", "emit_ui_patch", "canvas_publish",
            "code_execution", "python_run", "run_code", "exec_python",
        }
        intent_indices: set[int] = set()
        for idx, msg in enumerate(messages):
            if not getattr(msg, "tool_calls", None):
                continue
            for tc in msg.tool_calls:
                name = (
                    tc.get("name")
                    or tc.get("function", {}).get("name", "")
                    if isinstance(tc, dict)
                    else getattr(tc, "name", "")
                )
                if name in _ARTIFACT_TOOLS:
                    for back in range(idx - 1, -1, -1):
                        if getattr(messages[back], "role", "") == "user":
                            intent_indices.add(back)
                            break
                    break
        return [messages[i] for i in sorted(intent_indices)]

    def _snip_compact(self, conversation: ConversationContext) -> bool:
        """Remove zombie / stale messages from the conversation.

        Zombie messages are:
        - Tool result messages where the corresponding tool_call is gone.
        - Duplicate consecutive messages of the same role/content.
        """
        messages = conversation.messages
        if len(messages) < 2:
            return False

        # Collect all tool_call ids that are still referenced
        active_tool_call_ids: set[str] = set()
        for msg in messages:
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    tc_id = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                    if tc_id:
                        active_tool_call_ids.add(tc_id)

        filtered = []
        seen_hashes: set[str] = set()

        for msg in messages:
            # Drop orphaned tool results
            if msg.tool_call_id and msg.tool_call_id not in active_tool_call_ids:
                continue

            # Drop duplicate consecutive messages
            h = f"{msg.role}:{(msg.content or '')[:200]}"
            if h in seen_hashes:
                continue
            seen_hashes.add(h)
            filtered.append(msg)

        if len(filtered) < len(messages):
            conversation.messages = filtered
            logger.info(
                "snip_compact",
                removed=len(messages) - len(filtered),
                kept=len(filtered),
            )
            return True
        return False

    def context_collapse(self, conversation: ConversationContext) -> bool:
        """Restructure context by keeping only the most recent N turns.

        This is the last-resort compaction: drop everything except the
        system prompt and the most recent ``min_turns_to_keep`` turns.
        """
        min_keep = 4
        if len(conversation.messages) <= min_keep * 2:
            return False

        conversation.messages = conversation.messages[-(min_keep * 2):]
        logger.info("context_collapse", kept=len(conversation.messages))
        return True
