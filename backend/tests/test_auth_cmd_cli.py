"""CLI force password reset (``leagent reset-password``)."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from click.testing import CliRunner

from leagent.cli.auth_cmd import force_reset_password
from leagent.cli.main import cli
from leagent.services.auth.store import reset_security_store_for_tests
from leagent.services.auth.users import UserRecord


@pytest.fixture()
def auth_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    home = tmp_path / "leagent-home"
    home.mkdir()
    monkeypatch.setenv("LEAGENT_HOME", str(home))
    monkeypatch.setenv("LEAGENT_SECRET_KEY", "unit-test-secret-key-32bytes-min")
    store = reset_security_store_for_tests(home / "security.json")
    return store


def test_reset_password_help() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["reset-password", "--help"])
    assert result.exit_code == 0
    assert "--username" in result.output
    assert "--password" in result.output
    assert "--yes" in result.output


def test_force_reset_access_password(auth_home) -> None:
    auth_home.set_access_password("old-password")
    assert auth_home.verify_access_password("old-password")

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["reset-password", "--password", "new-secret", "--yes"],
    )
    assert result.exit_code == 0, result.output
    assert "access password reset" in result.output.lower()
    assert auth_home.verify_access_password("new-secret")
    assert not auth_home.verify_access_password("old-password")


def test_force_reset_aborts_without_yes(auth_home) -> None:
    auth_home.set_access_password("old-password")
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["reset-password", "--password", "new-secret"],
        input="n\n",
    )
    assert result.exit_code == 1
    assert auth_home.verify_access_password("old-password")


def test_force_reset_named_user(monkeypatch: pytest.MonkeyPatch) -> None:
    uid = uuid4()
    calls: list[tuple[object, str]] = []

    monkeypatch.setattr(
        "leagent.services.auth.users.list_users",
        lambda: [
            UserRecord(
                user_id=uid,
                username="alice",
                display_name="Alice",
                role="user",
                disabled=False,
                is_superuser=False,
            )
        ],
    )

    def _set_password(user_id, password: str) -> None:
        calls.append((user_id, password))

    monkeypatch.setattr("leagent.services.auth.users.set_user_password", _set_password)

    summary = force_reset_password(username="alice", password="brand-new")
    assert "alice" in summary.lower()
    assert calls == [(uid, "brand-new")]

    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["reset-password", "-u", "alice", "-p", "another-one", "-y"],
    )
    assert result.exit_code == 0, result.output
    assert calls[-1] == (uid, "another-one")


def test_force_reset_unknown_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("leagent.services.auth.users.list_users", lambda: [])
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["reset-password", "-u", "missing-user", "-p", "brand-new", "-y"],
    )
    assert result.exit_code == 1
    assert "not found" in result.output.lower()
