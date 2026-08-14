"""Resolving a stopped run the way an operator would resolve one.

`attest_task` is the only exit from `intervention_required`, and an operator standing at a bench
does not import `ReferenceRuntime`. If the way out is reachable only from Python, the dead end is
still a dead end for the person who has to walk over and look at the equipment.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import opensdl_cli.main as cli
from opensdl_controller import OpenSDLSystem
from opensdl_core import RunState, TaskState

EXAMPLE = Path(__file__).parents[3] / "examples" / "simulated-color-mixing"


@pytest.fixture
def laboratory(tmp_path: Path) -> Path:
    target = tmp_path / "lab"
    shutil.copytree(EXAMPLE, target, ignore=shutil.ignore_patterns(".opensdl", "__pycache__"))
    return target


async def _stop_a_task(laboratory: Path) -> str:
    """Leave one task of a real run awaiting a person, reached the way a laboratory reaches it.

    The state is not written here. Abandoning a dispatched call is one of the ways the runtime
    arrives at `intervention_required`: the wait was abandoned, the instrument was not, and nothing
    established what happened. Writing the state directly is refused by the machine anyway, which
    is the machine working.
    """

    manifest_path = laboratory / "opensdl.yaml"
    manifest = manifest_path.read_text(encoding="utf-8")
    # Long enough that the call is certainly still in flight when it is abandoned.
    manifest = manifest.replace(
        "        color_noise: 0", "        color_noise: 0\n        latency_seconds: 30"
    )
    manifest_path.write_text(manifest, encoding="utf-8")

    system = OpenSDLSystem.from_manifest(manifest_path)
    await system.start()
    try:
        execution = asyncio.create_task(
            system.runtime.execute_capability(
                "sim.mix_color",
                {
                    "sample_id": "stopped",
                    "red_fraction": 0.5,
                    "blue_fraction": 0.5,
                    "total_mass_g": 5.0,
                },
                environment="simulation",
            )
        )
        await asyncio.sleep(0.4)
        execution.cancel()
        with pytest.raises(asyncio.CancelledError):
            await execution

        run = system.repositories.list_runs()[0]
        task = system.repositories.list_tasks(run.id)[0]
        assert task.state is TaskState.INTERVENTION_REQUIRED
        assert run.state is RunState.INTERVENTION_REQUIRED
        return task.id
    finally:
        await system.close()


@pytest.mark.asyncio
async def test_an_operator_resolves_a_stopped_run_from_the_command_line(laboratory: Path) -> None:
    task_id = await _stop_a_task(laboratory)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "attest",
            task_id,
            "--finding",
            "completed",
            "--basis",
            "plate seated in the mixer with the lid closed; deck otherwise clear",
            "--operator",
            "operator/alice",
            "--manifest",
            str(laboratory / "opensdl.yaml"),
        ],
    )

    assert result.exit_code == 0, result.output
    recorded = json.loads(result.output)
    assert recorded["finding"] == "completed"
    assert recorded["operator_id"] == "operator/alice"
    assert recorded["basis"].startswith("plate seated")
    # The published contract has no field for a measurement, and neither does what the CLI writes.
    assert "outputs" not in recorded


@pytest.mark.asyncio
async def test_the_command_refuses_a_task_nobody_is_waiting_on(laboratory: Path) -> None:
    """A settled task is not established by inspection, and the exit code says refusal."""

    await _stop_a_task(laboratory)
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        [
            "attest",
            "task_does_not_exist",
            "--finding",
            "completed",
            "--basis",
            "it looked fine",
            "--manifest",
            str(laboratory / "opensdl.yaml"),
        ],
    )

    assert result.exit_code == cli.EXIT_NOT_FOUND
    assert "unknown task" in result.output


def test_the_command_refuses_an_attestation_with_no_basis(laboratory: Path) -> None:
    """Someone who cannot say how they know has not established anything."""

    runner = CliRunner()
    result = runner.invoke(
        cli.app,
        [
            "attest",
            "task_anything",
            "--finding",
            "completed",
            "--manifest",
            str(laboratory / "opensdl.yaml"),
        ],
    )

    assert result.exit_code != 0
    assert "basis" in result.output.lower()
