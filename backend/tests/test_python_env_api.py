"""Tests for /api/v1/python-env endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def mock_run() -> MagicMock:
    with patch("leagent.services.python_env.manager.subprocess.run") as m:
        yield m


class TestPythonEnvListPackages:
    def test_list_packages_ok(self, client: TestClient, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='[{"name": "pip", "version": "24.0"}]',
            stderr="",
        )
        r = client.get("/api/v1/python-env/packages")
        assert r.status_code == 200
        data = r.json()
        assert data["packages"] == [{"name": "pip", "version": "24.0"}]
        mock_run.assert_called_once()

    def test_list_packages_failure(self, client: TestClient, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="pip exploded")
        r = client.get("/api/v1/python-env/packages")
        assert r.status_code == 500
        assert "pip exploded" in r.json()["message"]


class TestPythonEnvInstall:
    def test_install_ok(self, client: TestClient, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="OK\n", stderr="")
        r = client.post("/api/v1/python-env/install", json={"spec": "numpy"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_install_bad_spec(self, client: TestClient, mock_run: MagicMock) -> None:
        r = client.post("/api/v1/python-env/install", json={"spec": "bad;inject"})
        assert r.status_code == 400
        mock_run.assert_not_called()

    def test_install_failure(self, client: TestClient, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="no such pkg")
        r = client.post("/api/v1/python-env/install", json={"spec": "nonexistent-xyz-abc"})
        assert r.status_code == 500
        assert "no such pkg" in r.json()["message"]


class TestPythonEnvUninstall:
    def test_uninstall_ok(self, client: TestClient, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=0, stdout="Removed\n", stderr="")
        r = client.post("/api/v1/python-env/uninstall", json={"package": "numpy"})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_uninstall_bad_name(self, client: TestClient, mock_run: MagicMock) -> None:
        r = client.post("/api/v1/python-env/uninstall", json={"package": "bad;name"})
        assert r.status_code == 400
        mock_run.assert_not_called()

    def test_uninstall_failure(self, client: TestClient, mock_run: MagicMock) -> None:
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="not installed")
        r = client.post("/api/v1/python-env/uninstall", json={"package": "numpy"})
        assert r.status_code == 500


class TestPythonEnvInfo:
    def test_info_ok(self, client: TestClient) -> None:
        r = client.get("/api/v1/python-env/info")
        assert r.status_code == 200
        body = r.json()
        assert "python_executable" in body
        assert "backend_root" in body
        assert "uses_uv" in body
