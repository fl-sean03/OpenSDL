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

from .prelude import PRELUDE

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
import mathutils as _mathutils

def _finite(values):
    return all(isinstance(v, (int, float)) and _math.isfinite(v) for v in values)

_scene = _bpy.context.scene
_scene.render.filepath = {{RENDER_PATH!r}}
_scene.render.image_settings.file_format = "PNG"
_scene.render.resolution_x = {{WIDTH}}
_scene.render.resolution_y = {{HEIGHT}}
# Cycles registers itself as a plugin, so it never appears in the class-level RNA enum even
# when it is installed and working. Introspecting `enum_items` reports a false negative; the
# only honest test is to assign and see whether it takes.
_wanted = {{ENGINE!r}}
_engine_note = None
try:
    _scene.render.engine = _wanted
except TypeError:
    _engine_note = f"engine {{{{_wanted!r}}}} is unavailable in this Blender; used EEVEE instead"
    _wanted = "BLENDER_EEVEE"
_scene.render.engine = _wanted
if _wanted == "CYCLES":
    _scene.cycles.samples = {{SAMPLES}}
    # OptiX first, CUDA second, CPU last. Hardware ray tracing plus OptiX denoising gives a clean
    # image at sample counts where an undenoised render would still be visibly grainy, which is
    # the difference between a usable critique and one arguing about noise.
    _prefs = _bpy.context.preferences.addons["cycles"].preferences
    _chosen = None
    for _backend in ("OPTIX", "CUDA"):
        try:
            _prefs.compute_device_type = _backend
            _prefs.refresh_devices()
        except Exception:
            continue
        _gpus = [_d for _d in _prefs.devices if _d.type == _backend]
        if _gpus:
            for _d in _prefs.devices:
                _d.use = _d.type == _backend
            _chosen = _backend
            break
    if _chosen:
        _scene.cycles.device = "GPU"
        _report_device = f"{{{{_chosen}}}}:{{{{_gpus[0].name}}}}"
    else:
        _scene.cycles.device = "CPU"
        _report_device = "CPU"
    try:
        _scene.cycles.use_denoising = True
        _scene.cycles.denoiser = "OPTIX" if _chosen == "OPTIX" else "OPENIMAGEDENOISE"
    except Exception:
        pass
else:
    _report_device = "CPU"


# Blender defaults the view transform to AgX, which is built for filmic HDR footage: it
# desaturates and lifts shadows hard. A 0.2-albedo bench under a normal key comes out of it as
# light grey, so a scene with correct materials renders washed out and the critic blames the
# materials. Standard is the honest transform for a technical illustration, and the harness owns
# render settings the same way it owns resolution and engine.
try:
    _scene.view_settings.view_transform = "Standard"
except Exception:
    pass

_report = {{{{"engine": _wanted, "device": _report_device, "objects": [], "cameras": 0, "lights": 0, "meshes": 0, "defects": []}}}}
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

# Does the camera actually frame anything? A scene can have every object it needs, a camera and a
# light, and still render a picture of the floor because the camera points at nothing. That reads
# as a clean scene to every scalar check and as a failure to anyone who looks at it.
try:
    from bpy_extras.object_utils import world_to_camera_view as _w2c

    _cam = _scene.camera
    if _cam is not None:
        _visible = 0
        _considered = 0
        for _obj in _bpy.data.objects:
            if _obj.type != "MESH" or not _obj.data.vertices:
                continue
            _considered += 1
            _corners = [_obj.matrix_world @ _mathutils.Vector(c) for c in _obj.bound_box]
            for _corner in _corners:
                _ndc = _w2c(_scene, _cam, _corner)
                if 0.0 <= _ndc.x <= 1.0 and 0.0 <= _ndc.y <= 1.0 and _ndc.z > 0.0:
                    _visible += 1
                    break
        _report["meshes_in_frame"] = _visible
        _report["meshes_considered"] = _considered
        if _considered and _visible == 0:
            _report["defects"].append(
                "the camera frames none of the geometry. Every mesh is outside the view or "
                "behind the camera, so the render shows background only"
            )
        elif _considered >= 3 and _visible <= _considered // 4:
            _report["defects"].append(
                f"the camera frames only {{{{_visible}}}} of {{{{_considered}}}} meshes; most of "
                "the scene is out of shot"
            )
except Exception as _exc:
    _report["defects"].append(f"framing check failed: {{{{_exc}}}}")

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
    # What the image is actually made of. A render can be structurally perfect and still be a
    # grey rectangle, and these three numbers say so without anyone looking.
    try:
        _img = _bpy.data.images.load({{RENDER_PATH!r}})
        _px = list(_img.pixels)
        _lum = [
            _px[_i] * 0.2126 + _px[_i + 1] * 0.7152 + _px[_i + 2] * 0.0722
            for _i in range(0, len(_px), 4)
        ]
        _n = len(_lum) or 1
        _mean = sum(_lum) / _n
        _blown = sum(1 for _v in _lum if _v > 0.98) / _n
        _crushed = sum(1 for _v in _lum if _v < 0.02) / _n
        _spread = (sum((_v - _mean) ** 2 for _v in _lum) / _n) ** 0.5
        _report["exposure"] = {{{{
            "mean": round(_mean, 3),
            "blown": round(_blown, 4),
            "crushed": round(_crushed, 4),
            "contrast": round(_spread, 3),
        }}}}
        if _blown > 0.10:
            _report["defects"].append(
                f"{{{{_blown*100:.0f}}}}% of the image is blown to white; the key light is far too strong"
            )
        if _crushed > 0.25:
            _report["defects"].append(
                f"{{{{_crushed*100:.0f}}}}% of the image is crushed to black; there is not enough fill"
            )
        if _spread < 0.06:
            _report["defects"].append(
                f"the image has almost no tonal range (contrast {{{{_spread:.3f}}}}); it reads as a "
                "flat field rather than as lit geometry"
            )
        _bpy.data.images.remove(_img)
    except Exception as _exc:
        _report["defects"].append(f"exposure check failed: {{{{_exc}}}}")
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
    engine: str = "CYCLES",
    samples: int = 256,
    timeout: float = 420.0,
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
        handle.write(PRELUDE)
        handle.write("\n")
        handle.write(source)
        handle.write("\n")
        handle.write(probe)
        script_path = Path(handle.name)

    try:
        completed = subprocess.run(  # noqa: S603
            # No `--factory-startup`: it disables addons, and Cycles never returns to the engine
            # enum even after `addon_enable`, so the GPU path becomes unreachable. Scene-level
            # determinism comes from the candidate calling `read_factory_settings(use_empty=True)`,
            # which resets the scene without resetting preferences.
            [blender_executable(blender), "-b", "-P", str(script_path)],
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
