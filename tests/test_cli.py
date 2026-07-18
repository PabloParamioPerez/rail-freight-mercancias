"""CLI wiring. Offline: --help never runs a command body, and `info` only reads settings."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from redferro.cli import app

runner = CliRunner()


def test_root_help_lists_subcommands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for name in ("network", "db", "hab", "map", "info"):
        assert name in result.stdout


@pytest.mark.parametrize(
    "args",
    [
        ["network", "--help"],
        ["network", "fetch", "--help"],
        ["db", "build", "--help"],
        ["hab", "graph", "--help"],
        ["map", "--help"],
    ],
)
def test_subcommand_help(args: list[str]):
    """Typer builds each command's parser here, which is what catches a bad
    Option annotation — mypy cannot, since typer.Option is typed as Any."""
    result = runner.invoke(app, args)
    assert result.exit_code == 0


def test_optional_flags_are_declared_optional():
    assert "--stamp" in runner.invoke(app, ["network", "fetch", "--help"]).stdout
    assert "--as-of" in runner.invoke(app, ["hab", "graph", "--help"]).stdout


def test_info_reports_resolved_settings():
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "EPSG:25830" in result.stdout


def test_no_args_shows_usage():
    """no_args_is_help prints usage; exit code 2 is click's missing-subcommand
    convention, not a crash."""
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "Usage:" in result.stdout
