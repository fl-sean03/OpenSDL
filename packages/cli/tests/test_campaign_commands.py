"""The closed loop, driven the way an operator would drive it.

A campaign was reachable only from bespoke `asyncio` Python: `examples/simulated-color-mixing/
run_campaign.py` was the entire interface. These tests run the reference laboratory's campaign
through the shipped command line and read it back, because "the headline feature has an interface"
is only true if the interface starts a real campaign against a real manifest.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import typer.main
from typer.testing import CliRunner

import opensdl_cli.main as cli

EXAMPLE = Path(__file__).parents[3] / "examples" / "simulated-color-mixing"
OPTIMIZER_CONFIG = json.dumps(
    {
        "candidates": [
            {"red_fraction": 0.0, "blue_fraction": 1.0},
            {"red_fraction": 0.5, "blue_fraction": 0.5},
        ]
    }
)
BASE_INPUTS = json.dumps({"total_mass_g": 5.0, "target_rgb": [127.5, 0.0, 127.5]})


@pytest.fixture
def laboratory(tmp_path: Path) -> Path:
    target = tmp_path / "lab"
    shutil.copytree(EXAMPLE, target, ignore=shutil.ignore_patterns(".opensdl", "__pycache__"))
    return target


def test_a_campaign_starts_from_the_command_line_and_reads_back(laboratory: Path) -> None:
    runner = CliRunner()

    started = runner.invoke(
        cli.app,
        [
            "campaign",
            "start",
            str(laboratory / "workflow.yaml"),
            "--manifest",
            str(laboratory / "opensdl.yaml"),
            "--optimizer",
            "grid",
            "--optimizer-config",
            OPTIMIZER_CONFIG,
            "--base-inputs",
            BASE_INPUTS,
            "--max-iterations",
            "2",
            "--iteration-id-input",
            "sample_id",
            "--operator-id",
            "operator/cli-test",
        ],
    )

    assert started.exit_code == 0, started.output
    record = json.loads(started.stdout)
    assert record["state"] == "completed"
    assert record["stop_reason"] == "max_iterations"
    assert record["succeeded"] == 2
    assert record["failed"] == 0
    # The environment is the laboratory's, never the caller's: policy is evaluated against it.
    assert record["environment"] == "simulation"
    assert record["operator_id"] == "operator/cli-test"
    assert record["best"]["candidate"] == {"red_fraction": 0.5, "blue_fraction": 0.5}
    campaign_id = record["campaign_id"]

    listed = runner.invoke(
        cli.app, ["campaign", "list", "--manifest", str(laboratory / "opensdl.yaml")]
    )
    assert listed.exit_code == 0, listed.output
    assert [item["campaign_id"] for item in json.loads(listed.stdout)] == [campaign_id]

    inspected = runner.invoke(
        cli.app,
        ["campaign", "inspect", campaign_id, "--manifest", str(laboratory / "opensdl.yaml")],
    )
    assert inspected.exit_code == 0, inspected.output
    inspection = json.loads(inspected.stdout)
    assert inspection["campaign"]["campaign_id"] == campaign_id
    assert [item["state"] for item in inspection["campaign"]["iterations"]] == [
        "succeeded",
        "succeeded",
    ]
    # Every run and task event of every iteration answers to the campaign, so the execution
    # history is one query rather than a walk through decision payloads.
    assert {"CampaignStarted", "RunCreated", "TaskSucceeded", "RunCompleted"} <= {
        event["type"] for event in inspection["events"]
    }

    scoped = runner.invoke(
        cli.app,
        [
            "events",
            "--manifest",
            str(laboratory / "opensdl.yaml"),
            "--campaign-id",
            campaign_id,
        ],
    )
    assert scoped.exit_code == 0, scoped.output
    assert {event["campaign_id"] for event in json.loads(scoped.stdout)} == {campaign_id}


def test_the_campaign_environment_is_not_a_command_line_option(laboratory: Path) -> None:
    """A campaign that could state its own environment would write a false provenance record.

    The environment comes from the manifest, so a laboratory that declares `production` cannot
    have its one unattended path talked into recording `simulation`.

    Read against the command's declared parameters rather than its rendered help. Rich wraps and
    truncates that help to the terminal width, so an earlier form of this test asserted on a string
    whose content depended on how wide the terminal was: it passed locally, passed in CI, and then
    failed in CI alone the day three options were added and `--operator-id` became `--operator-i…`.
    """
    group = typer.main.get_command(cli.app)
    start = group.commands["campaign"].commands["start"]  # type: ignore[attr-defined]
    declared = {option for parameter in start.params for option in parameter.opts}

    assert "--environment" not in declared
    assert "--operator-id" in declared


def test_inspecting_a_campaign_that_was_never_recorded_is_a_clean_not_found(
    laboratory: Path,
) -> None:
    runner = CliRunner()
    runner.invoke(
        cli.app,
        [
            "campaign",
            "start",
            str(laboratory / "workflow.yaml"),
            "--manifest",
            str(laboratory / "opensdl.yaml"),
            "--optimizer",
            "grid",
            "--optimizer-config",
            OPTIMIZER_CONFIG,
            "--base-inputs",
            BASE_INPUTS,
            "--max-iterations",
            "1",
            "--iteration-id-input",
            "sample_id",
        ],
    )

    result = runner.invoke(
        cli.app,
        ["campaign", "inspect", "campaign-nothing", "--manifest", str(laboratory / "opensdl.yaml")],
    )

    assert result.exit_code == cli.EXIT_NOT_FOUND
    assert "Traceback" not in result.output


def test_an_unknown_optimizer_names_the_ones_that_exist(laboratory: Path) -> None:
    result = CliRunner().invoke(
        cli.app,
        [
            "campaign",
            "start",
            str(laboratory / "workflow.yaml"),
            "--manifest",
            str(laboratory / "opensdl.yaml"),
            "--optimizer",
            "bayesian",
        ],
    )

    assert result.exit_code == cli.EXIT_NOT_FOUND
    assert "Traceback" not in result.output
    assert "grid" in result.output
