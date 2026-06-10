"""Domain-model plugin system tests.

Covers the registry facade, the ``Model.<task>.<provider>`` node builder
(param→IO mapping, 5-tuple outputs, progress plumbing), the self-hosted
diffusion adapter against a fake pipeline manager (no GPU / no network),
the local audio adapters, and builtin registration gating.
"""

from __future__ import annotations

import base64
from typing import Any

import pytest

from leagent.llm.domain_models import register_builtin_domain_models
from leagent.llm.domain_models.diffusion import manager as diffusion_manager
from leagent.llm.domain_models.diffusion.adapter import DiffusersTxt2ImgAdapter
from leagent.llm.domain_models.diffusion.manager import GenerationResult
from leagent.llm.domain_models.local_audio import (
    LocalTTSAdapter,
    LocalWhisperASRAdapter,
)
from leagent.llm.domain_registry import (
    DomainModelRegistry,
    DomainModelResult,
    DomainModelSpec,
    DomainParam,
)
from leagent.workflow.engine.progress import ProgressRegistry
from leagent.workflow.io import HiddenHolder
from leagent.workflow.nodes.domain_model_nodes import (
    MODEL_OUTPUT_NAMES,
    build_domain_model_node,
)


class _FakeAdapter:
    """Minimal adapter implementing the DomainModelAdapter protocol."""

    def __init__(self, spec: DomainModelSpec | None = None) -> None:
        self.spec = spec or DomainModelSpec(
            task="echo",
            provider="fake",
            model="echo-1",
            display_name="Echo",
            params=(
                DomainParam(id="text", io_type="STRING", required=True, multiline=True),
                DomainParam(id="count", io_type="INT", default=1, min=0, max=10),
                DomainParam(id="gain", io_type="FLOAT", default=0.5, min=0.0, max=1.0),
                DomainParam(id="mode", io_type="COMBO", choices=("a", "b"), default="a"),
                DomainParam(id="flag", io_type="BOOLEAN", default=False),
            ),
            output="text",
        )
        self.calls: list[dict[str, Any]] = []
        self.result = DomainModelResult(
            text="ok", model="echo-1", provider="fake", mime="text/plain"
        )

    async def invoke(self, **params: Any) -> DomainModelResult:
        self.calls.append(params)
        return self.result


# ---------------------------------------------------------------------------
# Registry facade
# ---------------------------------------------------------------------------


async def test_registry_register_get_invoke():
    registry = DomainModelRegistry()
    adapter = _FakeAdapter()
    registry.register(adapter)

    assert registry.get("echo", "fake") is adapter
    assert registry.get("echo") is adapter  # provider-less lookup
    assert registry.get("missing") is None
    assert registry.tasks() == ["echo"]

    result = await registry.invoke_task("echo", text="hi")
    assert result.success and result.text == "ok"
    assert adapter.calls == [{"text": "hi"}]


async def test_registry_duplicate_and_replace():
    registry = DomainModelRegistry()
    registry.register(_FakeAdapter())
    with pytest.raises(ValueError):
        registry.register(_FakeAdapter())
    registry.register(_FakeAdapter(), replace=True)  # no raise


async def test_invoke_task_unknown_returns_error_envelope():
    registry = DomainModelRegistry()
    result = await registry.invoke_task("nope")
    assert not result.success
    assert "No domain model registered" in (result.error or "")


async def test_invoke_task_wraps_adapter_exception():
    registry = DomainModelRegistry()

    class _Boom(_FakeAdapter):
        async def invoke(self, **params: Any) -> DomainModelResult:
            raise RuntimeError("kaput")

    registry.register(_Boom())
    result = await registry.invoke_task("echo")
    assert not result.success and "kaput" in (result.error or "")


# ---------------------------------------------------------------------------
# Node builder: schema shape + execution
# ---------------------------------------------------------------------------


def test_build_domain_model_node_schema_shape():
    adapter = _FakeAdapter()
    node_cls = build_domain_model_node(adapter)
    schema = node_cls.get_schema()

    assert node_cls.NODE_ID == "Model.echo.fake"
    assert schema.category == "models/echo"
    assert node_cls.RETURN_NAMES() == MODEL_OUTPUT_NAMES

    inputs = {i.id: i for i in schema.inputs}
    assert inputs["text"].io_type == "STRING" and not inputs["text"].optional
    assert inputs["count"].io_type == "INT" and inputs["count"].optional
    assert inputs["gain"].io_type == "FLOAT"
    assert inputs["mode"].io_type == "COMBO"
    assert inputs["flag"].io_type == "BOOLEAN"
    assert schema.metadata["domain_task"] == "echo"
    assert schema.metadata["domain_provider"] == "fake"


