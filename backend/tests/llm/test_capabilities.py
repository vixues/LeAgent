"""Tests for the unified capability layer (profile / registry / router)."""

from __future__ import annotations

import pytest

from leagent.llm.capabilities import (
    BackendClass,
    CapabilityContract,
    CapabilityProfile,
    CapabilityRegistry,
    CapabilityRouter,
    Modality,
    TaskType,
    from_domain_spec,
    from_generation_backend,
    from_model_spec,
)
from leagent.llm.domain_registry import DomainModelSpec, DomainParam
from leagent.llm.generation.backends import (
    ImageProviderBackend,
    OfflineGenerationBackend,
)
from leagent.llm.model_spec import ModelCapabilities, ModelSpec


# ---------------------------------------------------------------------------
# Profile / contract
# ---------------------------------------------------------------------------


def test_profile_normalises_string_modalities_and_tasks():
    p = CapabilityProfile(
        id="x",
        provider="acme",
        backend_class=BackendClass.MULTIMODAL_LLM,
        inputs={"text", "image", "bogus"},
        outputs={"text"},
        tasks={"chat", "vision", "nope"},
    )
    assert p.inputs == frozenset({Modality.TEXT, Modality.IMAGE})
    assert p.tasks == frozenset({TaskType.CHAT, TaskType.VISION})
    assert p.supports_input(Modality.IMAGE)
    assert not p.supports_input(Modality.AUDIO)
    assert p.supports_task("chat")


def test_contract_matches_requires_task_and_modality_subset():
    profile = CapabilityProfile(
        id="img",
        provider="openai",
        backend_class=BackendClass.DEDICATED_IMAGE,
        inputs={Modality.TEXT},
        outputs={Modality.IMAGE},
        tasks={TaskType.IMAGE_GEN},
    )
    assert CapabilityContract(task=TaskType.IMAGE_GEN, outputs={Modality.IMAGE}).matches(profile)
    # Wrong task
    assert not CapabilityContract(task=TaskType.VIDEO_GEN).matches(profile)
    # Requires an output the profile lacks
    assert not CapabilityContract(task=TaskType.IMAGE_GEN, outputs={Modality.VIDEO}).matches(profile)
    # Requires an input the profile lacks
    assert not CapabilityContract(task=TaskType.IMAGE_GEN, inputs={Modality.IMAGE}).matches(profile)


def test_availability_probe_used_and_safe():
    p = CapabilityProfile(
        id="a", provider="p", backend_class=BackendClass.DEDICATED_IMAGE,
        availability=lambda: False,
    )
    assert p.available() is False

    def boom() -> bool:
        raise RuntimeError("nope")

    p2 = CapabilityProfile(
        id="b", provider="p", backend_class=BackendClass.DEDICATED_IMAGE, availability=boom,
    )
    assert p2.available() is False  # exceptions swallowed → unavailable


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------


def test_from_model_spec_vision_chat_is_multimodal():
    spec = ModelSpec(
        name="gpt-4o", provider="openai", kind="chat",
        capabilities=ModelCapabilities(
            input=frozenset({"text", "image"}), output=frozenset({"text"}), tool_call=True,
        ),
    )
    p = from_model_spec(spec)
    assert p.backend_class == BackendClass.MULTIMODAL_LLM
    assert TaskType.CHAT in p.tasks and TaskType.VISION in p.tasks
    assert p.supports_input(Modality.IMAGE)


def test_from_model_spec_text_chat_is_text_llm():
    spec = ModelSpec(name="text", provider="acme", kind="chat")
    p = from_model_spec(spec)
    assert p.backend_class == BackendClass.TEXT_LLM
    assert TaskType.VISION not in p.tasks


def test_from_domain_spec_maps_output_and_params():
    spec = DomainModelSpec(
        task="tts", provider="openai", model="tts-1", output="audio",
        params=(DomainParam(id="text", io_type="STRING"),),
    )
    p = from_domain_spec(spec)
    assert TaskType.TTS in p.tasks
    assert p.supports_output(Modality.AUDIO)
    assert p.backend_class == BackendClass.EXTERNAL_API


def test_from_domain_spec_local_is_local_pipeline():
    spec = DomainModelSpec(task="image_gen", provider="local", output="image")
    p = from_domain_spec(spec)
    assert p.backend_class == BackendClass.LOCAL_PIPELINE
    assert TaskType.IMAGE_GEN in p.tasks
    assert p.cost_tier == 1


