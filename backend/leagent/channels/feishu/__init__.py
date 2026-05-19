"""Feishu/Lark channel for LeAgent."""

from .channel import (
    FeishuChannel,
    FEISHU_API_BASE,
    FEISHU_TOKEN_TTL_SECONDS,
)

__all__ = [
    "FeishuChannel",
    "FEISHU_API_BASE",
    "FEISHU_TOKEN_TTL_SECONDS",
]
