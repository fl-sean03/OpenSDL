from __future__ import annotations

import asyncio
import json
from pathlib import Path

from opensdl_adapter_grid_optimizer import GridOptimizer
from opensdl_controller import OpenSDLSystem
from opensdl_runtime import (
    CampaignRunner,
    CandidateConstraint,
    Objective,
    Parameter,
    SearchSpace,
)
from opensdl_workflows import load_workflow

ROOT = Path(__file__).parent


async def main() -> None:
    system = OpenSDLSystem.from_manifest(ROOT / "opensdl.yaml")
    await system.start()
    try:
        workflow = load_workflow(ROOT / "workflow.yaml")
        fractions = [0.0, 0.25, 0.5, 0.75, 1.0]
        optimizer = GridOptimizer(
            {"candidates": [{"red_fraction": red, "blue_fraction": 1.0 - red} for red in fractions]}
        )
        result = await CampaignRunner(system.runtime, system.repositories).run(
            workflow,
            optimizer,
            # The campaign runs unattended, so it states where the work happens rather than
            # inheriting a default: this is the environment the manifest declares and the one
            # policy is evaluated against.
            environment=system.manifest.spec.environment,
            operator_id="software/campaign",
            base_inputs={"total_mass_g": 5.0, "target_rgb": [127.5, 0.0, 127.5]},
            objectives=[Objective(name="colour-distance", output="score")],
            # The two fractions are a mixture, so they are bounded and they sum to one. Declaring
            # that here is what lets the framework refuse a candidate before a run is created, a
            # policy decision is taken, or the mixer is leased. It used to be enforced only by the
            # expression that generated the grid, so nothing checked what an optimizer proposed.
            search_space=SearchSpace(
                parameters=[
                    Parameter.continuous("red_fraction", 0.0, 1.0),
                    Parameter.continuous("blue_fraction", 0.0, 1.0),
                ]
            ),
            candidate_constraints=[
                CandidateConstraint(
                    name="fractions-sum-to-one",
                    weights={"red_fraction": 1.0, "blue_fraction": 1.0},
                    lower=1.0,
                    upper=1.0,
                    description="the two dyes are the whole mixture",
                )
            ],
            max_iterations=5,
            # The grid points are independent, so the optimizer proposes the whole sweep at once.
            # They still run one at a time: this laboratory declares a single virtual mixer, and
            # `max_parallel_runs` — which defaults to one — is what would change that.
            batch_size=5,
            # This workflow mixes a physical sample, so each iteration needs its own identifier.
            # A computational workflow leaves this unset and receives no injected input.
            iteration_id_input="sample_id",
        )
        payload = {
            "campaign_id": result.campaign_id,
            "environment": system.manifest.spec.environment,
            "iterations": len(result.history),
            "succeeded": len(result.successes),
            "failed": len(result.failures),
            "rejected": len(result.rejected),
            "stop_reason": result.stop_reason.value,
            "stop_detail": result.stop_detail,
            "best": {
                "candidate": result.best.candidate,
                "score": result.best.score,
                "run_id": result.best.run_id,
                "rationale": result.best.suggestion.rationale if result.best.suggestion else "",
            }
            if result.best
            else None,
        }
        print(json.dumps(payload, indent=2))
    finally:
        await system.close()


if __name__ == "__main__":
    asyncio.run(main())
