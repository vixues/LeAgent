"""Tests for extractive knowledge-base summaries."""

from __future__ import annotations

from leagent.library.summary import summarize_extracted_text


def test_summarize_empty_returns_none() -> None:
    assert summarize_extracted_text(None) is None
    assert summarize_extracted_text("") is None
    assert summarize_extracted_text("   \n\n  ") is None


def test_summarize_prefers_markdown_heading() -> None:
    text = "# Onboarding Guide\n\nWelcome to the team. Follow these steps carefully."
    summary = summarize_extracted_text(text)
    assert summary is not None
    assert summary.startswith("Onboarding Guide")
    assert "Welcome" in summary


def test_summarize_truncates_to_max_chars() -> None:
    body = "word " * 200
    summary = summarize_extracted_text(body, max_chars=50)
    assert summary is not None
    assert len(summary) <= 50
    assert summary.endswith("…")


def test_summarize_plain_paragraph() -> None:
    text = "First paragraph about refunds.\n\nSecond paragraph with more detail."
    summary = summarize_extracted_text(text, max_chars=200)
    assert summary is not None
    assert "First paragraph" in summary
