"""Read/write allowlisted API tokens via ``~/.leagent/.env`` (desktop secrets).

GET returns only whether each key is non-empty — never the secret value.
"""

from __future__ import annotations

import os
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from leagent.config.constants import LEAGENT_HOME
from leagent.services.auth.deps import get_current_principal

router = APIRouter()

ALLOWED_ENV_KEYS: tuple[str, ...] = (
    "LEAGENT_GITHUB_TOKEN",
    "GITHUB_TOKEN",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "DEEPSEEK_THINKING_TYPE",
    "DEEPSEEK_REASONING_EFFORT",
    "DASHSCOPE_API_KEY",
    "LLM_TIER1_API_KEY",
    "LLM_TIER2_API_KEY",
    # Web search (`web_search` tool) + Google image search (`web_image_search`)
    "WEB_SEARCH_PROVIDER",
    "WEB_SEARCH_BING_API_KEY",
    "WEB_SEARCH_SEARXNG_BASE_URL",
    "IMAGE_SEARCH_API_KEY",
    "IMAGE_SEARCH_CX",
    # Polite fetch / robots (optional overrides; see AGENTS.md)
    "WEB_FETCH_ENABLED",
    "WEB_FETCH_CHECK_ROBOTS",
    "WEB_FETCH_MIN_INTERVAL_MS",
    "WEB_FETCH_USER_AGENT",
    # Outbound SMTP (Settings → Mail + email_send defaults)
    "LEAGENT_SMTP_HOST",
    "LEAGENT_SMTP_PORT",
    "LEAGENT_SMTP_USERNAME",
    "LEAGENT_SMTP_PASSWORD",
    "LEAGENT_SMTP_USE_TLS",
    "LEAGENT_SMTP_USE_SSL",
    "LEAGENT_SMTP_FROM_EMAIL",
    "LEAGENT_SMTP_FROM_NAME",
)


class TokenKeyStatus(BaseModel):
    env_key: str
    set: bool


class TokensStatusResponse(BaseModel):
    keys: list[TokenKeyStatus]


class TokensUpdateBody(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


def _env_path() -> Any:
    return LEAGENT_HOME / ".env"


def _is_set(key: str) -> bool:
    return bool((os.environ.get(key) or "").strip())


async def _trigger_llm_reload() -> None:
    try:
        from leagent.services.service_manager import get_service_manager

        sm = get_service_manager()
        await sm.reload_llm_service()
    except Exception:
        pass


def _apply_dotenv_updates(updates: dict[str, str]) -> None:
    try:
        from dotenv import set_key, unset_key
    except ImportError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="python-dotenv is required",
        ) from None

    path_str = str(_env_path())
    for key, val in updates.items():
        if val == "":
            unset_key(path_str, key)
        else:
            set_key(path_str, key, val)


_DEEPSEEK_KEY_RE = re.compile(r"^sk-[A-Za-z0-9]{8,}$")


def _validate_updates(updates: dict[str, str]) -> None:
    """Validate updates to prevent accidentally writing non-secret payloads."""
    for key, raw in updates.items():
        val = (raw or "").strip()
        if val == "":
            continue

        # Prevent common accidental pastes of structured error payloads.
        lowered = val.lower()
        if "finish_reason" in lowered and "error" in lowered:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid value for {key}: looks like an error payload, not a secret.",
            )

        if key == "DEEPSEEK_API_KEY":
            # DeepSeek keys are typically `sk-...`. Enforce a minimal sanity check
            # to avoid writing accidental dict/JSON strings into ~/.leagent/.env.
            if "{" in val or "}" in val or "\\" in val:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid DEEPSEEK_API_KEY: must be a key like `sk-...`, not a structured string.",
                )
            if not _DEEPSEEK_KEY_RE.match(val):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid DEEPSEEK_API_KEY format (expected `sk-...`).",
                )

        if key == "DEEPSEEK_THINKING_TYPE" and val not in ("enabled", "disabled"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid DEEPSEEK_THINKING_TYPE (must be enabled|disabled).",
            )
        if key == "DEEPSEEK_REASONING_EFFORT" and val not in ("high", "max"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid DEEPSEEK_REASONING_EFFORT (must be high|max).",
            )

        if key == "WEB_SEARCH_PROVIDER" and val not in ("duckduckgo_lite", "searxng", "bing"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid WEB_SEARCH_PROVIDER (must be duckduckgo_lite|searxng|bing).",
            )
        if key == "WEB_SEARCH_SEARXNG_BASE_URL" and val:
            if not (val.startswith("http://") or val.startswith("https://")):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="WEB_SEARCH_SEARXNG_BASE_URL must start with http:// or https://",
                )
            if len(val) > 512:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="WEB_SEARCH_SEARXNG_BASE_URL is too long.",
                )

        if key in ("WEB_FETCH_ENABLED", "WEB_FETCH_CHECK_ROBOTS") and val:
            low = val.lower()
            if low not in ("0", "1", "true", "false", "yes", "no"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid {key} (use 0|1|true|false|yes|no).",
                )
        if key == "WEB_FETCH_MIN_INTERVAL_MS" and val:
            try:
                n = float(val)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="WEB_FETCH_MIN_INTERVAL_MS must be a number",
                ) from e
            if n < 0 or n > 60_000:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="WEB_FETCH_MIN_INTERVAL_MS out of range (0–60000)",
                )
        if key == "WEB_FETCH_USER_AGENT" and val and len(val) > 512:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="WEB_FETCH_USER_AGENT is too long",
            )

        if key == "LEAGENT_SMTP_HOST" and val:
            if len(val) > 256 or "\n" in val or "\r" in val:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="LEAGENT_SMTP_HOST is invalid or too long",
                )
        if key == "LEAGENT_SMTP_PORT" and val:
            try:
                p = int(val)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="LEAGENT_SMTP_PORT must be an integer",
                ) from e
            if p < 1 or p > 65535:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="LEAGENT_SMTP_PORT out of range (1–65535)",
                )
        if key in ("LEAGENT_SMTP_USE_TLS", "LEAGENT_SMTP_USE_SSL") and val:
            low = val.lower()
            if low not in ("0", "1", "true", "false", "yes", "no"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid {key} (use 0|1|true|false|yes|no).",
                )
        if key == "LEAGENT_SMTP_FROM_EMAIL" and val:
            if len(val) > 254 or " " in val:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="LEAGENT_SMTP_FROM_EMAIL is invalid",
                )
        if key == "LEAGENT_SMTP_FROM_NAME" and val and len(val) > 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="LEAGENT_SMTP_FROM_NAME is too long",
            )
        if key == "LEAGENT_SMTP_USERNAME" and val and len(val) > 512:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="LEAGENT_SMTP_USERNAME is too long",
            )


