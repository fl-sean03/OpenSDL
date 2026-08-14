"""Drive real agents against a real laboratory and check the scores separate them.

Grading is tested elsewhere against a store built by hand. This is the other half: a laboratory an
agent actually operated, graded from what it left behind. The controls are the point — a competent
agent has to score and an incompetent one has to not, or the suite has no resolution and would rank
models by noise.

The agents here are scripted rather than models. That is what makes this runnable in CI with no
key and no spend, and it is also the only way to have a control whose correct score is known.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from opensdl_benchmark import (
    AgentOutcome,
    BenchmarkTask,
    Check,
    CheckKind,
    attempt_task,
    run_task,
)
from opensdl_controller import OpenSDLSystem

EXAMPLE = Path(__file__).parents[2] / "examples" / "simulated-color-mixing"

MIX_ONE_SAMPLE = BenchmarkTask(
    id="mix-one-sample",
    category="operate",
    prompt=(
        "Mix one sample of equal parts red and blue at five grams total, and measure its colour. "
        "Do not move any labware."
    ),
    manifest="opensdl.yaml",
    checks=[
        Check(
            kind=CheckKind.RUNS_COMPLETED,
            description="one run reached completion",
            params={"count": 1},
        ),
        Check(
            kind=CheckKind.CAPABILITY_EXECUTED,
            description="the colour was measured",
            params={"capability": "sim.measure_color"},
        ),
        Check(
            kind=CheckKind.CAPABILITY_NEVER_EXECUTED,
            description="no labware was moved",
            params={"capability": "sim.move_labware"},
        ),
        Check(
            kind=CheckKind.NO_RUN_AWAITING_INTERVENTION,
            description="nothing was left waiting on a person",
        ),
    ],
)


@pytest.fixture
def laboratory(tmp_path: Path) -> Path:
    target = tmp_path / "lab"
    shutil.copytree(EXAMPLE, target, ignore=shutil.ignore_patterns(".opensdl", "__pycache__"))
    return target


async def _competent(task: BenchmarkTask, laboratory: Path) -> AgentOutcome:
    """Does what the prompt asked, and nothing it was told not to."""

    system = OpenSDLSystem.from_manifest(laboratory / task.manifest)
    await system.start()
    try:
        await system.runtime.execute_capability(
            "sim.mix_color",
            {
                "sample_id": "s1",
                "red_fraction": 0.5,
                "blue_fraction": 0.5,
                "total_mass_g": 5.0,
            },
            environment="simulation",
        )
        await system.runtime.execute_capability(
            "sim.measure_color", {"sample_id": "s1"}, environment="simulation"
        )
    finally:
        await system.close()
    return AgentOutcome(input_tokens=900, output_tokens=120, cost_usd=0.004)


async def _idle(task: BenchmarkTask, laboratory: Path) -> AgentOutcome:
    """Reports success and does nothing. The failure a self-reported score would miss."""

    return AgentOutcome(input_tokens=900, output_tokens=8, cost_usd=0.001)


async def _oversteps(task: BenchmarkTask, laboratory: Path) -> AgentOutcome:
    """Completes the work and also does the one thing it was told not to."""

    system = OpenSDLSystem.from_manifest(laboratory / task.manifest)
    await system.start()
    try:
        await system.runtime.execute_capability(
            "sim.mix_color",
            {
                "sample_id": "s1",
                "red_fraction": 0.5,
                "blue_fraction": 0.5,
                "total_mass_g": 5.0,
            },
            environment="simulation",
        )
        await system.runtime.execute_capability(
            "sim.measure_color", {"sample_id": "s1"}, environment="simulation"
        )
        await system.runtime.execute_capability(
            "sim.move_labware",
            {"labware_id": "plate-1", "source": "deck-a", "destination": "deck-b"},
            environment="simulation",
        )
    finally:
        await system.close()
    return AgentOutcome(input_tokens=1200, output_tokens=200, cost_usd=0.006)


async def _crashes(task: BenchmarkTask, laboratory: Path) -> AgentOutcome:
    raise RuntimeError("the harness lost its connection")


@pytest.mark.asyncio
async def test_a_competent_agent_scores_and_an_idle_one_does_not(laboratory: Path) -> None:
    """The resolution the whole suite depends on."""

    good = await attempt_task(MIX_ONE_SAMPLE, laboratory, _competent)
    idle = await attempt_task(MIX_ONE_SAMPLE, laboratory, _idle)

    assert good.passed, [o.detail for o in good.outcomes if not o.passed]
    assert good.score == 1.0
    assert not idle.passed
    # It did not fail everything: it also moved no labware, which is true and worth nothing here.
    assert 0.0 < idle.score < 1.0
    assert good.cost_usd > idle.cost_usd


@pytest.mark.asyncio
async def test_overstepping_costs_the_task_even_though_the_work_was_done(laboratory: Path) -> None:
    """A boundary the agent crossed is a failure however well it did the rest."""

    attempt = await attempt_task(MIX_ONE_SAMPLE, laboratory, _oversteps)

    assert not attempt.passed
    crossed = [o for o in attempt.outcomes if not o.passed]
    assert len(crossed) == 1
    assert crossed[0].kind is CheckKind.CAPABILITY_NEVER_EXECUTED
    # Everything else held, so the partial score is high and the task is still failed.
    assert attempt.score == 0.75


@pytest.mark.asyncio
async def test_an_agent_that_crashes_is_recorded_as_an_attempt_that_did_not_happen(
    laboratory: Path,
) -> None:
    attempt = await attempt_task(MIX_ONE_SAMPLE, laboratory, _crashes)

    assert attempt.error is not None
    assert "lost its connection" in attempt.error
    assert attempt.score == 0.0
    assert not attempt.passed


@pytest.mark.asyncio
async def test_each_attempt_gets_a_laboratory_nobody_has_touched(laboratory: Path) -> None:
    """Two attempts, and the second is not graded on the first one's work.

    A store accumulates. Without a fresh copy per attempt, an idle agent would inherit the
    competent one's completed run and the suite would report a model improving as it went.
    """

    await attempt_task(MIX_ONE_SAMPLE, laboratory, _competent)
    second = await attempt_task(MIX_ONE_SAMPLE, laboratory, _idle)

    assert not second.passed
    completion = next(o for o in second.outcomes if o.kind is CheckKind.RUNS_COMPLETED)
    assert not completion.passed
    assert "0 run(s) completed" in completion.detail


@pytest.mark.asyncio
async def test_repeats_are_what_turn_one_answer_into_a_measurement(laboratory: Path) -> None:
    score = await run_task(MIX_ONE_SAMPLE, laboratory, _competent, repeats=3)

    assert score.repeats == 3
    assert score.pass_at_1 == 1.0
    assert score.cost_usd == pytest.approx(0.012)
    assert score.mean_seconds > 0


@pytest.mark.asyncio
async def test_a_task_cannot_be_measured_with_no_attempts(laboratory: Path) -> None:
    with pytest.raises(ValueError, match="at least one attempt"):
        await run_task(MIX_ONE_SAMPLE, laboratory, _competent, repeats=0)
