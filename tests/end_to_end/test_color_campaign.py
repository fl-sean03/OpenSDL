from pathlib import Path
import shutil

import pytest

from opensdl_adapter_grid_optimizer import GridOptimizer
from opensdl_controller import OpenSDLSystem
from opensdl_runtime import CampaignRunner
from opensdl_runtime.campaign import CampaignStopReason
from opensdl_workflows import load_workflow


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_closed_loop_campaign(tmp_path: Path) -> None:
    source = Path(__file__).parents[2] / "examples" / "simulated-color-mixing"
    target = tmp_path / "lab"
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(".opensdl", "__pycache__"),
    )
    system = OpenSDLSystem.from_manifest(target / "opensdl.yaml")
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
            load_workflow(target / "workflow.yaml"),
            optimizer,
            environment=system.manifest.spec.environment,
            operator_id="software/campaign",
            base_inputs={"total_mass_g": 5.0, "target_rgb": [127.5, 0, 127.5]},
            max_iterations=3,
            iteration_id_input="sample_id",
        )
        assert result.best is not None
        assert result.best.candidate == {"red_fraction": 0.5, "blue_fraction": 0.5}
        assert result.best.score == 0
        assert result.stop_reason is CampaignStopReason.MAX_ITERATIONS
        assert len(result.successes) == 3
        assert result.failures == []
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
    finally:
        await system.close()
