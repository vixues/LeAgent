"""WeChat Work channel for LeAgent."""

from .channel import (
    WeChatWorkChannel,
    WECHAT_WORK_API_BASE,
    WECHAT_WORK_MAX_TEXT_LENGTH,
    WECHAT_WORK_TOKEN_TTL_SECONDS,
)

__all__ = [
    "WeChatWorkChannel",
    "WECHAT_WORK_API_BASE",
    "WECHAT_WORK_MAX_TEXT_LENGTH",
    "WECHAT_WORK_TOKEN_TTL_SECONDS",
]
