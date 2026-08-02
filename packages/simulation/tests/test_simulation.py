import pytest

from opensdl_simulation import FaultPlan, SimulationState


@pytest.mark.asyncio
async def test_fault_plan_is_deterministic() -> None:
    plan = FaultPlan(fail_on_calls={2})
    await plan.before_call()
    with pytest.raises(RuntimeError):
        await plan.before_call()
    assert plan.calls == 2


def test_state_snapshot_isolated() -> None:
    state = SimulationState()
    state.set("sample", {"x": 1})
    snapshot = state.snapshot()
    snapshot["sample"]["x"] = 2
    assert state.get("sample")["x"] == 1
