"""Spatial invariants for the OpenSDL digital-twin reference cell.

``validate_motion`` in ``build_scene.py`` checks scalars: deck pitch, object
counts, keyframe values, orbit radius.  A scalar check cannot see a plate that
slides out of the gripper, jaws that close on empty air, or a carriage that
travels through the bench it is supposed to work over, because none of those
facts belong to a single object.  This module checks relationships between
bodies.

Invariant A - carry rigidity
    Whenever a payload moves it moves rigidly with the body carrying it.  The
    supports are the gripper carriage, the shaker rotor, and the two hotel
    shuttles; nothing else in the cell can move labware.

Invariant B - grip contact
    Whenever the jaws hold a closed grip width, the jaw assemblies bracket that
    payload with no gap larger than ``GRIP_SEPARATION`` on any axis, and the
    payload never rides the carriage with the jaws open.

Invariant C - interpenetration
    No moving assembly pushes into a fixed assembly deeper than the contact
    margin, except for the documented contacts in ``ALLOWED_CONTACTS``.

Invariant D - gripper mechanism continuity
    Every jaw reaches the carriage through an unbroken mechanism: paddle to
    finger to carrier to cross-rail.  Each link stays in contact at every
    frame and therefore at every authored jaw width, and neither carrier ever
    runs off the end of the rail it rides.  A jaw can be parented perfectly and
    track its carriage exactly while still reading as a bar floating in space,
    because nothing spans the gap; only this check sees that.

Run standalone against a built file::

    blender -b <scene>.blend --factory-startup -noaudio \
        -P scene/check_scene.py -- --step 2

``build_scene.py`` imports :func:`validate_spatial` and runs it before the GLB
export, so a violation stops the build instead of shipping.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from fnmatch import fnmatch

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


# Motion thresholds.  A payload counts as moving above MOVE_EPSILON, and a
# rigid carry may not drift from its support by more than RIGID_TOLERANCE.
MOVE_EPSILON = 1e-5
RIGID_TOLERANCE = 1e-4
# A closed jaw may not stand off its payload by more than 2 mm on any axis.
GRIP_SEPARATION = 0.002
# Rigid bodies in contact touch.  Each body is eroded by CONTACT_MARGIN before
# the overlap test, so surfaces that meet, or overlap by less than twice the
# margin, are contact rather than interpenetration.
CONTACT_MARGIN = 0.00025

# Authored gripper states, mirrored from build_scene.animate_scene.  The jaw
# width identifies what the gripper is holding without inspecting the payload.
JAW_OPEN = 0.092
JAW_PLATE_CLOSED = 0.0719
JAW_LID_CLOSED = 0.0855
JAW_STATE_TOLERANCE = 1e-4

PLATE = "SampleCarrier"
READER_LID = "ColorimeterDoor"
CARRIAGE = "RobotCarriage"
JAW_LEFT = "GripperJawLeft"
JAW_RIGHT = "GripperJawRight"

# Every body in the cell that can move labware.
SUPPORTS = (CARRIAGE, "MixerRotor", "InputStacker_Shuttle", "OutputStacker_Shuttle")

MOVERS = (PLATE, CARRIAGE, JAW_LEFT, JAW_RIGHT, "DispenserHead")
# The line is open, so there is no enclosure to test against.  What a mover can
# run into instead is the machine frame it is built into, the process deck, the
# service assemblies packed under that deck, the runway that carries it, and the
# modules and labware on the deck.
STATICS = (
    "Frame",
    "Workstation",
    "ServiceDeck",
    "Controls",
    "ComputeRack",
    "Fluidics",
    "WasteColumn",
    "TransferPort",
    "MachineServices",
    "GantryPortal",
    "Station_input",
    "Station_dispenser",
    "Station_mixer",
    "Station_characterizer",
    "Station_output",
    "HeaterShaker",
    "ColorimeterHousing",
    "ReaderLidCaddy",
    "InputStacker",
    "OutputStacker",
    "TipRack",
    "ReagentReservoir",
)

# Invariant D.  Each side of the gripper is a chain of bodies from the paddle
# that touches the payload up to the carrier that rides the cross-rail.  Every
# consecutive pair has to stay in contact, at every jaw width, or the paddle is
# hanging in the air.
JAW_MECHANISM: dict[str, tuple[str, ...]] = {
    "left": ("GripperPadLeft", "GripperPaddleLeft", "GripperFingerLeft", JAW_LEFT),
    "right": ("GripperPadRight", "GripperPaddleRight", "GripperFingerRight", JAW_RIGHT),
}
# The rail members the carriers ride.  Their combined X span bounds jaw travel.
JAW_RAIL_MEMBERS = ("GripperCrossRailFront", "GripperCrossRailRear", "GripperLeadScrew")
# Two bodies count as coupled when their world bounds overlap on every axis.
# A positive gap on any axis is a visible seam.
MECHANISM_GAP = 0.0

# Fluid volumes are not rigid obstacles.  A pipette tip that enters a reagent
# lane or a filled well is working, not colliding.
FLUID_PREFIXES = ("ReservoirChannel_",)
FLUID_MARKERS = ("_Liquid_",)
# The scene represents absent tips by collapsing a column to 2 % of its height.
# A collapsed column stands for geometry that is not there.
ABSENT_SCALE = 0.05

# Legitimate contact, allowed per pair, per frame window, and where useful per
# body pattern, each with a reason.  Nothing is listed here to suppress a
# number: each entry is a place where the authored physical story requires the
# two bodies to occupy the same space.  A contact outside these windows, or
# between other bodies of the same two assemblies, still fails.
ALLOWED_CONTACTS: tuple[dict[str, object], ...] = (
    {
        "mover": "DispenserHead",
        "static": "TipRack",
        "frames": (164, 186),
        "bodies": (("PipetteNozzle_*", "RackTip_*"), ("AttachedTip_*", "RackTip_*")),
        "reason": (
            "Mounting a disposable tip puts the nozzle inside the tip bore, and the "
            "racked tip and the mounted tip are the same physical body during the "
            "handover.  Contact with the rack frame itself is not allowed."
        ),
    },
    {
        "mover": "DispenserHead",
        "static": "TipRack",
        "frames": (342, 360),
        "bodies": (("PipetteNozzle_*", "RackTip_*"), ("AttachedTip_*", "RackTip_*")),
        "reason": "Second tip pickup; same nozzle-in-tip contact as the first.",
    },
    {
        "mover": PLATE,
        "static": "InputStacker",
        "frames": (1, 110),
        "reason": (
            "The input plate starts inside the storage tower and rides the shuttle out "
            "through it.  The tower is modelled as a closed shell standing in for a "
            "magazine, so the stored and hand-off positions are inside that shell by "
            "construction."
        ),
    },
    {
        "mover": PLATE,
        "static": "OutputStacker",
        "frames": (900, 960),
        "reason": (
            "The finished plate rides the output shuttle back into the storage tower. "
            "Same closed-shell simplification as the input tower."
        ),
    },
)


def _object(name: str) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise RuntimeError(f"Spatial validation needs missing object {name!r}")
    return obj


def _group_members(root: bpy.types.Object) -> list[bpy.types.Object]:
    return [root, *root.children_recursive]


def _is_fluid(name: str) -> bool:
    return name.startswith(FLUID_PREFIXES) or any(marker in name for marker in FLUID_MARKERS)


def _collision_members(root: bpy.types.Object) -> list[bpy.types.Object]:
    return [obj for obj in _group_members(root) if obj.type == "MESH" and not _is_fluid(obj.name)]


def _world_bounds(
    objects: Iterable[bpy.types.Object],
    depsgraph: bpy.types.Depsgraph,
) -> tuple[Vector, Vector] | None:
    minimum = Vector((float("inf"),) * 3)
    maximum = Vector((float("-inf"),) * 3)
    found = False
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        if evaluated.type not in {"MESH", "CURVE", "FONT", "SURFACE", "META"}:
            continue
        matrix = evaluated.matrix_world
        for corner in evaluated.bound_box:
            point = matrix @ Vector(corner)
            minimum.x = min(minimum.x, point.x)
            minimum.y = min(minimum.y, point.y)
            minimum.z = min(minimum.z, point.z)
            maximum.x = max(maximum.x, point.x)
            maximum.y = max(maximum.y, point.y)
            maximum.z = max(maximum.z, point.z)
            found = True
    return (minimum, maximum) if found else None


def _axis_gap(first: tuple[Vector, Vector], second: tuple[Vector, Vector]) -> Vector:
    """Per-axis separation between two boxes.  Zero where they overlap."""
    return Vector(
        (
            max(0.0, max(first[0][axis], second[0][axis]) - min(first[1][axis], second[1][axis]))
            for axis in range(3)
        )
    )


def _boxes_overlap(
    first: tuple[Vector, Vector], second: tuple[Vector, Vector], slack: float
) -> bool:
    return all(
        first[0][axis] - slack <= second[1][axis] and second[0][axis] - slack <= first[1][axis]
        for axis in range(3)
    )


class _Body:
    """A mesh cached in local space, eroded by the contact margin."""

    def __init__(self, obj: bpy.types.Object, depsgraph: bpy.types.Depsgraph) -> None:
        self.object = obj
        self.vertices: list[Vector] = []
        self.triangles: list[tuple[int, int, int]] = []
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        if mesh is None:
            evaluated.to_mesh_clear()
            return
        mesh_bm = bmesh.new()
        mesh_bm.from_mesh(mesh)
        bmesh.ops.triangulate(mesh_bm, faces=mesh_bm.faces[:])
        mesh_bm.verts.ensure_lookup_table()
        vertices = [vert.co.copy() for vert in mesh_bm.verts]
        triangles = [tuple(vert.index for vert in face.verts) for face in mesh_bm.faces]
        mesh_bm.free()
        evaluated.to_mesh_clear()
        if not triangles or not self._erode(vertices):
            return
        self.vertices = vertices
        self.triangles = triangles  # type: ignore[assignment]

    @staticmethod
    def _erode(vertices: list[Vector]) -> bool:
        """Shrink a body by the contact margin on every axis.

        Bodies thinner than the margin, such as engraved labels, carry no
        collision meaning and are dropped instead of being turned inside out.
        """
        minimum = Vector((min(vertex[axis] for vertex in vertices) for axis in range(3)))
        maximum = Vector((max(vertex[axis] for vertex in vertices) for axis in range(3)))
        center = (minimum + maximum) * 0.5
        factor = Vector((1.0, 1.0, 1.0))
        for axis in range(3):
            extent = maximum[axis] - minimum[axis]
            if extent <= 2.0 * CONTACT_MARGIN:
                return False
            factor[axis] = (extent - 2.0 * CONTACT_MARGIN) / extent
        for vertex in vertices:
            for axis in range(3):
                vertex[axis] = center[axis] + (vertex[axis] - center[axis]) * factor[axis]
        return True

    @property
    def usable(self) -> bool:
        return bool(self.triangles)


class _Assembly:
    """An object plus its descendants, tested as one rigid collection."""

    def __init__(self, root: bpy.types.Object, depsgraph: bpy.types.Depsgraph) -> None:
        self.name = root.name
        self.root = root
        self.bodies = [
            body
            for body in (_Body(obj, depsgraph) for obj in _collision_members(root))
            if body.usable
        ]

    def present(self, body: _Body, depsgraph: bpy.types.Depsgraph) -> bool:
        scale = body.object.evaluated_get(depsgraph).matrix_world.to_scale()
        return all(abs(component) >= ABSENT_SCALE for component in scale)

    def bounds(self, depsgraph: bpy.types.Depsgraph) -> tuple[Vector, Vector] | None:
        return _world_bounds(
            (body.object for body in self.bodies if self.present(body, depsgraph)), depsgraph
        )

    def tree(self, depsgraph: bpy.types.Depsgraph) -> tuple[BVHTree, list[tuple[int, str]]]:
        vertices: list[Vector] = []
        triangles: list[tuple[int, int, int]] = []
        spans: list[tuple[int, str]] = []
        for body in self.bodies:
            if not self.present(body, depsgraph):
                continue
            matrix = body.object.evaluated_get(depsgraph).matrix_world
            offset = len(vertices)
            vertices.extend(matrix @ vertex for vertex in body.vertices)
            triangles.extend(
                (first + offset, second + offset, third + offset)
                for first, second, third in body.triangles
            )
            spans.append((len(triangles), body.object.name))
        return BVHTree.FromPolygons(vertices, triangles, all_triangles=True), spans


def _span_name(spans: Sequence[tuple[int, str]], index: int) -> str:
    for end, name in spans:
        if index < end:
            return name
    return "?"


def _allowed(
    mover: str, static: str, frame: int, bodies: Sequence[tuple[str, str]]
) -> dict[str, object] | None:
    """Return the allowlist entry covering this contact, if any."""
    for entry in ALLOWED_CONTACTS:
        first, last = entry["frames"]  # type: ignore[misc]
        if entry["mover"] != mover or entry["static"] != static:
            continue
        if not first <= frame <= last:
            continue
        patterns = entry.get("bodies")
        if patterns is not None and not all(
            any(
                fnmatch(first_body, first_pattern) and fnmatch(second_body, second_pattern)
                for first_pattern, second_pattern in patterns  # type: ignore[union-attr]
            )
            for first_body, second_body in bodies
        ):
            continue
        return entry
    return None


def _jaw_state(left: bpy.types.Object, right: bpy.types.Object) -> str:
    width = (abs(left.location.x) + abs(right.location.x)) * 0.5
    if abs(width - JAW_PLATE_CLOSED) <= JAW_STATE_TOLERANCE:
        return "plate"
    if abs(width - JAW_LID_CLOSED) <= JAW_STATE_TOLERANCE:
        return "lid"
    if abs(width - JAW_OPEN) <= JAW_STATE_TOLERANCE:
        return "open"
    return "moving"


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def _carry_rigidity(
    scene: bpy.types.Scene, frames: Sequence[int]
) -> tuple[list[dict[str, object]], dict[str, list[int]]]:
    """Invariant A.  Sample every frame and attribute every payload move."""
    payloads = {PLATE: _object(PLATE), READER_LID: _object(READER_LID)}
    supports = {name: _object(name) for name in SUPPORTS}
    tracked = {**payloads, **supports}
    samples: dict[str, list[Vector]] = {name: [] for name in tracked}
    for frame in frames:
        scene.frame_set(frame)
        for name, obj in tracked.items():
            samples[name].append(obj.matrix_world.translation.copy())

    checks: list[dict[str, object]] = []
    ridden: dict[str, list[int]] = {PLATE: [], READER_LID: []}
    for payload in payloads:
        moving = 0
        unsupported = 0
        unsupported_frames: list[int] = []
        worst_gap = 0.0
        worst_frame = 0
        naive_slip = 0.0
        naive_worst = 0.0
        naive_worst_frame = 0
        naive_unfollowed = 0
        carriage_worst = 0.0
        carriage_worst_frame = 0
        for index in range(1, len(frames)):
            frame = frames[index]
            delta = samples[payload][index] - samples[payload][index - 1]
            if delta.length <= MOVE_EPSILON:
                continue
            moving += 1
            residuals = {
                name: (delta - (samples[name][index] - samples[name][index - 1])).length
                for name in supports
            }
            best = min(residuals, key=lambda name: residuals[name])
            if residuals[best] > RIGID_TOLERANCE:
                unsupported += 1
                if len(unsupported_frames) < 12:
                    unsupported_frames.append(frame)
                if residuals[best] > worst_gap:
                    worst_gap = residuals[best]
                    worst_frame = frame
            elif best == CARRIAGE:
                ridden[payload].append(frame)
                if residuals[CARRIAGE] > carriage_worst:
                    carriage_worst = residuals[CARRIAGE]
                    carriage_worst_frame = frame
            # The measurement Sean reported: payload against the carriage with
            # no notion of which body is carrying it.
            if residuals[CARRIAGE] > RIGID_TOLERANCE:
                naive_unfollowed += 1
                naive_slip += residuals[CARRIAGE]
                if residuals[CARRIAGE] > naive_worst:
                    naive_worst = residuals[CARRIAGE]
                    naive_worst_frame = frame
        checks.append(
            {
                "name": f"{payload} moves rigidly with a support",
                "passed": unsupported == 0 and moving > 0,
                "actual": {
                    "movingFrames": moving,
                    "unsupportedFrames": unsupported,
                    "unsupportedSample": unsupported_frames,
                    "worstSlipMm": _round(worst_gap * 1000.0),
                    "worstFrame": worst_frame,
                    "carriageOnlySlipFrames": naive_unfollowed,
                    "carriageOnlyWorstSlipMm": _round(naive_worst * 1000.0),
                    "carriageOnlyWorstFrame": naive_worst_frame,
                    "carriageOnlyTotalSlipMm": _round(naive_slip * 1000.0, 1),
                },
                "expected": {"unsupportedFrames": 0, "worstSlipMm": 0.0},
            }
        )
        checks.append(
            {
                "name": f"{payload} rides the carriage without slip",
                "passed": bool(ridden[payload]) and carriage_worst <= RIGID_TOLERANCE,
                "actual": {
                    "carriedFrames": len(ridden[payload]),
                    "worstSlipMm": _round(carriage_worst * 1000.0),
                    "worstFrame": carriage_worst_frame,
                },
                "expected": {"carriedFrames": "> 0", "worstSlipMm": "<= 0.1"},
            }
        )
    return checks, ridden


def _grip_contact(
    scene: bpy.types.Scene, frames: Sequence[int], ridden: dict[str, list[int]]
) -> list[dict[str, object]]:
    """Invariant B.  A closed jaw pair must be on the payload it holds."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    left = _object(JAW_LEFT)
    right = _object(JAW_RIGHT)
    payload_of = {"plate": _object(PLATE), "lid": _object(READER_LID)}
    groups = {state: _group_members(obj) for state, obj in payload_of.items()}
    jaws = {"left": _group_members(left), "right": _group_members(right)}

    worst: dict[str, tuple[float, int]] = {state: (0.0, 0) for state in payload_of}
    held: dict[str, int] = {state: 0 for state in payload_of}
    straddle_failures: dict[str, int] = {state: 0 for state in payload_of}
    open_carry: dict[str, list[int]] = {PLATE: [], READER_LID: []}
    state_by_frame: dict[int, str] = {}

    for frame in frames:
        scene.frame_set(frame)
        depsgraph.update()
        state = _jaw_state(left, right)
        state_by_frame[frame] = state
        if state not in payload_of:
            continue
        payload_bounds = _world_bounds(groups[state], depsgraph)
        if payload_bounds is None:
            continue
        held[state] += 1
        center = (payload_bounds[0] + payload_bounds[1]) * 0.5
        for side, members in jaws.items():
            jaw_bounds = _world_bounds(members, depsgraph)
            if jaw_bounds is None:
                continue
            gap = max(_axis_gap(jaw_bounds, payload_bounds))
            if gap > worst[state][0]:
                worst[state] = (gap, frame)
            jaw_center = (jaw_bounds[0].x + jaw_bounds[1].x) * 0.5
            outside = jaw_center < center.x if side == "left" else jaw_center > center.x
            if not outside:
                straddle_failures[state] += 1

    for payload, name in ((PLATE, "plate"), (READER_LID, "lid")):
        for frame in ridden[payload]:
            if state_by_frame.get(frame) != name:
                open_carry[payload].append(frame)

    checks: list[dict[str, object]] = []
    for state, label in (("plate", PLATE), ("lid", READER_LID)):
        gap, frame = worst[state]
        checks.append(
            {
                "name": f"jaws close on {label}",
                "passed": (
                    held[state] > 0 and gap <= GRIP_SEPARATION and straddle_failures[state] == 0
                ),
                "actual": {
                    "grippedFrames": held[state],
                    "worstSeparationMm": _round(gap * 1000.0, 2),
                    "worstFrame": frame,
                    "jawOnWrongSideFrames": straddle_failures[state],
                },
                "expected": {
                    "grippedFrames": "> 0",
                    "worstSeparationMm": f"<= {GRIP_SEPARATION * 1000.0}",
                },
            }
        )
    for payload in (PLATE, READER_LID):
        checks.append(
            {
                "name": f"{payload} only rides the carriage in a closed grip",
                "passed": not open_carry[payload],
                "actual": {
                    "carriedFrames": len(ridden[payload]),
                    "openGripFrames": len(open_carry[payload]),
                    "firstOpenGripFrame": open_carry[payload][0] if open_carry[payload] else 0,
                },
                "expected": {"openGripFrames": 0},
            }
        )
    return checks


