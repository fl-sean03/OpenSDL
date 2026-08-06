"""Diagnostics every ordinary mistake produces.

A command-line tool is judged by what it does when the user is wrong, not when the user is right.
Every case here is a mistake a first-time operator makes on their first afternoon: a path that does
not exist, a plugin name that was guessed, a capability spelled the way the instrument vendor spells
it. Each one must produce a single readable line on stderr and an exit code that says which kind of
failure it was, because an operator reading a wrapped traceback through framework internals learns
nothing and a supervising script reading exit code 1 learns less.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml
from typer.testing import CliRunner

import opensdl_cli.main as cli

EXAMPLE = Path(__file__).parents[3] / "examples" / "simulated-color-mixing"
INPUTS = json.dumps(
    {
        "sample_id": "s",
        "red_fraction": 0.5,
        "blue_fraction": 0.5,
        "total_mass_g": 5,
        "target_rgb": [127.5, 0, 127.5],
    }
)


def _lab(tmp_path: Path) -> Path:
    target = tmp_path / "lab"
    shutil.copytree(EXAMPLE, target, ignore=shutil.ignore_patterns(".opensdl", "__pycache__"))
    return target


def _recorded_lab(tmp_path: Path) -> Path:
    """A laboratory with a store, because a read command against one without has its own answer."""
    lab = _lab(tmp_path)
    result = CliRunner().invoke(
        cli.app,
        [
            "run",
            str(lab / "workflow.yaml"),
            "--manifest",
            str(lab / "opensdl.yaml"),
            "--inputs",
            INPUTS,
        ],
    )
    assert result.exit_code == 0, result.output
    return lab


def _rewrite(path: Path, edit) -> Path:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    edit(document)
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def _assert_clean(result, *, exit_code: int) -> None:
    """A clean failure is one line the operator can act on, and nothing about our machine."""
    assert result.exit_code == exit_code, result.output
    assert "Traceback" not in result.output
    assert ".venv" not in result.output
    assert "site-packages" not in result.output
    assert len(result.stderr.strip().splitlines()) == 1, result.stderr


def test_a_missing_manifest_is_reported_as_a_missing_file(tmp_path: Path) -> None:
    result = CliRunner().invoke(cli.app, ["validate", str(tmp_path / "nope.yaml")])

    _assert_clean(result, exit_code=cli.EXIT_NOT_FOUND)
    assert "nope.yaml" in result.stderr


def test_a_missing_workflow_is_reported_as_a_missing_file(tmp_path: Path) -> None:
    lab = _lab(tmp_path)

    result = CliRunner().invoke(
        cli.app,
        ["run", str(lab / "gone.yaml"), "--manifest", str(lab / "opensdl.yaml")],
    )

    _assert_clean(result, exit_code=cli.EXIT_NOT_FOUND)
    assert "gone.yaml" in result.stderr


def test_inputs_that_are_not_json_are_reported_as_invalid(tmp_path: Path) -> None:
    lab = _lab(tmp_path)

    result = CliRunner().invoke(
        cli.app,
        [
            "run",
            str(lab / "workflow.yaml"),
            "--manifest",
            str(lab / "opensdl.yaml"),
            "--inputs",
            "{not json}",
        ],
    )

    _assert_clean(result, exit_code=cli.EXIT_INVALID)


def test_inspect_reports_an_unknown_run_instead_of_a_key_error(tmp_path: Path) -> None:
    lab = _recorded_lab(tmp_path)

    result = CliRunner().invoke(
        cli.app,
        ["inspect", "run-does-not-exist", "--manifest", str(lab / "opensdl.yaml")],
    )

    _assert_clean(result, exit_code=cli.EXIT_NOT_FOUND)
    assert "run-does-not-exist" in result.stderr


def test_export_reports_an_unknown_run_instead_of_a_key_error(tmp_path: Path) -> None:
    lab = _recorded_lab(tmp_path)

    result = CliRunner().invoke(
        cli.app,
        ["export", "run-does-not-exist", "--manifest", str(lab / "opensdl.yaml")],
    )

    _assert_clean(result, exit_code=cli.EXIT_NOT_FOUND)
    assert "run-does-not-exist" in result.stderr


def test_reading_a_laboratory_that_has_never_run_says_so_and_creates_nothing(
    tmp_path: Path,
) -> None:
    """Inspecting a nonexistent run used to create the store, its tables, and its seed rows."""
    lab = _lab(tmp_path)

    result = CliRunner().invoke(
        cli.app,
        ["inspect", "run-does-not-exist", "--manifest", str(lab / "opensdl.yaml")],
    )

    _assert_clean(result, exit_code=cli.EXIT_NOT_FOUND)
    assert "recorded no runs yet" in result.stderr
    assert not (lab / ".opensdl").exists()


def test_an_unknown_adapter_plugin_keeps_the_registry_message_and_loses_the_traceback(
    tmp_path: Path,
) -> None:
    """The plugin registry already writes the best error in the project. Do not flatten it."""
    lab = _lab(tmp_path)
    manifest = _rewrite(
        lab / "opensdl.yaml",
        lambda document: document["spec"]["adapters"][0].update(plugin="opentrons-ot2"),
    )

    result = CliRunner().invoke(
        cli.app,
        ["run", str(lab / "workflow.yaml"), "--manifest", str(manifest), "--inputs", INPUTS],
    )

    _assert_clean(result, exit_code=cli.EXIT_NOT_FOUND)
    assert "unknown adapter plugin 'opentrons-ot2'" in result.stderr
    assert "available: human-task, local-compute, simulated-lab" in result.stderr


def test_a_denied_execution_exits_differently_from_a_crash(tmp_path: Path) -> None:
    lab = _lab(tmp_path)
    manifest = _rewrite(
        lab / "opensdl.yaml",
        lambda document: document["spec"]["policy"].update(default_effect="deny", rules=[]),
    )

    result = CliRunner().invoke(
        cli.app,
        ["run", str(lab / "workflow.yaml"), "--manifest", str(manifest), "--inputs", INPUTS],
    )

    _assert_clean(result, exit_code=cli.EXIT_DENIED)
    assert "denied" in result.stderr
    assert "default policy effect" in result.stderr


def test_a_refusal_written_by_the_runtime_reaches_the_operator_whole(
    tmp_path: Path, monkeypatch
) -> None:
    """The runtime's ambiguous-resume refusal is a paragraph of safety reasoning.

    Wave 1 wrote it precisely because the operator has to be told that OpenSDL does not know
    whether the physical action happened. An error boundary that truncates it to a summary
    destroys the only place that reasoning is delivered.
    """
    refusal = (
        "cannot resume run run-1: task task-1 for step 'mix' (capability sim.mix_color) is "
        "recorded as 'intervention_required', so OpenSDL does not know whether the physical "
        "action already happened and will not dispatch it again."
    )

    async def refuse(*args: object, **kwargs: object) -> dict[str, object]:
        raise cli_workflow_error(refusal)

    monkeypatch.setattr(cli, "_run", refuse)

    result = CliRunner().invoke(cli.app, ["run", "workflow.yaml"])

    _assert_clean(result, exit_code=cli.EXIT_FAILED)
    assert refusal in result.stderr


def cli_workflow_error(message: str) -> Exception:
    from opensdl_core import WorkflowExecutionError

    return WorkflowExecutionError(message)


def test_the_traceback_stays_reachable_for_debugging(tmp_path: Path) -> None:
    result = CliRunner().invoke(
        cli.app,
        ["--traceback", "validate", str(tmp_path / "nope.yaml")],
    )

    assert isinstance(result.exception, FileNotFoundError)


def test_the_traceback_env_var_reaches_the_same_place(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENSDL_TRACEBACK", "1")

    result = CliRunner().invoke(cli.app, ["validate", str(tmp_path / "nope.yaml")])

    assert isinstance(result.exception, FileNotFoundError)


def test_every_public_failure_class_has_a_declared_exit_code() -> None:
    """The taxonomy is matched by name, so a renamed class must fail here rather than in the field.

    `scripts/check-boundaries.py` deliberately keeps `opensdl_cli` off `opensdl_core`, so the
    boundary cannot classify by `isinstance`. This test is what makes the name table trustworthy.
    """
    import opensdl_core

    public_errors = {
        name
        for name, value in vars(opensdl_core).items()
        if isinstance(value, type) and issubclass(value, Exception)
    }

    assert public_errors, "opensdl_core exports no error classes; the taxonomy test is vacuous"
    assert public_errors <= set(cli.EXIT_BY_FAILURE)


def test_the_exit_codes_distinguish_the_failures_they_name() -> None:
    codes = {
        cli.EXIT_INTERNAL,
        cli.EXIT_USAGE,
        cli.EXIT_INVALID,
        cli.EXIT_NOT_FOUND,
        cli.EXIT_DENIED,
        cli.EXIT_BUSY,
        cli.EXIT_TIMEOUT,
        cli.EXIT_CONFLICT,
        cli.EXIT_FAILED,
    }

    assert len(codes) == 9


# --- F1: validate must resolve what it certifies -------------------------------------------


def test_validate_rejects_a_manifest_naming_an_adapter_plugin_that_does_not_exist(
    tmp_path: Path,
) -> None:
    lab = _lab(tmp_path)
    manifest = _rewrite(
        lab / "opensdl.yaml",
        lambda document: document["spec"]["adapters"][0].update(plugin="opentrons-ot2"),
    )

    result = CliRunner().invoke(cli.app, ["validate", str(manifest)])

    assert result.exit_code != 0, result.output
    assert "unknown adapter plugin 'opentrons-ot2'" in result.stderr
    assert "Manifest valid" not in result.stdout


def test_validate_rejects_a_workflow_naming_a_capability_the_laboratory_does_not_expose(
    tmp_path: Path,
) -> None:
    lab = _lab(tmp_path)
    workflow = _rewrite(
        lab / "workflow.yaml",
        lambda document: document["steps"][0].update(capability="sim.mix_colour"),
    )

    result = CliRunner().invoke(
        cli.app,
        ["validate", str(lab / "opensdl.yaml"), "--workflow", str(workflow)],
    )

    assert result.exit_code == cli.EXIT_NOT_FOUND, result.output
    assert "sim.mix_colour" in result.stderr
    assert "sim.mix_color" in result.stderr, "the operator needs the available capabilities"
    assert "Workflow valid" not in result.stdout


def test_validate_accepts_the_reference_laboratory_and_its_workflow(tmp_path: Path) -> None:
    lab = _lab(tmp_path)

    result = CliRunner().invoke(
        cli.app,
        ["validate", str(lab / "opensdl.yaml"), "--workflow", str(lab / "workflow.yaml")],
    )

    assert result.exit_code == 0, result.output
    assert "Manifest valid" in result.stdout
    assert "Workflow valid" in result.stdout


def test_validate_does_not_create_the_configured_store(tmp_path: Path) -> None:
    """`validate` answers a question. Answering it must not build the laboratory's database."""
    lab = _lab(tmp_path)

    result = CliRunner().invoke(
        cli.app,
        ["validate", str(lab / "opensdl.yaml"), "--workflow", str(lab / "workflow.yaml")],
    )

    assert result.exit_code == 0, result.output
    assert not (lab / ".opensdl").exists(), sorted(path.name for path in lab.iterdir())
