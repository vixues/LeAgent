"""Weixin (personal WeChat) channel via iLink Bot API."""

from .channel import WeixinChannel, check_weixin_requirements, split_text_for_delivery
from .client import ILINK_BASE_URL, WEIXIN_CDN_BASE_URL, SessionExpiredError, WeixinClient
from .login import WeixinLoginResult, WeixinQrSession, check_qr_session, run_qr_login, start_qr_session
from .store import ContextTokenStore, load_account, save_account

__all__ = [
    "ILINK_BASE_URL",
    "WEIXIN_CDN_BASE_URL",
    "ContextTokenStore",
    "SessionExpiredError",
    "WeixinChannel",
    "WeixinClient",
    "WeixinLoginResult",
    "WeixinQrSession",
    "check_qr_session",
    "check_weixin_requirements",
    "load_account",
    "run_qr_login",
    "save_account",
    "split_text_for_delivery",
    "start_qr_session",
]
