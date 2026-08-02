from __future__ import annotations

import asyncio
import json
from pathlib import Path

from opensdl_adapter_grid_optimizer import GridOptimizer
from opensdl_controller import OpenSDLSystem
from opensdl_runtime import CampaignRunner
from opensdl_workflows import load_workflow

ROOT = Path(__file__).parent


async def main() -> None:
    system = OpenSDLSystem.from_manifest(ROOT / "opensdl.yaml")
    await system.start()
    try:
        workflow = load_workflow(ROOT / "workflow.yaml")
        fractions = [0.0, 0.25, 0.5, 0.75, 1.0]
        optimizer = GridOptimizer(
            {
                "candidates": [
                    {"red_fraction": red, "blue_fraction": 1.0 - red}
                    for red in fractions
                ]
            }
        )
        result = await CampaignRunner(system.runtime, system.repositories).run(
            workflow,
            optimizer,
            base_inputs={"total_mass_g": 5.0, "target_rgb": [127.5, 0.0, 127.5]},
            score_output="score",
            max_iterations=5,
        )
        payload = {
            "campaign_id": result.campaign_id,
            "iterations": len(result.history),
            "best": {
                "candidate": result.best.candidate,
                "score": result.best.score,
                "run_id": result.best.run_id,
            } if result.best else None,
        }
        print(json.dumps(payload, indent=2))
    finally:
        await system.close()


if __name__ == "__main__":
    asyncio.run(main())
