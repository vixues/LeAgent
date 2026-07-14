"""Runtime configuration models and YAML persistence."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from leagent.config.constants import CONFIG_PATH

logger = logging.getLogger(__name__)


class ChannelConfig(BaseModel):
    """Configuration for a single messaging channel (web, API, WeChat, etc.)."""

    enabled: bool = False
    endpoint: str = ""
    token: str = ""
    webhook_url: str = ""
    extra: dict[str, Any] = Field(default_factory=dict)


class MCPServerConfig(BaseModel):
    """Configuration for a Model Context Protocol server."""

    name: str = ""
    url: str = ""
    api_key: str = ""
    enabled: bool = False
    tools: list[str] = Field(default_factory=list)


class AgentConfig(BaseModel):
    """Per-agent runtime configuration."""

    name: str = "default"
    system_prompt: str = ""
    max_iterations: int = 15
    tools: list[str] = Field(default_factory=list)
    temperature: float = 0.1
    enabled: bool = True


class HeartbeatConfig(BaseModel):
    """Heartbeat / health-check settings."""

    enabled: bool = True
    interval_sec: int = 30
    timeout_sec: int = 10
    failure_threshold: int = 3


class Config(BaseModel):
    """Top-level runtime configuration persisted to YAML."""

    channels: dict[str, ChannelConfig] = Field(default_factory=lambda: {
        "web": ChannelConfig(enabled=True),
        "api": ChannelConfig(enabled=True),
        "console": ChannelConfig(enabled=True),
        "wechat_work": ChannelConfig(),
        "weixin": ChannelConfig(),
        "feishu": ChannelConfig(),
        "dingtalk": ChannelConfig(),
    })
    mcp_servers: list[MCPServerConfig] = Field(default_factory=list)
    agents: dict[str, AgentConfig] = Field(default_factory=lambda: {
        "default": AgentConfig(),
    })
    heartbeat: HeartbeatConfig = Field(default_factory=HeartbeatConfig)
    extra: dict[str, Any] = Field(default_factory=dict)


_config_cache: Config | None = None
_config_cache_mtime: float | None = None
_config_cache_path: str | None = None


def _invalidate_config_cache() -> None:
    global _config_cache, _config_cache_mtime, _config_cache_path
    _config_cache = None
    _config_cache_mtime = None
    _config_cache_path = None


def load_config(path: Path | str | None = None) -> Config:
    """Load runtime configuration from a YAML file, falling back to defaults.

    Results are cached by path mtime so hot status endpoints do not re-read
    and re-log the YAML on every poll.
    """
    global _config_cache, _config_cache_mtime, _config_cache_path

    config_path = Path(path) if path else CONFIG_PATH
    path_key = str(config_path.resolve()) if config_path.exists() else str(config_path)
    if config_path.exists():
        try:
            mtime = config_path.stat().st_mtime
            if (
                _config_cache is not None
                and _config_cache_path == path_key
                and _config_cache_mtime == mtime
            ):
                return _config_cache
            with open(config_path, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            config = Config.model_validate(raw)
            _config_cache = config
            _config_cache_mtime = mtime
            _config_cache_path = path_key
            logger.debug("Loaded runtime config from %s", config_path)
            return config
        except Exception:
            logger.warning("Failed to parse config at %s, using defaults", config_path, exc_info=True)
            _invalidate_config_cache()
    return Config()


def save_config(config: Config, path: Path | str | None = None) -> None:
    """Persist runtime configuration to a YAML file."""
    global _config_cache, _config_cache_mtime, _config_cache_path

    config_path = Path(path) if path else CONFIG_PATH
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(
            config.model_dump(mode="json"),
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
        )
    try:
        _config_cache = config
        _config_cache_mtime = config_path.stat().st_mtime
        _config_cache_path = str(config_path.resolve())
    except OSError:
        _invalidate_config_cache()
    logger.info("Saved runtime config to %s", config_path)