def test_model_node_object_info_contract(monkeypatch):
    """Model.* nodes serve COMBO choices + numeric widget hints via /object_info."""
    monkeypatch.setenv("LEAGENT_DIFFUSION_DEFAULT_MODEL", "fake/model")
    adapter = DiffusersTxt2ImgAdapter(manager=_FakePipelineManager())
    info = build_domain_model_node(adapter).get_schema().get_info_dict()

    assert info["name"] == "Model.image_gen.local"
    assert info["output_name"] == list(MODEL_OUTPUT_NAMES)
    assert len(info["output_colors"]) == len(MODEL_OUTPUT_NAMES)

    optional = info["input"]["optional"]
    # COMBO inputs serialize their wire type as the list of choices.
    model_type, _ = optional["model"]
    assert isinstance(model_type, list) and "fake/model" in model_type
    lora_type, _ = optional["lora"]
    assert isinstance(lora_type, list) and "none" in lora_type
    scheduler_type, _ = optional["scheduler"]
    assert "euler_a" in scheduler_type

    # FLOAT inputs expose slider bounds + widget hint for the editor.
    cfg_type, cfg_opts = optional["cfg_scale"]
    assert cfg_type == "FLOAT"
    assert cfg_opts["min"] == 0.0 and cfg_opts["max"] == 30.0
    assert cfg_opts["widget"] == "float"
    assert "color" in cfg_opts

    # Required prompt renders as a multiline string widget.
    prompt_type, prompt_opts = info["input"]["required"]["prompt"]
    assert prompt_type == "STRING" and prompt_opts["multiline"] is True


async def test_node_execute_returns_envelope():
    adapter = _FakeAdapter()
    node_cls = build_domain_model_node(adapter)
    node = node_cls()

    out = await node.execute(
        hidden=HiddenHolder(unique_id="n1"),
        text="hello",
        count=None,  # None inputs are dropped before invoke
    )
    assert out.error is None
    text, data_b64, mime, envelope, success = out.values
    assert (text, data_b64, mime, success) == ("ok", "", "text/plain", True)
    assert envelope["model"] == "echo-1"
    assert adapter.calls == [{"text": "hello"}]


async def test_node_execute_failure_maps_to_error():
    adapter = _FakeAdapter()
    adapter.result = DomainModelResult(success=False, error="quota exceeded")
    node = build_domain_model_node(adapter)()

    out = await node.execute(hidden=HiddenHolder(unique_id="n1"), text="x")
    assert out.error == "quota exceeded"


async def test_node_progress_callback_plumbing():
    """supports_progress adapters receive `_progress` wired to the registry."""
    spec = DomainModelSpec(
        task="image_gen",
        provider="fake",
        params=(DomainParam(id="prompt", io_type="STRING", required=True),),
        output="image",
        supports_progress=True,
    )
    adapter = _FakeAdapter(spec)
    node = build_domain_model_node(adapter)()

    progress = ProgressRegistry(prompt_id="p1")
    events: list[Any] = []
    progress.add_handler(events.append)

    await node.execute(
        hidden=HiddenHolder(unique_id="node-7", progress=progress),
        prompt="cat",
    )

    (call,) = adapter.calls
    assert callable(call.get("_progress"))
    call["_progress"](3, 25)
    state = progress.state("node-7")
    assert state.value == 3.0 and state.max == 25.0
    assert any(e.type == "progress" and e.node_id == "node-7" for e in events)


async def test_node_without_progress_support_gets_no_callback():
    adapter = _FakeAdapter()  # supports_progress=False
    node = build_domain_model_node(adapter)()
    await node.execute(
        hidden=HiddenHolder(unique_id="n1", progress=ProgressRegistry("p")),
        text="x",
    )
    assert "_progress" not in adapter.calls[0]


# ---------------------------------------------------------------------------
# Diffusion: discovery + adapter against a fake pipeline manager
# ---------------------------------------------------------------------------


