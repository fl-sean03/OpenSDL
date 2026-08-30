"""Turn a generated scene into something OpenSDL can bind to.

A render is a picture. A twin is a picture with names an adapter can address: `twin.yaml` maps a
semantic entity to a scene node, so when a capability moves the gripper, the projector knows which
node to move. Without that mapping a beautiful scene is decoration.

This is the step that carries forward. Whatever domain D6 lands on, the facility-scale scene has to
arrive as GLB plus a digest plus an entity mapping, exactly as
`examples/digital-twin-surrogate/twin.yaml` does today. Proving it on a bench with two instruments
is cheap; discovering it does not work at facility scale is not.

The generated `twin.yaml` is a DRAFT. It names every body the scene declared and guesses which are
worth binding, and a human decides what is actually a resource. Guessing the mapping and presenting
it as authoritative would be the wrong kind of helpful.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .prelude import PRELUDE
from .render import blender_executable

#: Appended after the scene script. Exports the GLB and reports the node inventory.
EXPORT = """
# ---- appended by scripts/scene_agent/export.py ----
import json as _json
import bpy as _bpy
import mathutils as _mathutils

_bpy.context.view_layer.update()

_inventory = []
for _obj in _bpy.data.objects:
    if _obj.type != "MESH":
        continue
    _pts = [_obj.matrix_world @ _mathutils.Vector(_c) for _c in _obj.bound_box]
    _inventory.append(
        {{
            "node": _obj.name,
            "location": [round(_v, 5) for _v in _obj.location],
            "dimensions": [round(_v, 5) for _v in _obj.dimensions],
            "centre": [
                round(sum(_p[_i] for _p in _pts) / len(_pts), 5) for _i in range(3)
            ],
            "top": round(max(_p.z for _p in _pts), 5),
        }}
    )

_bpy.ops.export_scene.gltf(
    filepath={GLB_PATH!r},
    export_format="GLB",
    use_selection=False,
    export_apply=True,
)

print("<<<OPENSDL-EXPORT")
print(_json.dumps({{"nodes": _inventory}}))
print("OPENSDL-EXPORT>>>")
"""


@dataclass(frozen=True)
class Export:
    glb: Path
    digest: str
    nodes: list[dict[str, object]]
    twin: Path


#: A body worth binding is one a capability could plausibly act on. Everything else is set
#: dressing, and listing the floor as a resource would make the draft worse than useless.
#: `shell_` is the prefix `room()` puts on the floor, ceiling, walls, mullions and the lit card
#: outside the glazing. A mullion is small enough to pass the size cut below, so the prefix is what
#: keeps a window frame out of a list of things a capability can address.
SCENERY = ("floor", "backdrop", "wall", "ground", "shell_", "lane_", "fixture", "tray_", "duct")


def _looks_bindable(node: dict[str, object]) -> bool:
    name = str(node.get("node", "")).lower()
    if any(word in name for word in SCENERY):
        return False
    dims = node.get("dimensions")
    return not (isinstance(dims, list) and dims and max(float(d) for d in dims) > 5.0)


def export_scene(
    source: str,
    out_dir: Path,
    *,
    blender: str | None = None,
    revision: str = "generated",
    timeout: float = 420.0,
) -> Export:
    """Render the script to a GLB, digest it, and write a draft twin definition beside it."""

    out_dir.mkdir(parents=True, exist_ok=True)
    glb = out_dir / "scene.glb"
    script = PRELUDE + "\n" + source + "\n" + EXPORT.format(GLB_PATH=str(glb))

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as handle:
        handle.write(script)
        path = Path(handle.name)
    try:
        done = subprocess.run(  # noqa: S603
            [blender_executable(blender), "-b", "-P", str(path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    finally:
        path.unlink(missing_ok=True)

    if "<<<OPENSDL-EXPORT" not in done.stdout:
        tail = "\n".join(done.stderr.strip().splitlines()[-20:])
        raise RuntimeError(f"the scene did not export:\n{tail}")
    body = done.stdout.split("<<<OPENSDL-EXPORT", 1)[1].split("OPENSDL-EXPORT>>>", 1)[0]
    nodes = json.loads(body.strip()).get("nodes", [])

    if not glb.is_file():
        raise RuntimeError("blender reported an export but wrote no GLB")
    digest = hashlib.sha256(glb.read_bytes()).hexdigest()

    bindable = [n for n in nodes if _looks_bindable(n)]
    lines = [
        "apiVersion: opensdl.dev/v0alpha1",
        "kind: DigitalTwin",
        "version: 0.1.0",
        f"revision: {revision}",
        "coordinateFrame:",
        "  unit: m",
        "  handedness: right",
        "  upAxis: Z",
        "  origin: [0.0, 0.0, 0.0]",
        "scene:",
        f"  path: {glb.name}",
        f"  sha256: {digest}",
        "# DRAFT. Every body the scene declared is listed below. Which of these are resources,",
        "# and what they are called in the manifest, is a decision for whoever owns the laboratory.",
        "entities:",
    ]
    for node in bindable:
        name = str(node["node"])
        lines.append(f"  - id: {name.lower().replace('_', '-')}")
        lines.append(f"    node: {name}")
        lines.append("    resources: []")
    lines.append("anchors:")
    for node in bindable:
        centre = node.get("centre") or [0, 0, 0]
        top = node.get("top", 0)
        name = str(node["node"])
        lines.append(f"  - id: {name.lower().replace('_', '-')}-top")
        lines.append(f"    node: {name}")
        lines.append(f"    position: [{centre[0]}, {centre[1]}, {top}]")

    twin = out_dir / "twin.yaml"
    twin.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return Export(glb=glb, digest=digest, nodes=nodes, twin=twin)