def _jaw_mechanism(scene: bpy.types.Scene, frames: Sequence[int]) -> list[dict[str, object]]:
    """Invariant D.  The paddle reaches the carriage through real geometry.

    ``_carry_rigidity`` and ``_grip_contact`` both pass for a gripper whose
    paddles are correctly parented to the carriage and correctly placed on the
    payload while nothing at all spans the distance between the two.  That is
    the state this scene shipped in, and it read as two bars floating beside
    the arm.  This walks the mechanism instead: paddle, finger, carrier, rail.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    rail = [_object(name) for name in JAW_RAIL_MEMBERS]
    checks: list[dict[str, object]] = []
    for side, chain in JAW_MECHANISM.items():
        members = {name: _object(name) for name in chain}
        links = list(zip(chain, chain[1:], strict=False))
        worst_link: dict[str, tuple[float, int]] = {f"{a} - {b}": (0.0, 0) for a, b in links}
        worst_rail = (0.0, 0)
        worst_overrun = (-1.0, 0)
        widths: set[float] = set()
        for frame in frames:
            scene.frame_set(frame)
            depsgraph.update()
            bounds = {name: _world_bounds([obj], depsgraph) for name, obj in members.items()}
            if any(value is None for value in bounds.values()):
                continue
            widths.add(round(abs(float(members[chain[-1]].location.x)), 5))
            for first, second in links:
                gap = max(_axis_gap(bounds[first], bounds[second]))  # type: ignore[arg-type]
                key = f"{first} - {second}"
                if gap > worst_link[key][0]:
                    worst_link[key] = (gap, frame)
            rail_bounds = _world_bounds(rail, depsgraph)
            carrier_bounds = bounds[chain[-1]]
            if rail_bounds is None or carrier_bounds is None:
                continue
            gap = max(_axis_gap(carrier_bounds, rail_bounds))
            if gap > worst_rail[0]:
                worst_rail = (gap, frame)
            overrun = max(
                rail_bounds[0].x - carrier_bounds[0].x,
                carrier_bounds[1].x - rail_bounds[1].x,
            )
            if overrun > worst_overrun[0]:
                worst_overrun = (overrun, frame)

        coupled = max(value[0] for value in worst_link.values())
        checks.append(
            {
                "name": f"{side} jaw stays coupled to the gripper mechanism",
                "passed": coupled <= MECHANISM_GAP,
                "actual": {
                    "authoredWidths": len(widths),
                    "worstGapMm": _round(coupled * 1000.0, 3),
                    "links": {
                        key: {"gapMm": _round(value[0] * 1000.0, 3), "frame": value[1]}
                        for key, value in worst_link.items()
                    },
                },
                "expected": {"worstGapMm": 0.0},
            }
        )
        checks.append(
            {
                "name": f"{side} jaw carrier stays on the cross-rail",
                "passed": worst_rail[0] <= MECHANISM_GAP and worst_overrun[0] <= 0.0,
                "actual": {
                    "worstRailGapMm": _round(worst_rail[0] * 1000.0, 3),
                    "worstRailGapFrame": worst_rail[1],
                    "worstOverrunMm": _round(worst_overrun[0] * 1000.0, 3),
                    "worstOverrunFrame": worst_overrun[1],
                },
                "expected": {"worstRailGapMm": 0.0, "worstOverrunMm": "<= 0"},
            }
        )
    return checks


def _interpenetration(scene: bpy.types.Scene, frames: Sequence[int]) -> list[dict[str, object]]:
    """Invariant C.  Movers may touch fixed bodies but never enter them."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    scene.frame_set(frames[0])
    depsgraph.update()
    movers = [_Assembly(_object(name), depsgraph) for name in MOVERS]
    statics = [_Assembly(_object(name), depsgraph) for name in STATICS]

    violations: dict[tuple[str, str], dict[str, object]] = {}
    allowed_hits: dict[tuple[str, str], int] = {}
    for frame in frames:
        scene.frame_set(frame)
        depsgraph.update()
        mover_bounds = {mover.name: mover.bounds(depsgraph) for mover in movers}
        static_bounds = {static.name: static.bounds(depsgraph) for static in statics}
        trees: dict[str, tuple[BVHTree, list[tuple[int, str]]]] = {}
        for mover in movers:
            first = mover_bounds[mover.name]
            if first is None:
                continue
            for static in statics:
                second = static_bounds[static.name]
                if second is None or not _boxes_overlap(first, second, 0.0):
                    continue
                for assembly in (mover, static):
                    if assembly.name not in trees:
                        trees[assembly.name] = assembly.tree(depsgraph)
                pairs = trees[mover.name][0].overlap(trees[static.name][0])
                if not pairs:
                    continue
                key = (mover.name, static.name)
                touching = sorted(
                    {
                        (
                            _span_name(trees[mover.name][1], first_index),
                            _span_name(trees[static.name][1], second_index),
                        )
                        for first_index, second_index in pairs
                    }
                )
                if _allowed(mover.name, static.name, frame, touching) is not None:
                    allowed_hits[key] = allowed_hits.get(key, 0) + 1
                    continue
                record = violations.setdefault(
                    key,
                    {
                        "mover": mover.name,
                        "static": static.name,
                        "frames": 0,
                        "sampleFrames": [],
                        "worstFacePairs": 0,
                        "worstFrame": 0,
                        "bodies": [],
                    },
                )
                record["frames"] = int(record["frames"]) + 1  # type: ignore[arg-type]
                if len(record["sampleFrames"]) < 12:  # type: ignore[arg-type]
                    record["sampleFrames"].append(frame)  # type: ignore[attr-defined]
                if len(pairs) > int(record["worstFacePairs"]):  # type: ignore[arg-type]
                    record["worstFacePairs"] = len(pairs)
                    record["worstFrame"] = frame
                    record["bodies"] = touching[:8]

    ordered = sorted(violations.values(), key=lambda record: -int(record["worstFacePairs"]))
    checks = [
        {
            "name": "movers stay clear of fixed bodies",
            "passed": not ordered,
            "actual": {
                "sampledFrames": len(frames),
                "violatingPairs": len(ordered),
                "detail": ordered,
            },
            "expected": {"violatingPairs": 0},
        }
    ]
    exercised = [
        {
            "pair": f"{entry['mover']} x {entry['static']}",
            "frames": entry["frames"],
            "sampledHits": allowed_hits.get(
                (str(entry["mover"]), str(entry["static"])),
                0,
            ),
            "reason": entry["reason"],
        }
        for entry in ALLOWED_CONTACTS
    ]
    checks.append(
        {
            "name": "documented contact allowlist stays exercised",
            "passed": all(int(entry["sampledHits"]) > 0 for entry in exercised),  # type: ignore[arg-type]
            "actual": exercised,
            "expected": "every allowed contact occurs and no other pair touches",
        }
    )
    return checks


