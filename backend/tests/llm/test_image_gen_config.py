"""Image-generation config store + config-aware backends + preset application.

All assertions run credential-free against a temp ``providers.yaml`` so the
real ``~/.leagent`` file is never touched.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import yaml

from leagent.llm.generation import config as cfg
from leagent.llm.generation.backends import SiliconFlowImageBackend
from leagent.llm.generation.config import ImageGenConfigStore, ImageGenPreset


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A store backed by a temp providers.yaml, also installed as the singleton."""
    path = tmp_path / "providers.yaml"
    s = ImageGenConfigStore(path=path)
    monkeypatch.setattr(cfg, "_STORE", s)
    return s


# -- presets ----------------------------------------------------------------


def test_default_presets_present_when_unconfigured(store):
    ids = {p.id for p in store.presets()}
    assert {"offline", "kolors"} <= ids
    assert store.default_preset_id() == ""


def test_upsert_and_get_preset_round_trip(store):
    store.upsert_preset(ImageGenPreset(
        id="myflux", label="My FLUX", backend="siliconflow",
        model="black-forest-labs/FLUX.1-dev", params={"width": 768, "height": 768},
    ))
    got = store.get_preset("myflux")
    assert got is not None
    assert got.backend == "siliconflow"
    assert got.params["width"] == 768
    # survives a fresh store on the same file
    reopened = ImageGenConfigStore(path=store._path)
    assert reopened.get_preset("myflux") is not None


def test_set_default_preset_and_delete(store):
    store.set_default_preset("kolors")
    assert store.default_preset_id() == "kolors"
    assert store.default_preset().backend == "siliconflow"
    # deleting the default clears it
    store.delete_preset("kolors")
    assert store.get_preset("kolors") is None
    assert store.default_preset_id() != "kolors"


def test_set_default_rejects_unknown(store):
    with pytest.raises(cfg.ImageGenConfigError):
        store.set_default_preset("does-not-exist")


# -- backend credentials -----------------------------------------------------


def test_backend_credentials_resolve_env_ref(store, monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-from-env")
    # default template is "${SILICONFLOW_API_KEY}"
    assert store.backend_credentials("siliconflow")["api_key"] == "sk-from-env"


def test_set_backend_credentials_literal_wins(store):
    store.set_backend_credentials("siliconflow", {"api_key": "sk-literal", "base_url": "https://x"})
    creds = store.backend_credentials("siliconflow")
    assert creds["api_key"] == "sk-literal"
    assert creds["base_url"] == "https://x"


def test_siliconflow_backend_available_from_config(store):
    assert SiliconFlowImageBackend().available() is False
    store.set_backend_credentials("siliconflow", {"api_key": "sk-literal"})
    assert SiliconFlowImageBackend().available() is True


def test_http_backend_url_from_config(store):
    store.set_backend_credentials("http_video", {"url": "https://vid.example", "key": "k"})
    url, key = store.backend_credentials("http_video").get("url"), store.backend_credentials("http_video").get("key")
    assert url == "https://vid.example"
    assert key == "k"


# -- local diffusion ---------------------------------------------------------


def test_local_config_defaults_and_update(store):
    cfg_local = store.local_config()
    assert cfg_local["enabled"] is True
    store.set_local_config({"models_dir": "/models/sd", "enabled": False})
    updated = store.local_config()
    assert updated["models_dir"] == "/models/sd"
    assert updated["enabled"] is False


# -- coexistence with chat providers -----------------------------------------


def test_image_gen_section_preserves_other_keys(store):
    # seed a chat-provider doc, then write an image_gen preset
    base_doc = {
        "version": 2,
        "providers": [{"name": "openai", "type": "openai", "models": []}],
        "routing": {"tasks": {"chat": {"provider": "openai", "model": "gpt-4o"}}},
    }
    store._path.write_text(yaml.safe_dump(base_doc), encoding="utf-8")
    store.upsert_preset(ImageGenPreset(id="p1", label="P1", backend="offline"))
    reloaded = yaml.safe_load(store._path.read_text(encoding="utf-8"))
    assert reloaded["providers"][0]["name"] == "openai"
    assert reloaded["routing"]["tasks"]["chat"]["model"] == "gpt-4o"
    assert any(p["id"] == "p1" for p in reloaded["image_gen"]["presets"])


def test_validate_v2_config_preserves_image_gen():
    from leagent.llm.providers_schema import validate_v2_config

    doc = {
        "version": 2,
        "providers": [{"name": "openai", "type": "openai", "models": [
            {"name": "gpt-4o", "kind": "chat", "capabilities": {"input": ["text"], "output": ["text"]}},
        ]}],
        "routing": {"tasks": {"chat": {"provider": "openai", "model": "gpt-4o"}}},
        "image_gen": {"default_preset": "kolors", "presets": [{"id": "kolors", "backend": "siliconflow"}]},
    }
    normalized = validate_v2_config(doc)
    assert normalized["image_gen"]["default_preset"] == "kolors"


# -- preset application in the art node --------------------------------------


@pytest.mark.asyncio
async def test_default_preset_applied_for_auto_node(store, monkeypatch):
    """A node left on ``auto`` adopts the workflow-level default preset."""
    store.upsert_preset(ImageGenPreset(
        id="tiny", label="Tiny", backend="offline",
        params={"width": 128, "height": 128},
    ))
    store.set_default_preset("tiny")

    from leagent.llm.generation import base as gen_base  # noqa: F401 - ensure import path
    from leagent.workflow.io import HiddenHolder
    from leagent.workflow.nodes.art.nodes import ImageGenNode

    captured: dict = {}

    class _FakeService:
        async def generate(self, *, kind, prompt, provider=None, max_retries=0, **params):
            captured["provider"] = provider
            captured["params"] = params
            from leagent.llm.generation.base import GenerationOutput

            return GenerationOutput.failure("image", "stop-before-persist")

    import leagent.llm.generation as gen_pkg

    monkeypatch.setattr(gen_pkg, "get_generation_service", lambda: _FakeService())

    node = ImageGenNode()
    hidden = HiddenHolder(unique_id="img", workflow_state=None,
                          tool_context=SimpleNamespace())
    out = await node.execute(hidden=hidden, prompt="hero", provider="auto")
    assert out.error  # we stopped before persist
    assert captured["provider"] == "offline"  # backend taken from default preset
    assert captured["params"]["width"] == 128


@pytest.mark.asyncio
async def test_explicit_preset_overrides_default(store, monkeypatch):
    store.upsert_preset(ImageGenPreset(id="a", label="A", backend="offline", params={"width": 64, "height": 64}))
    store.upsert_preset(ImageGenPreset(id="b", label="B", backend="offline", params={"width": 200, "height": 200}))
    store.set_default_preset("a")

    captured: dict = {}

    class _FakeService:
        async def generate(self, *, kind, prompt, provider=None, max_retries=0, **params):
            captured["params"] = params
            from leagent.llm.generation.base import GenerationOutput

            return GenerationOutput.failure("image", "stop")

    import leagent.llm.generation as gen_pkg

    monkeypatch.setattr(gen_pkg, "get_generation_service", lambda: _FakeService())

    from types import SimpleNamespace as NS

    from leagent.workflow.io import HiddenHolder
    from leagent.workflow.nodes.art.nodes import ImageGenNode

    node = ImageGenNode()
    hidden = HiddenHolder(unique_id="img", workflow_state=None, tool_context=NS())
    await node.execute(hidden=hidden, prompt="hero", provider="auto", preset="b")
    assert captured["params"]["width"] == 200
