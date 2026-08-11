"""Rediscover a dye recipe from its color alone, one 96-well plate per round.

The laboratory is told a color and nothing else. It is not told the recipe that produced it, and
the optimizer is not told how the dyes behave. Each round fills a plate with ninety-six recipes,
reads every well, and scores each against the target; the next round is drawn from a region that
has contracted around whatever came closest. The recipe is recovered, or it is not, and the record
says which.

    uv run --locked python examples/discovering-colors/run_campaign.py

Writes `plates.json` next to this file: what went into every well of every round, what the
colorimeter read back, and how each scored. That file is the only input to the renderer, so the
published image is a picture of this run rather than an illustration of one.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from opensdl_adapter_contracting_search import ContractingSearch
from opensdl_controller import OpenSDLSystem
from opensdl_core import CampaignObservation
from opensdl_runtime import (
    CampaignRunner,
    CandidateConstraint,
    Objective,
    Parameter,
    SearchSpace,
)
from opensdl_workflows import load_workflow

ROOT = Path(__file__).parent

#: The recipe the campaign has to find, stated as dye fractions. Nothing downstream of the target
#: color is allowed to see this: it is here to generate the target and to score the answer at the
#: end, and the assertion that those two uses are the only ones is what makes the result a
#: rediscovery rather than a lookup.
TRUE_RECIPE = {"cyan": 0.46, "magenta": 0.09, "yellow": 0.30}

#: A standard microplate, and the reason a round is ninety-six wells: that is what the labware
#: holds. The plate is the batch size, which is the honest way round — the equipment sets the
#: parallelism and the optimizer is asked for as many candidates as the plate has room for.
PLATE_ROWS = 8
PLATE_COLUMNS = 12
WELLS_PER_PLATE = PLATE_ROWS * PLATE_COLUMNS

ROUNDS = 6
WELL_VOLUME_UL = 200.0


def well_label(index: int) -> str:
    """`A1` through `H12`, the way a plate is actually addressed."""

    return f"{chr(ord('A') + index // PLATE_COLUMNS)}{index % PLATE_COLUMNS + 1}"


async def true_color(system: OpenSDLSystem) -> list[float]:
    """Mix the true recipe once, through the laboratory, to obtain the color to search for.

    Deliberately not computed in this file. The target is whatever this instrument reports for
    that recipe, so the campaign is searching against the laboratory it will actually run in.
    """
    run = await system.runtime.execute_capability(
        "sim.mix_dyes",
        {"sample_id": "target-reference", "well_volume_ul": WELL_VOLUME_UL, **TRUE_RECIPE},
        environment=system.manifest.spec.environment,
        operator_id="software/campaign",
    )
    return [float(channel) for channel in run.outputs["result"]["rgb"]]


def plates_from(history: list[CampaignObservation]) -> list[dict[str, Any]]:
    """Group the campaign's observations into the plates they were run as.

    Order within a batch is well order: the optimizer proposed ninety-six recipes, and they were
    dispensed into A1 through H12 in the order it proposed them.
    """
    rounds: dict[int, list[CampaignObservation]] = {}
    for observation in history:
        rounds.setdefault(observation.batch, []).append(observation)
    plates = []
    for number, (batch, observations) in enumerate(sorted(rounds.items()), start=1):
        wells = []
        for index, observation in enumerate(observations):
            outputs = observation.outputs
            wells.append(
                {
                    "well": well_label(index),
                    "row": index // PLATE_COLUMNS,
                    "column": index % PLATE_COLUMNS,
                    "recipe": {
                        name: observation.candidate.get(name)
                        for name in ("cyan", "magenta", "yellow")
                    },
                    "measured_rgb": outputs.get("measured_rgb"),
                    "score": observation.score,
                    "status": observation.status.value,
                    "run_id": observation.run_id,
                }
            )
        scored = [well["score"] for well in wells if well["score"] is not None]
        plates.append(
            {
                "round": number,
                "batch": batch,
                "wells": wells,
                "best_score": min(scored) if scored else None,
                "median_score": sorted(scored)[len(scored) // 2] if scored else None,
                "region": _region_of(observations),
            }
        )
    return plates


def _region_of(observations: list[CampaignObservation]) -> float | None:
    """How wide the optimizer said its sampling region was for this plate."""

    for observation in observations:
        if observation.suggestion is not None:
            region = observation.suggestion.model.get("region")
            if isinstance(region, int | float):
                return float(region)
    return None


async def main() -> None:
    system = OpenSDLSystem.from_manifest(ROOT / "opensdl.yaml")
    await system.start()
    try:
        workflow = load_workflow(ROOT / "workflow.yaml")
        target_rgb = await true_color(system)
        result = await CampaignRunner(system.runtime, system.repositories).run(
            workflow,
            ContractingSearch({"seed": 17, "contraction": 0.62}),
            environment=system.manifest.spec.environment,
            operator_id="software/campaign",
            base_inputs={"target_rgb": target_rgb, "well_volume_ul": WELL_VOLUME_UL},
            objectives=[Objective(name="color-distance", output="score")],
            search_space=SearchSpace(
                parameters=[
                    Parameter.continuous("cyan", 0.0, 1.0),
                    Parameter.continuous("magenta", 0.0, 1.0),
                    Parameter.continuous("yellow", 0.0, 1.0),
                ]
            ),
            # Water makes up whatever the dyes do not, so a recipe asking for more than a wellful
            # of dye is refused before anything is leased or dispensed. The mixer enforces this
            # too; declaring it here is what lets the campaign refuse the candidate instead of
            # spending a well to find out.
            candidate_constraints=[
                CandidateConstraint(
                    name="dye-fits-in-the-well",
                    weights={"cyan": 1.0, "magenta": 1.0, "yellow": 1.0},
                    upper=1.0,
                    description="the three dyes cannot exceed the well volume",
                )
            ],
            max_iterations=WELLS_PER_PLATE * ROUNDS,
            batch_size=WELLS_PER_PLATE,
            iteration_id_input="sample_id",
        )

        plates = plates_from(result.history)
        recovered = dict(result.best.candidate) if result.best else {}
        payload = {
            "campaign_id": result.campaign_id,
            "environment": system.manifest.spec.environment,
            "target": {"rgb": target_rgb, "recipe": TRUE_RECIPE},
            "plate": {"rows": PLATE_ROWS, "columns": PLATE_COLUMNS},
            "rounds": len(plates),
            "wells_run": len(result.successes),
            "failed": len(result.failures),
            "rejected": len(result.rejected),
            "stop_reason": result.stop_reason.value,
            "best": {
                "recipe": recovered,
                "score": result.best.score if result.best else None,
                "run_id": result.best.run_id if result.best else None,
                "measured_rgb": result.best.outputs.get("measured_rgb") if result.best else None,
            },
            "recipe_error": {
                name: abs(float(recovered.get(name, 0.0)) - value)
                for name, value in TRUE_RECIPE.items()
            }
            if recovered
            else {},
            "plates": plates,
        }
        (ROOT / "plates.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

        print(json.dumps({key: payload[key] for key in payload if key != "plates"}, indent=2))
        print(f"\n{'round':>5}  {'region':>7}  {'best ΔRGB':>10}  {'median ΔRGB':>12}")
        for plate in plates:
            region = plate["region"]
            print(
                f"{plate['round']:>5}  {region:>7.3f}  "
                f"{plate['best_score']:>10.2f}  {plate['median_score']:>12.2f}"
                if region is not None
                else f"{plate['round']:>5}  {'—':>7}  "
                f"{plate['best_score']:>10.2f}  {plate['median_score']:>12.2f}"
            )
    finally:
        await system.close()


if __name__ == "__main__":
    asyncio.run(main())
