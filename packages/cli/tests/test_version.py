from importlib.metadata import version as distribution_version

from typer.testing import CliRunner

from opensdl_cli.main import app


def test_version_command_uses_installed_distribution_metadata() -> None:
    result = CliRunner().invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == distribution_version("opensdl-cli")
