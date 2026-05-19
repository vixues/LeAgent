"""Microcompact / autocompact implementations used by ``query()``.

- **microcompact** is applied every turn and trims oversized tool_result
  payloads so they don't dominate the context window.
- **autocompact** kicks in when the cumulative token count exceeds a
  configured threshold; it summarises the oldest assistant/tool turns via
  the tier2 LLM and replaces them with a compact summary message.

Both helpers are intentionally conservative: if the LLM call fails for any
reason we fall back to the identity transform, because losing a turn is much
worse than hitting a context-size error.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

import structlog

from leagent.agent.deps import Autocompact, Microcompact

if TYPE_CHECKING:
    from leagent.agent.tool_use_context import ToolUseContext
    from leagent.llm import LLMService

logger = structlog.get_logger(__name__)

DEFAULT_TOOL_RESULT_BUDGET_CHARS = 8_000
AUTOCOMPACT_TOKEN_THRESHOLD = 24_000
AUTOCOMPACT_SUMMARY_RESERVE = 4_000
AUTOCOMPACT_KEEP_RECENT = 6

_FALLBACK_SUMMARISER_PROMPT = (
    "You are a transcript summariser. Produce a concise bulleted summary "
    "of the conversation below that preserves every decision, file path, "
    "artefact name, and numeric result. Respond with the summary only."
)

_SUMMARISER_PROMPT_CACHE: str | None = None


def _load_summariser_prompt() -> str:
    """Fetch the ``compact_summariser`` template from the prompt registry.

    Falls back to the legacy inline string if the registry / template
    file is unavailable (e.g. in a test harness that mocks out
    :mod:`leagent.prompts`). This keeps autocompact behaviour a
    no-worse-than-before when the new plumbing fails, instead of
    crashing the whole query loop.
    """
    global _SUMMARISER_PROMPT_CACHE
    if _SUMMARISER_PROMPT_CACHE is not None:
        return _SUMMARISER_PROMPT_CACHE
    try:
        from leagent.prompts import get_prompt_registry

        variant = get_prompt_registry().get("compact_summariser")
        body = (variant.body or "").strip()
        _SUMMARISER_PROMPT_CACHE = body or _FALLBACK_SUMMARISER_PROMPT
        return _SUMMARISER_PROMPT_CACHE
    except Exception as exc:  # noqa: BLE001 — optional dependency
        logger.debug("compact_summariser_template_missing", error=str(exc))
        _SUMMARISER_PROMPT_CACHE = _FALLBACK_SUMMARISER_PROMPT
        return _SUMMARISER_PROMPT_CACHE


def snap_autocompact_split(messages: list[dict[str, Any]], split: int) -> int:
    """Pull the autocompact window start backward so the tail never begins with ``tool``.

    Providers reject histories where a ``tool`` message is not immediately preceded
    by an ``assistant`` message that declares matching ``tool_calls``. Autocompact
    keeps the last ``keep_recent`` messages; if that slice would start inside a
    tool-result block (the owning assistant fell into the summarised ``older``
    region), move ``split`` left until the suffix head is no longer ``role ==
    \"tool\"``.
    """
    n = len(messages)
    split = max(0, min(split, n))
    while split < n and messages[split].get("role") == "tool":
        if split == 0:
            break
        split -= 1
    return split


# Provider-agnostic budget guess for one raster image in a multimodal ``content`` list.
_VISION_BLOCK_APPROX_TOKENS = 512

# Model / tool / system turns may carry generated image URLs or artifacts; those are not
# user-uploaded vision input and should not inflate context budgets the same way.
_SKIP_VISION_TOKEN_ROLES = frozenset({"assistant", "tool", "system"})


def is_vision_content_block(block: dict[str, Any]) -> bool:
    """Detect OpenAI / Anthropic / Gemini-style vision parts inside a content block."""
    btype = str(block.get("type") or "").lower()
    if btype in ("image_url", "image", "input_image", "image_file"):
        return True
    if "image_url" in block:
        return True
    src = block.get("source")
    if isinstance(src, dict):
        st = str(src.get("type") or "").lower()
        if st in ("base64", "url") and (
            btype == "image" or bool(src.get("media_type"))
        ):
            return True
    return False


def approximate_message_content_tokens(
    content: Any,
    *,
    chars_per_token: float = 3.0,
    message_role: str | None = None,
) -> int:
    """Cheap token estimate for one message ``content`` (string or multimodal list).

    Text uses ``len(text) / chars_per_token``. Vision blocks add a fixed allowance
    so image turns are not counted as ~0 tokens (which breaks autocompact /
    context preview / progressive compression budgets).

    For ``assistant`` / ``tool`` / ``system`` roles, vision blocks are skipped — they
    usually reference model- or code-generated images rather than user camera/uploads.
    """
    if content is None:
        return 0
    role_lc = (message_role or "").strip().lower()
    count_vision = role_lc not in _SKIP_VISION_TOKEN_ROLES
    if isinstance(content, str):
        return int(len(content) / chars_per_token) if content else 0
    if isinstance(content, list):
        total = 0.0
        for block in content:
            if isinstance(block, dict):
                if is_vision_content_block(block):
                    if count_vision:
                        total += _VISION_BLOCK_APPROX_TOKENS
                    continue
                txt = block.get("text")
                if isinstance(txt, str) and txt:
                    total += len(txt) / chars_per_token
                else:
                    total += len(json.dumps(block, ensure_ascii=False)) / (chars_per_token * 4)
            elif isinstance(block, str):
                total += len(block) / chars_per_token
        return int(total)
    return int(len(str(content)) / chars_per_token)


def _approximate_tokens(messages: list[dict[str, Any]]) -> int:
    total = 0
    for m in messages:
        r = m.get("role")
        role_str = str(r).strip().lower() if r is not None else ""
        total += approximate_message_content_tokens(
            m.get("content"),
            chars_per_token=3.0,
            message_role=role_str or None,
        )
    return total


def build_microcompact(
    llm: "LLMService | None" = None,
    *,
    budget_chars: int = DEFAULT_TOOL_RESULT_BUDGET_CHARS,
) -> Microcompact:
    """Truncate tool_result payloads to ``budget_chars`` and annotate the trim.

    This does *not* call the LLM — it's a pure structural operation, matching
    the cheap ``applyToolResultBudget`` step in the TS loop. Callers who want
    summary-style compaction (LLM-driven) can compose it with ``autocompact``.
    """

    async def _microcompact(
        messages: list[dict[str, Any]],
        tool_use_context: "ToolUseContext",
    ) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for msg in messages:
            if msg.get("role") != "tool":
                out.append(msg)
                continue
            content = msg.get("content")
            if isinstance(content, str) and len(content) > budget_chars:
                trimmed = (
                    content[: budget_chars]
                    + f"\n…[truncated {len(content) - budget_chars} chars by microcompact]"
                )
                out.append({**msg, "content": trimmed})
            else:
                out.append(msg)
        return out

    return _microcompact


def build_autocompact(
    llm: "LLMService | None" = None,
    *,
    token_threshold: int = AUTOCOMPACT_TOKEN_THRESHOLD,
    keep_recent: int = AUTOCOMPACT_KEEP_RECENT,
) -> Autocompact:
    """Summarise the oldest messages when the token budget is exceeded.

    Behaviour:
      1. Estimate token count.
      2. If under threshold, return ``messages`` unchanged.
      3. Otherwise split into ``(older, recent)`` at ``-keep_recent`` and ask
         the tier2 LLM to summarise ``older``; concatenate
         ``[summary, *recent]``.
    """

    async def _autocompact(
        messages: list[dict[str, Any]],
        tool_use_context: "ToolUseContext",
        system_prompt: str,
    ) -> list[dict[str, Any]]:
        if not messages:
            return messages
        if _approximate_tokens(messages) < token_threshold:
            return messages
        if llm is None or len(messages) <= keep_recent:
            return messages

        split = snap_autocompact_split(messages, len(messages) - keep_recent)
        older = messages[:split]
        recent = messages[split:]

        transcript = "\n\n".join(
            f"[{m.get('role','?')}] {m.get('content','')}"
            for m in older
            if isinstance(m.get("content"), str)
        )

        summariser_prompt = _load_summariser_prompt()
        summarise_prompt = [
            {"role": "system", "content": summariser_prompt},
            {"role": "user", "content": transcript[:20_000]},
        ]

        try:
            response = await llm.chat(
                messages=summarise_prompt,
                tools=None,
                temperature=0.1,
                model_tier="tier2",
            )
            summary = (response or {}).get("content") or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning("autocompact_llm_failed", error=str(exc))
            return messages

        if not summary.strip():
            return messages

        return [
            {
                "role": "system",
                "content": (
                    "<compacted_history>\n" + summary.strip() + "\n</compacted_history>"
                ),
            },
            *recent,
        ]

    return _autocompact


async def apply_forced_autocompact(
    messages: list[dict[str, Any]],
    *,
    llm: "LLMService | None",
    tool_use_context: "ToolUseContext",
    system_prompt: str,
    keep_recent: int,
) -> list[dict[str, Any]]:
    """Summarise oldest messages regardless of token threshold (manual compact).

    Same split/summariser as :func:`build_autocompact` but always runs when
    ``len(messages) > keep_recent`` and ``llm`` is set; falls back to identity
    when summarisation fails or ``llm`` is missing.
    """
    _ = tool_use_context, system_prompt  # API parity with autocompact; reserved for future anchoring
    if not messages:
        return messages
    if llm is None or len(messages) <= keep_recent:
        return messages

    split = snap_autocompact_split(messages, len(messages) - keep_recent)
    older = messages[:split]
    recent = messages[split:]

    transcript = "\n\n".join(
        f"[{m.get('role','?')}] {m.get('content','')}"
        for m in older
        if isinstance(m.get("content"), str)
    )

    summariser_prompt = _load_summariser_prompt()
    summarise_prompt = [
        {"role": "system", "content": summariser_prompt},
        {"role": "user", "content": transcript[:20_000]},
    ]

    try:
        response = await llm.chat(
            messages=summarise_prompt,
            tools=None,
            temperature=0.1,
            model_tier="tier2",
        )
        summary = (response or {}).get("content") or ""
    except Exception as exc:  # noqa: BLE001
        logger.warning("forced_autocompact_llm_failed", error=str(exc))
        return messages

    if not summary.strip():
        return messages

    return [
        {
            "role": "system",
            "content": (
                "<compacted_history>\n" + summary.strip() + "\n</compacted_history>"
            ),
        },
        *recent,
    ]
