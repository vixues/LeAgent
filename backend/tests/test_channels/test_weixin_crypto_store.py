"""Unit tests for Weixin iLink crypto, store, chunking, and channel helpers."""

from __future__ import annotations

import base64
from pathlib import Path

import pytest

from leagent.channels.weixin.channel import split_text_for_delivery
from leagent.channels.weixin.client import is_session_expired
from leagent.channels.weixin.crypto import (
    aes128_ecb_decrypt,
    aes128_ecb_encrypt,
    parse_aes_key,
)
from leagent.channels.weixin.store import (
    ContextTokenStore,
    MessageDeduplicator,
    load_account,
    save_account,
)


def test_aes_roundtrip() -> None:
    key = b"0123456789abcdef"
    plain = b"hello weixin media"
    cipher = aes128_ecb_encrypt(plain, key)
    assert aes128_ecb_decrypt(cipher, key) == plain


def test_parse_aes_key_formats() -> None:
    raw = b"0123456789abcdef"
    assert parse_aes_key(base64.b64encode(raw).decode()) == raw
    assert parse_aes_key(raw.hex()) == raw
    # base64 of hex string
    hex_b64 = base64.b64encode(raw.hex().encode("ascii")).decode()
    assert parse_aes_key(hex_b64) == raw


def test_session_expired_detection() -> None:
    assert is_session_expired(None, -14)
    assert is_session_expired(-14, None)
    assert is_session_expired(-2, -2, "unknown error")
    assert not is_session_expired(0, 0)
    assert not is_session_expired(-2, -2, "rate limited")


def test_context_token_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "leagent.channels.weixin.store.ACCOUNTS_DIR",
        tmp_path,
    )
    store = ContextTokenStore(root=tmp_path)
    store.set("acc1", "userA", "tok-1")
    assert store.get("acc1", "userA") == "tok-1"

    store2 = ContextTokenStore(root=tmp_path)
    assert store2.restore("acc1") == 1
    assert store2.get("acc1", "userA") == "tok-1"


def test_save_load_account(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("leagent.channels.weixin.store.ACCOUNTS_DIR", tmp_path)
    path = save_account(
        account_id="bot123",
        token="secret-token",
        base_url="https://ilinkai.weixin.qq.com",
    )
    assert path.exists()
    data = load_account("bot123")
    assert data is not None
    assert data["token"] == "secret-token"
    assert data["account_id"] == "bot123"


def test_message_dedup() -> None:
    dedup = MessageDeduplicator(ttl_seconds=60)
    assert dedup.seen("m1") is False
    assert dedup.seen("m1") is True
    assert dedup.seen("m2") is False


def test_split_text_keeps_short_message() -> None:
    text = "line1\n\nline2\nline3"
    assert split_text_for_delivery(text, max_length=4000) == [text]


def test_split_text_packs_long_content() -> None:
    block = "x" * 100
    parts = [block for _ in range(50)]
    content = "\n\n".join(parts)
    chunks = split_text_for_delivery(content, max_length=250)
    assert len(chunks) > 1
    assert all(len(c) <= 250 for c in chunks)
    assert "".join(chunks).replace("\n", "") == content.replace("\n", "")


def test_weixin_channel_from_config() -> None:
    from leagent.channels.base import ChannelType
    from leagent.channels.weixin import WeixinChannel

    ch = WeixinChannel.from_config(
        {
            "enabled": True,
            "token": "tok",
            "extra": {
                "account_id": "acc",
                "dm_policy": "allowlist",
                "allow_from": "u1,u2",
            },
        }
    )
    assert ch.channel_type == ChannelType.WEIXIN
    assert ch.account_id == "acc"
    assert ch.token == "tok"
    assert ch.allow_from == ["u1", "u2"]
    assert ch._allowed("dm", "u1") is True
    assert ch._allowed("dm", "u3") is False
    assert ch._allowed("group", "g1") is False  # default disabled
