"""Channel registry for LeAgent.

Provides auto-discovery and registration of channel implementations,
supporting both built-in and custom channels.
"""

from __future__ import annotations

import importlib
import logging
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

from .base import BaseChannel, ChannelType

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

BUILTIN_CHANNEL_SPECS: dict[str, tuple[str, str]] = {
    "console": (".console.channel", "ConsoleChannel"),
    "web": (".web.channel", "WebChannel"),
    "dingtalk": (".dingtalk.channel", "DingTalkChannel"),
    "feishu": (".feishu.channel", "FeishuChannel"),
    "wechat_work": (".wechat_work.channel", "WeChatWorkChannel"),
    "weixin": (".weixin.channel", "WeixinChannel"),
    "api": (".api.channel", "APIChannel"),
}

REQUIRED_CHANNEL_KEYS: frozenset[str] = frozenset({"console"})

_BUILTIN_CHANNEL_CACHE: dict[str, type[BaseChannel]] | None = None
_BUILTIN_CHANNEL_CACHE_LOCK = threading.Lock()

CUSTOM_CHANNELS_DIR = Path.cwd() / "custom_channels"


def _load_builtin_channels() -> dict[str, type[BaseChannel]]:
    """Load built-in channels safely.

    Optional dependency failures should not break startup.

    Returns:
        Dictionary mapping channel names to channel classes.
    """
    out: dict[str, type[BaseChannel]] = {}

    for key, (module_name, class_name) in BUILTIN_CHANNEL_SPECS.items():
        try:
            mod = importlib.import_module(module_name, package=__package__)
            cls = getattr(mod, class_name)

            if not (
                isinstance(cls, type) and issubclass(cls, BaseChannel) and cls is not BaseChannel
            ):
                raise TypeError(f"{module_name}.{class_name} is not a BaseChannel subtype")

        except Exception:
            if key in REQUIRED_CHANNEL_KEYS:
                logger.error(
                    'Failed to load required built-in channel "%s"',
                    key,
                    exc_info=True,
                )
                raise
            logger.debug(
                "Built-in channel unavailable: %s",
                key,
                exc_info=True,
            )
            continue

        out[key] = cls

    return out


def _get_cached_builtin_channels() -> dict[str, type[BaseChannel]]:
    """Return cached built-in channels (loaded once per process).

    Returns:
        Dictionary of built-in channel classes.
    """
    global _BUILTIN_CHANNEL_CACHE

    with _BUILTIN_CHANNEL_CACHE_LOCK:
        if _BUILTIN_CHANNEL_CACHE is None:
            _BUILTIN_CHANNEL_CACHE = _load_builtin_channels()
        return dict(_BUILTIN_CHANNEL_CACHE)


def clear_builtin_channel_cache() -> None:
    """Reset built-in channel cache. Primarily for testing."""
    global _BUILTIN_CHANNEL_CACHE

    with _BUILTIN_CHANNEL_CACHE_LOCK:
        _BUILTIN_CHANNEL_CACHE = None


def _discover_custom_channels(
    custom_dir: Path | None = None,
) -> dict[str, type[BaseChannel]]:
    """Load channel classes from custom channels directory.

    Args:
        custom_dir: Optional custom directory path.

    Returns:
        Dictionary mapping channel names to custom channel classes.
    """
    out: dict[str, type[BaseChannel]] = {}
    search_dir = custom_dir or CUSTOM_CHANNELS_DIR

    if not search_dir.is_dir():
        return out

    dir_str = str(search_dir)
    if dir_str not in sys.path:
        sys.path.insert(0, dir_str)

    for path in sorted(search_dir.iterdir()):
        if path.suffix == ".py" and path.stem != "__init__":
            name = path.stem
        elif path.is_dir() and (path / "__init__.py").exists():
            name = path.name
        else:
            continue

        try:
            mod = importlib.import_module(name)
        except Exception:
            logger.exception("Failed to load custom channel: %s", name)
            continue

        for obj in vars(mod).values():
            if (
                isinstance(obj, type)
                and issubclass(obj, BaseChannel)
                and obj is not BaseChannel
            ):
                key = getattr(obj, "channel_type", None)
                if key:
                    channel_name = key.value if isinstance(key, ChannelType) else str(key)
                    out[channel_name] = obj
                    logger.debug("Custom channel registered: %s", channel_name)

    return out


def get_channel_registry(
    custom_dir: Path | None = None,
) -> dict[str, type[BaseChannel]]:
    """Get complete channel registry with built-in and custom channels.

    Args:
        custom_dir: Optional custom channels directory.

    Returns:
        Dictionary mapping channel names to channel classes.
    """
    out = _get_cached_builtin_channels()
    out.update(_discover_custom_channels(custom_dir))
    return out


def get_channel(
    channel_type: ChannelType | str,
    custom_dir: Path | None = None,
) -> type[BaseChannel] | None:
    """Get a specific channel class by type.

    Args:
        channel_type: Channel type to retrieve.
        custom_dir: Optional custom channels directory.

    Returns:
        Channel class or None if not found.
    """
    channel_id = channel_type.value if isinstance(channel_type, ChannelType) else channel_type
    registry = get_channel_registry(custom_dir)
    return registry.get(channel_id)


def list_channels(
    custom_dir: Path | None = None,
) -> list[str]:
    """List all available channel names.

    Args:
        custom_dir: Optional custom channels directory.

    Returns:
        List of available channel names.
    """
    return list(get_channel_registry(custom_dir).keys())


def register_channel(
    channel_cls: type[BaseChannel],
    name: str | None = None,
) -> None:
    """Manually register a channel class.

    Args:
        channel_cls: Channel class to register.
        name: Optional name override (uses channel_type if not provided).
    """
    global _BUILTIN_CHANNEL_CACHE

    if not issubclass(channel_cls, BaseChannel):
        raise TypeError(f"{channel_cls} is not a BaseChannel subtype")

    channel_name = name
    if not channel_name:
        channel_type = getattr(channel_cls, "channel_type", None)
        if channel_type:
            channel_name = channel_type.value if isinstance(channel_type, ChannelType) else str(channel_type)

    if not channel_name:
        raise ValueError("Channel name could not be determined")

    with _BUILTIN_CHANNEL_CACHE_LOCK:
        if _BUILTIN_CHANNEL_CACHE is None:
            _BUILTIN_CHANNEL_CACHE = _load_builtin_channels()
        _BUILTIN_CHANNEL_CACHE[channel_name] = channel_cls

    logger.info("Channel registered: %s", channel_name)


BUILTIN_CHANNEL_KEYS = frozenset(BUILTIN_CHANNEL_SPECS.keys())
