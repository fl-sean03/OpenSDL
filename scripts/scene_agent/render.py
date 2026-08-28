"""Render a Blender script headlessly and report what came back.

The agent loop needs two things from every attempt and they fail differently. The image says
whether the scene looks like the thing it is supposed to be. The structured report says whether the
geometry is sane, and it catches what an image cannot: an object at the origin because a transform
silently failed, a mesh with no faces, a camera inside a wall, a NaN in a matrix.

`examples/digital-twin-surrogate/scene/check_scene.py` learned the same lesson the hard way. Its
docstring records that a scalar check "cannot see a plate that slides out of the gripper" — and the
converse is just as true, which is why both channels run on every iteration.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

#: Blender writes a great deal to stdout. Only the fenced block is ours.
PROBE_OPEN = "<<<OPENSDL-SCENE-PROBE"
PROBE_CLOSE = "OPENSDL-SCENE-PROBE>>>"

#: Appended to every candidate script. It runs after the scene is built, renders a still, and
#: prints a structured report the loop can parse. Keeping it here rather than asking the model to
#: emit it means the report format cannot drift between iterations.
PROBE = f'''
# ---- appended by scripts/scene_agent/render.py; not part of the candidate ----
import json as _json, math as _math, sys as _sys
import bpy as _bpy

def _finite(values):
    return all(isinstance(v, (int, float)) and _math.isfinite(v) for v in values)

_scene = _bpy.context.scene
_scene.render.filepath = {{RENDER_PATH!r}}
_scene.render.image_settings.file_format = "PNG"
_scene.render.resolution_x = {{WIDTH}}
_scene.render.resolution_y = {{HEIGHT}}
_available = {{{{item.identifier for item in
              type(_scene.render).bl_rna.properties["engine"].enum_items}}}}
_wanted = {{ENGINE!r}}
_engine_note = None
if _wanted not in _available:
    _engine_note = f"engine {{{{_wanted!r}}}} is unavailable in this Blender; used EEVEE instead"
    _wanted = "BLENDER_EEVEE" if "BLENDER_EEVEE" in _available else sorted(_available)[0]
_scene.render.engine = _wanted
if _wanted == "CYCLES":
    _scene.cycles.samples = {{SAMPLES}}

_report = {{{{"engine": _wanted, "objects": [], "cameras": 0, "lights": 0, "meshes": 0, "defects": []}}}}
if _engine_note:
    _report["defects"].append(_engine_note)
_at_origin = 0
for _obj in _bpy.data.objects:
    _loc = tuple(_obj.location)
    _dims = tuple(_obj.dimensions)
    _entry = {{{{"name": _obj.name, "type": _obj.type,
                 "location": [round(v, 4) for v in _loc],
                 "dimensions": [round(v, 4) for v in _dims]}}}}
    _report["objects"].append(_entry)
    if _obj.type == "CAMERA":
        _report["cameras"] += 1
    elif _obj.type == "LIGHT":
        _report["lights"] += 1
    elif _obj.type == "MESH":
        _report["meshes"] += 1
        if len(_obj.data.polygons) == 0:
            _report["defects"].append(f"mesh {{{{_obj.name!r}}}} has no faces")
    if not _finite(_loc) or not _finite(_dims):
        _report["defects"].append(f"object {{{{_obj.name!r}}}} has a non-finite transform")
    if _loc == (0.0, 0.0, 0.0) and _obj.type == "MESH":
        _at_origin += 1

if _report["cameras"] == 0:
    _report["defects"].append("the scene has no camera, so nothing can be rendered")
if _report["lights"] == 0 and _scene.render.engine != "BLENDER_WORKBENCH":
    _report["defects"].append("the scene has no light, so the render will be black")
if _at_origin > 1:
    _report["defects"].append(
        f"{{{{_at_origin}}}} meshes sit exactly at the origin, which usually means a transform "
        "was never applied"
    )

try:
    _bpy.ops.render.render(write_still=True)
    _report["rendered"] = True
except Exception as _exc:
    _report["rendered"] = False
    _report["defects"].append(f"render raised {{{{type(_exc).__name__}}}}: {{{{_exc}}}}")

print("{PROBE_OPEN}")
print(_json.dumps(_report))
print("{PROBE_CLOSE}")
'''


@dataclass(frozen=True)
class RenderOutcome:
    """Everything one attempt produced. `ok` means Blender ran, not that the scene is good."""

    ok: bool
    image: Path | None
    report: dict[str, object] = field(default_factory=dict)
    stderr: str = ""
    returncode: int = 0

    @property
    def defects(self) -> list[str]:
        found = self.report.get("defects", [])
        return [str(item) for item in found] if isinstance(found, list) else []


def blender_executable(explicit: str | None = None) -> str:
    """The Blender to run, preferring an explicit path and failing loudly without one."""

    found = explicit or shutil.which("blender")
    if not found:
        raise FileNotFoundError(
            "blender is not on PATH. The scene agent renders headlessly and cannot work without "
            "it. Install it, or pass --blender with a path."
        )
    return found


def render_script(
    source: str,
    out_dir: Path,
    *,
    blender: str | None = None,
    width: int = 960,
    height: int = 540,
    engine: str = "BLENDER_EEVEE",
    samples: int = 64,
    timeout: float = 300.0,
) -> RenderOutcome:
    """Run one candidate script in a fresh Blender and return its image and report.

    The script is written to a temporary file rather than piped, so a traceback names a real line
    number the model can act on.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    image = out_dir / "render.png"
    probe = PROBE.format(
        RENDER_PATH=str(image),
        WIDTH=width,
        HEIGHT=height,
        ENGINE=engine,
        SAMPLES=samples,
    )

    with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as handle:
        handle.write(source)
        handle.write("\n")
        handle.write(probe)
        script_path = Path(handle.name)

    try:
        completed = subprocess.run(  # noqa: S603
            [blender_executable(blender), "-b", "--factory-startup", "-P", str(script_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return RenderOutcome(
            ok=False,
            image=None,
            report={"defects": [f"blender did not finish within {timeout:.0f}s"]},
            returncode=-1,
        )
    finally:
        script_path.unlink(missing_ok=True)

    report = _parse_probe(completed.stdout)
    if report is None:
        return RenderOutcome(
            ok=False,
            image=None,
            report={"defects": ["the script failed before the probe ran"]},
            stderr=_tail(completed.stdout + completed.stderr),
            returncode=completed.returncode,
        )

    rendered = bool(report.get("rendered")) and image.is_file()
    return RenderOutcome(
        ok=rendered,
        image=image if rendered else None,
        report=report,
        stderr=_tail(completed.stderr),
        returncode=completed.returncode,
    )


def _parse_probe(stdout: str) -> dict[str, object] | None:
    """Pull the fenced report out of Blender's very chatty stdout."""

    if PROBE_OPEN not in stdout or PROBE_CLOSE not in stdout:
        return None
    body = stdout.split(PROBE_OPEN, 1)[1].split(PROBE_CLOSE, 1)[0].strip()
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _tail(text: str, lines: int = 40) -> str:
    """The end of a traceback is the part that says what went wrong."""

    kept = [line for line in text.splitlines() if line.strip()]
    return "\n".join(kept[-lines:])
