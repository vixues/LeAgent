"""Web search package — focus routing + pluggable providers."""

from leagent.tools.web.web_search.core import run_web_search
from leagent.tools.web.web_search.protocol import WEB_SEARCH_PROVIDER_IDS, SearchHit
from leagent.tools.web.web_search.service import get_web_search_service, reset_web_search_service

__all__ = [
    "WEB_SEARCH_PROVIDER_IDS",
    "SearchHit",
    "get_web_search_service",
    "reset_web_search_service",
    "run_web_search",
]
