from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path

from opensdl_twin import TwinService


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
SCENE_ROOT = EXAMPLE_ROOT / "scene"
ASSET_ROOT = SCENE_ROOT / "assets"


def _glb_document(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    magic, version, declared_length = struct.unpack_from("<4sII", data)
    assert magic == b"glTF"
    assert version == 2
    assert declared_length == len(data)

    json_length, json_type = struct.unpack_from("<II", data, 12)
    assert json_type == 0x4E4F534A
    return json.loads(data[20 : 20 + json_length].decode("utf-8"))


def test_scene_asset_matches_the_declared_twin_and_build_reports() -> None:
    service = TwinService.from_file(EXAMPLE_ROOT / "twin.yaml")
    scene_path = ASSET_ROOT / "surrogate-cell.glb"
    scene_digest = hashlib.sha256(scene_path.read_bytes()).hexdigest()
    inventory = json.loads((ASSET_ROOT / "node-inventory.json").read_text())
    motion = json.loads((ASSET_ROOT / "motion-validation.json").read_text())

    assert scene_digest == service.definition.scene.sha256
    assert scene_digest == inventory["sha256"]
    assert scene_digest == motion["sha256"]
    assert motion["passed"] is True
    assert len(motion["checks"]) == 70
    assert all(check["passed"] for check in motion["checks"])


def test_scene_contains_every_required_node_and_the_full_authored_timeline() -> None:
    inventory = json.loads((ASSET_ROOT / "node-inventory.json").read_text())
    document = _glb_document(ASSET_ROOT / "surrogate-cell.glb")
    node_names = {node.get("name") for node in document.get("nodes", [])}
    animations = document.get("animations", [])

    assert set(inventory["requiredNodes"]) <= node_names
    assert len(animations) == 27
    assert inventory["frameRange"] == {"start": 1, "end": 960, "fps": 24}

    max_animation_time = max(
        accessor["max"][0]
        for animation in animations
        for sampler in animation["samplers"]
        if "max" in (accessor := document["accessors"][sampler["input"]])
    )
    assert max_animation_time >= 40.0
