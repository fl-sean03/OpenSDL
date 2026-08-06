from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from typer.testing import CliRunner

import opensdl_cli.main as cli
from opensdl_twin import TwinProjectionError


def test_run_command_passes_caller_supplied_run_id(monkeypatch) -> None:
    received: dict[str, object] = {}

    async def fake_run(
        manifest: Path,
        workflow: Path,
        inputs: dict[str, object],
        operator_id: str,
        *,
        run_id: str | None = None,
    ) -> dict[str, object]:
        received.update(
            manifest=manifest,
            workflow=workflow,
            inputs=inputs,
            operator_id=operator_id,
            run_id=run_id,
        )
        return {"id": run_id}

    monkeypatch.setattr(cli, "_run", fake_run)

    result = CliRunner().invoke(
        cli.app,
        ["run", "workflow.yaml", "--run-id", "run-stable"],
    )

    assert result.exit_code == 0, result.output
    assert received["run_id"] == "run-stable"
    assert json.loads(result.stdout)["id"] == "run-stable"


def test_twin_validate_uses_public_loader(tmp_path: Path, monkeypatch) -> None:
    definition_path = tmp_path / "twin.yaml"
    load = Mock(return_value=SimpleNamespace(definition_path=definition_path.resolve()))
    monkeypatch.setattr(cli, "load_twin_definition", load)

    result = CliRunner().invoke(cli.app, ["twin", "validate", str(definition_path)])

    assert result.exit_code == 0, result.output
    load.assert_called_once_with(definition_path)
    # Whitespace-collapsed, because the console wraps to the terminal width and a long path
    # is broken across lines. Asserting on the rendered string directly made this test pass
    # or fail on how wide the terminal happened to be.
    assert str(definition_path.resolve()) in "".join(result.stdout.split())


def test_twin_validate_reports_invalid_definition_without_traceback(
    tmp_path: Path, monkeypatch
) -> None:
    definition_path = tmp_path / "invalid.yaml"
    monkeypatch.setattr(
        cli,
        "load_twin_definition",
        Mock(side_effect=ValueError("revision is required")),
    )

    result = CliRunner().invoke(cli.app, ["twin", "validate", str(definition_path)])

    assert result.exit_code == cli.EXIT_INVALID
    assert "Twin validation failed: revision is required" in result.stderr
    assert "Traceback" not in result.output


def test_twin_project_uses_configured_system(monkeypatch) -> None:
    dispose = Mock()
    system = SimpleNamespace(
        twin=object(),
        database=SimpleNamespace(dispose=dispose),
        project_twin_run=Mock(
            return_value={
                "run_id": "run-1",
                "definition_revision": "rev-1",
                "cues": [],
            }
        ),
    )
    monkeypatch.setattr(
        cli.OpenSDLSystem,
        "from_manifest",
        lambda manifest, **options: system,
    )

    result = CliRunner().invoke(
        cli.app,
        ["twin", "project", "run-1", "--manifest", "lab.yaml"],
    )

    assert result.exit_code == 0, result.output
    system.project_twin_run.assert_called_once_with("run-1")
    assert json.loads(result.stdout)["definition_revision"] == "rev-1"
    dispose.assert_called_once_with()


def test_twin_project_reports_incompatible_binding_without_traceback(monkeypatch) -> None:
    dispose = Mock()
    system = SimpleNamespace(
        twin=object(),
        database=SimpleNamespace(dispose=dispose),
        project_twin_run=Mock(
            side_effect=TwinProjectionError(
                "run 'run-old' was recorded against a different twin definition"
            )
        ),
    )
    monkeypatch.setattr(cli.OpenSDLSystem, "from_manifest", lambda manifest, **options: system)

    result = CliRunner().invoke(
        cli.app,
        ["twin", "project", "run-old", "--manifest", "lab.yaml"],
    )

    assert result.exit_code == cli.EXIT_INVALID
    assert "Twin projection failed" in result.stderr
    assert "different twin definition" in result.stderr
    assert "Traceback" not in result.output
    dispose.assert_called_once_with()
