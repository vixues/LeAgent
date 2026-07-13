"""Tests for the security control plane (auth setup/login, enforce, ownership)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from leagent.services.auth.secrets import clear_secret_cache
from leagent.services.auth.service import LOCAL_USER_ID, AuthService, init_auth_service
from leagent.services.auth.store import reset_security_store_for_tests


@pytest.fixture()
def auth_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "leagent-home"
    home.mkdir()
    monkeypatch.setenv("LEAGENT_HOME", str(home))
    monkeypatch.setenv("LEAGENT_SECRET_KEY", "unit-test-secret-key-32bytes-min")
    clear_secret_cache()
    store = reset_security_store_for_tests(home / "security.json")
    return store


def test_effective_enforce_auth_auto_on_open_bind(auth_home) -> None:
    from leagent.services.auth.policy import effective_enforce_auth

    class Sec:
        enforce_auth = None

    class S:
        host = "0.0.0.0"
        desktop_mode = False
        security = Sec()

    assert effective_enforce_auth(S()) is True

    class Loop:
        host = "127.0.0.1"
        desktop_mode = False
        security = Sec()

    assert effective_enforce_auth(Loop()) is False


def test_setup_login_roundtrip(auth_home, client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LEAGENT_SECURITY_ENFORCE_AUTH", "true")
    # Re-init settings cache is hard; drive AuthService directly + HTTP with override.

    status = client.get("/api/v1/auth/status")
    assert status.status_code == 200
    assert status.json()["setup_complete"] is False

    bad = client.post("/api/v1/auth/setup", json={"password": "123"})
    assert bad.status_code == 422

    setup = client.post(
        "/api/v1/auth/setup",
        json={"password": "secret12", "confirm_password": "secret12"},
    )
    assert setup.status_code == 200
    token = setup.json()["access_token"]
    assert token

    again = client.post(
        "/api/v1/auth/setup",
        json={"password": "secret12", "confirm_password": "secret12"},
    )
    assert again.status_code == 409

    login = client.post("/api/v1/auth/login", json={"password": "secret12"})
    assert login.status_code == 200
    access = login.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["role"] == "admin"


def test_auth_service_enforced_tokens(auth_home) -> None:
    class Sec:
        enforce_auth = True

    class S:
        host = "0.0.0.0"
        desktop_mode = False
        secret_key = "unit-test-secret-key-32bytes-min"
        security = Sec()
        files = type("F", (), {"signed_url_secret": ""})()

    svc = init_auth_service(S())
    assert svc.verify_access_token("garbage") is None
    tok = svc.create_access_token(LOCAL_USER_ID, role="admin", username="admin")
    assert svc.verify_access_token(tok) == LOCAL_USER_ID


def test_assert_execution_owner_helper() -> None:
    from fastapi import HTTPException

    from leagent.workflow.server.router import _assert_execution_owner

    uid = uuid4()
    _assert_execution_owner({"user_id": str(uid)}, uid)
    with pytest.raises(HTTPException) as ei:
        _assert_execution_owner({"user_id": str(uuid4())}, uid)
    assert ei.value.status_code == 403
