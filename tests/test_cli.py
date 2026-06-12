from __future__ import annotations

from assertpy import assert_that
from typer.testing import CliRunner

from selectel_sm import __version__
from selectel_sm.cli.app import app

runner = CliRunner()


def test_version_command() -> None:
    result = runner.invoke(app, ["version"])
    assert_that(result.exit_code).is_equal_to(0)
    assert_that(result.stdout).contains(__version__)


def test_no_args_shows_help() -> None:
    result = runner.invoke(app, [])
    # no_args_is_help exits with code 0 (newer typer) or 2; help text is what matters.
    assert_that(result.output).contains("auth-check")
