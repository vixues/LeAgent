"""Central API router that aggregates all versioned sub-routers."""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger(__name__)

api_router = APIRouter()

# ---------------------------------------------------------------------------
# v1 sub-routers
# ---------------------------------------------------------------------------

v1_router = APIRouter(prefix="/v1")

try:
    from leagent.api.v1 import meta as v1_meta
    v1_router.include_router(v1_meta.router, prefix="/meta", tags=["v1-meta"])
except ImportError:
    pass

try:
    from leagent.api.v1 import health as v1_health
    v1_router.include_router(v1_health.router, prefix="/health", tags=["v1-health"])
except ImportError:
    pass

try:
    from leagent.api.v1 import chat as v1_chat
    v1_router.include_router(v1_chat.router, prefix="/chat", tags=["v1-chat"])
except ImportError:
    pass

try:
    from leagent.api.v1 import tools as v1_tools
    v1_router.include_router(v1_tools.router, prefix="/tools", tags=["v1-tools"])
except ImportError:
    pass

try:
    from leagent.api.v1 import rules as v1_rules
    v1_router.include_router(v1_rules.router, prefix="/rules", tags=["v1-rules"])
except ImportError:
    pass

try:
    from leagent.api.v1 import models as v1_models
    v1_router.include_router(v1_models.router, prefix="/models", tags=["v1-models"])
except ImportError:
    pass

# ---------------------------------------------------------------------------
# v2 sub-routers (deferred heavy imports — see router_deferred.py)
# ---------------------------------------------------------------------------

v2_router = APIRouter(prefix="/v2")

# ---------------------------------------------------------------------------
# Mount versioned routers
# ---------------------------------------------------------------------------

api_router.include_router(v1_router)
api_router.include_router(v2_router)
