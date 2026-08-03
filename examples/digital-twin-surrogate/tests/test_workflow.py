from __future__ import annotations

import json
from importlib.metadata import entry_points
from pathlib import Path

import pytest

from opensdl_controller import OpenSDLSystem
from opensdl_schemas import load_manifest
from opensdl_workflows import load_workflow, validate_workflow_graph


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
CAPABILITY_IDS = {
    "cell.transfer_labware",
    "cell.dispense",
    "cell.mix",
    "cell.characterize",
}


def test_local_adapter_entry_point_is_discoverable() -> None:
    points = {point.name: point.value for point in entry_points(group="opensdl.adapters")}
    assert points["cell-surrogate"] == (
        "opensdl_adapter_cell_surrogate.adapter:CellSurrogateAdapter"
    )


def test_workflow_and_manifests_share_the_neutral_contract() -> None:
    simulation = load_manifest(EXAMPLE_ROOT / "opensdl.yaml")
    physical = load_manifest(EXAMPLE_ROOT / "opensdl.physical-example.yaml")
    workflow = load_workflow(EXAMPLE_ROOT / "workflow.yaml")
    validate_workflow_graph(workflow)

    workflow_capabilities = {step.capability for step in workflow.steps}
    simulation_capabilities = {
        binding.capability for binding in simulation.spec.capabilities if binding.enabled
    }
    physical_capabilities = {
        binding.capability for binding in physical.spec.capabilities if binding.enabled
    }
    assert workflow_capabilities == CAPABILITY_IDS
    assert simulation_capabilities == CAPABILITY_IDS
    assert physical_capabilities == CAPABILITY_IDS
    assert all(binding.adapter == "cell" for binding in simulation.spec.capabilities)
    assert all(binding.adapter == "cell" for binding in physical.spec.capabilities)


def test_physical_example_changes_only_environment_and_adapter_configuration() -> None:
    simulation = load_manifest(EXAMPLE_ROOT / "opensdl.yaml").model_dump(mode="json", by_alias=True)
    physical = load_manifest(EXAMPLE_ROOT / "opensdl.physical-example.yaml").model_dump(
        mode="json", by_alias=True
    )

    assert simulation["spec"]["environment"] == "simulation"
    assert physical["spec"]["environment"] == "physical"
    assert simulation["spec"]["adapters"] != physical["spec"]["adapters"]
    assert physical["spec"]["adapters"][0]["plugin"] == "qualified-physical-cell"

    for manifest in (simulation, physical):
        manifest["spec"].pop("environment")
        manifest["spec"].pop("adapters")
    assert simulation == physical


@pytest.mark.asyncio
async def test_representative_workflow_runs_through_local_plugin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENSDL_DATABASE_URL", f"sqlite:///{tmp_path / 'opensdl.db'}")
    monkeypatch.setenv("OPENSDL_ARTIFACT_ROOT", str(tmp_path / "artifacts"))
    inputs = json.loads((EXAMPLE_ROOT / "inputs.json").read_text(encoding="utf-8"))
    system = OpenSDLSystem.from_manifest(EXAMPLE_ROOT / "opensdl.yaml")
    await system.start()
    try:
        run = await system.run_workflow_file(
            EXAMPLE_ROOT / "workflow.yaml",
            inputs,
            operator_id="operator/showcase",
        )
        task_capabilities = {task.capability_id for task in system.repositories.list_tasks(run.id)}
    finally:
        await system.close()

    assert run.state.value == "completed"
    assert run.outputs["labware_id"] == "showcase-plate-001"
    assert run.outputs["location"] == "output"
    assert run.outputs["well_count"] == 96
    assert run.outputs["volume_per_well_ul"] == 100.0
    assert run.outputs["aggregate_volume_ul"] == 9600.0
    assert run.outputs["characterization"] == {
        "method": "normalized-response",
        "value": 0.56,
        "unit": "1",
        "quality": "ok",
    }
    assert task_capabilities == CAPABILITY_IDS
