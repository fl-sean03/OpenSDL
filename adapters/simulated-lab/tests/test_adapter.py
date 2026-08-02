import pytest

from opensdl_capabilities import run_adapter_conformance
from opensdl_core import ExecutionRequest
from opensdl_adapter_simulated_lab import SimulatedLabAdapter


@pytest.mark.asyncio
async def test_simulated_lab_conformance() -> None:
    report = await run_adapter_conformance(SimulatedLabAdapter())
    assert report.passed, report.model_dump()


@pytest.mark.asyncio
async def test_mix_and_measure() -> None:
    adapter = SimulatedLabAdapter()
    await adapter.execute(ExecutionRequest(capability_id="sim.mix_color", inputs={"sample_id":"s1","red_fraction":0.25,"blue_fraction":0.75,"total_mass_g":5}))
    result = await adapter.execute(ExecutionRequest(capability_id="sim.measure_color", inputs={"sample_id":"s1"}))
    assert result.output["rgb"] == [63.75, 0.0, 191.25]
