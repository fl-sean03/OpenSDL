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
    await adapter.execute(
        ExecutionRequest(
            capability_id="sim.mix_color",
            inputs={
                "sample_id": "s1",
                "red_fraction": 0.25,
                "blue_fraction": 0.75,
                "total_mass_g": 5,
            },
        )
    )
    result = await adapter.execute(
        ExecutionRequest(capability_id="sim.measure_color", inputs={"sample_id": "s1"})
    )
    assert result.output["rgb"] == [63.75, 0.0, 191.25]


async def _mix_dyes(adapter: SimulatedLabAdapter, sample_id: str, **recipe: float) -> list[float]:
    request = ExecutionRequest(
        capability_id="sim.mix_dyes",
        inputs={"sample_id": sample_id, "well_volume_ul": 200.0, **recipe},
    )
    result = await adapter.execute(request)
    return list(result.output["rgb"])


@pytest.mark.asyncio
async def test_dyes_absorb_their_own_channel_hardest() -> None:
    """Each stock is named for the light it passes, so it must absorb its complement."""
    adapter = SimulatedLabAdapter()
    cyan = await _mix_dyes(adapter, "c", cyan=1.0, magenta=0.0, yellow=0.0)
    magenta = await _mix_dyes(adapter, "m", cyan=0.0, magenta=1.0, yellow=0.0)
    yellow = await _mix_dyes(adapter, "y", cyan=0.0, magenta=0.0, yellow=1.0)
    assert cyan.index(min(cyan)) == 0
    assert magenta.index(min(magenta)) == 1
    assert yellow.index(min(yellow)) == 2


@pytest.mark.asyncio
async def test_an_empty_well_reads_white_and_dye_only_darkens() -> None:
    adapter = SimulatedLabAdapter()
    water = await _mix_dyes(adapter, "w", cyan=0.0, magenta=0.0, yellow=0.0)
    assert water == [255.0, 255.0, 255.0]
    tinted = await _mix_dyes(adapter, "t", cyan=0.2, magenta=0.1, yellow=0.05)
    assert all(channel < 255.0 for channel in tinted)


@pytest.mark.asyncio
async def test_a_fuller_well_of_the_same_recipe_reads_darker() -> None:
    """The well is the cuvette: Beer's law makes depth and absorbance proportional."""
    adapter = SimulatedLabAdapter()
    recipe = {"cyan": 0.3, "magenta": 0.2, "yellow": 0.1}
    shallow = await adapter.execute(
        ExecutionRequest(
            capability_id="sim.mix_dyes",
            inputs={"sample_id": "shallow", "well_volume_ul": 100.0, **recipe},
        )
    )
    deep = await adapter.execute(
        ExecutionRequest(
            capability_id="sim.mix_dyes",
            inputs={"sample_id": "deep", "well_volume_ul": 400.0, **recipe},
        )
    )
    assert all(d < s for d, s in zip(deep.output["rgb"], shallow.output["rgb"], strict=True))
    # Four times the path length is four times the absorbance, exactly.
    assert deep.output["absorbance"] == pytest.approx(
        [4.0 * value for value in shallow.output["absorbance"]]
    )


@pytest.mark.asyncio
async def test_the_mixer_refuses_a_well_that_would_need_negative_water() -> None:
    adapter = SimulatedLabAdapter()
    with pytest.raises(ValueError, match="water cannot be negative"):
        await _mix_dyes(adapter, "over", cyan=0.5, magenta=0.5, yellow=0.5)


@pytest.mark.asyncio
async def test_the_mixer_refuses_a_negative_dye_fraction() -> None:
    adapter = SimulatedLabAdapter()
    with pytest.raises(ValueError, match="non-negative"):
        await _mix_dyes(adapter, "neg", cyan=-0.1, magenta=0.0, yellow=0.0)


@pytest.mark.asyncio
async def test_a_dye_sample_reports_no_mass_rather_than_inventing_one() -> None:
    adapter = SimulatedLabAdapter()
    await _mix_dyes(adapter, "volumetric", cyan=0.1, magenta=0.1, yellow=0.1)
    with pytest.raises(LookupError, match="prepared by volume"):
        await adapter.execute(
            ExecutionRequest(capability_id="sim.measure_mass", inputs={"sample_id": "volumetric"})
        )


@pytest.mark.asyncio
async def test_the_colorimeter_reads_a_dye_sample() -> None:
    """`sim.measure_color` predates these dyes; it must still work against them unchanged."""
    adapter = SimulatedLabAdapter()
    mixed = await _mix_dyes(adapter, "read-me", cyan=0.25, magenta=0.15, yellow=0.05)
    result = await adapter.execute(
        ExecutionRequest(capability_id="sim.measure_color", inputs={"sample_id": "read-me"})
    )
    assert result.output["rgb"] == mixed
    assert result.output["unit"] == "sRGB-8bit"
