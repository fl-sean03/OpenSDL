import pytest

from opensdl_adapter_human_task import HumanTaskAdapter
from opensdl_capabilities import run_adapter_conformance


@pytest.mark.asyncio
async def test_human_task_adapter_conformance() -> None:
    report = await run_adapter_conformance(HumanTaskAdapter())
    assert report.passed, report.model_dump()
