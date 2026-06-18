"""Contract tests for ``/api/v1/models/image-gen`` against a temp providers.yaml."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from leagent.llm.generation import config as cfg
from leagent.llm.generation.config import ImageGenConfigStore

_BASE = "/api/v1/models/image-gen"


@pytest.fixture()
def temp_config(tmp_path, monkeypatch):
    """Point the image-gen config singleton at a temp file for the whole test."""
    store = ImageGenConfigStore(path=tmp_path / "providers.yaml")
    monkeypatch.setattr(cfg, "_STORE", store)
    # endpoints call reset_image_gen_config(); make it rebuild on the temp path
    monkeypatch.setattr(cfg, "PROVIDERS_PATH", tmp_path / "providers.yaml")
    yield store


def test_list_presets_returns_defaults(client: TestClient, temp_config: Any) -> None:
    resp = client.get(f"{_BASE}/presets")
    assert resp.status_code == 200, resp.text
    ids = {p["id"] for p in resp.json()}
    assert "kolors" in ids


def test_create_update_delete_preset(client: TestClient, temp_config: Any) -> None:
    create = client.post(f"{_BASE}/presets", json={
        "id": "custom", "label": "Custom", "backend": "siliconflow",
        "model": "Kwai-Kolors/Kolors", "params": {"width": 512, "height": 512},
    })
    assert create.status_code == 201, create.text

    dup = client.post(f"{_BASE}/presets", json={"id": "custom", "backend": "offline"})
    assert dup.status_code == 409

    update = client.put(f"{_BASE}/presets/custom", json={
        "id": "custom", "label": "Custom 2", "backend": "siliconflow",
        "model": "black-forest-labs/FLUX.1-dev", "params": {"width": 1024, "height": 1024},
    })
    assert update.status_code == 200
    assert update.json()["label"] == "Custom 2"

    delete = client.delete(f"{_BASE}/presets/custom")
    assert delete.status_code == 204
    assert client.delete(f"{_BASE}/presets/custom").status_code == 404


def test_default_preset_roundtrip(client: TestClient, temp_config: Any) -> None:
    client.post(f"{_BASE}/presets", json={"id": "p1", "backend": "offline"})
    put = client.put(f"{_BASE}/default", json={"preset_id": "p1"})
    assert put.status_code == 200
    assert client.get(f"{_BASE}/default").json()["preset_id"] == "p1"

    bad = client.put(f"{_BASE}/default", json={"preset_id": "nope"})
    assert bad.status_code == 400


def test_backends_and_models(client: TestClient, temp_config: Any) -> None:
    backends = client.get(f"{_BASE}/backends")
    assert backends.status_code == 200
    by_name = {b["name"]: b for b in backends.json()}
    assert by_name["offline"]["available"] is True
    assert by_name["siliconflow"]["credential_type"] == "api_key"
    assert by_name["http_video"]["credential_type"] == "http"

    models = client.get(f"{_BASE}/models", params={"backend": "siliconflow"})
    assert models.status_code == 200
    assert "Kwai-Kolors/Kolors" in models.json()


def test_credentials_status_and_update(client: TestClient, temp_config: Any) -> None:
    status = client.get(f"{_BASE}/credentials")
    assert status.status_code == 200
    names = {c["name"] for c in status.json()}
    assert {"siliconflow", "http_video"} <= names

    put = client.put(f"{_BASE}/credentials/siliconflow", json={"api_key": "sk-test", "base_url": "https://x"})
    assert put.status_code == 200
    assert put.json()["configured"] is True
    # secret is never returned
    assert "sk-test" not in put.text
    # blank api_key preserves the existing secret
    again = client.put(f"{_BASE}/credentials/siliconflow", json={"api_key": ""})
    assert again.json()["configured"] is True


def test_local_config_roundtrip(client: TestClient, temp_config: Any) -> None:
    get = client.get(f"{_BASE}/local")
    assert get.status_code == 200
    assert "discovered_models" in get.json()

    put = client.put(f"{_BASE}/local", json={
        "enabled": True, "models_dir": "/tmp/models", "lora_dir": "", "default_model": "",
    })
    assert put.status_code == 200
    assert put.json()["models_dir"] == "/tmp/models"


def test_test_endpoint_offline_preset(client: TestClient, temp_config: Any) -> None:
    client.post(f"{_BASE}/presets", json={
        "id": "off", "backend": "offline", "params": {"width": 128, "height": 128},
    })
    resp = client.post(f"{_BASE}/test", json={"preset_id": "off"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["placeholder"] is True


def test_backends_include_audio_and_concrete(client: TestClient, temp_config: Any) -> None:
    backends = client.get(f"{_BASE}/backends")
    assert backends.status_code == 200, backends.text
    by_name = {b["name"]: b for b in backends.json()}
    # Concrete starters + the audio-capable offline floor are enumerated.
    assert "replicate" in by_name
    assert "elevenlabs" in by_name
    assert "audio" in by_name["offline"]["kinds"]
    assert "audio" in by_name["elevenlabs"]["kinds"]


def test_test_endpoint_audio_preset_offline(client: TestClient, temp_config: Any) -> None:
    client.post(f"{_BASE}/presets", json={
        "id": "tts-off", "backend": "offline", "kind": "audio", "params": {},
    })
    resp = client.post(f"{_BASE}/test", json={"preset_id": "tts-off"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["success"] is True
    assert body["placeholder"] is True


def test_custom_provider_crud(client: TestClient, temp_config: Any) -> None:
    create = client.post(f"{_BASE}/providers", json={
        "name": "my-openai", "kinds": ["image", "audio"], "protocol": "openai",
        "base_url": "https://api.example.com/v1", "api_key": "sk-secret",
        "models": ["my-image", "my-tts"], "enabled": True,
    })
    assert create.status_code == 201, create.text
    info = create.json()
    assert info["configured"] is True
    # secret is never returned
    assert "sk-secret" not in create.text

    dup = client.post(f"{_BASE}/providers", json={"name": "my-openai", "protocol": "openai"})
    assert dup.status_code == 409

    # reserved backend names are rejected
    bad = client.post(f"{_BASE}/providers", json={"name": "offline", "protocol": "http"})
    assert bad.status_code == 400

    listed = client.get(f"{_BASE}/providers")
    assert "my-openai" in {p["name"] for p in listed.json()}

    # custom provider appears in the backends + models introspection
    backends = {b["name"]: b for b in client.get(f"{_BASE}/backends").json()}
    assert backends["my-openai"]["credential_type"] == "custom"
    models = client.get(f"{_BASE}/models", params={"backend": "my-openai"})
    assert models.json() == ["my-image", "my-tts"]

    # blank api_key preserves the stored secret
    update = client.put(f"{_BASE}/providers/my-openai", json={
        "name": "my-openai", "kinds": ["image"], "protocol": "openai",
        "base_url": "https://api.example.com/v1", "api_key": "",
        "models": ["my-image"], "enabled": True,
    })
    assert update.status_code == 200
    assert update.json()["configured"] is True

    delete = client.delete(f"{_BASE}/providers/my-openai")
    assert delete.status_code == 204
    assert client.delete(f"{_BASE}/providers/my-openai").status_code == 404
