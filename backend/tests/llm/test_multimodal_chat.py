"""Backend tests for ChatGPT-style multimodal chat (Phase 3).

Covers structured content parts, multi-turn vision rebuild / stripping,
capability-driven input/output modality checks, and the assistant_media SSE
event builder.
"""

from __future__ import annotations

import base64

from leagent.agent.base import ConversationMessage
from leagent.agent.content_parts import (
    ATTACHMENT_IMAGE_PATHS_KEY,
    ContentPart,
    MessageContent,
    rebuild_vision_history,
)
from leagent.agent.multimodal import (
    model_supports_image_input,
    model_supports_output_modality,
    model_supported_input_modalities,
)
from leagent.api.v1.chat.attachments import build_assistant_media_event
from leagent.llm.model_registry import ModelRegistry
from leagent.llm.model_spec import ModelCapabilities, ModelSpec


_PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


# ---------------------------------------------------------------------------
# Structured content parts
# ---------------------------------------------------------------------------


def test_message_content_roundtrip_text_and_image():
    mc = MessageContent(
        parts=[
            ContentPart.text_part("describe this"),
            ContentPart.image_part("data:image/png;base64,xx"),
        ]
    )
    assert mc.has_media
    dumped = mc.to_dict_list()
    restored = MessageContent.from_dict_list(dumped)
    assert restored.text() == "describe this"
    oai = restored.to_openai_content()
    assert isinstance(oai, list)
    assert oai[0]["type"] == "text"
    assert oai[1]["type"] == "image_url"


def test_message_content_text_only_returns_string():
    mc = MessageContent.from_openai_content("just text")
    assert not mc.has_media
    assert mc.to_openai_content() == "just text"


def test_conversation_message_emits_multimodal_content():
    msg = ConversationMessage(
        role="user",
        content="fallback",
        content_parts=[
            {"type": "text", "text": "hi"},
            {"type": "image", "url": "data:image/png;base64,xx"},
        ],
    )
    oai = msg.to_openai_format()
    assert isinstance(oai["content"], list)
    assert oai["content"][1]["type"] == "image_url"
    # The internal vision marker must never leak into a provider message.
    assert ATTACHMENT_IMAGE_PATHS_KEY not in oai


# ---------------------------------------------------------------------------
# Multi-turn vision rebuild / stripping
# ---------------------------------------------------------------------------


def test_rebuild_strips_images_for_text_only_model():
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "what is this"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}},
            ],
        }
    ]
    out = rebuild_vision_history(messages, supports_image=False)
    assert out[0]["content"] == "what is this"


def test_rebuild_inlines_images_from_paths_for_vision_model(tmp_path):
    img = tmp_path / "pic.png"
    img.write_bytes(_PNG_1PX)
    messages = [
        {"role": "user", "content": "look", ATTACHMENT_IMAGE_PATHS_KEY: [str(img)]},
        {"role": "assistant", "content": "ok"},
    ]
    out = rebuild_vision_history(messages, supports_image=True)
    user = out[0]
    assert isinstance(user["content"], list)
    assert any(b["type"] == "image_url" for b in user["content"])
    # Marker is always removed.
    assert ATTACHMENT_IMAGE_PATHS_KEY not in user


def test_rebuild_bounds_total_images(tmp_path):
    paths = []
    for i in range(6):
        p = tmp_path / f"p{i}.png"
        p.write_bytes(_PNG_1PX)
        paths.append(str(p))
    messages = [
        {"role": "user", "content": "a", ATTACHMENT_IMAGE_PATHS_KEY: paths[:3]},
        {"role": "user", "content": "b", ATTACHMENT_IMAGE_PATHS_KEY: paths[3:]},
    ]
    out = rebuild_vision_history(messages, supports_image=True, max_images=4)
    img_count = sum(
        1
        for m in out
        if isinstance(m["content"], list)
        for b in m["content"]
        if b["type"] == "image_url"
    )
    assert img_count == 4


# ---------------------------------------------------------------------------
# Capability-driven modality checks
# ---------------------------------------------------------------------------


def _catalog_with(spec: ModelSpec) -> ModelRegistry:
    reg = ModelRegistry()
    reg._specs[(spec.provider, spec.name)] = spec
    return reg


def test_model_supports_image_input_via_profile():
    vision = ModelSpec(
        name="gpt-4o", provider="openai", kind="chat",
        capabilities=ModelCapabilities(input=frozenset({"text", "image"})),
    )
    text = ModelSpec(name="text", provider="acme", kind="chat")
    cat = _catalog_with(vision)
    assert model_supports_image_input(provider="openai", model="gpt-4o", catalog=cat)
    cat2 = _catalog_with(text)
    assert not model_supports_image_input(provider="acme", model="text", catalog=cat2)


def test_model_supports_output_modality_defaults_false_for_unknown():
    assert not model_supports_output_modality(
        "image", provider="x", model="y", catalog=ModelRegistry()
    )
    spec = ModelSpec(
        name="img", provider="p", kind="chat",
        capabilities=ModelCapabilities(
            input=frozenset({"text"}), output=frozenset({"text", "image"}),
        ),
    )
    cat = _catalog_with(spec)
    assert model_supports_output_modality("image", provider="p", model="img", catalog=cat)


def test_model_supported_input_modalities():
    spec = ModelSpec(
        name="m", provider="p", kind="chat",
        capabilities=ModelCapabilities(input=frozenset({"text", "image"})),
    )
    mods = model_supported_input_modalities(provider="p", model="m", catalog=_catalog_with(spec))
    assert {"text", "image"} <= mods


# ---------------------------------------------------------------------------
# assistant_media SSE builder
# ---------------------------------------------------------------------------


def test_build_assistant_media_event_filters_media():
    payload = {
        "attachments": [
            {"id": "1", "kind": "image"},
            {"id": "2", "kind": "document"},
            {"id": "3", "content_type": "video/mp4"},
        ]
    }
    event = build_assistant_media_event(payload, native_image_output=True)
    assert event is not None
    ids = {a["id"] for a in event["attachments"]}
    assert ids == {"1", "3"}
    assert event["native"] is True


def test_build_assistant_media_event_none_when_no_media():
    payload = {"attachments": [{"id": "1", "kind": "document"}]}
    assert build_assistant_media_event(payload, native_image_output=False) is None
