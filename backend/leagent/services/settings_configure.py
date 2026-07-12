"""Shared settings configuration: env secrets, MCP, and channels.

Used by ``/api/v1/settings/tokens`` and the ``configure_settings`` agent tool
so UI and agent share one validation + write path.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

from leagent.config.constants import LEAGENT_HOME

logger = structlog.get_logger(__name__)

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
    "WEB_SEARCH_PROVIDER",
    "WEB_SEARCH_BING_API_KEY",
    "WEB_SEARCH_SEARXNG_BASE_URL",
    "WEB_SEARCH_BRAVE_API_KEY",
    "WEB_SEARCH_TAVILY_API_KEY",
    "WEB_SEARCH_EXA_API_KEY",
    "WEB_SEARCH_FIRECRAWL_API_KEY",
    "WEB_SEARCH_FIRECRAWL_API_URL",
    "WEB_SEARCH_SERPER_API_KEY",
    "IMAGE_SEARCH_API_KEY",
    "IMAGE_SEARCH_CX",
    "WEB_FETCH_ENABLED",
    "WEB_FETCH_CHECK_ROBOTS",
    "WEB_FETCH_MIN_INTERVAL_MS",
    "WEB_FETCH_USER_AGENT",
    "WEB_FETCH_CACHE_TTL_MINUTES",
    "LEAGENT_SMTP_HOST",
    "LEAGENT_SMTP_PORT",
    "LEAGENT_SMTP_USERNAME",
    "LEAGENT_SMTP_PASSWORD",
    "LEAGENT_SMTP_USE_TLS",
    "LEAGENT_SMTP_USE_SSL",
    "LEAGENT_SMTP_FROM_EMAIL",
    "LEAGENT_SMTP_FROM_NAME",
)

_SECRET_ENV_KEYS = frozenset(
    {
        "LEAGENT_GITHUB_TOKEN",
        "GITHUB_TOKEN",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "DASHSCOPE_API_KEY",
        "WEB_SEARCH_BING_API_KEY",
        "WEB_SEARCH_BRAVE_API_KEY",
        "WEB_SEARCH_TAVILY_API_KEY",
        "WEB_SEARCH_EXA_API_KEY",
        "WEB_SEARCH_FIRECRAWL_API_KEY",
        "WEB_SEARCH_SERPER_API_KEY",
        "IMAGE_SEARCH_API_KEY",
        "LEAGENT_SMTP_PASSWORD",
        "LEAGENT_SMTP_USERNAME",
    }
)

_LLM_ENV_KEYS = frozenset(
    {
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "DEEPSEEK_THINKING_TYPE",
        "DEEPSEEK_REASONING_EFFORT",
        "DASHSCOPE_API_KEY",
    }
)

_SETTINGS_CACHE_KEYS = frozenset(
    {
        "WEB_SEARCH_BING_API_KEY",
        "WEB_SEARCH_PROVIDER",
        "WEB_SEARCH_SEARXNG_BASE_URL",
        "WEB_SEARCH_BRAVE_API_KEY",
        "WEB_SEARCH_TAVILY_API_KEY",
        "WEB_SEARCH_EXA_API_KEY",
        "WEB_SEARCH_FIRECRAWL_API_KEY",
        "WEB_SEARCH_FIRECRAWL_API_URL",
        "WEB_SEARCH_SERPER_API_KEY",
        "IMAGE_SEARCH_API_KEY",
        "IMAGE_SEARCH_CX",
        "WEB_FETCH_ENABLED",
        "WEB_FETCH_CHECK_ROBOTS",
        "WEB_FETCH_MIN_INTERVAL_MS",
        "WEB_FETCH_USER_AGENT",
        "WEB_FETCH_CACHE_TTL_MINUTES",
        "LEAGENT_SMTP_HOST",
        "LEAGENT_SMTP_PORT",
        "LEAGENT_SMTP_USERNAME",
        "LEAGENT_SMTP_PASSWORD",
        "LEAGENT_SMTP_USE_TLS",
        "LEAGENT_SMTP_USE_SSL",
        "LEAGENT_SMTP_FROM_EMAIL",
        "LEAGENT_SMTP_FROM_NAME",
    }
)

CHANNEL_NAMES = frozenset(
    {
        "web",
        "api",
        "console",
        "wechat_work",
        "feishu",
        "dingtalk",
        "email",
        "webhook",
    }
)

CHANNEL_CONFIG_FIELDS: dict[str, list[str]] = {
    "web": ["endpoint"],
    "api": ["endpoint", "token"],
    "console": [],
    "wechat_work": ["endpoint", "token", "webhook_url"],
    "feishu": ["endpoint", "token", "webhook_url"],
    "dingtalk": ["endpoint", "token", "webhook_url"],
    "email": ["endpoint", "token"],
    "webhook": ["endpoint", "webhook_url"],
}

_DEEPSEEK_KEY_RE = re.compile(r"^sk-[A-Za-z0-9]{8,}$")


class SettingsConfigureError(ValueError):
    """Validation or apply failure for settings configuration."""


def env_path() -> Path:
    return LEAGENT_HOME / ".env"


def is_env_set(key: str) -> bool:
    return bool((os.environ.get(key) or "").strip())


def mask_secret(value: str, *, unset: bool = False) -> str:
    if unset or value == "":
        return "(unset)"
    v = value.strip()
    if len(v) <= 4:
        return "****"
    return f"****{v[-4:]}"


def redact_env_preview(key: str, value: str) -> str:
    if value == "":
        return "(unset)"
    if key in _SECRET_ENV_KEYS or key.endswith("_API_KEY") or key.endswith("_TOKEN") or key.endswith("_PASSWORD"):
        return mask_secret(value)
    if len(value) > 80:
        return value[:77] + "..."
    return value


def validate_env_updates(updates: dict[str, str]) -> None:
    """Validate updates to prevent accidentally writing non-secret payloads.

    Raises:
        SettingsConfigureError: On invalid key or value.
    """
    bad = [k for k in updates if k not in ALLOWED_ENV_KEYS]
    if bad:
        raise SettingsConfigureError(f"Unsupported keys: {', '.join(bad)}")

    for key, raw in updates.items():
        val = (raw or "").strip()
        if val == "":
            continue

        lowered = val.lower()
        if "finish_reason" in lowered and "error" in lowered:
            raise SettingsConfigureError(
                f"Invalid value for {key}: looks like an error payload, not a secret."
            )

        if key == "DEEPSEEK_API_KEY":
            if "{" in val or "}" in val or "\\" in val:
                raise SettingsConfigureError(
                    "Invalid DEEPSEEK_API_KEY: must be a key like `sk-...`, not a structured string."
                )
            if not _DEEPSEEK_KEY_RE.match(val):
                raise SettingsConfigureError(
                    "Invalid DEEPSEEK_API_KEY format (expected `sk-...`)."
                )

        if key == "DEEPSEEK_THINKING_TYPE" and val not in ("enabled", "disabled"):
            raise SettingsConfigureError(
                "Invalid DEEPSEEK_THINKING_TYPE (must be enabled|disabled)."
            )
        if key == "DEEPSEEK_REASONING_EFFORT" and val not in ("high", "max"):
            raise SettingsConfigureError(
                "Invalid DEEPSEEK_REASONING_EFFORT (must be high|max)."
            )

        if key == "WEB_SEARCH_PROVIDER" and val not in (
            "auto",
            "bing_playwright",
            "duckduckgo_lite",
            "searxng",
            "bing",
            "brave",
            "tavily",
            "exa",
            "firecrawl",
            "serper",
        ):
            raise SettingsConfigureError(
                "Invalid WEB_SEARCH_PROVIDER (must be auto|bing_playwright|duckduckgo_lite|"
                "searxng|bing|brave|tavily|exa|firecrawl|serper)."
            )
        if key == "WEB_SEARCH_SEARXNG_BASE_URL" and val:
            if not (val.startswith("http://") or val.startswith("https://")):
                raise SettingsConfigureError(
                    "WEB_SEARCH_SEARXNG_BASE_URL must start with http:// or https://"
                )
            if len(val) > 512:
                raise SettingsConfigureError("WEB_SEARCH_SEARXNG_BASE_URL is too long.")
        if key == "WEB_SEARCH_FIRECRAWL_API_URL" and val:
            if not (val.startswith("http://") or val.startswith("https://")):
                raise SettingsConfigureError(
                    "WEB_SEARCH_FIRECRAWL_API_URL must start with http:// or https://"
                )
            if len(val) > 512:
                raise SettingsConfigureError("WEB_SEARCH_FIRECRAWL_API_URL is too long.")

        if key in ("WEB_FETCH_ENABLED", "WEB_FETCH_CHECK_ROBOTS") and val:
            low = val.lower()
            if low not in ("0", "1", "true", "false", "yes", "no"):
                raise SettingsConfigureError(f"Invalid {key} (use 0|1|true|false|yes|no).")
        if key == "WEB_FETCH_MIN_INTERVAL_MS" and val:
            try:
                n = float(val)
            except ValueError as e:
                raise SettingsConfigureError("WEB_FETCH_MIN_INTERVAL_MS must be a number") from e
            if n < 0 or n > 60_000:
                raise SettingsConfigureError(
                    "WEB_FETCH_MIN_INTERVAL_MS out of range (0–60000)"
                )
        if key == "WEB_FETCH_USER_AGENT" and val and len(val) > 512:
            raise SettingsConfigureError("WEB_FETCH_USER_AGENT is too long")
        if key == "WEB_FETCH_CACHE_TTL_MINUTES" and val:
            try:
                n = float(val)
            except ValueError as e:
                raise SettingsConfigureError("WEB_FETCH_CACHE_TTL_MINUTES must be a number") from e
            if n < 0 or n > 24 * 60:
                raise SettingsConfigureError(
                    "WEB_FETCH_CACHE_TTL_MINUTES out of range (0–1440)"
                )

        if key == "LEAGENT_SMTP_HOST" and val:
            if len(val) > 256 or "\n" in val or "\r" in val:
                raise SettingsConfigureError("LEAGENT_SMTP_HOST is invalid or too long")
        if key == "LEAGENT_SMTP_PORT" and val:
            try:
                p = int(val)
            except ValueError as e:
                raise SettingsConfigureError("LEAGENT_SMTP_PORT must be an integer") from e
            if p < 1 or p > 65535:
                raise SettingsConfigureError("LEAGENT_SMTP_PORT out of range (1–65535)")
        if key in ("LEAGENT_SMTP_USE_TLS", "LEAGENT_SMTP_USE_SSL") and val:
            low = val.lower()
            if low not in ("0", "1", "true", "false", "yes", "no"):
                raise SettingsConfigureError(f"Invalid {key} (use 0|1|true|false|yes|no).")
        if key == "LEAGENT_SMTP_FROM_EMAIL" and val:
            if len(val) > 254 or " " in val:
                raise SettingsConfigureError("LEAGENT_SMTP_FROM_EMAIL is invalid")
        if key == "LEAGENT_SMTP_FROM_NAME" and val and len(val) > 200:
            raise SettingsConfigureError("LEAGENT_SMTP_FROM_NAME is too long")
        if key == "LEAGENT_SMTP_USERNAME" and val and len(val) > 512:
            raise SettingsConfigureError("LEAGENT_SMTP_USERNAME is too long")


def apply_dotenv_updates(updates: dict[str, str], *, path: Path | None = None) -> None:
    try:
        from dotenv import set_key, unset_key
    except ImportError as e:
        raise SettingsConfigureError("python-dotenv is required") from e

    target = path or env_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    path_str = str(target)
    for key, val in updates.items():
        if val == "":
            unset_key(path_str, key)
        else:
            set_key(path_str, key, val)


def _reload_catalog_if_github_changed(keys: frozenset[str]) -> None:
    if not keys.intersection({"LEAGENT_GITHUB_TOKEN", "GITHUB_TOKEN"}):
        return
    try:
        from leagent.skills.github_monorepo_catalog import reset_github_monorepo_catalog

        reset_github_monorepo_catalog()
    except Exception:
        pass


async def _trigger_llm_reload() -> None:
    try:
        from leagent.services.service_manager import get_service_manager

        sm = get_service_manager()
        await sm.reload_llm_service()
    except Exception:
        pass


@dataclass
class ChangeSummary:
    kind: str
    target: str
    action: str
    preview: str
    detail: str = ""


@dataclass
class InspectResult:
    ok: bool
    summary: list[ChangeSummary] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    already_set: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    normalized_changes: list[dict[str, Any]] = field(default_factory=list)
    verify_next: list[str] = field(default_factory=list)


@dataclass
class ApplyResult:
    ok: bool
    updated: int = 0
    applied: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    verify_next: list[str] = field(default_factory=list)


def _normalize_changes(changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for raw in changes:
        if not isinstance(raw, dict):
            raise SettingsConfigureError("Each change must be an object")
        kind = str(raw.get("kind") or "").strip().lower()
        if kind == "env":
            key = str(raw.get("key") or "").strip()
            if not key:
                raise SettingsConfigureError("env change requires key")
            value = raw.get("value")
            if value is None:
                value = ""
            out.append({"kind": "env", "key": key, "value": str(value)})
        elif kind == "mcp":
            name = str(raw.get("name") or "").strip()
            if not name:
                raise SettingsConfigureError("mcp change requires name")
            transport = str(raw.get("transport") or "stdio").strip().lower()
            item: dict[str, Any] = {
                "kind": "mcp",
                "name": name,
                "transport": transport,
                "command": raw.get("command"),
                "args": list(raw.get("args") or []),
                "url": raw.get("url"),
                "env": dict(raw.get("env") or {}),
                "enabled": bool(raw.get("enabled", True)),
                "auto_connect": bool(raw.get("auto_connect", True)),
                "description": raw.get("description"),
                "remove": bool(raw.get("remove", False)),
            }
            out.append(item)
        elif kind == "channel":
            name = str(raw.get("name") or "").strip().lower()
            if not name:
                raise SettingsConfigureError("channel change requires name")
            cfg = raw.get("config") if isinstance(raw.get("config"), dict) else {}
            item = {
                "kind": "channel",
                "name": name,
                "enabled": raw.get("enabled"),
                "config": {
                    k: cfg[k]
                    for k in ("endpoint", "token", "webhook_url")
                    if k in cfg and cfg[k] is not None
                },
            }
            out.append(item)
        else:
            raise SettingsConfigureError(f"Unknown change kind: {kind!r}")
    return out


def inspect_env_changes(values: dict[str, str]) -> InspectResult:
    result = InspectResult(ok=True)
    try:
        validate_env_updates(values)
    except SettingsConfigureError as e:
        result.ok = False
        result.errors.append(str(e))
        return result

    for key, value in values.items():
        already = is_env_set(key)
        if already and value != "":
            result.already_set.append(key)
            result.warnings.append(f"{key} is already set; this will overwrite it.")
        action = "unset" if value == "" else ("overwrite" if already else "set")
        result.summary.append(
            ChangeSummary(
                kind="env",
                target=key,
                action=action,
                preview=redact_env_preview(key, value),
            )
        )
        result.normalized_changes.append({"kind": "env", "key": key, "value": value})
        if key.startswith("WEB_SEARCH_"):
            result.verify_next.append("Try web_search with a short query to confirm search works.")
        if key.startswith("LEAGENT_SMTP_"):
            result.verify_next.append("Use Settings → Mail → Test, or email_send after confirmation.")
        if key in _LLM_ENV_KEYS:
            result.verify_next.append("Send a short chat message to confirm the LLM provider responds.")
    # de-dupe verify hints
    result.verify_next = list(dict.fromkeys(result.verify_next))
    return result


def inspect_changes(changes: list[dict[str, Any]]) -> InspectResult:
    """Inspect env / mcp / channel changes; never returns full secrets."""
    result = InspectResult(ok=True)
    try:
        normalized = _normalize_changes(changes)
    except SettingsConfigureError as e:
        result.ok = False
        result.errors.append(str(e))
        return result

    env_vals: dict[str, str] = {}
    for ch in normalized:
        if ch["kind"] == "env":
            env_vals[ch["key"]] = ch["value"]

    if env_vals:
        env_insp = inspect_env_changes(env_vals)
        if not env_insp.ok:
            return env_insp
        result.summary.extend(env_insp.summary)
        result.warnings.extend(env_insp.warnings)
        result.already_set.extend(env_insp.already_set)
        result.verify_next.extend(env_insp.verify_next)
        result.normalized_changes.extend(env_insp.normalized_changes)

    for ch in normalized:
        if ch["kind"] == "env":
            continue
        if ch["kind"] == "mcp":
            if ch.get("remove"):
                result.summary.append(
                    ChangeSummary(
                        kind="mcp",
                        target=ch["name"],
                        action="remove",
                        preview=f"remove MCP server {ch['name']}",
                    )
                )
            else:
                transport = ch.get("transport") or "stdio"
                if transport == "stdio" and not ch.get("command"):
                    result.ok = False
                    result.errors.append(f"mcp {ch['name']}: stdio requires command")
                    return result
                if transport in ("http", "sse") and not ch.get("url"):
                    result.ok = False
                    result.errors.append(f"mcp {ch['name']}: {transport} requires url")
                    return result
                cmd_preview = ch.get("command") or ch.get("url") or ""
                result.summary.append(
                    ChangeSummary(
                        kind="mcp",
                        target=ch["name"],
                        action="upsert",
                        preview=f"{transport}: {cmd_preview}",
                        detail=" ".join(str(a) for a in (ch.get("args") or [])[:6]),
                    )
                )
                result.verify_next.append(
                    f"Connect MCP server '{ch['name']}' from the MCP page or API."
                )
            result.normalized_changes.append(ch)
        elif ch["kind"] == "channel":
            name = ch["name"]
            if name not in CHANNEL_NAMES and name not in CHANNEL_CONFIG_FIELDS:
                result.warnings.append(
                    f"Channel '{name}' is not a built-in type; it will be created if applied."
                )
            cfg = ch.get("config") or {}
            parts: list[str] = []
            if ch.get("enabled") is not None:
                parts.append(f"enabled={bool(ch['enabled'])}")
            if cfg.get("endpoint"):
                parts.append(f"endpoint={cfg['endpoint']}")
            if cfg.get("webhook_url"):
                parts.append(f"webhook={mask_secret(str(cfg['webhook_url']))}")
            if cfg.get("token"):
                parts.append(f"token={mask_secret(str(cfg['token']))}")
            result.summary.append(
                ChangeSummary(
                    kind="channel",
                    target=name,
                    action="update",
                    preview="; ".join(parts) or "(no field changes)",
                )
            )
            result.verify_next.append(
                f"After apply, test channel '{name}' (CLI: leagent channels test {name})."
            )
            result.normalized_changes.append(ch)

    result.verify_next = list(dict.fromkeys(result.verify_next))
    if not result.normalized_changes:
        result.ok = False
        result.errors.append("No valid changes provided")
    return result


async def apply_env_changes(
    values: dict[str, str],
    *,
    path: Path | None = None,
) -> ApplyResult:
    result = ApplyResult(ok=True)
    try:
        validate_env_updates(values)
    except SettingsConfigureError as e:
        result.ok = False
        result.errors.append(str(e))
        return result

    if not values:
        return result

    try:
        apply_dotenv_updates(values, path=path)
    except SettingsConfigureError as e:
        result.ok = False
        result.errors.append(str(e))
        return result
    except Exception as e:
        result.ok = False
        result.errors.append(str(e))
        return result

    for key, val in values.items():
        if val == "":
            os.environ.pop(key, None)
        else:
            os.environ[key] = val
        result.applied.append(key)
        logger.info("settings_env_applied", key=key, unset=val == "")

    result.updated = len(values)
    fk = frozenset(values.keys())
    if fk.intersection(_LLM_ENV_KEYS):
        await _trigger_llm_reload()
    _reload_catalog_if_github_changed(fk)
    if fk.intersection(_SETTINGS_CACHE_KEYS):
        try:
            from leagent.config.settings import get_settings

            get_settings.cache_clear()
        except Exception:
            pass
        try:
            from leagent.tools.web.web_search.cache import reset_web_caches
            from leagent.tools.web.web_search.service import reset_web_search_service

            reset_web_caches()
            reset_web_search_service()
        except Exception:
            pass
    return result


def _apply_mcp_changes(changes: list[dict[str, Any]]) -> list[str]:
    from leagent.mcp.base import MCPServer, MCPTransport
    from leagent.mcp.manager import get_mcp_manager

    manager = get_mcp_manager()
    applied: list[str] = []
    for ch in changes:
        name = ch["name"]
        if ch.get("remove"):
            if manager.remove_server(name, persist=True):
                applied.append(f"mcp:{name}:removed")
            else:
                raise SettingsConfigureError(f"MCP server '{name}' not found")
            continue
        transport = MCPTransport(ch.get("transport") or "stdio")
        config = MCPServer(
            name=name,
            transport=transport,
            command=ch.get("command"),
            args=list(ch.get("args") or []),
            url=ch.get("url"),
            env=dict(ch.get("env") or {}),
            enabled=bool(ch.get("enabled", True)),
            auto_connect=bool(ch.get("auto_connect", True)),
            description=ch.get("description"),
        )
        if name in manager.server_names:
            manager.remove_server(name, persist=False)
        manager.add_server(config, persist=True)
        applied.append(f"mcp:{name}:upserted")
    return applied


def _apply_channel_changes(changes: list[dict[str, Any]]) -> list[str]:
    from leagent.config.config import ChannelConfig, load_config, save_config

    config = load_config()
    applied: list[str] = []
    for ch in changes:
        name = ch["name"]
        if name not in config.channels:
            config.channels[name] = ChannelConfig()
        channel = config.channels[name]
        if ch.get("enabled") is not None:
            channel.enabled = bool(ch["enabled"])
        cfg = ch.get("config") or {}
        if "endpoint" in cfg:
            channel.endpoint = str(cfg["endpoint"] or "")
        if "token" in cfg:
            channel.token = str(cfg["token"] or "")
        if "webhook_url" in cfg:
            channel.webhook_url = str(cfg["webhook_url"] or "")
        applied.append(f"channel:{name}")
    save_config(config)
    return applied


async def apply_changes(
    changes: list[dict[str, Any]],
    *,
    env_path_override: Path | None = None,
) -> ApplyResult:
    """Apply previously inspected/normalized changes."""
    result = ApplyResult(ok=True)
    try:
        normalized = _normalize_changes(changes)
    except SettingsConfigureError as e:
        result.ok = False
        result.errors.append(str(e))
        return result

    insp = inspect_changes(normalized)
    if not insp.ok:
        result.ok = False
        result.errors = insp.errors
        return result

    env_vals = {c["key"]: c["value"] for c in normalized if c["kind"] == "env"}
    mcp_chs = [c for c in normalized if c["kind"] == "mcp"]
    channel_chs = [c for c in normalized if c["kind"] == "channel"]

    if env_vals:
        env_res = await apply_env_changes(env_vals, path=env_path_override)
        if not env_res.ok:
            return env_res
        result.updated += env_res.updated
        result.applied.extend(env_res.applied)

    try:
        if mcp_chs:
            result.applied.extend(_apply_mcp_changes(mcp_chs))
            result.updated += len(mcp_chs)
        if channel_chs:
            result.applied.extend(_apply_channel_changes(channel_chs))
            result.updated += len(channel_chs)
    except SettingsConfigureError as e:
        result.ok = False
        result.errors.append(str(e))
        return result
    except Exception as e:
        result.ok = False
        result.errors.append(str(e))
        logger.warning("settings_apply_failed", error=str(e))
        return result

    result.verify_next = insp.verify_next
    return result
