"""The discovering-colors example, run short: does the closed loop actually converge?

The published example runs six plates of ninety-six. This runs two of twelve, which is enough to
show the loop closing without spending a minute of CI on it, and it runs against the example's own
manifest so a change that breaks the example breaks this first.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from opensdl_adapter_contracting_search import ContractingSearch
from opensdl_controller import OpenSDLSystem
from opensdl_core import CampaignObservationStatus
from opensdl_runtime import (
    CampaignRunner,
    CandidateConstraint,
    Objective,
    Parameter,
    SearchSpace,
)
from opensdl_workflows import load_workflow

EXAMPLE = Path(__file__).parents[2] / "examples" / "discovering-colors"
TRUE_RECIPE = {"cyan": 0.46, "magenta": 0.09, "yellow": 0.30}
WELL_VOLUME_UL = 200.0


def discovery_lab(tmp_path: Path) -> OpenSDLSystem:
    target = tmp_path / "lab"
    shutil.copytree(
        EXAMPLE,
        target,
        ignore=shutil.ignore_patterns(".opensdl", "__pycache__", "renders", "plates.json"),
    )
    return OpenSDLSystem.from_manifest(target / "opensdl.yaml")


def dye_space() -> SearchSpace:
    return SearchSpace(
        parameters=[
            Parameter.continuous("cyan", 0.0, 1.0),
            Parameter.continuous("magenta", 0.0, 1.0),
            Parameter.continuous("yellow", 0.0, 1.0),
        ]
    )


def fits_in_the_well() -> CandidateConstraint:
    return CandidateConstraint(
        name="dye-fits-in-the-well",
        weights={"cyan": 1.0, "magenta": 1.0, "yellow": 1.0},
        upper=1.0,
    )


async def run_campaign(system: OpenSDLSystem, *, rounds: int, wells: int):
    run = await system.runtime.execute_capability(
        "sim.mix_dyes",
        {"sample_id": "target", "well_volume_ul": WELL_VOLUME_UL, **TRUE_RECIPE},
        environment=system.manifest.spec.environment,
        operator_id="software/campaign",
    )
    target_rgb = [float(channel) for channel in run.outputs["result"]["rgb"]]
    result = await CampaignRunner(system.runtime, system.repositories).run(
        load_workflow(EXAMPLE / "workflow.yaml"),
        ContractingSearch({"seed": 17, "contraction": 0.5}),
        environment=system.manifest.spec.environment,
        operator_id="software/campaign",
        base_inputs={"target_rgb": target_rgb, "well_volume_ul": WELL_VOLUME_UL},
        objectives=[Objective(name="color-distance", output="score")],
        search_space=dye_space(),
        candidate_constraints=[fits_in_the_well()],
        max_iterations=wells * rounds,
        batch_size=wells,
        iteration_id_input="sample_id",
    )
    return result, target_rgb


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_the_loop_closes_on_a_color_it_was_only_shown(tmp_path: Path) -> None:
    system = discovery_lab(tmp_path)
    await system.start()
    try:
        result, _ = await run_campaign(system, rounds=3, wells=12)
    finally:
        await system.close()

    assert not result.failures
    assert result.best is not None

    rounds: dict[int, list[float]] = {}
    for observation in result.history:
        if observation.status is CampaignObservationStatus.SUCCEEDED:
            rounds.setdefault(observation.batch, []).append(float(observation.score))
    medians = [sorted(scores)[len(scores) // 2] for _, scores in sorted(rounds.items())]
    assert len(medians) == 3
    assert medians[-1] < medians[0], f"the search did not tighten: {medians}"

    # The recipe is recovered, having never been shown to anything downstream of the target color.
    recovered = result.best.candidate
    assert all(abs(recovered[dye] - value) < 0.2 for dye, value in TRUE_RECIPE.items()), recovered


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_every_well_records_the_recipe_and_the_reading_it_produced(
    tmp_path: Path,
) -> None:
    """The renderer reads these two fields off the record; a run that drops them is unpublishable."""

    system = discovery_lab(tmp_path)
    await system.start()
    try:
        result, target_rgb = await run_campaign(system, rounds=1, wells=12)
    finally:
        await system.close()

    for observation in result.history:
        if observation.status is not CampaignObservationStatus.SUCCEEDED:
            continue
        measured = observation.outputs["measured_rgb"]
        assert len(measured) == 3
        assert all(0.0 <= channel <= 255.0 for channel in measured)
        assert set(observation.candidate) == set(TRUE_RECIPE)
    assert len(target_rgb) == 3


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_a_recipe_larger_than_the_well_never_reaches_the_mixer(tmp_path: Path) -> None:
    """The campaign refuses it, so no run is created and no resource is leased."""

    system = discovery_lab(tmp_path)
    await system.start()
    try:
        workflow = load_workflow(EXAMPLE / "workflow.yaml")

        class Overfull:
            """An optimizer that proposes more dye than the well can hold."""

            def configure(self, problem) -> None:  # noqa: ANN001 - protocol is structural
                return None

            def suggest(self, history):  # noqa: ANN001, ANN201
                return {"cyan": 0.6, "magenta": 0.6, "yellow": 0.6}

            def observe(self, observation) -> None:  # noqa: ANN001
                return None

        result = await CampaignRunner(system.runtime, system.repositories).run(
            workflow,
            Overfull(),
            environment=system.manifest.spec.environment,
            operator_id="software/campaign",
            base_inputs={"target_rgb": [70.0, 145.0, 100.0], "well_volume_ul": WELL_VOLUME_UL},
            objectives=[Objective(name="color-distance", output="score")],
            search_space=dye_space(),
            candidate_constraints=[fits_in_the_well()],
            max_iterations=2,
            iteration_id_input="sample_id",
        )
    finally:
        await system.close()

    assert result.rejected, "an over-budget recipe was accepted"
    assert not result.successes
    assert all(item.run_id is None for item in result.rejected)
