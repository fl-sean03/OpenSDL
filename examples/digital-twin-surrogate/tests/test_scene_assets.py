from __future__ import annotations

import hashlib
import json
import re
import struct
from pathlib import Path

from opensdl_twin import TwinService


EXAMPLE_ROOT = Path(__file__).resolve().parents[1]
SCENE_ROOT = EXAMPLE_ROOT / "scene"
ASSET_ROOT = SCENE_ROOT / "assets"
VIEWER_DEMO = EXAMPLE_ROOT / "viewer" / "src" / "demo.ts"


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
    assert len(motion["checks"]) == 108
    assert all(check["passed"] for check in motion["checks"])


def _viewer_demo_binding_source() -> tuple[
    str | None, tuple[int, int] | None, dict[str, tuple[int, int]]
]:
    """Read the scene binding the viewer ships, straight out of its source.

    The viewer verifies this digest in the browser, so a demo file left behind
    by a scene change produces a viewer that refuses its own scene.  Nothing
    caught that: the asset tests close a ring around the GLB, the inventory,
    the motion report and ``twin.yaml``, and the viewer's own copy sat outside
    it.  This reads the literals rather than importing TypeScript, which is
    enough for a drift check and keeps the test in the suite that already owns
    the other four corners.
    """
    source = VIEWER_DEMO.read_text(encoding="utf-8")

    digest_match = re.search(r'sha256:\s*"([0-9a-f]{64})"', source)
    timeline_match = re.search(
        r"animationTimeline:\s*\{[^}]*?frameStart:\s*(\d+),\s*frameEnd:\s*(\d+),",
        source,
        re.S,
    )
    # Scoped to the bindings array, because an entity or anchor identifier
    # followed by the timeline's own frame range parses as a binding otherwise.
    # ``index`` raising is the intended behaviour if that block is restructured:
    # a parse that silently found nothing is the failure mode this test exists
    # to prevent, so it must not be able to degrade into one quietly.
    block_start = source.index("bindings: [")
    block = source[block_start : source.index("\n};", block_start)]
    bindings = {
        match.group("id"): (int(match.group("start")), int(match.group("end")))
        for match in re.finditer(
            r'id:\s*"(?P<id>[a-z0-9-]+)",(?:(?!id:).)*?frameStart:\s*(?P<start>\d+),'
            r"\s*frameEnd:\s*(?P<end>\d+),",
            block,
            re.S,
        )
    }
    return (
        digest_match.group(1) if digest_match else None,
        (int(timeline_match.group(1)), int(timeline_match.group(2))) if timeline_match else None,
        bindings,
    )


def test_viewer_demo_data_matches_the_declared_twin() -> None:
    service = TwinService.from_file(EXAMPLE_ROOT / "twin.yaml")
    timeline = service.definition.animation_timeline
    assert timeline is not None

    digest, viewer_range, viewer_bindings = _viewer_demo_binding_source()

    # A parse that found nothing would agree with everything, so each side is
    # compared against a value the twin actually declares.
    assert digest == service.definition.scene.sha256
    assert viewer_range == (timeline.frame_start, timeline.frame_end)
    assert viewer_bindings == {
        binding.id: (binding.frame_start, binding.frame_end) for binding in timeline.bindings
    }


def test_scene_contains_every_required_node_and_the_full_authored_timeline() -> None:
    inventory = json.loads((ASSET_ROOT / "node-inventory.json").read_text())
    document = _glb_document(ASSET_ROOT / "surrogate-cell.glb")
    node_names = {node.get("name") for node in document.get("nodes", [])}
    animations = document.get("animations", [])

    assert set(inventory["requiredNodes"]) <= node_names
    assert len(animations) == 32
    assert inventory["frameRange"] == {"start": 1, "end": 1176, "fps": 24}

    max_animation_time = max(
        accessor["max"][0]
        for animation in animations
        for sampler in animation["samplers"]
        if "max" in (accessor := document["accessors"][sampler["input"]])
    )
    assert max_animation_time >= 49.0