def _reload_catalog_if_github_changed(keys: frozenset[str]) -> None:
    if not keys.intersection({"LEAGENT_GITHUB_TOKEN", "GITHUB_TOKEN"}):
        return
    try:
        from leagent.skills.github_monorepo_catalog import reset_github_monorepo_catalog

        reset_github_monorepo_catalog()
    except Exception:
        pass


@router.get("/tokens", response_model=TokensStatusResponse)
async def get_tokens_status(_: Annotated[Any, Depends(get_current_principal)]) -> TokensStatusResponse:
    keys = [TokenKeyStatus(env_key=k, set=_is_set(k)) for k in ALLOWED_ENV_KEYS]
    return TokensStatusResponse(keys=keys)


@router.put("/tokens")
async def put_tokens(
    body: TokensUpdateBody,
    _: Annotated[Any, Depends(get_current_principal)],
) -> dict[str, Any]:
    bad = [k for k in body.values if k not in ALLOWED_ENV_KEYS]
    if bad:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported keys: {', '.join(bad)}",
        )

    if not body.values:
        return {"ok": True, "updated": 0}

    filtered = {k: v for k, v in body.values.items() if k in ALLOWED_ENV_KEYS}
    _validate_updates(filtered)
    _env_path().parent.mkdir(parents=True, exist_ok=True)
    try:
        _apply_dotenv_updates(filtered)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    for key, val in filtered.items():
        if val == "":
            os.environ.pop(key, None)
        else:
            os.environ[key] = val

    fk = frozenset(filtered.keys())
    llm_touch = fk.intersection(
        {
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "DEEPSEEK_API_KEY",
            "DEEPSEEK_BASE_URL",
            "DEEPSEEK_MODEL",
            "DEEPSEEK_THINKING_TYPE",
            "DEEPSEEK_REASONING_EFFORT",
            "DASHSCOPE_API_KEY",
            "LLM_TIER1_API_KEY",
            "LLM_TIER2_API_KEY",
        }
    )
    if llm_touch:
        await _trigger_llm_reload()

    _reload_catalog_if_github_changed(fk)

    if fk.intersection(
        {
            "WEB_SEARCH_BING_API_KEY",
            "WEB_SEARCH_PROVIDER",
            "WEB_SEARCH_SEARXNG_BASE_URL",
            "IMAGE_SEARCH_API_KEY",
            "IMAGE_SEARCH_CX",
            "WEB_FETCH_ENABLED",
            "WEB_FETCH_CHECK_ROBOTS",
            "WEB_FETCH_MIN_INTERVAL_MS",
            "WEB_FETCH_USER_AGENT",
            "LEAGENT_SMTP_HOST",
            "LEAGENT_SMTP_PORT",
            "LEAGENT_SMTP_USERNAME",
            "LEAGENT_SMTP_PASSWORD",
            "LEAGENT_SMTP_USE_TLS",
            "LEAGENT_SMTP_USE_SSL",
            "LEAGENT_SMTP_FROM_EMAIL",
            "LEAGENT_SMTP_FROM_NAME",
        }
    ):
        try:
            from leagent.config.settings import get_settings

            get_settings.cache_clear()
        except Exception:
            pass

    return {"ok": True, "updated": len(filtered)}
