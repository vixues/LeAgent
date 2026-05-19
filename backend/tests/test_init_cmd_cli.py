"""CLI help surface for leagent init."""

from __future__ import annotations

from click.testing import CliRunner

from leagent.cli.main import cli


def test_init_help_includes_defaults_flag() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["init", "--help"])
    assert result.exit_code == 0
    assert "--defaults" in result.output
