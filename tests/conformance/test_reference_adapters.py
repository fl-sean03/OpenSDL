import pytest

from opensdl_adapter_human_task import HumanTaskAdapter
from opensdl_adapter_local_compute import LocalComputeAdapter
from opensdl_adapter_simulated_lab import SimulatedLabAdapter
from opensdl_capabilities import run_adapter_conformance


@pytest.mark.conformance
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "adapter",
    [SimulatedLabAdapter(), LocalComputeAdapter(), HumanTaskAdapter()],
)
async def test_reference_adapter_conformance(adapter) -> None:
    report = await run_adapter_conformance(adapter)
    assert report.passed, report.model_dump()
