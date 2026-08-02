from pathlib import Path
import shutil

import pytest

from opensdl_adapter_grid_optimizer import GridOptimizer
from opensdl_controller import OpenSDLSystem
from opensdl_runtime import CampaignRunner
from opensdl_workflows import load_workflow


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_complete_closed_loop_campaign(tmp_path: Path) -> None:
    source = Path(__file__).parents[2] / "examples" / "simulated-color-mixing"
    target = tmp_path / "lab"
    shutil.copytree(source, target)
    system = OpenSDLSystem.from_manifest(target / "opensdl.yaml")
    await system.start()
    try:
        optimizer = GridOptimizer({"candidates":[
            {"red_fraction":0.0,"blue_fraction":1.0},
            {"red_fraction":0.5,"blue_fraction":0.5},
            {"red_fraction":1.0,"blue_fraction":0.0},
        ]})
        result = await CampaignRunner(system.runtime, system.repositories).run(
            load_workflow(target / "workflow.yaml"),
            optimizer,
            base_inputs={"total_mass_g":5.0,"target_rgb":[127.5,0,127.5]},
            max_iterations=3,
        )
        assert result.best is not None
        assert result.best.candidate == {"red_fraction":0.5,"blue_fraction":0.5}
        assert result.best.score == 0
        assert len(system.repositories.list_runs()) == 3
        assert any(event.type == "CampaignCompleted" for event in system.repositories.list_events(campaign_id=result.campaign_id))
    finally:
        await system.close()
