"""Lightweight HTTP fetch package (extract + SSRF + summarize)."""

from __future__ import annotations

from leagent.tools.web.web_fetch.extract import html_to_readable_text
from leagent.tools.web.web_fetch.ssrf import assert_public_http_url

__all__ = ["assert_public_http_url", "html_to_readable_text"]
