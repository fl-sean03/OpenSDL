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

# Setting `obj.location` does not update `obj.matrix_world`; the depsgraph does, lazily. Every
# geometry check below reads matrix_world, so without this they silently read local coordinates
# and a bench 0.9 m up looks like it straddles the origin. This one line is load-bearing.
_bpy.context.view_layer.update()

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
    if _obj.type == "MESH" and _obj.data.materials:
        # What the surface actually is, so a critique of how it looks can be checked against it.
        # The recurring note has been "reads mid-grey, not the dark grey specified", and without
        # this nobody can tell whether the material is wrong or the light is.
        _mat = _obj.data.materials[0]
        try:
            _bsdf = _mat.node_tree.nodes["Principled BSDF"]
            _base = _bsdf.inputs["Base Color"].default_value
            _entry["material"] = {{{{
                "name": _mat.name,
                "albedo": round(sum(_base[:3]) / 3.0, 3),
                "roughness": round(_bsdf.inputs["Roughness"].default_value, 2),
                "metallic": round(_bsdf.inputs["Metallic"].default_value, 2),
            }}}}
        except Exception:
            pass

    if _obj.type == "CAMERA":
        _report["cameras"] += 1
        _entry["lens"] = round(_obj.data.lens, 1)
    elif _obj.type == "LIGHT":
        _report["lights"] += 1
        # The critic asked for these by name: without energy and size it cannot tell an
        # underexposed scene from a correctly lit one that needs a stronger key.
        _entry["light"] = {{{{
            "type": _obj.data.type,
            "energy": round(_obj.data.energy, 1),
            "size": round(getattr(_obj.data, "size", 0.0), 3),
            "color": [round(_c, 3) for _c in _obj.data.color],
        }}}}
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
        _cropped = []
        for _obj in _bpy.data.objects:
            if _obj.type != "MESH" or not _obj.data.vertices:
                continue
            if max(_obj.dimensions) > 5.0:
                continue
            _considered += 1
            _corners = [_obj.matrix_world @ _mathutils.Vector(c) for c in _obj.bound_box]
            _inside = 0
            for _corner in _corners:
                _ndc = _w2c(_scene, _cam, _corner)
                if 0.0 <= _ndc.x <= 1.0 and 0.0 <= _ndc.y <= 1.0 and _ndc.z > 0.0:
                    _inside += 1
            if _inside:
                _visible += 1
            # Partly in shot is its own failure. A leg whose foot is cut off satisfies any check
            # that asks "is this object visible" and still breaks the composition.
            #
            # A ground plane is the exception: it is supposed to run past the frame, and reporting
            # it every time trains the reader to ignore this defect.
            # Scenery is meant to run past the frame; only subject matter can be "cropped".
            _dims = _obj.dimensions
            _scenery = max(_dims) > 5.0
            if 0 < _inside < 8 and not _scenery:
                _cropped.append(_obj.name)
        _report["meshes_in_frame"] = _visible
        _report["meshes_considered"] = _considered
        if _cropped:
            _report["cropped"] = _cropped
            _report["defects"].append(
                "these bodies are cut off by the frame edge: "
                + ", ".join(_cropped[:6])
                + ". Pull the camera back or raise the lens until each one is whole"
            )
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

# Two bodies whose faces sit at the same height AND overlap in plan will fight for the same
# pixels. Both conditions matter: four legs at one corner height each are a bench, not a bug, and
# only the pair that also overlaps in x and y can actually z-fight. Testing the geometry rather
# than the names avoids guessing which of Leg_BL and Leg_FR are siblings.
_boxes = []
for _obj in _bpy.data.objects:
    if _obj.type != "MESH" or not _obj.data.vertices:
        continue
    # A ground plane is what everything else rests on, so it shares a height with every body that
    # touches it. That is a floor, not a defect.
    if max(_obj.dimensions) > 5.0:
        continue
    _pts = [_obj.matrix_world @ _mathutils.Vector(_c) for _c in _obj.bound_box]
    _boxes.append(
        (
            _obj.name,
            min(_p.x for _p in _pts), max(_p.x for _p in _pts),
            min(_p.y for _p in _pts), max(_p.y for _p in _pts),
            min(_p.z for _p in _pts), max(_p.z for _p in _pts),
        )
    )

def _overlaps(_a, _b, _c, _d):
    return min(_b, _d) - max(_a, _c) > 1e-4

_fights = []
for _i in range(len(_boxes)):
    for _j in range(_i + 1, len(_boxes)):
        _p, _q = _boxes[_i], _boxes[_j]
        if not _overlaps(_p[1], _p[2], _q[1], _q[2]):
            continue
        if not _overlaps(_p[3], _p[4], _q[3], _q[4]):
            continue
        # Bottom-to-bottom is not a fight. Two bodies resting on the same surface are both sunk
        # into it by the same amount, so their undersides coincide inside a third body where
        # nothing can see them. What fights is a top meeting a top, or a top meeting a bottom.
        for _ia, _za in ((0, _p[5]), (1, _p[6])):
            for _ib, _zb in ((0, _q[5]), (1, _q[6])):
                if _ia == 0 and _ib == 0:
                    continue
                if abs(_za - _zb) < 5e-4:
                    _fights.append((_p[0], _q[0], round(_za, 4)))
if _fights:
    _report["coplanar"] = [
        {{{{"a": _a, "b": _b, "z": _z}}}} for _a, _b, _z in _fights[:8]
    ]
    _report["defects"].append(
        "these bodies overlap in plan and share an exact height, so they will z-fight: "
        + "; ".join(f"{{{{_a}}}}/{{{{_b}}}} at z={{{{_z}}}}" for _a, _b, _z in _fights[:3])
        + ". Sink one into the other by a few millimetres"
    )

