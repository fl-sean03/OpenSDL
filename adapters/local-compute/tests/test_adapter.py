import pytest
from opensdl_core import ExecutionRequest
from opensdl_adapter_local_compute import LocalComputeAdapter


@pytest.mark.asyncio
async def test_distance() -> None:
    result = await LocalComputeAdapter().execute(ExecutionRequest(capability_id="compute.euclidean_distance", inputs={"a":[0,0],"b":[3,4]}))
    assert result.output["distance"] == 5
