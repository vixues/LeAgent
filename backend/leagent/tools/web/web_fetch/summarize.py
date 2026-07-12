"""Size-gated content compression for ``web_fetch`` results."""

from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def maybe_summarize_content(
    content: str,
    *,
    threshold: int,
    output_chars: int,
    refuse_over: int,
) -> tuple[str, dict[str, Any]]:
    """Return ``(content, meta)`` after size-gated truncation / optional LLM summary.

    Meta keys: ``compressed`` (bool), ``mode`` (raw|truncated|summarized|refused),
    ``original_chars``, ``notes``.
    """
    n = len(content or "")
    meta: dict[str, Any] = {"original_chars": n, "compressed": False, "mode": "raw", "notes": []}

    if n == 0:
        return "", meta

    if n > refuse_over:
        meta["compressed"] = True
        meta["mode"] = "refused"
        meta["notes"].append(
            f"Page exceeds {refuse_over} characters; refused. Use a more focused URL or web_scraper."
        )
        return content[:output_chars], meta

    if n <= threshold:
        return content, meta

    summarized = await _try_llm_summarize(content, max_out=output_chars)
    if summarized:
        meta["compressed"] = True
        meta["mode"] = "summarized"
        meta["notes"].append("Long page summarized via auxiliary LLM to fit context.")
        return summarized, meta

    meta["compressed"] = True
    meta["mode"] = "truncated"
    meta["notes"].append(
        f"Long page truncated to ~{output_chars} chars (summarization unavailable)."
    )
    return content[:output_chars], meta


async def _try_llm_summarize(content: str, *, max_out: int) -> str | None:
    try:
        from leagent.llm.base import ChatMessage, MessageRole
        from leagent.llm.service import LLMService
    except Exception:
        return None

    try:
        llm = LLMService.from_settings()
    except Exception as e:
        logger.debug("web_fetch_llm_unavailable", error=str(e))
        return None

    # Cap input to keep aux cost bounded.
    sample = content[:120_000]
    prompt = (
        "Compress the following web page into a dense factual extract for an agent. "
        "Keep quotes, code, numbers, names, and URLs. Do not invent facts. "
        f"Target under {max_out} characters.\n\n---\n{sample}"
    )
    try:
        resp = await llm.complete(
            [ChatMessage(role=MessageRole.USER, content=prompt)],
            max_tokens=min(2048, max(256, max_out // 3)),
            temperature=0.0,
        )
        text = (getattr(resp, "content", None) or "").strip()
        if not text:
            return None
        return text[:max_out]
    except Exception as e:
        logger.warning("web_fetch_summarize_failed", error=str(e))
        return None
    finally:
        try:
            await llm.aclose()
        except Exception:
            pass
