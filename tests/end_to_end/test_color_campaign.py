from pathlib import Path
import shutil

import pytest

from opensdl_adapter_grid_optimizer import GridOptimizer
from opensdl_controller import OpenSDLSystem
from opensdl_runtime import (
    CampaignReader,
    CampaignRunner,
    CandidateConstraint,
    Objective,
    Parameter,
    SearchSpace,
)
from opensdl_runtime.campaign import CampaignObservationStatus, CampaignStopReason
from opensdl_workflows import load_workflow


def mixture_space() -> SearchSpace:
    return SearchSpace(
        parameters=[
            Parameter.continuous("red_fraction", 0.0, 1.0),
            Parameter.continuous("blue_fraction", 0.0, 1.0),
        ]
    )


def sums_to_one() -> CandidateConstraint:
    return CandidateConstraint(
        name="fractions-sum-to-one",
        weights={"red_fraction": 1.0, "blue_fraction": 1.0},
        lower=1.0,
        upper=1.0,
    )


def reference_lab(tmp_path: Path) -> OpenSDLSystem:
    source = Path(__file__).parents[2] / "examples" / "simulated-color-mixing"
    target = tmp_path / "lab"
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(".opensdl", "__pycache__"),
    )
    return OpenSDLSystem.from_manifest(target / "opensdl.yaml")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_closed_loop_campaign(tmp_path: Path) -> None:
    system = reference_lab(tmp_path)
    await system.start()
    try:
        optimizer = GridOptimizer(
            {
                "candidates": [
                    {"red_fraction": 0.0, "blue_fraction": 1.0},
                    {"red_fraction": 0.5, "blue_fraction": 0.5},
                    {"red_fraction": 1.0, "blue_fraction": 0.0},
                ]
            }
        )
        result = await CampaignRunner(system.runtime, system.repositories).run(
            load_workflow(Path(system.manifest_path).parent / "workflow.yaml"),
            optimizer,
            environment=system.manifest.spec.environment,
            operator_id="software/campaign",
            base_inputs={"total_mass_g": 5.0, "target_rgb": [127.5, 0, 127.5]},
            objectives=[Objective(name="colour-distance", output="score")],
            search_space=mixture_space(),
            candidate_constraints=[sums_to_one()],
            max_iterations=3,
            batch_size=3,
            iteration_id_input="sample_id",
        )
        assert result.best is not None
        assert result.best.candidate == {"red_fraction": 0.5, "blue_fraction": 0.5}
        assert result.best.score == 0
        assert result.stop_reason is CampaignStopReason.MAX_ITERATIONS
        assert len(result.successes) == 3
        assert result.failures == []
        assert result.rejected == []
        # The whole sweep was proposed as one batch and still ran one candidate at a time, because
        # this laboratory declares a single virtual mixer and `max_parallel_runs` defaults to one.
        assert [item.batch for item in result.history] == [0, 0, 0]
        runs = system.repositories.list_runs()
        assert len(runs) == 3
        # The campaign executed where the manifest says the laboratory is, and said so in its own
        # record: a campaign that defaulted the environment would file a false provenance record.
        assert {run.environment for run in runs} == {system.manifest.spec.environment}
        assert {run.operator_id for run in runs} == {"software/campaign"}
        events = system.repositories.list_events(campaign_id=result.campaign_id, limit=None)
        completed = next(event for event in events if event.type == "CampaignCompleted")
        assert completed.payload["stopReason"] == "max_iterations"
        assert completed.payload["succeeded"] == 3
        # One query returns every run the campaign launched.
        launched = {
            event.payload["runId"] for event in events if event.type == "CampaignIterationStarted"
        }
        assert launched == {run.id for run in runs}

        # Every decision was recorded before the run it caused, and rests on the runs that existed
        # when it was made rather than on the run it produced.
        decisions = [event for event in events if event.type == "DecisionRecorded"]
        assert len(decisions) == 3
        assert all(item.payload["decision"]["evidence_run_ids"] == [] for item in decisions)
        assert all(
            "enumeration order" in item.payload["decision"]["rationale"] for item in decisions
        )
        assert [item.payload["batchIndex"] for item in decisions] == [0, 1, 2]

        record = CampaignReader(system.repositories).get(result.campaign_id)
        assert record.problem is not None
        assert [item.name for item in record.problem.objectives] == ["colour-distance"]
        assert record.problem.candidate_constraints[0].name == "fractions-sum-to-one"
        assert record.batch_size == 3
        assert record.iterations[0].decision is not None
        assert record.iterations[0].decision.acquisition_function == "none/enumeration"
        assert record.best is not None
        assert record.best.candidate == {"red_fraction": 0.5, "blue_fraction": 0.5}
    finally:
        await system.close()


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_a_candidate_that_breaks_the_declared_mixture_never_reaches_the_laboratory(
    tmp_path: Path,
) -> None:
    """The reference laboratory's one constraint used to be enforced by how the grid was written.

    Declaring it means the framework refuses a candidate that breaks it before a run is created, a
    policy decision is taken, or the mixer is leased — whatever proposed it.
    """

    class BrokenOptimizer:
        """Proposes a mixture that does not add up, then a valid one."""

        def __init__(self) -> None:
            self.proposals = [
                {"red_fraction": 0.5, "blue_fraction": 0.9},
                {"red_fraction": 0.5, "blue_fraction": 0.5},
            ]

        def suggest(self, history: list[object]) -> dict[str, float] | None:
            return self.proposals.pop(0) if self.proposals else None

        def observe(self, observation: object) -> None:
            return None

    system = reference_lab(tmp_path)
    await system.start()
    try:
        result = await CampaignRunner(system.runtime, system.repositories).run(
            load_workflow(Path(system.manifest_path).parent / "workflow.yaml"),
            BrokenOptimizer(),
            environment=system.manifest.spec.environment,
            operator_id="software/campaign",
            base_inputs={"total_mass_g": 5.0, "target_rgb": [127.5, 0, 127.5]},
            search_space=mixture_space(),
            candidate_constraints=[sums_to_one()],
            max_iterations=2,
            iteration_id_input="sample_id",
        )

        assert [item.status for item in result.history] == [
            CampaignObservationStatus.REJECTED,
            CampaignObservationStatus.SUCCEEDED,
        ]
        refused = result.history[0]
        assert refused.run_id is None
        assert "fractions-sum-to-one" in (refused.error or "")
        # Exactly one run exists, and no policy decision was ever taken for the refused candidate.
        assert len(system.repositories.list_runs()) == 1
        events = system.repositories.list_events(campaign_id=result.campaign_id, limit=None)
        assert [event.type for event in events].count("PolicyEvaluated") == 4
        rejected = next(event for event in events if event.type == "CampaignCandidateRejected")
        assert rejected.payload["iteration"] == 0
    finally:
        await system.close()
