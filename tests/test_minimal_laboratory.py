"""The smallest laboratory that works must keep working, and keep being small.

This is the enforcement mechanism for the scale-invariance decision in
`docs/development/buildout.md`. Facility work must not tax the one-bench case, and the observable
form of that promise being broken is the *minimum* growing: one new required field, one newly
mandatory service, one more line nobody can omit.

Nothing else in the suite would notice. Every other test declares a laboratory rich enough to
exercise what it is testing, so a field becoming required is invisible until somebody with one
instrument tries to start and cannot.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from opensdl_controller import OpenSDLSystem
from opensdl_core import (
    CapabilityDefinition,
    ExecutionResult,
    ExecutorType,
    ResultBasis,
    RunState,
    TaskState,
)
from opensdl_schemas import validate_manifest_file

MINIMAL = Path(__file__).parents[1] / "examples" / "computation-only" / "opensdl.yaml"

#: The smallest laboratory is 17 lines today. The headroom is deliberately thin: this number is
#: meant to be argued with in review, not quietly absorbed. Raising it is a decision about who the
#: framework is for, and `docs/development/buildout.md` asks that such a decision be justified.
MANIFEST_LINE_LIMIT = 20


def test_the_smallest_laboratory_stays_small() -> None:
    """A required field added for facility scale would show up here first."""

    lines = MINIMAL.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) <= MANIFEST_LINE_LIMIT, (
        f"the minimal laboratory manifest is now {len(lines)} lines, over the {MANIFEST_LINE_LIMIT} "
        "line limit. Something became required. See docs/development/buildout.md decision D4: "
        "facility features are opt-in by configuration, never by requirement."
    )


def test_the_smallest_laboratory_still_validates() -> None:
    """Line count catches creep; this catches a field becoming required without the file growing."""

    validate_manifest_file(MINIMAL)


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_the_smallest_laboratory_still_runs_work(tmp_path: Path) -> None:
    """Small is not enough — it has to be a laboratory that does something.

    Deliberately end to end against the real controller rather than a constructed system: what is
    being checked is that no scheduler, broker, migration step or optional service crept into the
    path between a fifteen-line manifest and executed work.
    """
    laboratory = tmp_path / "lab"
    shutil.copytree(
        MINIMAL.parent, laboratory, ignore=shutil.ignore_patterns(".opensdl", "__pycache__")
    )

    system = OpenSDLSystem.from_manifest(laboratory / "opensdl.yaml")
    await system.start()
    try:
        run = await system.runtime.execute_capability(
            "compute.euclidean_distance",
            {"a": [0.0, 0.0], "b": [3.0, 4.0]},
            environment="simulation",
        )

        assert [record.state for record in system.repositories.list_runs()] == [RunState.COMPLETED]
        tasks = system.repositories.list_tasks(run.id)
        assert [task.state for task in tasks] == [TaskState.SUCCEEDED]
        # The arithmetic is checked so this is a laboratory that produced a right answer, rather
        # than one that merely reached a terminal state without doing anything.
        assert tasks[0].outputs["distance"] == pytest.approx(5.0)
    finally:
        await system.close()


def test_the_smallest_laboratory_declares_no_optional_service() -> None:
    """Tier 1 must never require anything from tier 4.

    Checked against the manifest text rather than the parsed model on purpose: the failure this
    guards against is a future field, and a parsed model can only be asked about fields that
    already exist.
    """
    manifest = MINIMAL.read_text(encoding="utf-8").lower()

    for service in (
        "postgresql://",
        "postgres://",
        "redis",
        "amqp",
        "kafka",
        "scheduler:",
        "broker",
    ):
        assert service not in manifest, (
            f"the minimal laboratory now mentions {service!r}. The smallest working laboratory runs "
            "in one process against SQLite with no optional service. See buildout.md decision D4."
        )


def test_the_smallest_laboratory_makes_no_prediction_machinery_required() -> None:
    """Progressive results must cost the one-bench case nothing, including a decision.

    Decision D9 ranks progressive results first because shortening a measurement beats scheduling
    around one, and decision D4 requires that facility work stay opt-in. Those two meet here: a
    capability written before predictions existed declares nothing, predicts nothing, and every
    result it returns is a measurement.

    This assertion lives in this file rather than beside the models because this is the file whose
    job is noticing a default being flipped.
    """

    capability = CapabilityDefinition(
        id="capability/plain",
        name="a capability that knows nothing about predictions",
        executor_type=ExecutorType.SIMULATOR,
        input_schema={},
        output_schema={},
    )
    assert capability.progressive_results is False, (
        "progressive_results now defaults to True, so every capability claims it can predict. A "
        "provisional number from an adapter that was never revisited would enter the evidence "
        "store wearing an instrument's clothes. See docs/development/buildout.md decisions D4 "
        "and D9."
    )

    result = ExecutionResult(request_id="request/1")
    assert result.basis is ResultBasis.MEASURED, (
        "a result no longer defaults to being a measurement, which silently reclassifies every "
        "existing adapter's output as a prediction."
    )
    assert result.predictor == {}
    assert result.completeness is None
    assert result.revises is None