# A detail modelled inside a solid body renders as nothing at all. The model builds a slot or a
# recessed panel as its own box and places it within the housing, where it is invisible and the
# critic reports a featureless block. Containment is exact and cheap to test, so it should not need
# an eye.
_buried = []
for _i in range(len(_boxes)):
    for _j in range(len(_boxes)):
        if _i == _j:
            continue
        _a, _b = _boxes[_i], _boxes[_j]
        _inside = (
            _a[1] >= _b[1] - 1e-5 and _a[2] <= _b[2] + 1e-5
            and _a[3] >= _b[3] - 1e-5 and _a[4] <= _b[4] + 1e-5
            and _a[5] >= _b[5] - 1e-5 and _a[6] <= _b[6] + 1e-5
        )
        _smaller = (
            (_a[2] - _a[1]) * (_a[4] - _a[3]) * (_a[6] - _a[5])
            < (_b[2] - _b[1]) * (_b[4] - _b[3]) * (_b[6] - _b[5]) * 0.95
        )
        if _inside and _smaller:
            _buried.append((_a[0], _b[0]))
            break
if _buried:
    _report["buried"] = [{{{{"inner": _a, "outer": _b}}}} for _a, _b in _buried[:8]]
    _report["defects"].append(
        "these bodies are entirely inside another and cannot be seen: "
        + "; ".join(f"{{{{_a}}}} inside {{{{_b}}}}" for _a, _b in _buried[:4])
        + ". A slot or recess has to break the outer surface: make the detail proud of the face by "
        "1-2 mm, or model the housing as separate panels around the opening"
    )

# Contrast between the subject and what it stands on is a material decision, not a lighting one,
# and it is the note this build has drawn most often.
_albedos = {{{{}}}}
for _entry_ in _report["objects"]:
    _m = _entry_.get("material")
    if _m:
        _albedos[_entry_["name"]] = _m["albedo"]
_ground_albedo = None
for _obj in _bpy.data.objects:
    if _obj.type == "MESH" and max(_obj.dimensions) > 5.0 and _obj.name in _albedos:
        _ground_albedo = _albedos[_obj.name]
        break
if _ground_albedo is not None:
    _too_close = [
        _n for _n, _a in _albedos.items()
        if _n not in ("Floor", "Backdrop")
        and abs(_a - _ground_albedo) < 0.06
        and _n in [_o.name for _o in _bpy.data.objects if max(_o.dimensions) <= 5.0]
    ]
    if _too_close:
        _report["defects"].append(
            f"these surfaces sit within 0.06 albedo of the ground ({{{{_ground_albedo}}}}) and will "
            f"not read as distinct from it: {{{{', '.join(_too_close[:4])}}}}. Take the material from "
            "palette() rather than choosing a value"
        )

# Detail modelled on a face the camera cannot see is the same waste as detail buried inside a
# body: a loading slot on the back of an instrument is invisible and the housing reads as a plain
# block. Small bodies touching a much larger one are checked against the view direction.
if _scene.camera is not None:
    _eye = _scene.camera.matrix_world.translation
    _hidden = []
    for _i in range(len(_boxes)):
        for _j in range(len(_boxes)):
            if _i == _j:
                continue
            _s, _big = _boxes[_i], _boxes[_j]
            _vs = (_s[2] - _s[1]) * (_s[4] - _s[3]) * (_s[6] - _s[5])
            _vb = (_big[2] - _big[1]) * (_big[4] - _big[3]) * (_big[6] - _big[5])
            if _vb <= 0 or _vs > _vb * 0.35 or _vb > 2.0:
                continue
            _touch = (
                min(_s[2], _big[2]) - max(_s[1], _big[1]) > -0.02
                and min(_s[4], _big[4]) - max(_s[3], _big[3]) > -0.02
                and min(_s[6], _big[6]) - max(_s[5], _big[5]) > -0.02
            )
            if not _touch:
                continue
            _cs = _mathutils.Vector(((_s[1] + _s[2]) / 2, (_s[3] + _s[4]) / 2, (_s[5] + _s[6]) / 2))
            # A feature on a housing sits within that housing's own height. A leg sits below the
            # bench it holds up, and is structure rather than detail, so it is not this check's
            # business even though it is small and touching and behind.
            if not (_big[5] - 1e-4 <= _cs.z <= _big[6] + 1e-4):
                continue
            _cb = _mathutils.Vector(
                ((_big[1] + _big[2]) / 2, (_big[3] + _big[4]) / 2, (_big[5] + _big[6]) / 2)
            )
            _view = (_cb - _eye).normalized()
            if (_cs - _cb).dot(_view) > 0.01:
                _hidden.append((_s[0], _big[0]))
            break
    if _hidden:
        _report["facing_away"] = [{{{{"detail": _a, "body": _b}}}} for _a, _b in _hidden[:6]]
        _report["defects"].append(
            "these details sit on the far side of the body they belong to and the camera cannot "
            "see them: " + ", ".join(f"{{{{_a}}}} on {{{{_b}}}}" for _a, _b in _hidden[:4])
            + ". Put the features on the face the camera is looking at"
        )

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
        if _mean < 0.14:
            _report["defects"].append(
                f"the image is underexposed (mean luminance {{{{_mean:.3f}}}}); raise the key light "
                "or move it closer"
            )
        if _mean > 0.72:
            _report["defects"].append(
                f"the image is overexposed (mean luminance {{{{_mean:.3f}}}}); lower the key light"
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