def test_from_generation_backend_offline_and_image():
    offline = from_generation_backend(OfflineGenerationBackend())
    assert offline.backend_class == BackendClass.OFFLINE
    assert {TaskType.IMAGE_GEN, TaskType.VIDEO_GEN, TaskType.MESH_GEN} <= offline.tasks

    img = from_generation_backend(ImageProviderBackend("openai"))
    assert img.backend_class == BackendClass.DEDICATED_IMAGE
    assert TaskType.IMAGE_GEN in img.tasks
    assert TaskType.UPSCALE in img.tasks  # image backends also serve upscale
    assert img.supports_output(Modality.IMAGE)


# ---------------------------------------------------------------------------
# Registry + router
# ---------------------------------------------------------------------------


def _img_profile(provider: str, *, cost: int, offline: bool = False, available: bool = True):
    return CapabilityProfile(
        id=f"gen:{provider}",
        provider=provider,
        backend_class=BackendClass.OFFLINE if offline else BackendClass.DEDICATED_IMAGE,
        inputs={Modality.TEXT},
        outputs={Modality.IMAGE},
        tasks={TaskType.IMAGE_GEN},
        cost_tier=cost,
        availability=(lambda: available),
    )


def test_registry_query_filters():
    reg = CapabilityRegistry()
    reg.register(_img_profile("openai", cost=2))
    reg.register(_img_profile("offline", cost=0, offline=True))
    assert len(reg.query(task=TaskType.IMAGE_GEN)) == 2
    assert len(reg.query(output=Modality.VIDEO)) == 0
    assert {p.provider for p in reg.query(backend_class=BackendClass.OFFLINE)} == {"offline"}


def test_router_ranks_by_cost_and_appends_offline_last():
    reg = CapabilityRegistry()
    reg.register(_img_profile("openai", cost=2))
    reg.register(_img_profile("local", cost=1))
    reg.register(_img_profile("offline", cost=0, offline=True))
    router = CapabilityRouter(reg)

    contract = CapabilityContract(task=TaskType.IMAGE_GEN, outputs={Modality.IMAGE})
    ranked = router.candidates(contract)
    names = [p.provider for p in ranked]
    assert names == ["local", "openai", "offline"]  # cheaper first, offline floor last


def test_router_preferred_provider_pin_keeps_offline_floor():
    reg = CapabilityRegistry()
    reg.register(_img_profile("openai", cost=2, available=False))  # unavailable but pinned
    reg.register(_img_profile("offline", cost=0, offline=True))
    router = CapabilityRouter(reg)

    contract = CapabilityContract(task=TaskType.IMAGE_GEN, outputs={Modality.IMAGE})
    ranked = router.candidates(contract, preferred_provider="openai", available_only=False)
    assert [p.provider for p in ranked] == ["openai", "offline"]


def test_router_available_only_drops_unavailable():
    reg = CapabilityRegistry()
    reg.register(_img_profile("openai", cost=2, available=False))
    reg.register(_img_profile("offline", cost=0, offline=True))
    router = CapabilityRouter(reg)

    contract = CapabilityContract(task=TaskType.IMAGE_GEN, outputs={Modality.IMAGE})
    ranked = router.candidates(contract, available_only=True)
    assert [p.provider for p in ranked] == ["offline"]


def test_provider_options_lists_all_with_offline_last():
    reg = CapabilityRegistry()
    reg.register(_img_profile("openai", cost=2, available=False))
    reg.register(_img_profile("local", cost=1))
    reg.register(_img_profile("offline", cost=0, offline=True))
    router = CapabilityRouter(reg)
    contract = CapabilityContract(task=TaskType.IMAGE_GEN, outputs={Modality.IMAGE})
    assert router.provider_options(contract) == ["openai", "local", "offline"]


# ---------------------------------------------------------------------------
# Generation service integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generation_service_offline_floor(monkeypatch):
    from leagent.llm.generation import build_default_generation_service

    monkeypatch.setenv("LEAGENT_ART_OFFLINE", "1")
    svc = build_default_generation_service()
    out = await svc.generate(kind="image", prompt="a knight")
    assert out.success and out.provider == "offline" and out.data


def test_generation_service_palette_providers_include_local(monkeypatch):
    from leagent.llm.generation import build_default_generation_service

    svc = build_default_generation_service()
    providers = svc.palette_providers("image")
    assert "local" in providers
    assert providers[-1] == "offline"
