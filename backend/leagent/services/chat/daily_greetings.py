"""Daily rotating greetings via tier-2 LLM (cached per locale, UTC day).

Covers both:
- Empty-state chat hero welcome lines (10 per day).
- Pet speech-bubble acknowledgment lines shown after agent replies (10 per day).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from datetime import datetime, timezone

from typing import TYPE_CHECKING

from leagent.exceptions.llm import LLMServiceError
from leagent.llm import ChatMessage
from leagent.llm import MessageRole as LLMMessageRole

if TYPE_CHECKING:
    from leagent.llm.service import LLMService

logger = logging.getLogger(__name__)

_CACHE_LOCK = asyncio.Lock()
_CACHE: dict[str, tuple[str, list[str]]] = {}

_PET_BUBBLE_CACHE_LOCK = asyncio.Lock()
_PET_BUBBLE_CACHE: dict[str, tuple[str, list[str]]] = {}

_GREETING_SYSTEM = """You write short welcome lines for an AI assistant's empty chat screen.
Tone: warm, witty, lightly playful — clever wordplay or gentle humor is welcome; still safe for work
(no slurs, no harassment, no medical/legal certainty claims). Invite the user to start a task or chat.

Rules:
- Output ONLY a JSON array of exactly 10 strings, no markdown fences, no keys, no commentary.
- Each string is one line (question, invitation, or quip), max 72 characters.
- Match the requested UI language exactly (Simplified Chinese or English as specified).
- Lines must be clearly distinct; at most one tasteful emoji per line (often zero is fine).
- No quotes around the array; valid JSON only."""

_PET_BUBBLE_SYSTEM = """You write very short post-reply captions for an AI desk-pet speech bubble.
These appear beside a small mascot after the assistant finishes answering.
Tone: brief, warm, lightly playful — like a tiny sidekick acknowledging the reply is done.