class _FakePipelineManager:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def generate(self, **kwargs: Any) -> GenerationResult:
        self.calls.append(kwargs)
        progress = kwargs.get("progress")
        if progress is not None:
            for step in range(1, 4):
                progress(step, 3)
        return GenerationResult(
            png_b64=base64.b64encode(b"\x89PNG fake").decode(),
            seed=kwargs["seed"] if kwargs.get("seed", -1) >= 0 else 1234,
            model=kwargs["model"],
            scheduler=kwargs.get("scheduler", "euler_a"),
            lora=None if kwargs.get("lora") in (None, "none") else kwargs["lora"],
            metadata={"steps": kwargs.get("steps")},
        )


def test_diffusion_discovery(tmp_path, monkeypatch):
    models = tmp_path / "models"
    loras = tmp_path / "loras"
    (models / "sub").mkdir(parents=True)
    (models / "dreamshaper.safetensors").write_bytes(b"x")
    (models / "sub" / "anime.ckpt").write_bytes(b"x")
    (models / "notes.txt").write_text("ignored")
    loras.mkdir()
    (loras / "detail.safetensors").write_bytes(b"x")

    monkeypatch.setenv("LEAGENT_DIFFUSION_MODELS_DIR", str(models))
    monkeypatch.setenv("LEAGENT_DIFFUSION_LORA_DIR", str(loras))
    monkeypatch.setenv("LEAGENT_DIFFUSION_DEFAULT_MODEL", "hub/some-model")

    found = diffusion_manager.discover_models()
    assert "dreamshaper.safetensors" in found
    assert "sub/anime.ckpt" in found
    assert "hub/some-model" in found  # hub default appended
    assert "notes.txt" not in found

    assert diffusion_manager.discover_loras() == ["none", "detail.safetensors"]


async def test_diffusers_adapter_with_fake_manager(monkeypatch):
    monkeypatch.setenv("LEAGENT_DIFFUSION_DEFAULT_MODEL", "fake/model")
    fake = _FakePipelineManager()
    adapter = DiffusersTxt2ImgAdapter(manager=fake)

    assert adapter.spec.key == "image_gen.local"
    assert adapter.spec.supports_progress is True
    param_ids = {p.id for p in adapter.spec.params}
    assert {"prompt", "model", "steps", "cfg_scale", "seed", "scheduler",
            "lora", "lora_scale"} <= param_ids

    steps_seen: list[tuple[int, int]] = []
    result = await adapter.invoke(
        prompt="a cat",
        negative_prompt="dog",
        width=512,
        height=768,
        steps=3,
        cfg_scale=5.5,
        seed=42,
        scheduler="ddim",
        lora="detail.safetensors",
        lora_scale=0.6,
        _progress=lambda s, t: steps_seen.append((s, t)),
    )

    (call,) = fake.calls
    assert call["model"] == "fake/model"
    assert call["prompt"] == "a cat"
    assert call["negative_prompt"] == "dog"
    assert (call["width"], call["height"]) == (512, 768)
    assert call["steps"] == 3 and call["cfg_scale"] == 5.5
    assert call["seed"] == 42 and call["scheduler"] == "ddim"
    assert call["lora"] == "detail.safetensors" and call["lora_scale"] == 0.6

    assert result.success and result.mime == "image/png"
    assert base64.b64decode(result.b64_data or "").startswith(b"\x89PNG")
    assert result.metadata["seed"] == 42
    assert result.metadata["lora"] == "detail.safetensors"
    assert steps_seen == [(1, 3), (2, 3), (3, 3)]


async def test_diffusers_adapter_random_seed_and_defaults(monkeypatch):
    monkeypatch.setenv("LEAGENT_DIFFUSION_DEFAULT_MODEL", "fake/model")
    fake = _FakePipelineManager()
    adapter = DiffusersTxt2ImgAdapter(manager=fake)

    result = await adapter.invoke(prompt="x")
    (call,) = fake.calls
    assert call["seed"] == -1 and call["lora"] == "none"
    assert result.metadata["seed"] == 1234  # fake manager resolved random seed
    assert result.metadata["lora"] is None


async def test_diffusers_adapter_requires_prompt(monkeypatch):
    monkeypatch.setenv("LEAGENT_DIFFUSION_DEFAULT_MODEL", "fake/model")
    adapter = DiffusersTxt2ImgAdapter(manager=_FakePipelineManager())
    result = await adapter.invoke(prompt="")
    assert not result.success and "prompt" in (result.error or "")


