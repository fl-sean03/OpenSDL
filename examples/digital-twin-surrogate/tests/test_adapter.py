from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from opensdl_adapter_cell_surrogate import CellSurrogateAdapter
from opensdl_capabilities import run_adapter_conformance
from opensdl_core import CapabilityDefinition, ExecutionRequest

from .fake_physical_adapter import FakePhysicalCellAdapter


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
INPUTS = {
    "labware_id": "plate-1",
    "additions": [
        {"material_id": "reagent-a", "volume_per_well_ul": 40.0},
        {"material_id": "reagent-b", "volume_per_well_ul": 60.0},
    ],
    "mix_speed_rpm": 800.0,
    "mix_duration_seconds": 20.0,
}
CONFIG = {"material_responses": {"reagent-a": 0.2, "reagent-b": 0.8}}


async def _run_cell_cycle(adapter: CellSurrogateAdapter) -> list[dict[str, object]]:
    requests = [
        ExecutionRequest(
            capability_id="cell.transfer_labware",
            inputs={
                "labware_id": INPUTS["labware_id"],
                "source": "input",
                "destination": "dispense",
            },
        ),
        ExecutionRequest(
            capability_id="cell.dispense",
            inputs={
                "labware_id": INPUTS["labware_id"],
                "additions": INPUTS["additions"],
            },
        ),
        ExecutionRequest(
            capability_id="cell.transfer_labware",
            inputs={
                "labware_id": INPUTS["labware_id"],
                "source": "dispense",
                "destination": "mix",
            },
        ),
        ExecutionRequest(
            capability_id="cell.mix",
            inputs={
                "labware_id": INPUTS["labware_id"],
                "speed_rpm": INPUTS["mix_speed_rpm"],
                "duration_seconds": INPUTS["mix_duration_seconds"],
            },
        ),
        ExecutionRequest(
            capability_id="cell.transfer_labware",
            inputs={
                "labware_id": INPUTS["labware_id"],
                "source": "mix",
                "destination": "characterize",
            },
        ),
        ExecutionRequest(
            capability_id="cell.characterize",
            inputs={
                "labware_id": INPUTS["labware_id"],
                "method": "normalized-response",
            },
        ),
        ExecutionRequest(
            capability_id="cell.transfer_labware",
            inputs={
                "labware_id": INPUTS["labware_id"],
                "source": "characterize",
                "destination": "output",
            },
        ),
    ]
    return [(await adapter.execute(request)).output for request in requests]


@pytest.mark.asyncio
async def test_adapter_conformance() -> None:
    report = await run_adapter_conformance(CellSurrogateAdapter(CONFIG))
    assert report.passed, report.model_dump()


@pytest.mark.asyncio
async def test_cycle_is_deterministic_and_stateful() -> None:
    first = CellSurrogateAdapter(CONFIG)
    second = CellSurrogateAdapter(CONFIG)

    first_outputs = await _run_cell_cycle(first)
    second_outputs = await _run_cell_cycle(second)

    assert first_outputs == second_outputs
    assert first_outputs[1]["well_count"] == 96
    assert first_outputs[1]["volume_per_well_ul"] == 100.0
    assert first_outputs[1]["aggregate_volume_ul"] == 9600.0
    assert first_outputs[5]["value"] == 0.56
    assert first_outputs[-1]["destination"] == "output"
    assert first.snapshot() == second.snapshot()
    assert first.snapshot()["revision"] == 7


@pytest.mark.asyncio
async def test_state_transition_failure_does_not_advance_revision() -> None:
    adapter = CellSurrogateAdapter(CONFIG)
    await adapter.execute(
        ExecutionRequest(
            capability_id="cell.transfer_labware",
            inputs={"labware_id": "plate-1", "source": "input", "destination": "dispense"},
        )
    )

    with pytest.raises(ValueError, match="not requested source mix"):
        await adapter.execute(
            ExecutionRequest(
                capability_id="cell.transfer_labware",
                inputs={
                    "labware_id": "plate-1",
                    "source": "mix",
                    "destination": "output",
                },
            )
        )

    assert adapter.snapshot()["revision"] == 1
    assert adapter.snapshot()["labware"]["plate-1"]["location"] == "dispense"


@pytest.mark.asyncio
async def test_transfer_rejects_locations_outside_the_twin_contract() -> None:
    adapter = CellSurrogateAdapter(CONFIG)

    with pytest.raises(ValueError, match="unknown cell location: quarantine"):
        await adapter.execute(
            ExecutionRequest(
                capability_id="cell.transfer_labware",
                inputs={
                    "labware_id": "plate-1",
                    "source": "input",
                    "destination": "quarantine",
                },
            )
        )

    assert adapter.snapshot()["revision"] == 0


def test_capability_cards_match_adapter_definitions() -> None:
    definitions = {
        definition.id: definition.model_dump(mode="json")
        for definition in CellSurrogateAdapter().capability_definitions()
    }
    cards = {}
    for path in sorted((EXAMPLE_ROOT / "capabilities").glob("*.yaml")):
        card = CapabilityDefinition.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        cards[card.id] = card.model_dump(mode="json")

    assert cards == definitions


@pytest.mark.asyncio
async def test_fake_physical_adapter_has_semantic_and_output_parity() -> None:
    surrogate = CellSurrogateAdapter(CONFIG)
    physical = FakePhysicalCellAdapter(CONFIG)

    assert surrogate.capability_definitions() == physical.capability_definitions()
    assert await _run_cell_cycle(surrogate) == await _run_cell_cycle(physical)

    request = ExecutionRequest(
        capability_id="cell.transfer_labware",
        inputs={"labware_id": "metadata-plate", "source": "input", "destination": "dispense"},
    )
    surrogate_result = await CellSurrogateAdapter(CONFIG).execute(request)
    physical_result = await FakePhysicalCellAdapter(CONFIG).execute(request)
    assert surrogate_result.output == physical_result.output
    assert surrogate_result.metadata["execution_mode"] == "surrogate"
    assert physical_result.metadata["execution_mode"] == "fake-physical"