Rules:
- Output ONLY a JSON array of exactly 10 strings, no markdown fences, no keys, no commentary.
- Each string max 60 characters. They acknowledge/celebrate a completed reply.
- Match the requested UI language exactly (Simplified Chinese or English as specified).
- Lines must be clearly distinct; at most one tasteful emoji per line (often zero is fine).
- Do NOT repeat the answer content; these are generic "done" acknowledgments with personality.
- No quotes around the array; valid JSON only."""


def _utc_day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def normalize_greeting_locale(locale: str | None) -> str:
    raw = (locale or "en-US").strip().replace("_", "-")
    low = raw.lower()
    if low.startswith("zh"):
        return "zh-CN"
    return "en-US"


def default_greetings(locale: str) -> list[str]:
    if locale == "zh-CN":
        return [
            "你好呀——今天主线是摸鱼还是改变世界？我两种档期都有。",
            "咖啡续杯了吗？聊五毛钱的也行，聊五块钱的更欢迎。",
            "bug 躲猫猫？文档堆成山？甩我一半，锅分着背更轻。",
            "点子像爆米花时记得叫我，我自带黄油味耐心。",
            "先丢给我「最让你头大」那件事的前三个字，我接龙。",
            "严肃复盘、胡闹脑暴、正经写代码——今天想开哪种副本？",
            "假装这是一场只有两个人的「超重要」站会，话筒给你。",
            "我是一块海绵，专吸疑难杂症和离谱需求（太离谱会先笑一下）。",
            "三、二、一——开始今天的第一句灵光，别让它溜走。",
            "需要我当你的嘴替、手替，还是单纯当你的脑洞放大器？",
        ]
    return [
        "Coffee first, cosmic questions second — what's on the stove today?",
        "Bug playing hide-and-seek? Toss me a clue; we'll corner it politely.",
        "Tiny spark or giant hairball of a task — I brought metaphorical scissors.",
        "Let's run the world's shortest stand-up: one block, one win, your mic.",
        "Docs, doodles, debugging, mild drama — pick a lane; I'll match your vibe.",
        "If today feels like a side quest, I'm the NPC with suspiciously good loot.",
        "Stuck in a loop? I'll be your rubber duck — with opinions and snacks.",
        "Brain low on RAM? Offload a tab to me; we'll defrag in plain English.",
        "Serious work, silly asides — both stamps are valid at this desk.",
        "Three, two, one — drop the first line of your plot twist; I'll improvise.",
    ]


def _sanitize_line(s: object) -> str | None:
    if not isinstance(s, str):
        return None
    text = " ".join(s.split())
    text = text.strip()
    if len(text) < 2:
        return None
    if len(text) > 120:
        text = text[:120].rstrip()
    return text


def _parse_greeting_json(raw: str) -> list[str] | None:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
        text = text.strip()
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        m = re.search(r"\[[\s\S]*\]", text)
        if not m:
            return None
        try:
            data = json.loads(m.group(0))
        except (TypeError, ValueError):
            return None
    if not isinstance(data, list):
        return None
    out: list[str] = []
    for item in data:
        line = _sanitize_line(item)
        if line:
            out.append(line)
        if len(out) >= 10:
            break
    if len(out) < 10:
        return None
    return out


async def _generate_with_llm(llm: LLMService, locale: str, day: str) -> list[str] | None:
    lang_hint = "Simplified Chinese (zh-CN)" if locale == "zh-CN" else "English (en-US)"
    user_msg = (
        f"Calendar day (UTC): {day}.\n"
        f"UI language: {lang_hint}.\n"
        "Return the JSON array now."
    )
    messages = [
        ChatMessage(role=LLMMessageRole.SYSTEM, content=_GREETING_SYSTEM),
        ChatMessage(role=LLMMessageRole.USER, content=user_msg),
    ]
    try:
        response = await llm.complete(
            messages,
            tier="tier2",
            temperature=0.85,
            max_tokens=512,
            tool_choice="none",
        )
    except LLMServiceError:
        logger.debug("daily_greetings_llm_failed", exc_info=True)
        return None
    except Exception:
        logger.debug("daily_greetings_llm_unexpected", exc_info=True)
        return None
    return _parse_greeting_json(response.content or "")


async def get_daily_greetings_for_locale(llm: LLMService | None, locale: str) -> tuple[str, list[str]]:
    """Return ``(utc_date_iso, greetings_10)`` using cache and optional LLM."""
    norm = normalize_greeting_locale(locale)
    day = _utc_day()
    async with _CACHE_LOCK:
        hit = _CACHE.get(norm)
        if hit and hit[0] == day:
            return day, list(hit[1])
    base = default_greetings(norm)
    generated: list[str] | None = None
    if llm is not None:
        generated = await _generate_with_llm(llm, norm, day)
    merged = generated if generated else base
    async with _CACHE_LOCK:
        hit = _CACHE.get(norm)
        if hit and hit[0] == day:
            return day, list(hit[1])
        _CACHE[norm] = (day, merged)
        logger.info("daily_greetings_cached locale=%s day=%s source=%s", norm, day, "llm" if generated else "default")
    return day, list(merged)


# ---------------------------------------------------------------------------
# Pet bubble greetings (post-reply acknowledgment lines)
# ---------------------------------------------------------------------------


def default_pet_bubble_greetings(locale: str) -> list[str]:
    """Static fallback pet bubble lines when LLM is unavailable."""
    if locale == "zh-CN":
        return [
            "搞定啦，看看回复吧~",
            "回答已就位，请过目。",
            "任务完成，给你比个心。",
            "写好了！有问题随时再问。",
            "答案新鲜出炉 ✨",
            "好了好了，看这里~",
            "已处理，等你下一道指令。",
            "这一轮交差！",
            "完工！下一个挑战呢？",
            "今日份回答已送达。",
        ]
    return [
        "All set — see my reply here.",
        "Done! Let me know if you need more.",
        "Fresh answer, hot off the press.",
        "Task complete. What's next?",
        "Delivered — hope that helps!",
        "Here you go ✨",
        "Reply ready. Fire away again anytime.",
        "Wrapped up! Anything else?",
        "Another one down. You're on a roll.",
        "Finished — I'll be right here.",
    ]


_PERSONALITY_MAX_CHARS = 2000


def _personality_hash(personality: str | None) -> str:
    if not personality:
        return "none"
    digest = hashlib.sha256(personality.strip().encode("utf-8")).hexdigest()
    return digest[:12]


def _pet_bubble_cache_key(locale: str, personality: str | None) -> str:
    return f"{locale}:{_personality_hash(personality)}"


async def _generate_pet_bubbles_with_llm(
    llm: LLMService,
    locale: str,
    day: str,
    personality: str | None = None,
) -> list[str] | None:
    lang_hint = "Simplified Chinese (zh-CN)" if locale == "zh-CN" else "English (en-US)"
    user_lines = [
        f"Calendar day (UTC): {day}.",
        f"UI language: {lang_hint}.",
    ]
    if personality:
        trimmed = personality.strip()
        if len(trimmed) > _PERSONALITY_MAX_CHARS:
            trimmed = trimmed[:_PERSONALITY_MAX_CHARS].rstrip()
        user_lines.append("")
        user_lines.append("Pet personality (write the bubble lines AS this character):")
        user_lines.append(trimmed)
    user_lines.append("")
    user_lines.append("Return the JSON array now.")
    user_msg = "\n".join(user_lines)
    messages = [
        ChatMessage(role=LLMMessageRole.SYSTEM, content=_PET_BUBBLE_SYSTEM),
        ChatMessage(role=LLMMessageRole.USER, content=user_msg),
    ]
    try:
        response = await llm.complete(
            messages,
            tier="tier2",
            temperature=0.85,
            max_tokens=512,
            tool_choice="none",
        )
    except LLMServiceError:
        logger.debug("daily_pet_bubbles_llm_failed", exc_info=True)
        return None
    except Exception:
        logger.debug("daily_pet_bubbles_llm_unexpected", exc_info=True)
        return None
    return _parse_greeting_json(response.content or "")


async def get_daily_pet_bubble_greetings(
    llm: LLMService | None,
    locale: str,
    personality: str | None = None,
) -> tuple[str, list[str]]:
    """Return ``(utc_date_iso, pet_bubble_lines_10)`` using cache and optional LLM.

    When ``personality`` is provided, lines are generated in that character's voice
    and cached under a personality-aware key so different personas don't share lines.
    """
    norm = normalize_greeting_locale(locale)
    day = _utc_day()
    cache_key = _pet_bubble_cache_key(norm, personality)
    async with _PET_BUBBLE_CACHE_LOCK:
        hit = _PET_BUBBLE_CACHE.get(cache_key)
        if hit and hit[0] == day:
            return day, list(hit[1])
    base = default_pet_bubble_greetings(norm)
    generated: list[str] | None = None
    if llm is not None:
        generated = await _generate_pet_bubbles_with_llm(llm, norm, day, personality)
    merged = generated if generated else base
    async with _PET_BUBBLE_CACHE_LOCK:
        hit = _PET_BUBBLE_CACHE.get(cache_key)
        if hit and hit[0] == day:
            return day, list(hit[1])
        _PET_BUBBLE_CACHE[cache_key] = (day, merged)
        logger.info(
            "daily_pet_bubbles_cached locale=%s day=%s persona=%s source=%s",
            norm,
            day,
            _personality_hash(personality),
            "llm" if generated else "default",
        )
    return day, list(merged)