@pytest.mark.live
async def test_diffusers_real_pipeline_smoke():
    """Real-pipeline smoke test; requires `uv sync --extra diffusion` + weights."""
    pytest.importorskip("diffusers")
    pytest.importorskip("torch")
    adapter = DiffusersTxt2ImgAdapter()
    result = await adapter.invoke(prompt="a red square", steps=2, width=64, height=64)
    assert result.success and result.b64_data


# ---------------------------------------------------------------------------
# Local audio adapters
# ---------------------------------------------------------------------------


def test_local_audio_env_config(monkeypatch):
    monkeypatch.setenv("LEAGENT_LOCAL_ASR_URL", "http://localhost:8000")
    monkeypatch.setenv("LEAGENT_LOCAL_ASR_MODEL", "large-v3")
    monkeypatch.setenv("LEAGENT_LOCAL_TTS_URL", "http://localhost:8880/v1")
    monkeypatch.delenv("LEAGENT_LOCAL_TTS_MODEL", raising=False)

    asr = LocalWhisperASRAdapter()
    assert asr.spec.key == "asr.local"
    assert asr.spec.model == "large-v3"
    assert asr.base_url == "http://localhost:8000/v1"  # /v1 appended

    tts = LocalTTSAdapter()
    assert tts.spec.key == "tts.local"
    assert tts.base_url == "http://localhost:8880/v1"  # /v1 preserved


def test_local_audio_requires_url(monkeypatch):
    monkeypatch.delenv("LEAGENT_LOCAL_ASR_URL", raising=False)
    monkeypatch.delenv("LEAGENT_LOCAL_TTS_URL", raising=False)
    with pytest.raises(ValueError):
        LocalWhisperASRAdapter()
    with pytest.raises(ValueError):
        LocalTTSAdapter()


# ---------------------------------------------------------------------------
# Builtin registration gating
# ---------------------------------------------------------------------------


def _clear_provider_env(monkeypatch) -> None:
    for var in (
        "DASHSCOPE_API_KEY",
        "OPENAI_API_KEY",
        "LEAGENT_LOCAL_ASR_URL",
        "LEAGENT_LOCAL_TTS_URL",
    ):
        monkeypatch.delenv(var, raising=False)


def test_gating_nothing_configured(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("LEAGENT_DIFFUSION_ENABLED", "0")
    registry = DomainModelRegistry()
    assert register_builtin_domain_models(registry) == []
    assert registry.all() == []


def test_gating_local_audio_urls(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("LEAGENT_DIFFUSION_ENABLED", "0")
    monkeypatch.setenv("LEAGENT_LOCAL_ASR_URL", "http://localhost:8000")
    monkeypatch.setenv("LEAGENT_LOCAL_TTS_URL", "http://localhost:8880")

    registry = DomainModelRegistry()
    registered = register_builtin_domain_models(registry)
    assert set(registered) == {"asr.local", "tts.local"}
    assert registry.get("asr", "local") is not None
    assert registry.get("tts", "local") is not None


def test_gating_diffusion_import(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.delenv("LEAGENT_DIFFUSION_ENABLED", raising=False)
    monkeypatch.setenv("LEAGENT_DIFFUSION_DEFAULT_MODEL", "fake/model")

    import leagent.llm.domain_models.diffusion as diffusion_pkg

    # Simulate diffusers installed without importing torch.
    monkeypatch.setattr(diffusion_pkg, "diffusers_available", lambda: True)
    registry = DomainModelRegistry()
    assert "image_gen.local" in register_builtin_domain_models(registry)
    adapter = registry.get("image_gen", "local")
    assert adapter is not None and adapter.spec.supports_progress

    # Simulate diffusers missing.
    monkeypatch.setattr(diffusion_pkg, "diffusers_available", lambda: False)
    registry2 = DomainModelRegistry()
    assert register_builtin_domain_models(registry2) == []


def test_gating_diffusion_disabled_by_env(monkeypatch):
    _clear_provider_env(monkeypatch)
    monkeypatch.setenv("LEAGENT_DIFFUSION_ENABLED", "0")

    import leagent.llm.domain_models.diffusion as diffusion_pkg

    monkeypatch.setattr(diffusion_pkg, "diffusers_available", lambda: True)
    registry = DomainModelRegistry()
    assert register_builtin_domain_models(registry) == []
