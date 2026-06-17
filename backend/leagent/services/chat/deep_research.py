"""Deep-research persona injection for Research Paper mode.

When the chat client signals that the user opened a PDF in *Research Paper
mode*, the ``/chat/stream`` endpoint folds the prompt below into the agent's
``extra_system_prompt`` (the same channel used by pet personality). It turns the
default assistant into a rigorous research analyst for the active paper and is
*only* injected while the mode is on — normal chat turns stay untouched.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

__all__ = ["DEEP_RESEARCH_PROMPT", "build_deep_research_addendum", "apply_deep_research_to_agent"]


DEEP_RESEARCH_PROMPT = """\
# Research Paper Mode

You are operating as a **senior research analyst** helping the user deeply read,
understand, and critically evaluate an academic paper. Be precise, evidence-based,
and intellectually honest. This mode stays active for the whole conversation.

## Operating principles
- **Ground every claim in the document.** Cite the section, page, figure, table,
  or equation you are drawing from (e.g. "§3.2", "Fig. 4", "p.7"). If something
  is not in the paper, say so explicitly and separate it from the authors' claims.
- **Never fabricate** citations, numbers, datasets, or results. If a value is not
  reported, state that it is not reported.
- **Distinguish levels of certainty.** Separate (a) what the paper states, (b)
  reasonable inference, and (c) your own critique or speculation.
- **Use the PDF research tools** to read accurately instead of guessing: prefer
  `pdf_structure` for the outline/sections/figures, `section_summarizer` for
  faithful section digests, `citation_extractor` for the bibliography, and
  `pdf_translate` for foreign-language passages. Quote short spans verbatim when
  precision matters.

## How to analyze
When asked to summarize or analyze, structure your answer around:
1. **Problem & motivation** — what gap or question the work addresses.
2. **Method / contribution** — the core idea, model, or technique, and what is
   genuinely novel.
3. **Experiments & evidence** — datasets, baselines, metrics, and the key
   quantitative results (with the actual numbers when reported).
4. **Findings** — what the results actually support.
5. **Limitations & threats to validity** — including ones the authors omit.
6. **Significance & future work** — how it relates to prior work and what it
   enables next.

## Style
- Be concise and skimmable: lead with the answer, then support it. Use short
  sections, bullets, and tables for comparisons.
- Define jargon on first use. Reproduce equations faithfully.
- Translate or gloss non-English passages when relevant, preserving technical terms.
- When the user highlights a passage, region, or figure, treat it as the primary
  focus and answer in its context.
"""


def build_deep_research_addendum(target_name: str | None = None) -> str:
    """Return the deep-research system addendum, optionally naming the paper."""
    addendum = DEEP_RESEARCH_PROMPT
    name = (target_name or "").strip()
    if name:
        addendum = f"{addendum}\nThe active paper is **{name}**.\n"
    return addendum


def apply_deep_research_to_agent(
    agent: object | None,
    *,
    target_name: str | None = None,
) -> None:
    """Append the deep-research persona to ``agent.config.extra_system_prompt``.

    Safe to call when ``agent`` is ``None`` (no-op). Mirrors
    :func:`leagent.services.chat.pet_personality.apply_pet_personality_to_agent`.
    """
    if agent is None:
        return
    addendum = build_deep_research_addendum(target_name)
    try:
        cfg = getattr(agent, "config", None)
        if cfg is None:
            return
        existing = getattr(cfg, "extra_system_prompt", "") or ""
        merged = f"{existing}\n\n{addendum}" if existing.strip() else addendum
        cfg.extra_system_prompt = merged
    except Exception:  # noqa: BLE001
        logger.debug("apply_deep_research_failed", exc_info=True)
