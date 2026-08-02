from pathlib import Path
import shutil

import pytest

from opensdl_controller import OpenSDLSystem


@pytest.mark.integration
@pytest.mark.asyncio
async def test_controller_loads_manifest_and_reports_health(tmp_path: Path) -> None:
    source = Path(__file__).parents[2] / "examples" / "simulated-color-mixing"
    target = tmp_path / "lab"
    shutil.copytree(source, target)
    system = OpenSDLSystem.from_manifest(target / "opensdl.yaml")
    try:
        await system.start()
        report = await system.doctor()
        assert report["passed"]
        capability_ids = {item.id for item in system.registry.list_capabilities()}
        assert capability_ids == {
            "compute.euclidean_distance",
            "sim.locate_labware",
            "sim.measure_color",
            "sim.measure_mass",
            "sim.mix_color",
            "sim.move_labware",
        }
        assert [pack["name"] for pack in system.domain_packs] == ["materials"]
        context = system.context_builder.build()
        assert context.domain_packs[0]["name"] == "materials"
    finally:
        await system.close()