def spatial_checks(*, step: int = 2, frame_end: int | None = None) -> list[dict[str, object]]:
    """Measure the three spatial invariants and return their check records."""
    scene = bpy.context.scene
    original = scene.frame_current
    start = scene.frame_start
    end = frame_end if frame_end is not None else scene.frame_end
    every_frame = list(range(start, end + 1))
    sampled = list(range(start, end + 1, max(1, step)))
    if sampled[-1] != end:
        sampled.append(end)

    checks, ridden = _carry_rigidity(scene, every_frame)
    checks.extend(_grip_contact(scene, every_frame, ridden))
    checks.extend(_jaw_mechanism(scene, every_frame))
    checks.extend(_interpenetration(scene, sampled))
    scene.frame_set(original)
    return checks


def validate_spatial(*, step: int = 2, frame_end: int | None = None) -> list[dict[str, object]]:
    """Check the three spatial invariants and raise on any failure."""
    checks = spatial_checks(step=step, frame_end=frame_end)
    failures = [check for check in checks if not check["passed"]]
    if failures:
        raise RuntimeError(
            "Digital-twin spatial validation failed:\n- "
            + "\n- ".join(
                f"{check['name']}: expected {check['expected']!r}, got {check['actual']!r}"
                for check in failures
            )
        )
    return checks


def main(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", type=int, default=2, help="frame step for the overlap sweep")
    parser.add_argument("--json", default="", help="write the full report to this path")
    options = parser.parse_args(argv)
    checks = spatial_checks(step=options.step)
    for check in checks:
        print(f"[{'ok' if check['passed'] else 'FAIL'}] {check['name']}")
        print(f"        {json.dumps(check['actual'])}")
    if options.json:
        with open(options.json, "w", encoding="utf-8") as stream:
            json.dump(checks, stream, indent=2)
    return 0 if all(check["passed"] for check in checks) else 1


if __name__ == "__main__":
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    sys.exit(main(arguments))
