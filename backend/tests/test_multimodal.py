"""Tests for multimodal user-message preparation."""

from __future__ import annotations

from pathlib import Path

from leagent.agent.multimodal import (
    TEXT_ONLY_IMAGE_ATTACHMENT_HINT,
    prepare_user_message_with_attachments,
)
from leagent.llm.model_registry import ModelRegistry
from leagent.llm.model_spec import ModelCapabilities, ModelSpec


def _text_registry(provider: str, model: str) -> ModelRegistry:
    reg = ModelRegistry()
    reg._specs[(provider, model)] = ModelSpec(  # noqa: SLF001
        name=model,
        provider=provider,
        capabilities=ModelCapabilities(input=frozenset({"text"}), tool_call=True),
    )
    return reg


def test_text_only_model_gets_path_hint(tmp_path: Path) -> None:
    img = tmp_path / "photo.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    catalog = _text_registry("deepseek", "deepseek-v4-flash")
    out = prepare_user_message_with_attachments(
        f"convert this to gif\n\nAttached files:\n- {img}\n",
        [str(img)],
        provider="deepseek",
        model="deepseek-v4-flash",
        catalog=catalog,
    )
    assert isinstance(out, str)
    assert str(img) in out
    assert TEXT_ONLY_IMAGE_ATTACHMENT_HINT in out


def test_oversized_image_falls_back_to_path_hint(tmp_path: Path) -> None:
    img = tmp_path / "big.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * (9 * 1024 * 1024))
    reg = ModelRegistry()
    reg._specs[("openai", "gpt-4o")] = ModelSpec(  # noqa: SLF001
        name="gpt-4o",
        provider="openai",
        capabilities=ModelCapabilities(
            input=frozenset({"text", "image"}),
            tool_call=True,
        ),
    )
    out = prepare_user_message_with_attachments(
        "describe",
        [str(img)],
        provider="openai",
        model="gpt-4o",
        catalog=reg,
    )
    assert isinstance(out, str)
    assert TEXT_ONLY_IMAGE_ATTACHMENT_HINT in out
