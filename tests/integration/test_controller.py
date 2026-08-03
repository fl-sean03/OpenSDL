from pathlib import Path
import hashlib
import shutil

import pytest
import yaml

from opensdl_controller import OpenSDLSystem
from opensdl_twin import TwinProjectionError, TwinService


@pytest.mark.integration
@pytest.mark.asyncio
async def test_controller_loads_manifest_and_reports_health(tmp_path: Path) -> None:
    source = Path(__file__).parents[2] / "examples" / "simulated-color-mixing"
    target = tmp_path / "lab"
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(".opensdl", "__pycache__"),
    )
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


@pytest.mark.integration
@pytest.mark.asyncio
async def test_controller_loads_and_projects_manifest_relative_twin(
    tmp_path: Path,
) -> None:
    source = Path(__file__).parents[2] / "examples" / "simulated-color-mixing"
    target = tmp_path / "lab"
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(".opensdl", "__pycache__"),
    )
    twin_root = target / "digital-twin"
    scene = twin_root / "exports" / "lab.glb"
    scene.parent.mkdir(parents=True)
    scene.write_bytes(b"test-scene")
    viewer_root = twin_root / "viewer"
    viewer_root.mkdir()
    twin_definition = {
        "apiVersion": "opensdl.dev/v0alpha1",
        "kind": "DigitalTwin",
        "version": "0.1.0",
        "revision": "test-revision",
        "coordinateFrame": {
            "unit": "m",
            "handedness": "right",
            "upAxis": "Z",
        },
        "scene": {
            "path": "exports/lab.glb",
            "sha256": hashlib.sha256(scene.read_bytes()).hexdigest(),
        },
        "entities": [
            {
                "id": "mixer",
                "node": "Mixer",
                "resources": ["virtual-mixer"],
            }
        ],
        "projectionRules": [
            {
                "id": "mix-started",
                "match": {
                    "eventType": "TaskStarted",
                    "capability": "sim.mix_color",
                    "phase": "started",
                },
                "action": "highlight",
                "target": "mixer",
            }
        ],
    }
    (twin_root / "twin.yaml").write_text(
        yaml.safe_dump(twin_definition, sort_keys=False),
        encoding="utf-8",
    )
    manifest_path = target / "opensdl.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["spec"]["twin"] = {
        "definition": "digital-twin/twin.yaml",
        "viewer_root": "digital-twin/viewer",
    }
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )

    system = OpenSDLSystem.from_manifest(manifest_path)
    try:
        assert system.twin is not None
        assert system.twin.definition_path == (twin_root / "twin.yaml").resolve()
        assert system.twin.scene_path == scene.resolve()
        assert system.twin_viewer_root == viewer_root.resolve()

        await system.start()
        run = await system.run_workflow_file(
            target / "workflow.yaml",
            {
                "sample_id": "controller",
                "red_fraction": 0.5,
                "blue_fraction": 0.5,
                "total_mass_g": 5,
                "target_rgb": [127.5, 0, 127.5],
            },
            run_id="run-controller-stable",
        )
        projection = system.project_twin_run(run.id)
        assert projection["definition_revision"] == "test-revision"
        assert projection["run_id"] == "run-controller-stable"
        assert len(projection["cues"]) == 1
        assert projection["cues"][0]["runId"] == "run-controller-stable"
        assert projection["cues"][0]["target"] == "mixer"
        created_events = [
            event
            for event in system.repositories.list_events(run_id=run.id, limit=None)
            if event.type == "RunCreated"
        ]
        assert len(created_events) == 1
        pinned = created_events[0].payload["context"]["twinBinding"]
        assert pinned["definitionRevision"] == "test-revision"
        assert pinned["sceneSha256"] == hashlib.sha256(scene.read_bytes()).hexdigest()

        twin_definition["revision"] = "changed-after-run"
        twin_path = twin_root / "twin.yaml"
        twin_path.write_text(
            yaml.safe_dump(twin_definition, sort_keys=False),
            encoding="utf-8",
        )
        system.twin = TwinService.from_file(twin_path)
        with pytest.raises(TwinProjectionError, match="different twin definition"):
            system.project_twin_run(run.id)
    finally:
        await system.close()
