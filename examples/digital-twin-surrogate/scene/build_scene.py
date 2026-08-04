"""Build the OpenSDL Flex-class digital-twin reference cell.

This is an original, full-scale reconstruction based on published dimensions and
operating behavior for real laboratory automation equipment.  It intentionally
does not vendor manufacturer CAD or present itself as engineering evidence.

Run from the repository root::

    blender -b -P examples/digital-twin-surrogate/scene/build_scene.py

Useful render modes are accepted after ``--``::

    blender -b -P examples/digital-twin-surrogate/scene/build_scene.py -- \
      --render-still --engine cycles --samples 96
    blender -b -P examples/digital-twin-surrogate/scene/build_scene.py -- \
      --render-animation --engine cycles --samples 48
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TypedDict

import bpy
from mathutils import Vector


HERE = Path(__file__).resolve().parent
ASSET_DIR = HERE / "assets"
RENDER_DIR = HERE / "renders"
ASSET_DIR.mkdir(parents=True, exist_ok=True)
RENDER_DIR.mkdir(parents=True, exist_ok=True)

BLEND_PATH = ASSET_DIR / "surrogate-cell.blend"
GLB_PATH = ASSET_DIR / "surrogate-cell.glb"
PREVIEW_PATH = ASSET_DIR / "preview.png"
VIDEO_PATH = RENDER_DIR / "opensdl-surrogate-cell.mp4"
FRAME_DIR = RENDER_DIR / "frames"
INVENTORY_PATH = ASSET_DIR / "node-inventory.json"
VALIDATION_PATH = ASSET_DIR / "motion-validation.json"
CAMERA_RIG_PATH = ASSET_DIR / "camera-poses.json"

FPS = 24
FRAME_END = 960
# The transport plane.  Every seating height in this machine is set by the
# gantry's reach envelope, not by a person's elbows: DECK_Z is where the mover
# can put a plate down, and everything else composes against it.  BENCH_Z is the
# lower module mounting plane the two tall plate hotels bolt to, so their
# presentation nests land level with the process deck.
BENCH_Z = 0.92
DECK_Z = 1.135
SLOT_PITCH_X = 0.164
SLOT_PITCH_Y = 0.107

# The plant space.  This is not a laboratory room with automation in it: it is
# the volume a machine is installed in.  Sealed resin floor, plain painted
# panel walls, an exposed services ceiling carrying linear battens, a cable tray
# and a duct run, and one service door.  Nothing here serves an occupant.
ROOM_WALL_Y = 1.05
ROOM_DEPTH = 5.6
ROOM_FRONT_Y = ROOM_WALL_Y - ROOM_DEPTH
ROOM_HALF_X = 3.9
ROOM_CEILING_Z = 3.10
ROOM_BUILD_UP = 0.14
SKIRTING_HEIGHT = 0.100
# The service door is in the left wall, clear of the machine footprint.
DOOR_WIDTH = 1.100
DOOR_HEIGHT = 2.100
DOOR_CENTER_Y = -2.60

# The five workflow stations are positions along one transport axis.  Every
# station owns a world X offset and every slot inside a station is placed
# relative to that offset, so a station can be re-spaced without editing what
# stands on it.
STATION_ORDER = ("input", "dispense", "mix", "characterize", "output")
STATION_PITCH = 0.78
STATION_X = {name: (index - 2) * STATION_PITCH for index, name in enumerate(STATION_ORDER)}
# Two working rows per station, one deck pitch apart.  The rows are packed at
# machine spacing: there is no walkway between them and nothing is set back for
# a hand to reach in.
ROW_FRONT = -SLOT_PITCH_Y / 2.0
ROW_BACK = SLOT_PITCH_Y / 2.0
# A plate hotel stands at the back of its station and presents labware this far
# in front of its own root.
HOTEL_PRESENT_Y = 0.164

# Slot table: id -> (station, x offset inside the station, y).  Slot ids say
# what the slot is for; the station column is what places them on the deck.
SLOT_TABLE: dict[str, tuple[str, float, float]] = {
    "input-handoff": ("input", 0.0, ROW_FRONT),
    "input-hotel": ("input", 0.0, ROW_FRONT + HOTEL_PRESENT_Y),
    "reservoir": ("dispense", -SLOT_PITCH_X, ROW_BACK),
    "tips": ("dispense", 0.0, ROW_BACK),
    "tip-waste": ("dispense", SLOT_PITCH_X, ROW_BACK),
    "stage": ("dispense", 0.0, ROW_FRONT),
    "mixer": ("mix", 0.0, ROW_FRONT),
    "door-dock": ("characterize", 0.0, ROW_BACK),
    "reader": ("characterize", 0.0, ROW_FRONT),
    "output-handoff": ("output", 0.0, ROW_FRONT),
    "output-hotel": ("output", 0.0, ROW_FRONT + HOTEL_PRESENT_Y),
}
# Slots that are a seat on a station deck.  The two hand-off slots and the two
# hotel roots belong to the hotels, which bring their own presentation surface,
# so no deck plate is built under them.
DECK_SLOTS = ("reservoir", "tips", "tip-waste", "stage", "mixer", "door-dock", "reader")
DOOR_DOCK_SLOT = "door-dock"

# The machine frame.  40/45-series aluminium extrusion, four full-height corner
# towers and two rear intermediate uprights, standing on levelling feet through
# anchor plates bolted to the floor.  The frame is the machine: the transport
# runway lands straight on the end towers, the process deck is carried on its
# cross members, and every service bay below is a volume inside it.
PROFILE = 0.045
FRAME_HALF_LENGTH = 1.80
FRAME_FRONT_Y = -0.560
FRAME_REAR_Y = 0.560
FRAME_TOP_Z = 2.200
FRAME_FOOT_HEIGHT = 0.062
FRAME_POST_HALF = PROFILE / 2.0
FRAME_POST_X = (
    -(FRAME_HALF_LENGTH - FRAME_POST_HALF),
    -0.600,
    0.600,
    FRAME_HALF_LENGTH - FRAME_POST_HALF,
)
FRAME_CORNER_X = (FRAME_POST_X[0], FRAME_POST_X[3])
FRAME_POST_Y = (FRAME_FRONT_Y + FRAME_POST_HALF, FRAME_REAR_Y - FRAME_POST_HALF)
# Rail planes.  Base tie at the feet, the service deck, the hotel mounting
# plane, the deck carrier, and the top tie the runway and the trunking hang off.
FRAME_BASE_Z = FRAME_FOOT_HEIGHT + FRAME_POST_HALF
FRAME_SERVICE_Z = 0.720
SERVICE_TOP_Z = FRAME_SERVICE_Z + FRAME_POST_HALF + 0.008
DECK_THICKNESS = 0.018
# The hotel mounting plane is derived downward from the hotel base height, so
# the presentation nest lands level with the process deck by construction.
FRAME_MOUNT_Z = BENCH_Z - 0.008 - FRAME_POST_HALF
FRAME_DECK_RAIL_Z = DECK_Z - DECK_THICKNESS - FRAME_POST_HALF
FRAME_TOP_RAIL_Z = FRAME_TOP_Z - FRAME_POST_HALF

# The process deck: one machined tooling plate carried on the deck rails.  It
# spans the three in-line process stations only; the two labware hotels stand
# outside it on the mounting plane, which is what puts the input at one end of
# the machine and the output at the other.
DECK_HALF_LENGTH = 1.160
DECK_FRONT_Y = -0.205
DECK_REAR_Y = 0.300
DECK_CARRIER_X = (-1.080, -0.400, 0.0, 0.400, 1.080)
# The work-light bars under the top tie.  A machine this size lights its own
# process; leaving that to the room is what makes a render look like a set.
WORKLIGHT_RUNS = ((-0.330, 2.110), (0.330, 2.110))
# The service-bay strip under the deck lip.  The half of this machine that says
# it is self-driving lives in the deck's shadow, so the deck lights it.
UNDERDECK_RUN = (-0.238, 1.072)
# Vertical strip lighting on the inner face of the front uprights, aimed into
# the service bays.  Real workcells light their own bays; without it the half of
# this machine that makes it self-driving sits in the deck's shadow.
BAY_STRIP_X = (-1.7775, -1.20, 1.20, 1.7775)
BAY_STRIP_Y = -0.505
BAY_STRIP_Z = (0.190, 0.820)

# Service bays, packed into the volume under the deck.  Every one of them faces
# forward, because the front of this machine is where its services are, not
# where an operator stands.
BAY_FACE_Y = -0.300
BAY_FLOOR_Z = FRAME_BASE_Z + FRAME_POST_HALF
CABINET_X = (-1.755, -1.115)
RACK_X = (1.115, 1.755)
WASTE_X = -0.616
FLUIDICS_X = (-0.230, 0.560)
CONSUMABLE_X = (0.660, 1.020)

# The transport.  There is exactly one mover.  It rides a bridge that rides two
# runway beams landed directly on the frame's end towers, so the transport is
# part of the frame rather than four posts bolted to a bench.  The mover carries
# no tooling of its own: a head couples to it, and the head it is not using
# waits in that head's own dock.  One carriage cannot collide with itself.
MOVER_HALF_SPAN = FRAME_HALF_LENGTH - PROFILE - 0.020
MOVER_RAIL_Z = 1.618
MOVER_BRIDGE_Z = 1.565
MOVER_RAIL_POST_Y = 0.285
# Where the mover waits at the end of the cycle.
MOVER_PARK_X = STATION_X["mix"] + STATION_PITCH / 2.0

# Physical seating planes.  The plate root is at the vertical center of its
# 14.3 mm envelope, so every station defines the actual supporting surface
# rather than using one visually convenient Z value for the whole deck.
PLATE_LENGTH = 0.12776
PLATE_DEPTH = 0.08548
PLATE_HEIGHT = 0.0143
PLATE_HALF_HEIGHT = PLATE_HEIGHT / 2.0
DECK_SLOT_TOP_Z = DECK_Z + 0.0075
DIRECT_DECK_PLATE_Z = DECK_SLOT_TOP_Z + PLATE_HALF_HEIGHT
HOTEL_NEST_TOP_Z = BENCH_Z + 0.228 + 0.011 + 0.0025
HOTEL_PLATE_Z = HOTEL_NEST_TOP_Z + PLATE_HALF_HEIGHT
MIXER_PLATFORM_TOP_Z = DECK_Z + 0.008 + 0.069 + 0.007
MIXER_PLATE_Z = MIXER_PLATFORM_TOP_Z + PLATE_HALF_HEIGHT

# The Heater-Shaker clamp closes on the two short ends of the plate, clear of
# the long sides the gripper paddles occupy.  It holds the plate edge at plate
# height, so the plate still lifts straight out and opening only has to break
# contact.  Deck rows are 107 mm apart, so the open bar also has to stay out of
# the next row's work envelope.
MIXER_LATCH_THICKNESS = 0.006
MIXER_LATCH_CLEARANCE = 0.0008
MIXER_LATCH_CLOSED_Y = PLATE_DEPTH / 2.0 + MIXER_LATCH_CLEARANCE + MIXER_LATCH_THICKNESS / 2.0
MIXER_LATCH_OPEN_Y = MIXER_LATCH_CLOSED_Y + 0.004
MIXER_LATCH_OPEN_ANGLE = math.radians(12.0)

# Published reader dimensions describe an assembled envelope of roughly
# 57-60 mm.  The detector body is 18.5 mm high; the plate and removable lid
# occupy the remainder without stacking two full-height housings.
CHARACTERIZER_ROOT_Z = DECK_Z + 0.008
CHARACTERIZER_DECK_TOP_Z = CHARACTERIZER_ROOT_Z + 0.0205
CHARACTERIZER_PLATE_Z = CHARACTERIZER_DECK_TOP_Z + PLATE_HALF_HEIGHT
DOOR_CLOSED_Z = CHARACTERIZER_ROOT_Z + 0.0350
# The lid parks on a caddy rather than flat on the deck: the caddy lifts the
# grip line above the neighbouring module tops, so the paddles never descend
# past them when docking the lid.
DOOR_DOCK_HEIGHT = 0.030
DOOR_DOCK_Z = DECK_SLOT_TOP_Z + DOOR_DOCK_HEIGHT
DOOR_HEIGHT_M = 0.0220
DOOR_GRIP_Z = 0.0140
DOOR_GRIP_DEPTH = 0.008
DOOR_GRIP_OUTER_X = 0.0775

# Pipette tips.  The rack presents full-length tips standing proud of its
# insert, so a mounted tip occupies exactly the volume the rack tip vacated
# instead of reaching down through the rack body.
TIP_LENGTH = 0.046
TIP_RADIUS = 0.00155
TIP_RACK_ROOT_Z = DECK_Z + 0.008
TIP_RACK_INSERT_TOP_Z = TIP_RACK_ROOT_Z + 0.020
TIP_RACK_STANDOFF = 0.0015
TIP_TOP_Z = TIP_RACK_INSERT_TOP_Z + TIP_RACK_STANDOFF + TIP_LENGTH
# The mounted tip hangs from the nozzle column, whose top sits at this height
# in PipetteHead space; the nozzle enters the tip by 3 mm when mounting.
NOZZLE_TIP_TOP_LOCAL_Z = 1.286
# The nozzle column hangs 6 mm in front of the carriage origin.  Commanded
# positions are tool-point positions, so the gantry compensates for the offset
# and the tips land on the target rather than 6 mm in front of it.
NOZZLE_COLUMN_Y = -0.006
TIP_PICK_Z = TIP_TOP_Z - NOZZLE_TIP_TOP_LOCAL_Z

# Reagent reservoir.  Lanes are open at the top: the white polymer strips are
# the dividers between lanes, not lids over them.
RESERVOIR_ROOT_Z = DECK_Z + 0.008
RESERVOIR_SKIRT_TOP_Z = RESERVOIR_ROOT_Z + 0.021
RESERVOIR_LANE_PITCH = 0.009
RESERVOIR_LANE_WIDTH = 0.0073
RESERVOIR_ASPIRATE_Z = (RESERVOIR_SKIRT_TOP_Z + 0.002) - (NOZZLE_TIP_TOP_LOCAL_Z - TIP_LENGTH)

# The tool changer.  Every head presents the same interface, so the mover does
# not know or care which one it is holding.  Reading down from the mover:
# the changer's master plate on the mover's underside, an open gap that makes
# the joint visible, then the head's own collar and the head below it.
HEAD_TOP_Z = 1.3575
HEAD_COLLAR_HEIGHT = 0.012
HEAD_COLLAR_LENGTH = 0.104
# The collar is deeper than it is wide on purpose.  A head drops onto its dock
# straight down, so the only feature the cradle may touch is one that is proud
# of every body below it along the whole descent.  Nothing under the collar
# reaches past HEAD_BODY_HALF_DEPTH, so the cradle takes the collar there.
HEAD_COLLAR_DEPTH = 0.116
HEAD_BODY_HALF_DEPTH = 0.038
HEAD_COLLAR_TOP_Z = HEAD_TOP_Z + HEAD_COLLAR_HEIGHT
COUPLER_GAP = 0.016
COUPLER_PLATE_HEIGHT = 0.012
COUPLER_BOSS_RADIUS = 0.017
COUPLER_PIN_RADIUS = 0.005
COUPLER_PIN_X = 0.034
# The boss reaches through the collar and into the head body; the guide pins
# stop just inside the head's top face.  Both are what "coupled" means.
COUPLER_BOSS_BOTTOM_Z = HEAD_TOP_Z - 0.008
COUPLER_PIN_BOTTOM_Z = HEAD_TOP_Z - 0.004
# The mover.  One carriage on the bridge, ending in the changer's master plate.
MOVER_BOTTOM_Z = HEAD_COLLAR_TOP_Z + COUPLER_GAP
COUPLER_PLATE_Z = MOVER_BOTTOM_Z + COUPLER_PLATE_HEIGHT / 2.0
MOVER_CARRIAGE_BOTTOM_Z = MOVER_BOTTOM_Z + COUPLER_PLATE_HEIGHT
MOVER_CARRIAGE_TOP_Z = 1.5625
MOVER_CARRIAGE_HEIGHT = MOVER_CARRIAGE_TOP_Z - MOVER_CARRIAGE_BOTTOM_Z
MOVER_CARRIAGE_LOCAL_Z = MOVER_CARRIAGE_BOTTOM_Z + MOVER_CARRIAGE_HEIGHT / 2.0

# The head docks.  An idle head hangs by its collar on a two-armed cradle that
# reaches in from posts standing clear of the head's widest body.  The mover
# lowers a head onto the arms, unlocks, and rises away; the head stays.
# HEAD_DOCK_Z is the mover height at which a head is seated, so the arm face
# and the docked collar are the same number by construction.
# Deep enough that a head crossing the dock row at travel height passes over
# the cradle arms instead of through them.  The gripper head's cross-rails hang
# 69 mm below its collar, so a shallow dock is one the head shears off on the
# way in; that is what the first build of this dock did.
HEAD_DOCK_Z = -0.112
HEAD_DOCK_ARM_TOP_Z = HEAD_TOP_Z + HEAD_DOCK_Z
HEAD_DOCK_ARM_HEIGHT = 0.010
HEAD_DOCK_ARM_Y = HEAD_BODY_HALF_DEPTH + 0.014
HEAD_DOCK_ARM_DEPTH = 0.020
HEAD_DOCK_ARM_LENGTH = 0.120
HEAD_DOCK_POST_X = 0.054
HEAD_DOCK_Y = ROW_BACK
# Docked left of the mix station and right of it.  The order matters: a head on
# the coupler never travels over the other head's dock, because each dock lies
# on the far side of the machine from the work the other head does.
HEAD_DOCK_X = {"Pipette": -0.30, "Gripper": 0.30}

# The gripper head.  PLATE_GRIP_LOCAL_Z is the height of the grip line in the
# mover's own space: a payload held by the jaws sits at
# (mover x, bridge y, mover z + PLATE_GRIP_LOCAL_Z).  Every carried
# keyframe is derived from that relation instead of being authored twice.
PLATE_GRIP_LOCAL_Z = 1.267
# The gripper is a mechanism, not two bars.  Reading down from the collar:
# a socket block, the actuator housing that drives the jaws, a cross-rail
# spanning the whole jaw travel, a finger carrier per side that rides that
# rail, a finger, and the paddle that actually touches the payload.  Each
# stage is authored flush with the one above it, so the chain is continuous
# from the coupler to the paddle at every jaw width.
GRIPPER_WRIST_HEIGHT = 0.032
GRIPPER_WRIST_Z = HEAD_TOP_Z - GRIPPER_WRIST_HEIGHT / 2.0
GRIPPER_HOUSING_HEIGHT = 0.025
GRIPPER_HOUSING_Z = GRIPPER_WRIST_Z - (GRIPPER_WRIST_HEIGHT + GRIPPER_HOUSING_HEIGHT) / 2.0
GRIPPER_RAIL_HEIGHT = 0.012
GRIPPER_RAIL_Z = GRIPPER_HOUSING_Z - (GRIPPER_HOUSING_HEIGHT + GRIPPER_RAIL_HEIGHT) / 2.0
# The paddles hang from the grip line and stop level with the plate skirt, so
# they never reach below the surface the plate is picked from.
JAW_DROP_BELOW_GRIP = 0.0065
JAW_THICKNESS = 0.016
JAW_PADDLE_HEIGHT = 0.024
JAW_PADDLE_LOCAL_Z = PLATE_GRIP_LOCAL_Z - JAW_DROP_BELOW_GRIP + JAW_PADDLE_HEIGHT / 2.0
JAW_PAD_THICKNESS = 0.006
JAW_PAD_HEIGHT = 0.018
JAW_CARRIER_HEIGHT = 0.020
JAW_CARRIER_DEPTH = 0.056
JAW_CARRIER_THICKNESS = 0.030
# The carrier straddles the cross-rail, so it is centred on the rail.
JAW_CARRIER_LOCAL_Z = GRIPPER_RAIL_Z
JAW_FINGER_HEIGHT = 0.019
JAW_FINGER_THICKNESS = 0.016
# The finger bridges the gap between the paddle top and the carrier bottom and
# overlaps both, so no authored jaw width can open a visible seam.
JAW_FINGER_LOCAL_Z = (
    JAW_PADDLE_LOCAL_Z + JAW_PADDLE_HEIGHT / 2.0 + JAW_CARRIER_LOCAL_Z - JAW_CARRIER_HEIGHT / 2.0
) / 2.0
# Widest authored jaw width plus half a carrier: the rail has to be at least
# this long or a carrier would run off its own guide.
JAW_TRAVEL_LIMIT = 0.092
GRIPPER_RAIL_LENGTH = 2.0 * (JAW_TRAVEL_LIMIT + JAW_CARRIER_THICKNESS / 2.0 + 0.010)
GRIPPER_HOUSING_LENGTH = GRIPPER_RAIL_LENGTH - 0.012
# The reader lid is gripped by its side features, which sit
# DOOR_GRIP_Z above the lid root.
DOOR_GRIP_LOCAL_Z = PLATE_GRIP_LOCAL_Z - DOOR_GRIP_Z

# The authored timeline, as one ordered table of named marks and the gap in
# frames from the previous mark.  Every keyframe in ``animate_scene``, every
# checkpoint in ``validate_motion``, every window in ``check_scene`` and every
# range published in ``../twin.yaml`` reads a name out of ``BEAT``, so the seven
# workflow phases and the two head changes are re-timed in exactly one place.
#
# The two head changes are the two long gaps.  A change is a real beat - travel
# to the dock, seat, unlock, rise away, cross to the other dock, lower, lock,
# rise - and it needs about sixty frames to read as a mechanism rather than as a
# cut.  Everything else was compressed to pay for them inside the same 960.
_BEATS: tuple[tuple[str, int], ...] = (
    ("start", 1),
    # Phase 1: stage the reader door, then transfer the input plate to dispense.
    ("door_settle", 16),
    ("door_down", 7),
    ("door_grip", 5),
    ("door_lift", 7),
    ("door_cross", 8),
    ("door_seat", 7),
    ("door_release", 5),
    ("door_clear", 7),
    ("door_row_front", 8),
    ("plate_approach", 18),
    ("plate_down", 7),
    ("plate_grip", 5),
    ("plate_lift", 7),
    ("plate_cross", 14),
    ("plate_seat", 7),
    ("plate_release", 5),
    ("plate_clear", 7),
    ("transfer_in_end", 9),
    # Head change A: gripper head to its dock, pipetting head onto the mover.
    ("swap_a_over_gripper", 10),
    ("swap_a_row_back", 6),
    ("swap_a_seat", 7),
    ("swap_a_unlock", 4),
    ("swap_a_lift", 6),
    ("swap_a_traverse", 9),
    ("swap_a_down", 7),
    ("swap_a_lock", 4),
    ("swap_a_ready", 5),
    # Phase 2: two 8-channel tip, aspirate, dispense and tip-drop passes.
    ("tips_a_approach", 6),
    ("tips_a_down", 8),
    ("tips_a_dwell", 3),
    ("tips_a_taken", 3),
    ("tips_a_up", 7),
    ("res_a_approach", 6),
    ("res_a_down", 7),
    ("res_a_hold", 3),
    ("res_a_up", 5),
    ("fill_a_start", 6),
    ("fill_a_end", 96),
    ("waste_a_approach", 6),
    ("waste_a_down", 6),
    ("waste_a_drop", 3),
    ("waste_a_up", 5),
    ("tips_b_approach", 6),
    ("tips_b_down", 8),
    ("tips_b_dwell", 3),
    ("tips_b_taken", 3),
    ("tips_b_up", 7),
    ("res_b_approach", 6),
    ("res_b_down", 7),
    ("res_b_hold", 3),
    ("res_b_up", 5),
    ("fill_b_start", 6),
    ("fill_b_end", 96),
    ("waste_b_approach", 6),
    ("waste_b_down", 6),
    ("waste_b_drop", 3),
    ("waste_b_up", 5),
    ("dispense_end", 4),
    # Head change B: pipetting head to its dock, gripper head onto the mover.
    ("swap_b_over_pipette", 10),
    ("swap_b_seat", 7),
    ("swap_b_unlock", 4),
    ("swap_b_lift", 6),
    ("swap_b_traverse", 9),
    ("swap_b_down", 7),
    ("swap_b_lock", 4),
    ("swap_b_lift2", 6),
    ("swap_b_row_front", 7),
    # Phase 3: transfer dispense -> mix.
    ("mix_approach", 14),
    ("mix_pick_down", 6),
    ("mix_pick_grip", 5),
    ("mix_pick_lift", 6),
    ("mix_cross", 12),
    ("mix_place_down", 6),
    ("mix_place_release", 5),
    ("mix_place_clear", 6),
    # Phase 4: orbital mixing.
    ("mix_clamp_closed", 6),
    ("mix_orbit_end", 36),
    ("mix_clamp_open", 6),
    ("mix_settle", 4),
    # Phase 5: transfer mix -> characterize.
    ("read_pick_down", 6),
    ("read_pick_grip", 5),
    ("read_pick_lift", 6),
    ("read_cross", 12),
    ("read_place_down", 6),
    ("read_place_release", 5),
    ("read_place_clear", 6),
    # Phase 6: close the reader with its door, read, reopen.
    ("characterize_start", 6),
    ("door_fetch_cross", 8),
    ("door_fetch_down", 6),
    ("door_fetch_grip", 5),
    ("door_fetch_lift", 6),
    ("door_close_cross", 8),
    ("door_close_down", 6),
    ("door_close_release", 5),
    ("door_close_clear", 6),
    ("read_hold", 22),
    ("door_open_down", 6),
    ("door_open_grip", 5),
    ("door_open_lift", 6),
    ("door_return_cross", 8),
    ("door_return_down", 6),
    ("door_return_release", 5),
    ("door_return_clear", 6),
    ("characterize_end", 2),
    # Phase 7: transfer characterize -> output, then store.
    ("out_start", 6),
    ("out_pick_down", 6),
    ("out_pick_grip", 5),
    ("out_pick_lift", 6),
    ("out_cross", 12),
    ("out_place_down", 6),
    ("out_place_release", 5),
    ("out_place_clear", 6),
    ("out_stored", 12),
    ("cycle_end", 4),
)


def _beat_table() -> dict[str, int]:
    marks: dict[str, int] = {}
    frame = 0
    for name, gap in _BEATS:
        frame += gap
        marks[name] = frame
    if frame != FRAME_END:
        raise RuntimeError(f"Authored beats total {frame} frames, not {FRAME_END}")
    return marks


BEAT = _beat_table()
# The seven workflow phases, published to ../twin.yaml as animationTimeline
# frame ranges.  The gaps between them are the machine's own housekeeping: the
# two long ones are the head changes.
PHASE_RANGES: dict[str, tuple[int, int]] = {
    "input-to-dispense": (BEAT["start"], BEAT["transfer_in_end"]),
    "dispense-cycle": (BEAT["swap_a_ready"], BEAT["dispense_end"]),
    "dispense-to-mix": (BEAT["swap_b_row_front"], BEAT["mix_place_clear"]),
    "mix-cycle": (BEAT["mix_place_clear"], BEAT["mix_settle"]),
    "mix-to-characterize": (BEAT["mix_settle"], BEAT["read_place_clear"]),
    "characterize-cycle": (BEAT["characterize_start"], BEAT["characterize_end"]),
    "characterize-to-output": (BEAT["out_start"], BEAT["cycle_end"]),
}
# One dispense column every WELL_COLUMN_PITCH frames: approach, descend, fill,
# rise.  The pitch cannot drop below eight without two keys landing on the same
# frame at the hand-over between columns.
WELL_COLUMN_PITCH = 8
# Nozzle depths, expressed as mover heights rather than remembered numbers.
WELL_ENTRY_Z = -0.083
WASTE_ENTRY_Z = -0.082

MATERIALS: dict[str, bpy.types.Material] = {}
COLLECTIONS: dict[str, bpy.types.Collection] = {}


def args_from_blender() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-still", action="store_true")
    parser.add_argument("--render-animation", action="store_true")
    parser.add_argument("--render-poses", action="store_true")
    parser.add_argument("--poses", default="", help="comma-separated CAM_RIG pose names")
    parser.add_argument("--poses-dir", default="", help="where pose renders are written")
    parser.add_argument("--engine", choices=("eevee", "cycles"), default="eevee")
    parser.add_argument("--samples", type=int, default=64)
    parser.add_argument("--resolution", default="1280x720")
    parser.add_argument("--frame", type=int, default=548)
    parser.add_argument("--no-export", action="store_true")
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def reset_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for blocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.images,
    ):
        for block in list(blocks):
            if block.users == 0:
                blocks.remove(block)


def collection(name: str) -> bpy.types.Collection:
    result = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(result)
    COLLECTIONS[name] = result
    return result


def link_only(obj: bpy.types.Object, target: bpy.types.Collection) -> None:
    for source in list(obj.users_collection):
        source.objects.unlink(obj)
    target.objects.link(obj)


def make_material(
    name: str,
    color: tuple[float, float, float, float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.4,
    transmission: float = 0.0,
    ior: float = 1.45,
    emission: float = 0.0,
    coat: float = 0.0,
    microtexture: float = 0.0,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    mat.use_nodes = True
    tree = mat.node_tree
    bsdf = tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["IOR"].default_value = ior
    bsdf.inputs["Alpha"].default_value = color[3]
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = transmission
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = coat
    if emission:
        bsdf.inputs["Emission Color"].default_value = color
        bsdf.inputs["Emission Strength"].default_value = emission
    if microtexture:
        noise = tree.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 340.0
        noise.inputs["Detail"].default_value = 2.0
        noise.inputs["Roughness"].default_value = 0.72
        bump = tree.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = microtexture
        bump.inputs["Distance"].default_value = 0.0007
        tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    if color[3] < 1.0:
        mat.surface_render_method = "DITHERED"
        mat.use_transparency_overlap = False
    MATERIALS[name] = mat
    return mat


def init_materials() -> None:
    make_material(
        "PowderCoatBlack",
        (0.014, 0.017, 0.022, 1.0),
        roughness=0.26,
        coat=0.28,
        microtexture=0.09,
    )
    make_material(
        "PowderCoatGraphite",
        (0.041, 0.048, 0.060, 1.0),
        metallic=0.10,
        roughness=0.28,
        coat=0.16,
        microtexture=0.07,
    )
    make_material(
        "AnodizedAluminum",
        (0.485, 0.512, 0.538, 1.0),
        metallic=0.74,
        roughness=0.24,
        microtexture=0.030,
    )
    make_material(
        "BrushedStainless",
        (0.52, 0.556, 0.578, 1.0),
        metallic=0.96,
        roughness=0.145,
        microtexture=0.022,
    )
    make_material(
        "MachinedAluminum",
        (0.66, 0.70, 0.72, 1.0),
        metallic=0.9,
        roughness=0.16,
    )
    # Black-anodised profile for the sub-structure.  Real frames are built in
    # two finishes for the same reason: the working planes read, and the ties
    # that only carry load step back instead of stacking into a ladder.
    make_material(
        "BlackAnodized",
        (0.037, 0.040, 0.046, 1.0),
        metallic=0.55,
        roughness=0.29,
        microtexture=0.045,
    )
    # Hard-anodised tooling plate: the process deck, and the darkest large
    # surface on the machine, so every module standing on it separates from it.
    # The clear coat is what keeps it a machined surface under the work lights
    # instead of a matte hole in the middle of the frame.
    make_material(
        "HardAnodized",
        (0.048, 0.052, 0.060, 1.0),
        metallic=0.0,
        roughness=0.50,
        coat=0.22,
        microtexture=0.055,
    )
    make_material("BlackPolymer", (0.018, 0.021, 0.024, 1.0), roughness=0.42)
    make_material("WhitePolymer", (0.76, 0.79, 0.80, 1.0), roughness=0.32)
    make_material("PlatePolymer", (0.40, 0.44, 0.46, 0.62), roughness=0.16, transmission=0.44)
    make_material("Rubber", (0.006, 0.007, 0.008, 1.0), roughness=0.72)
    make_material(
        "Polycarbonate",
        (0.13, 0.22, 0.27, 0.10),
        roughness=0.035,
        transmission=0.95,
        ior=1.585,
        coat=0.35,
    )
    make_material(
        "ClearLabware",
        (0.56, 0.67, 0.72, 0.24),
        roughness=0.12,
        transmission=0.82,
        ior=1.49,
    )
    make_material("ScreenGlass", (0.004, 0.008, 0.012, 1.0), roughness=0.08, coat=0.35)
    make_material("ScreenGreen", (0.04, 0.52, 0.24, 1.0), roughness=0.28, emission=0.7)
    make_material("CyanIndicator", (0.0, 0.62, 0.78, 1.0), roughness=0.22, emission=4.0)
    make_material("WhiteIndicator", (0.80, 0.88, 0.91, 1.0), roughness=0.22, emission=2.6)
    make_material("ReaderIndicator", (0.28, 0.78, 0.94, 1.0), roughness=0.22, emission=1.0)
    make_material("AmberIndicator", (0.95, 0.36, 0.025, 1.0), roughness=0.22, emission=2.2)
    make_material("RedIndicator", (0.70, 0.018, 0.012, 1.0), roughness=0.22, emission=2.5)
    make_material("SampleBlue", (0.015, 0.31, 0.48, 0.74), roughness=0.18, transmission=0.18)
    make_material("SampleViolet", (0.29, 0.045, 0.46, 0.74), roughness=0.18, transmission=0.18)
    make_material("LabelWhite", (0.82, 0.86, 0.87, 1.0), roughness=0.46)
    make_material("LabelGray", (0.34, 0.39, 0.41, 1.0), roughness=0.46)

    # Machine safety and signalling.  These are the only saturated colours in
    # the scene, and every one of them is a control that does something.
    make_material("SafetyYellow", (0.720, 0.450, 0.012, 1.0), roughness=0.36, coat=0.16)
    make_material("SignalRed", (0.560, 0.017, 0.012, 1.0), roughness=0.28, coat=0.26)
    make_material("BeaconGreen", (0.06, 0.72, 0.24, 1.0), roughness=0.20, emission=9.0)
    make_material("BeaconAmber", (0.240, 0.085, 0.006, 1.0), roughness=0.20)
    make_material("BeaconRed", (0.260, 0.010, 0.008, 1.0), roughness=0.20)
    # Campaign display.  Emissive marks on a dark panel: nothing on this screen
    # is a sentence, so the value of each mark is carried by its brightness.
    make_material("ScreenCyan", (0.05, 0.62, 0.80, 1.0), roughness=0.24, emission=9.0)
    make_material("ScreenCyanDim", (0.03, 0.24, 0.34, 1.0), roughness=0.24, emission=2.6)
    make_material("ScreenGridDim", (0.02, 0.10, 0.15, 1.0), roughness=0.24, emission=1.4)
    make_material("ScreenAmber", (0.90, 0.42, 0.03, 1.0), roughness=0.24, emission=8.0)
    make_material("SwatchWarm", (0.82, 0.26, 0.10, 1.0), roughness=0.24, emission=5.5)
    make_material("SwatchMid", (0.62, 0.36, 0.62, 1.0), roughness=0.24, emission=5.5)
    make_material("SwatchCool", (0.10, 0.34, 0.78, 1.0), roughness=0.24, emission=5.5)
    # Cast black epoxy resin: the worktop a laboratory actually specifies, and
    # the darkest large surface in the room.  Everything standing on it reads
    # against it, so it is what stops the frame collapsing into one grey band.
    # The same resin where hands have taken the gloss off it.  Same pigment,
    # scattered instead of polished: a value shift, not a stain.
    make_material("CableBlue", (0.018, 0.10, 0.17, 1.0), roughness=0.46)
    make_material("CableBlack", (0.008, 0.009, 0.010, 1.0), roughness=0.58)
    # Cable is colour-coded on a real machine, so it is also the cheapest
    # honest colour in the scene: blue for data, red for 24 V, green-yellow for
    # protective earth, orange for the safety circuit.
    make_material("CableRed", (0.360, 0.022, 0.014, 1.0), roughness=0.50)
    make_material("CableEarth", (0.250, 0.320, 0.020, 1.0), roughness=0.52)
    make_material("CableOrange", (0.560, 0.160, 0.010, 1.0), roughness=0.50)

    # Room fabric.  Painted plasterboard, welded vinyl sheet with a coved
    # skirting, mineral-fibre ceiling tile on an exposed white T-bar grid.
    # The wall is a neutral eggshell, not a tinted one: a wall that carries a
    # hue competes with the casework standing against it, and the two then read
    # as one field.  Dropping it also leaves headroom above it for the ceiling.
    make_material("Wall", (0.082, 0.088, 0.100, 1.0), roughness=0.80)
    make_material("WallLower", (0.092, 0.098, 0.111, 1.0), roughness=0.66)
    # Dark welded vinyl.  The floor is the largest surface in frame; keeping it
    # in the same light-grey band as the walls is what flattens the whole image.
    # Poured resin, sealed and polished.  A floor that returns a reflection is
    # what makes a plant space read as maintained rather than as unlit.
    make_material("Floor", (0.128, 0.137, 0.150, 1.0), roughness=0.125, coat=0.55)
    # Sheet vinyl loses its gloss where it is walked on long before it loses
    # colour, so the traffic path is a scattering change first.
    make_material("CeilingTile", (0.100, 0.105, 0.114, 1.0), roughness=0.84)
    make_material("CeilingGrid", (0.520, 0.530, 0.530, 1.0), metallic=0.10, roughness=0.50)
    make_material("TrofferDiffuser", (0.92, 0.945, 1.0, 1.0), roughness=0.30, emission=1.7)
    make_material("WorkLightLens", (1.00, 0.905, 0.790, 1.0), roughness=0.30, emission=1.4)
    # Machine strip lighting.  Real workcells light their own decks and their own
    # service bays; these are the fixtures, and the assembler puts a matched
    # area light behind each one.
    make_material("StripWarm", (1.00, 0.865, 0.700, 1.0), roughness=0.28, emission=4.2)
    make_material("StripCool", (0.86, 0.945, 1.00, 1.0), roughness=0.28, emission=3.4)
    make_material("DoorLeaf", (0.300, 0.318, 0.330, 1.0), roughness=0.44, coat=0.10)
    make_material("DoorFrame", (0.235, 0.248, 0.256, 1.0), roughness=0.40)

    # Casework.  Painted steel carcasses with a satin finish; handles and feet
    # reuse the stainless already in the palette.
    make_material("CaseworkShadow", (0.0265, 0.0280, 0.0288, 1.0), roughness=0.55)
    # Laboratory casework is very often two-tone with the dark element low: the
    # carcasses stand on a painted base rail, and the bottom drawer front is
    # finished to match it.  That band is what gives the run a bottom edge.
    # Instrument housings on a dark worktop have to separate from it, and real
    # laboratory automation is painted light grey for exactly that reason.
    # Machine covers are painted a slightly cool grey.  That cast is what
    # separates a cover from the aluminium it is bolted to instead of letting
    # the two merge into one field.
    make_material(
        "InstrumentGrey",
        (0.248, 0.268, 0.296, 1.0),
        roughness=0.29,
        coat=0.24,
        microtexture=0.045,
    )

    # Consumables and set dressing.
    make_material("AmberGlass", (0.230, 0.082, 0.014, 0.58), roughness=0.14, transmission=0.72)
    make_material("HDPEWhite", (0.640, 0.655, 0.650, 0.90), roughness=0.44, transmission=0.22)
    make_material("HDPEBlueCap", (0.020, 0.150, 0.290, 1.0), roughness=0.40)
    make_material("TipBoxBlue", (0.035, 0.135, 0.205, 1.0), roughness=0.40)
    make_material("PaperWhite", (0.690, 0.700, 0.690, 1.0), roughness=0.80)


def apply_material(obj: bpy.types.Object, material: str) -> None:
    if not hasattr(obj.data, "materials"):
        return
    obj.data.materials.clear()
    obj.data.materials.append(MATERIALS[material])


def mark_export(obj: bpy.types.Object, export: bool = True) -> bpy.types.Object:
    obj["opensdlExport"] = export
    if export:
        obj["asset_id"] = obj.name
        obj["source_unit"] = "m"
    return obj


def empty(
    name: str,
    *,
    target: bpy.types.Collection,
    location: Sequence[float] = (0.0, 0.0, 0.0),
    parent: bpy.types.Object | None = None,
    export: bool = True,
) -> bpy.types.Object:
    obj = bpy.data.objects.new(name, None)
    target.objects.link(obj)
    obj.location = location
    obj.parent = parent
    return mark_export(obj, export)


def rounded_box(
    name: str,
    size: Sequence[float],
    location: Sequence[float],
    material: str,
    *,
    target: bpy.types.Collection,
    parent: bpy.types.Object | None = None,
    rotation: Sequence[float] = (0.0, 0.0, 0.0),
    bevel: float = 0.008,
    segments: int = 3,
    export: bool = True,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.location = location
    obj.rotation_euler = rotation
    obj.parent = parent
    apply_material(obj, material)
    if bevel > 0:
        modifier = obj.modifiers.new("Manufactured edge radius", "BEVEL")
        modifier.width = bevel
        modifier.segments = segments
        modifier.limit_method = "ANGLE"
    link_only(obj, target)
    return mark_export(obj, export)


def cylinder(
    name: str,
    radius: float,
    depth: float,
    location: Sequence[float],
    material: str,
    *,
    target: bpy.types.Collection,
    parent: bpy.types.Object | None = None,
    rotation: Sequence[float] = (0.0, 0.0, 0.0),
    vertices: int = 32,
    bevel: float = 0.001,
    export: bool = True,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth)
    obj = bpy.context.object
    obj.name = name
    obj.location = location
    obj.rotation_euler = rotation
    obj.parent = parent
    apply_material(obj, material)
    if bevel > 0:
        modifier = obj.modifiers.new("Machined edge", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    link_only(obj, target)
    return mark_export(obj, export)


def sphere(
    name: str,
    radius: float,
    location: Sequence[float],
    material: str,
    *,
    target: bpy.types.Collection,
    parent: bpy.types.Object | None = None,
    export: bool = True,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=radius)
    obj = bpy.context.object
    obj.name = name
    obj.location = location
    obj.parent = parent
    apply_material(obj, material)
    bpy.ops.object.shade_smooth()
    link_only(obj, target)
    return mark_export(obj, export)


def torus(
    name: str,
    major_radius: float,
    minor_radius: float,
    location: Sequence[float],
    material: str,
    *,
    target: bpy.types.Collection,
    parent: bpy.types.Object | None = None,
    rotation: Sequence[float] = (0.0, 0.0, 0.0),
    export: bool = True,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=24,
        minor_segments=8,
    )
    obj = bpy.context.object
    obj.name = name
    obj.location = location
    obj.rotation_euler = rotation
    obj.parent = parent
    apply_material(obj, material)
    link_only(obj, target)
    return mark_export(obj, export)


def tube_path(
    name: str,
    points: Sequence[Sequence[float]],
    radius: float,
    material: str,
    *,
    target: bpy.types.Collection,
    parent: bpy.types.Object | None = None,
    export: bool = True,
) -> bpy.types.Object:
    curve = bpy.data.curves.new(f"{name}Curve", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 3
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for control, point in zip(spline.bezier_points, points, strict=True):
        control.co = point
        control.handle_left_type = "AUTO"
        control.handle_right_type = "AUTO"
    obj = bpy.data.objects.new(name, curve)
    target.objects.link(obj)
    obj.parent = parent
    apply_material(obj, material)
    return mark_export(obj, export)


def text_mesh(
    name: str,
    body: str,
    location: Sequence[float],
    size: float,
    material: str,
    *,
    target: bpy.types.Collection,
    parent: bpy.types.Object | None = None,
    rotation: Sequence[float] = (math.pi / 2, 0.0, 0.0),
    align: str = "CENTER",
    extrude: float = 0.00025,
    export: bool = True,
) -> bpy.types.Object:
    curve = bpy.data.curves.new(f"{name}Font", "FONT")
    curve.body = body
    curve.align_x = align
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = extrude
    curve.bevel_depth = extrude * 0.25
    obj = bpy.data.objects.new(name, curve)
    target.objects.link(obj)
    obj.location = location
    obj.rotation_euler = rotation
    obj.parent = parent
    apply_material(obj, material)
    return mark_export(obj, export)


def screw(
    name: str,
    location: Sequence[float],
    *,
    target: bpy.types.Collection,
    parent: bpy.types.Object | None = None,
    axis: str = "Y",
    radius: float = 0.004,
    material: str = "MachinedAluminum",
) -> bpy.types.Object:
    rotation = (
        (math.pi / 2, 0.0, 0.0)
        if axis == "Y"
        else (0.0, math.pi / 2, 0.0)
        if axis == "X"
        else (0.0, 0.0, 0.0)
    )
    head = cylinder(
        name,
        radius,
        0.0024,
        location,
        material,
        target=target,
        parent=parent,
        rotation=rotation,
        vertices=24,
        bevel=0.00045,
    )
    return head


# The plant ceiling carries continuous linear battens on the machine axis
# rather than a field of office troffers: two runs over the frame and one over
# the aisle behind it, and they are the only light sources in the volume.
BATTEN_RUNS: tuple[tuple[float, float, float], ...] = (
    (0.0, 0.20, 2.780),
    (0.0, -0.95, 2.780),
    (0.0, -2.45, 2.780),
    (0.0, -3.70, 2.780),
)
BATTEN_WIDTH = 0.115


def extrusion(
    name: str,
    length: float,
    axis: str,
    center: "Sequence[float]",
    *,
    target: bpy.types.Collection,
    parent: bpy.types.Object | None = None,
    profile: float = PROFILE,
    material: str = "AnodizedAluminum",
    slots: bool = True,
    export: bool = True,
) -> bpy.types.Object:
    """One length of T-slot aluminium profile.

    The member is a square section with a slot machined into each of its four
    faces.  The slots are what make an extrusion read as an extrusion instead of
    as a painted bar: they run the whole length, they catch a dark line in every
    light, and they are the reason anything can be clamped anywhere on this
    frame.  They cost four thin boxes per member and they are worth it.
    """
    index = {"X": 0, "Y": 1, "Z": 2}[axis]
    size = [profile, profile, profile]
    size[index] = length
    body = rounded_box(
        name,
        size,
        center,
        material,
        target=target,
        parent=parent,
        bevel=0.0022,
        segments=2,
        export=export,
    )
    if not slots:
        return body
    groove_depth = 0.0055
    groove_width = profile * 0.34
    for face in range(3):
        if face == index:
            continue
        for sign in (-1.0, 1.0):
            groove_size = [groove_width, groove_width, groove_width]
            groove_size[index] = length - 0.004
            groove_size[face] = groove_depth
            offset = [0.0, 0.0, 0.0]
            offset[face] = sign * (profile / 2.0 - groove_depth / 2.0 + 0.0004)
            rounded_box(
                f"{name}Slot_{face}{sign:+.0f}",
                groove_size,
                (center[0] + offset[0], center[1] + offset[1], center[2] + offset[2]),
                "CaseworkShadow",
                target=target,
                parent=parent,
                bevel=0.0,
                export=export,
            )
    return body


def frame_bracket(
    name: str,
    center: "Sequence[float]",
    *,
    target: bpy.types.Collection,
    parent: bpy.types.Object,
    sign_x: float = 1.0,
    sign_z: float = 1.0,
    leg: float = 0.080,
) -> None:
    """A cast corner gusset in the XZ plane, with its web and two bolts.

    Approximated as two legs plus a 45 degree web rather than a true cast
    fillet: the read comes from the diagonal face and the socket heads, and the
    fillet would cost geometry nobody can see at machine scale.
    """
    x, y, z = center
    for index, size, offset in (
        (0, (leg, 0.012, 0.020), (sign_x * leg / 2.0, 0.0, sign_z * 0.010)),
        (1, (0.020, 0.012, leg), (sign_x * 0.010, 0.0, sign_z * leg / 2.0)),
    ):
        rounded_box(
            f"{name}Leg{index}",
            size,
            (x + offset[0], y + offset[1], z + offset[2]),
            "PowderCoatGraphite",
            target=target,
            parent=parent,
            bevel=0.002,
        )
        screw(
            f"{name}Bolt{index}",
            (
                x + offset[0] * 1.45,
                y - 0.008,
                z + offset[2] * 1.45,
            ),
            target=target,
            parent=parent,
            axis="Y",
            radius=0.0055,
        )
    rounded_box(
        f"{name}Web",
        (leg * 1.20, 0.010, 0.014),
        (x + sign_x * leg * 0.34, y, z + sign_z * leg * 0.34),
        "PowderCoatGraphite",
        target=target,
        parent=parent,
        rotation=(0.0, math.radians(-45.0) * sign_x * sign_z, 0.0),
        bevel=0.002,
    )


def frame_foot(
    name: str, x: float, y: float, *, target: bpy.types.Collection, parent: bpy.types.Object
) -> None:
    """A levelling foot on a threaded stud, through an anchored floor plate."""
    rounded_box(
        f"{name}AnchorPlate",
        (0.150, 0.150, 0.010),
        (x, y, 0.005),
        "PowderCoatGraphite",
        target=target,
        parent=parent,
        bevel=0.003,
    )
    for corner_x, corner_y in ((-0.055, -0.055), (0.055, 0.055)):
        cylinder(
            f"{name}AnchorBolt_{corner_x:+.3f}",
            0.0085,
            0.016,
            (x + corner_x, y + corner_y, 0.014),
            "BrushedStainless",
            target=target,
            parent=parent,
            vertices=14,
            bevel=0.0008,
        )
    cylinder(
        f"{name}Pad",
        0.036,
        0.014,
        (x, y, 0.017),
        "MachinedAluminum",
        target=target,
        parent=parent,
        vertices=20,
        bevel=0.0015,
    )
    cylinder(
        f"{name}Stud",
        0.009,
        FRAME_FOOT_HEIGHT - 0.024,
        (x, y, 0.024 + (FRAME_FOOT_HEIGHT - 0.024) / 2.0),
        "BrushedStainless",
        target=target,
        parent=parent,
        vertices=12,
        bevel=0.0005,
    )
    cylinder(
        f"{name}LockNut",
        0.017,
        0.010,
        (x, y, 0.031),
        "PowderCoatGraphite",
        target=target,
        parent=parent,
        vertices=6,
        bevel=0.0008,
    )


def trunking(
    name: str,
    length: float,
    axis: str,
    center: "Sequence[float]",
    *,
    target: bpy.types.Collection,
    parent: bpy.types.Object,
    width: float = 0.060,
    height: float = 0.060,
    fingers: int = 0,
) -> None:
    """Slotted cable trunking: a fingered channel with its lid clipped on."""
    index = {"X": 0, "Y": 1, "Z": 2}[axis]
    across = 1 if index == 0 else 0
    back = [width, width, height] if index != 2 else [width, height, width]
    back[index] = length
    back[across] = 0.006
    offset = [0.0, 0.0, 0.0]
    offset[across] = -width / 2.0
    rounded_box(
        f"{name}Back",
        back,
        (center[0] + offset[0], center[1] + offset[1], center[2] + offset[2]),
        "WhitePolymer",
        target=target,
        parent=parent,
        bevel=0.001,
    )
    count = fingers or max(6, int(length / 0.052))
    for side in (-1.0, 1.0):
        for finger in range(count):
            position = -length / 2.0 + (finger + 0.5) * length / count
            finger_size = [0.0, 0.0, 0.0]
            finger_size[index] = length / count * 0.55
            finger_size[across] = width
            finger_size[3 - index - across] = 0.006
            place = [center[0], center[1], center[2]]
            place[index] += position
            place[3 - index - across] += side * (height / 2.0 - 0.003)
            rounded_box(
                f"{name}Finger_{side:+.0f}_{finger:02d}",
                finger_size,
                place,
                "WhitePolymer",
                target=target,
                parent=parent,
                bevel=0.0,
            )
    lid = [0.0, 0.0, 0.0]
    lid[index] = length
    lid[across] = 0.006
    lid[3 - index - across] = height
    lid_place = [center[0], center[1], center[2]]
    lid_place[across] += width / 2.0
    rounded_box(
        f"{name}Lid",
        lid,
        lid_place,
        "WhitePolymer",
        target=target,
        parent=parent,
        bevel=0.002,
    )


def build_frame(cell_root: bpy.types.Object) -> bpy.types.Object:
    """The machine frame: the subject of this scene.

    Nothing here is furniture.  Four corner towers and five intermediate
    uprights in 45-series T-slot profile stand on levelling feet through anchor
    plates bolted into the floor slab.  Horizontal members tie them at five
    working planes, and each plane is a machine plane: the base tie, the service
    deck the fluid supply stands on, the mounting plane the two labware hotels
    bolt to, the deck carrier under the process plate, and the top tie that the
    transport runway, the trunking and the beacon all hang from.

    The frame is open on the front and on both long sides.  Panels appear only
    where a process needs one - a splash guard behind the liquid handling, a
    light baffle behind the detector - because a wall that exists to separate a
    person from the machine has no job here.
    """
    target = COLLECTIONS["Frame"]
    frame = empty("Frame", target=target, location=(0.0, 0.0, 0.0), parent=cell_root)
    front_y, rear_y = FRAME_POST_Y

    towers = [(x, y, FRAME_TOP_Z) for x in FRAME_CORNER_X for y in (front_y, rear_y)]
    towers += [(x, rear_y, FRAME_TOP_Z) for x in (-1.20, 0.0, 1.20)]
    # The two front intermediates stop just above the deck.  Carrying them to
    # full height would put a column in front of the liquid handling, and the
    # top tie already spans between the corner towers.
    towers += [(x, front_y, 1.200) for x in (-1.20, 1.20)]
    for x, y, top in towers:
        height = top - FRAME_FOOT_HEIGHT
        extrusion(
            f"FramePost_{x:+.3f}_{y:+.3f}",
            height,
            "Z",
            (x, y, FRAME_FOOT_HEIGHT + height / 2.0),
            target=target,
            parent=frame,
        )
        frame_foot(f"FrameFoot_{x:+.3f}_{y:+.3f}", x, y, target=target, parent=frame)

    span = 2 * (FRAME_HALF_LENGTH - FRAME_POST_HALF) + PROFILE
    # Working planes in natural anodised, load ties in black.
    rail_planes = (
        ("Base", FRAME_BASE_Z, (-1.7775, -1.20, 0.0, 1.20, 1.7775), "BlackAnodized"),
        ("Service", FRAME_SERVICE_Z, (-0.200, 0.200, 0.500), "BlackAnodized"),
        ("Mount", FRAME_MOUNT_Z, (-1.680, -1.440, 1.440, 1.680), "BlackAnodized"),
        ("Deck", FRAME_DECK_RAIL_Z, DECK_CARRIER_X, "AnodizedAluminum"),
        ("Top", FRAME_TOP_RAIL_Z, (-1.7775, -1.20, 0.0, 1.20, 1.7775), "AnodizedAluminum"),
    )
    for label, z, cross_xs, material in rail_planes:
        for rail_y in (front_y, rear_y):
            extrusion(
                f"FrameRail{label}_{rail_y:+.3f}",
                span,
                "X",
                (0.0, rail_y, z),
                target=target,
                parent=frame,
                material=material,
            )
        for cross_x in cross_xs:
            extrusion(
                f"FrameCross{label}_{cross_x:+.3f}",
                rear_y - front_y - PROFILE,
                "Y",
                (cross_x, (front_y + rear_y) / 2.0, z),
                target=target,
                parent=frame,
                material=material,
            )

    # Corner gussets where the towers meet the top and base ties.  Real frames
    # are braced at the corners and nowhere else; bracing every joint is what a
    # rendering does, not what a fabricator does.
    for x in FRAME_CORNER_X:
        for y in (front_y, rear_y):
            frame_bracket(
                f"FrameGussetTop_{x:+.3f}_{y:+.3f}",
                (x, y, FRAME_TOP_RAIL_Z - PROFILE / 2.0),
                target=target,
                parent=frame,
                sign_x=-1.0 if x > 0 else 1.0,
                sign_z=-1.0,
            )
            frame_bracket(
                f"FrameGussetBase_{x:+.3f}_{y:+.3f}",
                (x, y, FRAME_BASE_Z + PROFILE / 2.0),
                target=target,
                parent=frame,
                sign_x=-1.0 if x > 0 else 1.0,
                sign_z=1.0,
            )
    # Diagonal braces in the two end tower planes.  A 2.2 m tower with a moving
    # bridge landing on it needs the triangle, and the triangle is also what
    # stops the ends reading as two goalposts.
    for x in FRAME_CORNER_X:
        for lower, upper in (
            (FRAME_BASE_Z + 0.10, FRAME_DECK_RAIL_Z - 0.10),
            (FRAME_DECK_RAIL_Z + 0.10, FRAME_TOP_RAIL_Z - 0.10),
        ):
            depth = rear_y - front_y - 0.14
            rise = upper - lower
            extrusion(
                f"FrameBrace_{x:+.3f}_{lower:.3f}",
                math.hypot(depth, rise),
                "Y",
                (x, (front_y + rear_y) / 2.0, (lower + upper) / 2.0),
                target=target,
                parent=frame,
                profile=0.030,
                slots=False,
            ).rotation_euler = (math.atan2(rise, depth) * (1.0 if x < 0 else -1.0), 0.0, 0.0)

    # A warm strip under the front mounting rail, washing the bay fronts.  It
    # is also the line that stops the lower half of the machine reading as one
    # unlit block from the aisle.
    rounded_box(
        "MountStripChannel",
        (span - 0.30, 0.030, 0.024),
        (0.0, front_y + 0.012, FRAME_MOUNT_Z - 0.038),
        "MachinedAluminum",
        target=target,
        parent=frame,
        bevel=0.002,
    )
    rounded_box(
        "MountStripLens",
        (span - 0.34, 0.016, 0.010),
        (0.0, front_y + 0.006, FRAME_MOUNT_Z - 0.048),
        "StripWarm",
        target=target,
        parent=frame,
        bevel=0.001,
    )

    # Bay strip lighting, on the inner face of every front upright.
    for strip_x in BAY_STRIP_X:
        strip_height = BAY_STRIP_Z[1] - BAY_STRIP_Z[0]
        strip_z = (BAY_STRIP_Z[0] + BAY_STRIP_Z[1]) / 2.0
        rounded_box(
            f"BayStripChannel_{strip_x:+.3f}",
            (0.022, 0.026, strip_height),
            (strip_x, BAY_STRIP_Y, strip_z),
            "MachinedAluminum",
            target=target,
            parent=frame,
            bevel=0.002,
        )
        rounded_box(
            f"BayStripLens_{strip_x:+.3f}",
            (0.014, 0.008, strip_height - 0.020),
            (strip_x, BAY_STRIP_Y + 0.016, strip_z),
            "StripWarm",
            target=target,
            parent=frame,
            bevel=0.002,
        )

    # Machine work lights on the top tie: two bars aimed down at the process
    # plane.  This is the machine lighting its own work, which is the reason a
    # frame this tall has a top tie at all.
    for index, (light_y, light_z) in enumerate(WORKLIGHT_RUNS):
        rounded_box(
            f"WorkLightBody_{index}",
            (2 * DECK_HALF_LENGTH + 0.30, 0.070, 0.058),
            (0.0, light_y, light_z),
            "PowderCoatGraphite",
            target=target,
            parent=frame,
            bevel=0.006,
        )
        rounded_box(
            f"WorkLightLens_{index}",
            (2 * DECK_HALF_LENGTH + 0.26, 0.050, 0.012),
            (0.0, light_y, light_z - 0.032),
            "WorkLightLens",
            target=target,
            parent=frame,
            bevel=0.003,
        )
        for bracket_x in (-1.20, 0.0, 1.20):
            rounded_box(
                f"WorkLightBracket_{index}_{bracket_x:+.2f}",
                (0.030, 0.026, 0.090),
                (bracket_x, light_y + math.copysign(0.048, light_y), light_z + 0.040),
                "PowderCoatGraphite",
                target=target,
                parent=frame,
                bevel=0.003,
            )
    return frame


def build_decks(cell_root: bpy.types.Object) -> bpy.types.Object:
    """The process plate and the service plate the frame carries.

    ``Workstation`` is the process plane: one machined tooling plate at
    ``DECK_Z``, bolted down through the deck carriers, with the module bolt
    pattern, the locating dowels and the cable pass-throughs that let a module
    be moved along it.  The seating height is set by the transport, not by a
    person: 1135 mm is where the bridge can put a plate down.
    """
    target = COLLECTIONS["Cell"]
    station = empty("Workstation", target=target, location=(0.0, 0.0, 0.0), parent=cell_root)
    deck_depth = DECK_REAR_Y - DECK_FRONT_Y
    deck_center_y = (DECK_REAR_Y + DECK_FRONT_Y) / 2.0
    rounded_box(
        "WorkstationDeck",
        (2 * DECK_HALF_LENGTH, deck_depth, DECK_THICKNESS),
        (0.0, deck_center_y, DECK_Z - DECK_THICKNESS / 2.0),
        "HardAnodized",
        target=target,
        parent=station,
        bevel=0.003,
    )
    # T-slots milled the length of the plate.  They are what lets a module be
    # re-sited without drilling, and they are also what stops half a square
    # metre of plate reading as a sheet of steel.
    for slot_index, slot_y in enumerate((DECK_FRONT_Y + 0.056, DECK_REAR_Y - 0.056)):
        rounded_box(
            f"DeckChannel_{slot_index}",
            (2 * DECK_HALF_LENGTH - 0.030, 0.020, 0.006),
            (0.0, slot_y, DECK_Z - 0.002),
            "CaseworkShadow",
            target=target,
            parent=station,
            bevel=0.0,
        )
        for lip in (-1.0, 1.0):
            rounded_box(
                f"DeckChannelLip_{slot_index}_{lip:+.0f}",
                (2 * DECK_HALF_LENGTH - 0.030, 0.005, 0.005),
                (0.0, slot_y + lip * 0.0125, DECK_Z - 0.0015),
                "MachinedAluminum",
                target=target,
                parent=station,
                bevel=0.0,
            )
    # The M6 fixing grid, on 100 mm centres across the working area.  Most of
    # these are under a module and invisible; the ones that are not are what
    # make the plate read as a deck rather than as a sheet of steel.
    grid_columns = int(round((2 * DECK_HALF_LENGTH - 0.24) / 0.100))
    grid_rows = int(round((DECK_REAR_Y - DECK_FRONT_Y - 0.20) / 0.100))
    for column in range(grid_columns + 1):
        for row in range(grid_rows + 1):
            cylinder(
                f"DeckFixing_{column:02d}_{row}",
                0.0055,
                0.0030,
                (
                    -(DECK_HALF_LENGTH - 0.120) + column * 0.100,
                    DECK_FRONT_Y + 0.100 + row * 0.100,
                    DECK_Z - 0.0013,
                ),
                "CaseworkShadow",
                target=target,
                parent=station,
                vertices=12,
                bevel=0.0,
            )
    # The plate is bolted to every deck carrier it crosses.  Two socket heads
    # per carrier, on the plate centre line, is what a machined plate on an
    # extrusion frame actually looks like from above.
    for carrier_x in DECK_CARRIER_X:
        for bolt_y in (DECK_FRONT_Y + 0.030, DECK_REAR_Y - 0.030):
            screw(
                f"DeckBolt_{carrier_x:+.3f}_{bolt_y:+.3f}",
                (carrier_x, bolt_y, DECK_Z - 0.001),
                target=target,
                parent=station,
                axis="Z",
                radius=0.0065,
            )
    # Cable and tubing pass-throughs, one behind each station, so a module's
    # umbilical drops straight through the plate instead of over its edge.
    for name in STATION_ORDER[1:4]:
        rounded_box(
            f"DeckPassThrough_{name}",
            (0.086, 0.030, DECK_THICKNESS + 0.004),
            (STATION_X[name] + 0.082, DECK_REAR_Y - 0.052, DECK_Z - DECK_THICKNESS / 2.0),
            "PowderCoatBlack",
            target=target,
            parent=station,
            bevel=0.003,
        )
    # The service-bay strip, mounted behind the deck's front lip.
    rounded_box(
        "UnderdeckStripBody",
        (2 * DECK_HALF_LENGTH + 0.24, 0.044, 0.036),
        (0.0, UNDERDECK_RUN[0], UNDERDECK_RUN[1]),
        "PowderCoatGraphite",
        target=target,
        parent=station,
        bevel=0.004,
    )
    rounded_box(
        "UnderdeckStripLens",
        (2 * DECK_HALF_LENGTH + 0.20, 0.030, 0.010),
        (0.0, UNDERDECK_RUN[0], UNDERDECK_RUN[1] - 0.016),
        "WorkLightLens",
        target=target,
        parent=station,
        bevel=0.002,
    )
    # A stiffening lip on the free front edge.
    rounded_box(
        "WorkstationDeckLip",
        (2 * DECK_HALF_LENGTH, 0.016, 0.048),
        (0.0, DECK_FRONT_Y + 0.008, DECK_Z - DECK_THICKNESS - 0.020),
        "PowderCoatGraphite",
        target=target,
        parent=station,
        bevel=0.003,
    )
    # The IO panel on the rear plane.  Every module's umbilical lands on a
    # bulkhead here instead of trailing off the deck, which is the difference
    # between equipment plugged in on a bench and a machine that is wired.
    rounded_box(
        "DeckIoPanel",
        (0.760, 0.008, 0.290),
        (0.700, 0.310, 1.290),
        "InstrumentGrey",
        target=target,
        parent=station,
        bevel=0.004,
    )
    for row in range(4):
        for hole in range(19):
            rounded_box(
                f"DeckIoPerf_{row}_{hole:02d}",
                (0.007, 0.004, 0.007),
                (0.372 + hole * 0.0364, 0.3055, 1.180 + row * 0.0725),
                "CaseworkShadow",
                target=target,
                parent=station,
                bevel=0.0,
            )
    for port in range(5):
        rounded_box(
            f"DeckIoBulkhead_{port}",
            (0.044, 0.026, 0.038),
            (0.410 + port * 0.070, 0.294, 1.216),
            "MachinedAluminum",
            target=target,
            parent=station,
            bevel=0.002,
        )
        tube_path(
            f"DeckIoLead_{port}",
            (
                (0.410 + port * 0.070, 0.280, 1.216),
                (0.560 + port * 0.030, 0.352, 1.130),
                (0.700, 0.470, 1.010),
            ),
            0.0038,
            ("CableBlue", "CableRed", "CableBlack", "CableEarth", "CableOrange")[port],
            target=target,
            parent=station,
        )
    rounded_box(
        "DeckIoLabel",
        (0.150, 0.003, 0.018),
        (0.700, 0.3045, 1.402),
        "PowderCoatGraphite",
        target=target,
        parent=station,
        bevel=0.001,
    )
    rounded_box(
        "WorkstationAssetTag",
        (0.084, 0.003, 0.026),
        (-1.130, DECK_FRONT_Y + 0.0002, DECK_Z - 0.030),
        "LabelWhite",
        target=target,
        parent=station,
        bevel=0.001,
    )
    text_mesh(
        "WorkstationAssetTagText",
        "SDL-01  ASSET 41207",
        (-1.130, DECK_FRONT_Y - 0.0018, DECK_Z - 0.030),
        0.0060,
        "LabelGray",
        target=target,
        parent=station,
    )

    # Process guarding, and only where a process needs it: a clear splash guard
    # standing behind the liquid handling, and a black baffle behind the
    # detector so its own stray light does not come back at it.
    for label, x_from, x_to, material, top in (("Splash", -1.14, 0.26, "Polycarbonate", 1.500),):
        rounded_box(
            f"ProcessGuard{label}",
            (x_to - x_from, 0.006, top - DECK_Z),
            ((x_from + x_to) / 2.0, 0.200, (DECK_Z + top) / 2.0),
            material,
            target=target,
            parent=station,
            bevel=0.002,
        )
        for post_x in (x_from + 0.020, x_to - 0.020):
            extrusion(
                f"ProcessGuardPost{label}_{post_x:+.3f}",
                top - DECK_Z + 0.010,
                "Z",
                (post_x, 0.212, (DECK_Z + top) / 2.0),
                target=target,
                parent=station,
                profile=0.020,
                slots=False,
            )
    return station


def build_service_deck(cell_root: bpy.types.Object) -> bpy.types.Object:
    """The fluid supply plane under the process deck."""
    target = COLLECTIONS["Frame"]
    root = empty("ServiceDeck", target=target, location=(0.0, 0.0, 0.0), parent=cell_root)
    rounded_box(
        "ServiceDeckPlate",
        (FLUIDICS_X[1] - FLUIDICS_X[0], 0.700, 0.008),
        ((FLUIDICS_X[0] + FLUIDICS_X[1]) / 2.0, 0.070, SERVICE_TOP_Z - 0.004),
        "BrushedStainless",
        target=target,
        parent=root,
        bevel=0.002,
    )
    # A bund with a raised lip: any bottle that lets go is contained on the
    # plate instead of running down through the frame onto the drives.
    for side, size, offset in (
        ("Front", (FLUIDICS_X[1] - FLUIDICS_X[0], 0.010, 0.032), (0.0, -0.275)),
        ("Rear", (FLUIDICS_X[1] - FLUIDICS_X[0], 0.010, 0.032), (0.0, 0.415)),
        ("Left", (0.010, 0.700, 0.032), (-(FLUIDICS_X[1] - FLUIDICS_X[0]) / 2.0, 0.070)),
        ("Right", (0.010, 0.700, 0.032), ((FLUIDICS_X[1] - FLUIDICS_X[0]) / 2.0, 0.070)),
    ):
        rounded_box(
            f"ServiceDeckBund{side}",
            size,
            (
                (FLUIDICS_X[0] + FLUIDICS_X[1]) / 2.0 + offset[0],
                offset[1],
                SERVICE_TOP_Z + 0.016,
            ),
            "BrushedStainless",
            target=target,
            parent=root,
            bevel=0.002,
        )
    return root


def build_controls(cell_root: bpy.types.Object) -> bpy.types.Object:
    """The controls cabinet and the open drive bank.

    Two halves of one story.  The cabinet is a sealed sheet-steel enclosure with
    a louvred door and a door-interlocked main isolator, which is where the
    mains side of the machine lives.  The drive bank is deliberately open: DIN
    rail, breakers, two 24 V supplies, three servo drives and a wiring duct
    behind a clear guard, so the part of the machine that decides where the
    mover goes is visible rather than hidden behind sheet metal.
    """
    target = COLLECTIONS["Frame"]
    root = empty("Controls", target=target, location=(0.0, 0.0, 0.0), parent=cell_root)

    left, right = CABINET_X
    width = right - left
    center_x = (left + right) / 2.0
    top_z = 0.856
    depth = 0.700
    center_y = BAY_FACE_Y + depth / 2.0
    height = top_z - BAY_FLOOR_Z
    rounded_box(
        "ControlCabinet",
        (width, depth, height),
        (center_x, center_y, BAY_FLOOR_Z + height / 2.0),
        "InstrumentGrey",
        target=target,
        parent=root,
        bevel=0.005,
    )
    rounded_box(
        "ControlCabinetDoor",
        (width - 0.024, 0.016, height - 0.024),
        (center_x, BAY_FACE_Y - 0.006, BAY_FLOOR_Z + height / 2.0),
        "InstrumentGrey",
        target=target,
        parent=root,
        bevel=0.004,
    )
    # Three louvre banks in the door.  The drives behind them dump heat, and a
    # blank door would say this cabinet has nothing in it.
    for bank, bank_z in enumerate((0.240, 0.430, 0.620)):
        for louvre in range(9):
            rounded_box(
                f"ControlLouvre_{bank}_{louvre}",
                (width - 0.120, 0.008, 0.007),
                (center_x, BAY_FACE_Y - 0.013, bank_z + louvre * 0.016),
                "CaseworkShadow",
                target=target,
                parent=root,
                bevel=0.001,
                rotation=(math.radians(28.0), 0.0, 0.0),
            )
    for hinge_z in (BAY_FLOOR_Z + 0.090, top_z - 0.090):
        cylinder(
            f"ControlCabinetHinge_{hinge_z:.3f}",
            0.011,
            0.052,
            (left + 0.016, BAY_FACE_Y - 0.006, hinge_z),
            "BrushedStainless",
            target=target,
            parent=root,
            vertices=14,
            bevel=0.001,
        )
    # Door-interlocked main isolator: black body, red handle on a yellow plate.
    rounded_box(
        "ControlIsolatorPlate",
        (0.086, 0.006, 0.086),
        (right - 0.075, BAY_FACE_Y - 0.016, top_z - 0.085),
        "SafetyYellow",
        target=target,
        parent=root,
        bevel=0.003,
    )
    rounded_box(
        "ControlIsolatorBody",
        (0.058, 0.014, 0.058),
        (right - 0.075, BAY_FACE_Y - 0.024, top_z - 0.085),
        "PowderCoatBlack",
        target=target,
        parent=root,
        bevel=0.004,
    )
    rounded_box(
        "ControlIsolatorHandle",
        (0.052, 0.014, 0.014),
        (right - 0.075, BAY_FACE_Y - 0.036, top_z - 0.085),
        "SignalRed",
        target=target,
        parent=root,
        bevel=0.005,
        rotation=(math.radians(-42.0), 0.0, 0.0),
    )
    rounded_box(
        "ControlFilterFan",
        (0.148, 0.020, 0.148),
        (left + 0.130, BAY_FACE_Y - 0.018, top_z - 0.135),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.006,
    )
    for louvre in range(7):
        rounded_box(
            f"ControlFilterFanSlot_{louvre}",
            (0.124, 0.006, 0.010),
            (left + 0.130, BAY_FACE_Y - 0.029, top_z - 0.192 + louvre * 0.019),
            "CaseworkShadow",
            target=target,
            parent=root,
            bevel=0.0,
        )
    rounded_box(
        "ControlGlandPlate",
        (0.220, 0.012, 0.090),
        (center_x, BAY_FACE_Y - 0.010, BAY_FLOOR_Z + 0.062),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.004,
    )
    for gland in range(4):
        cylinder(
            f"ControlGland_{gland}",
            0.014,
            0.026,
            (center_x - 0.078 + gland * 0.052, BAY_FACE_Y - 0.022, BAY_FLOOR_Z + 0.062),
            "MachinedAluminum",
            target=target,
            parent=root,
            rotation=(math.pi / 2, 0.0, 0.0),
            vertices=6,
            bevel=0.001,
        )
    cylinder(
        "ControlCabinetLatch",
        0.016,
        0.020,
        (right - 0.026, BAY_FACE_Y - 0.018, BAY_FLOOR_Z + height / 2.0),
        "BrushedStainless",
        target=target,
        parent=root,
        rotation=(math.pi / 2, 0.0, 0.0),
        vertices=20,
        bevel=0.002,
    )
    rounded_box(
        "ControlCabinetBadge",
        (0.072, 0.003, 0.020),
        (left + 0.070, BAY_FACE_Y - 0.015, top_z - 0.040),
        "AnodizedAluminum",
        target=target,
        parent=root,
        bevel=0.002,
    )
    text_mesh(
        "ControlCabinetBadgeText",
        "OpenSDL",
        (left + 0.070, BAY_FACE_Y - 0.0175, top_z - 0.040),
        0.0090,
        "LabelGray",
        target=target,
        parent=root,
    )

    # The open drive bank.
    bank_left, bank_right = CONSUMABLE_X
    bank_center = (bank_left + bank_right) / 2.0
    rounded_box(
        "DriveBackplate",
        (bank_right - bank_left, 0.006, 0.400),
        (bank_center, 0.120, 0.500),
        "BrushedStainless",
        target=target,
        parent=root,
        bevel=0.002,
    )
    for rail_index, rail_z in enumerate((0.360, 0.520, 0.660)):
        rounded_box(
            f"DinRail_{rail_index}",
            (bank_right - bank_left - 0.020, 0.020, 0.012),
            (bank_center, 0.108, rail_z),
            "MachinedAluminum",
            target=target,
            parent=root,
            bevel=0.001,
        )
    # Wiring ducts between the rails, slotted the way real duct is.
    for duct_index, duct_z in enumerate((0.430, 0.590)):
        trunking(
            f"DriveDuct_{duct_index}",
            bank_right - bank_left - 0.020,
            "X",
            (bank_center, 0.098, duct_z),
            target=target,
            parent=root,
            width=0.032,
            height=0.036,
            fingers=12,
        )
    # Three servo drives on the bottom rail, finned, each with its own display.
    for drive in range(3):
        drive_x = bank_left + 0.060 + drive * 0.088
        rounded_box(
            f"ServoDrive_{drive}",
            (0.058, 0.110, 0.140),
            (drive_x, 0.062, 0.352),
            "PowderCoatGraphite",
            target=target,
            parent=root,
            bevel=0.003,
        )
        for fin in range(6):
            rounded_box(
                f"ServoDriveFin_{drive}_{fin}",
                (0.052, 0.004, 0.126),
                (drive_x, 0.010 + fin * 0.009, 0.352),
                "MachinedAluminum",
                target=target,
                parent=root,
                bevel=0.0,
            )
        rounded_box(
            f"ServoDriveDisplay_{drive}",
            (0.030, 0.004, 0.014),
            (drive_x, 0.005, 0.402),
            "ScreenCyan",
            target=target,
            parent=root,
            bevel=0.001,
        )
    # Two 24 V supplies and a breaker bank on the upper rails.
    for supply in range(2):
        rounded_box(
            f"ControlPsu_{supply}",
            (0.060, 0.104, 0.118),
            (bank_left + 0.075 + supply * 0.080, 0.064, 0.585),
            "BrushedStainless",
            target=target,
            parent=root,
            bevel=0.003,
        )
        cylinder(
            f"ControlPsuLed_{supply}",
            0.0032,
            0.004,
            (bank_left + 0.075 + supply * 0.080, 0.010, 0.620),
            "ScreenGreen",
            target=target,
            parent=root,
            rotation=(math.pi / 2, 0.0, 0.0),
            vertices=10,
            bevel=0.0004,
        )
    for breaker in range(8):
        rounded_box(
            f"ControlBreaker_{breaker}",
            (0.017, 0.072, 0.082),
            (bank_left + 0.246 + breaker * 0.0185, 0.078, 0.706),
            "PowderCoatGraphite" if breaker % 2 else "WhitePolymer",
            target=target,
            parent=root,
            bevel=0.001,
        )
        rounded_box(
            f"ControlBreakerToggle_{breaker}",
            (0.010, 0.012, 0.020),
            (bank_left + 0.246 + breaker * 0.0185, 0.040, 0.712),
            "SignalRed",
            target=target,
            parent=root,
            bevel=0.001,
        )
    for terminal in range(22):
        rounded_box(
            f"ControlTerminal_{terminal:02d}",
            (0.0055, 0.050, 0.046),
            (bank_left + 0.028 + terminal * 0.0062, 0.086, 0.688),
            "PowderCoatGraphite" if terminal % 4 else "SafetyYellow",
            target=target,
            parent=root,
            bevel=0.0,
        )
    # The clear guard over the live side.
    rounded_box(
        "DriveGuard",
        (bank_right - bank_left + 0.020, 0.005, 0.430),
        (bank_center, BAY_FACE_Y + 0.020, 0.500),
        "Polycarbonate",
        target=target,
        parent=root,
        bevel=0.002,
    )
    for guard_x in (bank_left - 0.004, bank_right + 0.004):
        extrusion(
            f"DriveGuardPost_{guard_x:+.3f}",
            0.450,
            "Z",
            (guard_x, BAY_FACE_Y + 0.030, 0.500),
            target=target,
            parent=root,
            profile=0.020,
            slots=False,
        )
    return root


def build_compute(cell_root: bpy.types.Object) -> bpy.types.Object:
    """The compute node that makes this a self-driving laboratory.

    Everything else on this frame is automation: it moves labware and it reads
    it.  What closes the loop is here - a rack inside the machine running the
    campaign, choosing the next experiment from the last measurement and issuing
    it.  The rack carries two nodes, a switch, their supply, and one display
    that shows the campaign as state rather than as prose: how many iterations
    have run, where they have been in parameter space, and whether the objective
    is still moving.
    """
    target = COLLECTIONS["Frame"]
    root = empty("ComputeRack", target=target, location=(0.0, 0.0, 0.0), parent=cell_root)
    left, right = RACK_X
    center_x = (left + right) / 2.0
    depth = 0.640
    center_y = BAY_FACE_Y + depth / 2.0
    top_z = 0.856
    height = top_z - BAY_FLOOR_Z

    rounded_box(
        "RackShell",
        (right - left, depth, height),
        (center_x, center_y, BAY_FLOOR_Z + height / 2.0),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.004,
    )
    rounded_box(
        "RackVoid",
        (right - left - 0.040, depth - 0.060, height - 0.070),
        (center_x, center_y + 0.006, BAY_FLOOR_Z + height / 2.0),
        "PowderCoatBlack",
        target=target,
        parent=root,
        bevel=0.003,
    )
    # 19 inch mounting rails with their square hole pattern.
    for rail_x in (center_x - 0.2415, center_x + 0.2415):
        rounded_box(
            f"RackRail_{rail_x:+.3f}",
            (0.016, 0.028, height - 0.080),
            (rail_x, BAY_FACE_Y + 0.028, BAY_FLOOR_Z + height / 2.0),
            "MachinedAluminum",
            target=target,
            parent=root,
            bevel=0.001,
        )
        for hole in range(21):
            rounded_box(
                f"RackHole_{rail_x:+.3f}_{hole:02d}",
                (0.0072, 0.006, 0.0072),
                (rail_x, BAY_FACE_Y + 0.015, BAY_FLOOR_Z + 0.052 + hole * 0.0308),
                "CaseworkShadow",
                target=target,
                parent=root,
                bevel=0.0,
            )
    unit = 0.04445
    face_y = BAY_FACE_Y + 0.014
    stack_z = BAY_FLOOR_Z + 0.050

    def rack_unit(name: str, units: float, material: str) -> float:
        nonlocal stack_z
        depth_z = units * unit
        rounded_box(
            name,
            (0.470, 0.030, depth_z - 0.003),
            (center_x, face_y, stack_z + depth_z / 2.0),
            material,
            target=target,
            parent=root,
            bevel=0.002,
        )
        top = stack_z + depth_z
        stack_z = top
        return stack_z - depth_z / 2.0

    psu_z = rack_unit("RackPsuShelf", 2.0, "BrushedStainless")
    for outlet in range(6):
        cylinder(
            f"RackPsuOutlet_{outlet}",
            0.0085,
            0.008,
            (center_x - 0.170 + outlet * 0.068, face_y - 0.018, psu_z),
            "PowderCoatBlack",
            target=target,
            parent=root,
            rotation=(math.pi / 2, 0.0, 0.0),
            vertices=14,
            bevel=0.0008,
        )
    for node in range(2):
        node_z = rack_unit(f"ComputeNode_{node}", 2.0, "PowderCoatGraphite")
        for bay in range(8):
            rounded_box(
                f"ComputeNodeBay_{node}_{bay}",
                (0.030, 0.006, 0.062),
                (center_x - 0.190 + bay * 0.036, face_y - 0.017, node_z),
                "MachinedAluminum",
                target=target,
                parent=root,
                bevel=0.001,
            )
            cylinder(
                f"ComputeNodeBayLed_{node}_{bay}",
                0.0018,
                0.003,
                (center_x - 0.190 + bay * 0.036, face_y - 0.021, node_z - 0.024),
                "ScreenGreen" if bay % 3 else "CyanIndicator",
                target=target,
                parent=root,
                rotation=(math.pi / 2, 0.0, 0.0),
                vertices=8,
                bevel=0.0002,
            )
        for vent in range(9):
            rounded_box(
                f"ComputeNodeVent_{node}_{vent}",
                (0.006, 0.004, 0.056),
                (center_x + 0.120 + vent * 0.009, face_y - 0.016, node_z),
                "CaseworkShadow",
                target=target,
                parent=root,
                bevel=0.0,
            )
        cylinder(
            f"ComputeNodePower_{node}",
            0.0055,
            0.004,
            (center_x + 0.215, face_y - 0.018, node_z + 0.022),
            "CyanIndicator",
            target=target,
            parent=root,
            rotation=(math.pi / 2, 0.0, 0.0),
            vertices=12,
            bevel=0.0004,
        )
    switch_z = rack_unit("RackSwitch", 1.0, "PowderCoatBlack")
    for port in range(12):
        rounded_box(
            f"RackSwitchPort_{port:02d}",
            (0.012, 0.005, 0.011),
            (center_x - 0.180 + port * 0.019, face_y - 0.016, switch_z),
            "CaseworkShadow",
            target=target,
            parent=root,
            bevel=0.0,
        )
        if port % 3 == 0:
            cylinder(
                f"RackSwitchLed_{port:02d}",
                0.0014,
                0.003,
                (center_x - 0.180 + port * 0.019, face_y - 0.019, switch_z + 0.010),
                "ScreenGreen",
                target=target,
                parent=root,
                rotation=(math.pi / 2, 0.0, 0.0),
                vertices=8,
                bevel=0.0002,
            )
    rack_unit("RackBlank", 2.0, "PowderCoatGraphite")
    build_optimizer_display(root, center_x, face_y, stack_z + 0.010, top_z)

    # Patch leads from the switch out to the trunking, with real slack.
    for lead in range(2):
        tube_path(
            f"RackPatch_{lead}",
            (
                (center_x - 0.150 + lead * 0.040, face_y - 0.020, switch_z),
                (center_x - 0.240 - lead * 0.020, face_y - 0.060 - lead * 0.012, switch_z - 0.070),
                (left + 0.020, 0.180, switch_z - 0.120),
            ),
            0.0028,
            "CableBlue" if lead else "CableBlack",
            target=target,
            parent=root,
        )
    return root


def build_optimizer_display(
    root: bpy.types.Object, center_x: float, face_y: float, bottom_z: float, top_z: float
) -> None:
    """The campaign, drawn as state.

    A parameter-space scatter that tightens toward one corner, a residual trend
    that flattens, the measured response of the last ten plates, and the
    iteration count.  No sentences: a machine does not narrate itself, and a
    person reading this panel from the aisle is reading whether the loop is
    converging, not what it says.
    """
    target = COLLECTIONS["Frame"]
    height = top_z - bottom_z - 0.014
    center_z = (bottom_z + top_z) / 2.0
    panel = empty(
        "ComputeDisplay",
        target=target,
        location=(center_x, face_y - 0.012, center_z),
        parent=root,
    )
    panel.rotation_euler = (math.radians(9.0), 0.0, 0.0)
    width = 0.470
    rounded_box(
        "ComputeDisplayBezel",
        (width, 0.022, height),
        (0.0, 0.0, 0.0),
        "PowderCoatBlack",
        target=target,
        parent=panel,
        bevel=0.004,
    )
    rounded_box(
        "ComputeDisplayGlass",
        (width - 0.024, 0.006, height - 0.022),
        (0.0, -0.010, 0.0),
        "ScreenGlass",
        target=target,
        parent=panel,
        bevel=0.002,
    )

    def mark(
        name: str,
        size: "Sequence[float]",
        position: "Sequence[float]",
        material: str,
    ) -> None:
        rounded_box(
            name,
            (size[0], 0.0022, size[1]),
            (position[0], -0.0142, position[1]),
            material,
            target=target,
            parent=panel,
            bevel=0.0,
        )

    # Left: the parameter space, sampled and converging on one corner.
    field = 0.150
    field_x = -0.115
    for edge, (size, offset) in enumerate(
        (
            ((field, 0.0015), (0.0, -field / 2.0)),
            ((field, 0.0015), (0.0, field / 2.0)),
            ((0.0015, field), (-field / 2.0, 0.0)),
            ((0.0015, field), (field / 2.0, 0.0)),
        )
    ):
        mark(
            f"ComputeDisplayFieldEdge_{edge}",
            size,
            (field_x + offset[0], offset[1]),
            "ScreenCyanDim",
        )
    for grid in range(1, 4):
        mark(
            f"ComputeDisplayGridX_{grid}",
            (0.0008, field - 0.004),
            (field_x - field / 2.0 + grid * field / 4.0, 0.0),
            "ScreenGridDim",
        )
        mark(
            f"ComputeDisplayGridY_{grid}",
            (field - 0.004, 0.0008),
            (field_x, -field / 2.0 + grid * field / 4.0),
            "ScreenGridDim",
        )
    target_x, target_y = 0.030, 0.034
    for sample in range(34):
        progress = sample / 33.0
        radius = 0.062 * (1.0 - progress) ** 1.55 + 0.0035
        angle = sample * 2.39996
        position = (
            field_x + target_x + radius * math.cos(angle),
            target_y + radius * math.sin(angle) * 0.92,
        )
        mark(
            f"ComputeDisplaySample_{sample:02d}",
            (0.0052, 0.0052),
            position,
            "ScreenCyan" if progress > 0.72 else "ScreenCyanDim",
        )
    mark(
        "ComputeDisplayBestX",
        (0.020, 0.0012),
        (field_x + target_x, target_y),
        "ScreenAmber",
    )
    mark(
        "ComputeDisplayBestY",
        (0.0012, 0.020),
        (field_x + target_x, target_y),
        "ScreenAmber",
    )

    # Right, upper: the iteration count.
    text_mesh(
        "ComputeDisplayIteration",
        "27",
        (0.062, -0.0146, 0.052),
        0.042,
        "ScreenCyan",
        target=target,
        parent=panel,
        rotation=(math.pi / 2, 0.0, 0.0),
        align="LEFT",
        extrude=0.0004,
    )
    text_mesh(
        "ComputeDisplayBudget",
        "/48",
        (0.128, -0.0146, 0.042),
        0.017,
        "ScreenCyanDim",
        target=target,
        parent=panel,
        rotation=(math.pi / 2, 0.0, 0.0),
        align="LEFT",
        extrude=0.0004,
    )
    # Right, middle: the residual trend, flattening.
    for step in range(22):
        value = 0.052 * math.exp(-step / 6.2) + 0.0035
        mark(
            f"ComputeDisplayTrend_{step:02d}",
            (0.0055, value),
            (0.062 + step * 0.0078, -0.006 + value / 2.0),
            "ScreenAmber" if step > 17 else "ScreenCyanDim",
        )
    mark("ComputeDisplayTrendAxis", (0.180, 0.0010), (0.148, -0.008), "ScreenGridDim")
    # Right, lower: the measured response of the last ten plates.
    for swatch in range(10):
        mark(
            f"ComputeDisplaySwatch_{swatch}",
            (0.0135, 0.0135),
            (0.066 + swatch * 0.0170, -0.036),
            "SwatchWarm" if swatch % 3 == 0 else ("SwatchCool" if swatch % 3 == 1 else "SwatchMid"),
        )
    mark("ComputeDisplayProgressTrack", (0.180, 0.0055), (0.148, -0.058), "ScreenGridDim")
    mark("ComputeDisplayProgressFill", (0.101, 0.0055), (0.1085, -0.058), "ScreenCyan")


def build_fluidics(cell_root: bpy.types.Object) -> bpy.types.Object:
    """Bulk reagent supply on the service plane, plumbed up to the deck."""
    target = COLLECTIONS["Frame"]
    root = empty("Fluidics", target=target, location=(0.0, 0.0, 0.0), parent=cell_root)
    for index, (x, glass, contents) in enumerate(
        (
            (-0.130, "HDPEWhite", "SampleBlue"),
            (0.030, "AmberGlass", "SampleViolet"),
            (0.190, "HDPEWhite", "SwatchWarm"),
        )
    ):
        _reagent_bottle(
            f"SupplyBottle_{index}",
            (x, 0.160, SERVICE_TOP_Z),
            radius=0.052,
            height=0.230,
            glass=glass,
            target=target,
            parent=root,
        )
        # The reagent itself.  Three bottles of coloured stock is what a colour
        # campaign actually runs on, and it is honest colour rather than paint.
        cylinder(
            f"SupplyBottleContents_{index}",
            0.047,
            0.104,
            (x, 0.160, SERVICE_TOP_Z + 0.052),
            contents,
            target=target,
            parent=root,
            vertices=20,
            bevel=0.002,
        )
        tube_path(
            f"SupplyLine_{index}",
            (
                (x, 0.160, SERVICE_TOP_Z + 0.226),
                (x + 0.060, 0.330, SERVICE_TOP_Z + 0.320),
                (0.120, 0.462, 1.060),
                (0.120, 0.462, 1.300),
            ),
            0.0030,
            "CableBlue",
            target=target,
            parent=root,
        )
    # Peristaltic supply pump: head, rotor, motor can.
    rounded_box(
        "SupplyPump",
        (0.132, 0.150, 0.118),
        (0.430, 0.160, SERVICE_TOP_Z + 0.059),
        "InstrumentGrey",
        target=target,
        parent=root,
        bevel=0.006,
    )
    cylinder(
        "SupplyPumpHead",
        0.044,
        0.030,
        (0.430, 0.075, SERVICE_TOP_Z + 0.070),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        rotation=(math.pi / 2, 0.0, 0.0),
        vertices=24,
        bevel=0.002,
    )
    for roller in range(3):
        angle = roller * 2.0 * math.pi / 3.0
        cylinder(
            f"SupplyPumpRoller_{roller}",
            0.0075,
            0.024,
            (
                0.430 + 0.026 * math.cos(angle),
                0.062,
                SERVICE_TOP_Z + 0.070 + 0.026 * math.sin(angle),
            ),
            "BrushedStainless",
            target=target,
            parent=root,
            rotation=(math.pi / 2, 0.0, 0.0),
            vertices=12,
            bevel=0.0006,
        )
    cylinder(
        "SupplyPumpMotor",
        0.038,
        0.090,
        (0.430, 0.245, SERVICE_TOP_Z + 0.070),
        "BrushedStainless",
        target=target,
        parent=root,
        rotation=(math.pi / 2, 0.0, 0.0),
        vertices=20,
        bevel=0.002,
    )
    # The supply manifold on the rear plane, and the drop to the deck bulkhead.
    rounded_box(
        "SupplyManifold",
        (0.150, 0.052, 0.056),
        (0.120, 0.470, 1.330),
        "MachinedAluminum",
        target=target,
        parent=root,
        bevel=0.004,
    )
    for port in range(3):
        cylinder(
            f"SupplyManifoldPort_{port}",
            0.0075,
            0.020,
            (0.070 + port * 0.050, 0.470, 1.298),
            "BrushedStainless",
            target=target,
            parent=root,
            vertices=12,
            bevel=0.0008,
        )
    tube_path(
        "SupplyDrop",
        (
            (0.120, 0.470, 1.362),
            (-0.400, 0.484, 1.400),
            (-0.900, 0.470, 1.330),
            (-0.900, 0.446, 1.180),
        ),
        0.0042,
        "CableBlue",
        target=target,
        parent=root,
    )
    rounded_box(
        "SupplyBulkhead",
        (0.056, 0.026, 0.044),
        (-0.900, 0.436, 1.158),
        "MachinedAluminum",
        target=target,
        parent=root,
        bevel=0.003,
    )
    _tip_box_stack(
        "ConsumableBuffer",
        (0.430, 0.330, SERVICE_TOP_Z),
        3,
        "TipBoxBlue",
        target=target,
        parent=root,
    )
    return root


def build_waste_column(cell_root: bpy.types.Object) -> bpy.types.Object:
    """Tip and liquid waste, taken down through the deck to the base.

    A self-driving cell has to be able to throw things away for as long as it
    runs.  The chute drops straight off the deck into a clear-fronted tip bin,
    and the liquid line runs to a carboy on the base plane beside it, so how
    long the machine can run unattended is legible from the front.
    """
    target = COLLECTIONS["Frame"]
    root = empty("WasteColumn", target=target, location=(0.0, 0.0, 0.0), parent=cell_root)
    chute_y = ROW_BACK
    rounded_box(
        "WasteChuteDuct",
        (0.104, 0.076, 0.470),
        (WASTE_X, chute_y, 0.880),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.004,
    )
    rounded_box(
        "WasteChuteTransition",
        (0.150, 0.150, 0.090),
        (WASTE_X, chute_y - 0.030, 0.600),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.010,
    )
    bin_z = BAY_FLOOR_Z + 0.230
    rounded_box(
        "WasteBinShell",
        (0.230, 0.220, 0.450),
        (WASTE_X, chute_y - 0.070, bin_z),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.006,
    )
    rounded_box(
        "WasteBinWindow",
        (0.176, 0.010, 0.360),
        (WASTE_X, chute_y - 0.180, bin_z),
        "Polycarbonate",
        target=target,
        parent=root,
        bevel=0.004,
    )
    rounded_box(
        "WasteBinVoid",
        (0.190, 0.180, 0.390),
        (WASTE_X, chute_y - 0.068, bin_z),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.004,
    )
    for tip in range(52):
        angle = tip * 1.71
        cylinder(
            f"WasteTip_{tip:02d}",
            0.0018,
            0.044,
            (
                WASTE_X + 0.072 * math.cos(angle),
                chute_y - 0.086 + 0.056 * math.sin(angle * 1.31),
                BAY_FLOOR_Z + 0.026 + (tip % 7) * 0.013,
            ),
            "ClearLabware",
            target=target,
            parent=root,
            rotation=(math.radians(78.0), 0.0, angle),
            vertices=8,
            bevel=0.0,
        )
    rounded_box(
        "WasteBinHandle",
        (0.090, 0.016, 0.016),
        (WASTE_X, chute_y - 0.192, bin_z + 0.250),
        "BrushedStainless",
        target=target,
        parent=root,
        bevel=0.006,
    )
    # Liquid waste carboy beside the bin, with its line coming down the frame.
    carboy_z = BAY_FLOOR_Z
    cylinder(
        "WasteCarboy",
        0.108,
        0.300,
        (-0.930, 0.090, carboy_z + 0.150),
        "HDPEWhite",
        target=target,
        parent=root,
        vertices=24,
        bevel=0.010,
    )
    cylinder(
        "WasteCarboyShoulder",
        0.062,
        0.070,
        (-0.930, 0.090, carboy_z + 0.334),
        "HDPEWhite",
        target=target,
        parent=root,
        vertices=20,
        bevel=0.012,
    )
    cylinder(
        "WasteCarboyCap",
        0.036,
        0.026,
        (-0.930, 0.090, carboy_z + 0.380),
        "HDPEBlueCap",
        target=target,
        parent=root,
        vertices=16,
        bevel=0.002,
    )
    rounded_box(
        "WasteCarboyLabel",
        (0.110, 0.002, 0.070),
        (-0.930, -0.020, carboy_z + 0.170),
        "SafetyYellow",
        target=target,
        parent=root,
        bevel=0.001,
    )
    tube_path(
        "WasteLine",
        (
            (-0.930, 0.090, carboy_z + 0.396),
            (-0.960, 0.300, 0.640),
            (-0.905, 0.436, 1.120),
        ),
        0.0050,
        "CableBlack",
        target=target,
        parent=root,
    )
    return root


def build_transfer_port(cell_root: bpy.types.Object) -> bpy.types.Object:
    """The one place a person touches this machine.

    Everything else here runs without hands.  Material comes in and goes out
    through a single interlocked transfer nest at the front-left of the frame: a
    framed aperture in the only panel on the front of the machine, a roller bed
    through it, a guard standing open, an enable lamp and a palm button.  A
    plate set down here is the machine's from that moment on.
    """
    target = COLLECTIONS["Frame"]
    root = empty("TransferPort", target=target, location=(0.0, 0.0, 0.0), parent=cell_root)
    center_x = -1.560
    front_y, rear_y = -0.536, -0.180
    bed_z = 1.135
    panel_half = 0.235
    aperture_half = 0.160
    # The surround: the only sheet panel on the front of this machine, and it is
    # here because material crosses the boundary at exactly this point.
    for label, size, offset in (
        (
            "Left",
            (panel_half - aperture_half, 0.010, 0.560),
            (-(panel_half + aperture_half) / 2.0, 0.0),
        ),
        (
            "Right",
            (panel_half - aperture_half, 0.010, 0.560),
            ((panel_half + aperture_half) / 2.0, 0.0),
        ),
        ("Head", (2 * aperture_half, 0.010, 0.150), (0.0, 0.205)),
        ("Sill", (2 * aperture_half, 0.010, 0.130), (0.0, -0.215)),
    ):
        rounded_box(
            f"TransferPortSurround{label}",
            size,
            (center_x + offset[0], front_y, bed_z - 0.070 + offset[1]),
            "InstrumentGrey",
            target=target,
            parent=root,
            bevel=0.004,
        )
    rounded_box(
        "TransferPortReveal",
        (2 * aperture_half + 0.012, 0.014, 0.216),
        (center_x, front_y + 0.004, bed_z + 0.048),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.004,
    )
    rounded_box(
        "TransferPortBed",
        (0.300, rear_y - front_y, 0.012),
        (center_x, (front_y + rear_y) / 2.0, bed_z - 0.006),
        "BrushedStainless",
        target=target,
        parent=root,
        bevel=0.003,
    )
    for roller in range(5):
        cylinder(
            f"TransferPortRoller_{roller}",
            0.011,
            0.250,
            (center_x, front_y + 0.046 + roller * 0.066, bed_z + 0.009),
            "MachinedAluminum",
            target=target,
            parent=root,
            rotation=(0.0, math.pi / 2, 0.0),
            vertices=16,
            bevel=0.001,
        )
    for side in (-1.0, 1.0):
        extrusion(
            f"TransferPortRail_{side:+.0f}",
            rear_y - front_y,
            "Y",
            (center_x + side * 0.166, (front_y + rear_y) / 2.0, bed_z + 0.008),
            target=target,
            parent=root,
            profile=0.030,
            slots=False,
        )
        extrusion(
            f"TransferPortLeg_{side:+.0f}",
            bed_z - FRAME_MOUNT_Z,
            "Z",
            (center_x + side * 0.166, front_y + 0.060, (bed_z + FRAME_MOUNT_Z) / 2.0),
            target=target,
            parent=root,
            profile=0.030,
            slots=False,
        )
    # The guard, hinged at the head of the aperture and standing open.
    hinge_z = bed_z + 0.156
    guard_length = 0.300
    rounded_box(
        "TransferPortGuard",
        (2 * aperture_half, 0.006, guard_length),
        (
            center_x,
            front_y - guard_length / 2.0 * math.cos(math.radians(24.0)),
            hinge_z + guard_length / 2.0 * math.sin(math.radians(24.0)),
        ),
        "Polycarbonate",
        target=target,
        parent=root,
        bevel=0.003,
        rotation=(math.radians(66.0), 0.0, 0.0),
    )
    rounded_box(
        "TransferPortGuardHinge",
        (2 * aperture_half + 0.020, 0.024, 0.024),
        (center_x, front_y - 0.008, hinge_z),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.006,
    )
    rounded_box(
        "TransferPortGuardHandle",
        (0.120, 0.018, 0.018),
        (
            center_x,
            front_y - guard_length * math.cos(math.radians(24.0)) - 0.010,
            hinge_z + guard_length * math.sin(math.radians(24.0)),
        ),
        "BrushedStainless",
        target=target,
        parent=root,
        bevel=0.006,
    )
    # The control set: enable lamp, palm button, and the interlock switch that
    # says the boundary is closed.
    cylinder(
        "TransferPortEnable",
        0.018,
        0.014,
        (center_x - 0.196, front_y - 0.011, bed_z + 0.052),
        "AmberIndicator",
        target=target,
        parent=root,
        rotation=(math.pi / 2, 0.0, 0.0),
        vertices=20,
        bevel=0.001,
    )
    cylinder(
        "TransferPortPalmButton",
        0.026,
        0.016,
        (center_x + 0.196, front_y - 0.013, bed_z + 0.052),
        "ScreenGreen",
        target=target,
        parent=root,
        rotation=(math.pi / 2, 0.0, 0.0),
        vertices=24,
        bevel=0.003,
    )
    rounded_box(
        "TransferPortInterlock",
        (0.026, 0.030, 0.052),
        (center_x + aperture_half + 0.008, front_y - 0.014, bed_z + 0.148),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.003,
    )
    rounded_box(
        "TransferPortTag",
        (0.120, 0.002, 0.024),
        (center_x, front_y - 0.006, bed_z - 0.108),
        "LabelWhite",
        target=target,
        parent=root,
        bevel=0.001,
    )
    text_mesh(
        "TransferPortTagText",
        "LOAD / UNLOAD",
        (center_x, front_y - 0.008, bed_z - 0.108),
        0.0110,
        "LabelGray",
        target=target,
        parent=root,
    )
    return root


def build_machine_services(cell_root: bpy.types.Object) -> bpy.types.Object:
    """Trunking, conduit, the beacon and the emergency stops.

    A machine carries its own services on its own structure.  Trunking runs the
    length of the base and the top tie, conduit drops from the cabinet to each
    driven axis, one beacon on the left tower states machine state to the room,
    and two mushroom heads on the front rail stop it.
    """
    target = COLLECTIONS["Frame"]
    root = empty("MachineServices", target=target, location=(0.0, 0.0, 0.0), parent=cell_root)
    front_y, rear_y = FRAME_POST_Y
    span = 2 * (FRAME_HALF_LENGTH - FRAME_POST_HALF) - 0.20
    trunking(
        "BaseTrunking",
        span,
        "X",
        (0.0, rear_y - 0.052, FRAME_BASE_Z + 0.062),
        target=target,
        parent=root,
    )
    trunking(
        "TopTrunking",
        span,
        "X",
        (0.0, rear_y - 0.050, FRAME_TOP_RAIL_Z - 0.070),
        target=target,
        parent=root,
        width=0.048,
        height=0.048,
    )
    trunking(
        "RiserTrunking",
        FRAME_TOP_RAIL_Z - FRAME_BASE_Z - 0.20,
        "Z",
        (
            FRAME_CORNER_X[0] + 0.052,
            rear_y - 0.052,
            (FRAME_TOP_RAIL_Z + FRAME_BASE_Z) / 2.0,
        ),
        target=target,
        parent=root,
        width=0.048,
        height=0.048,
    )
    for index, (start, finish) in enumerate(
        (
            (
                (CABINET_X[1] - 0.020, 0.300, 0.680),
                (FRAME_CORNER_X[0] + 0.070, rear_y - 0.080, 0.520),
            ),
            ((CONSUMABLE_X[0] + 0.030, 0.140, 0.760), (0.240, rear_y - 0.076, 1.020)),
            ((0.500, rear_y - 0.076, 1.180), (0.500, rear_y - 0.060, FRAME_TOP_RAIL_Z - 0.130)),
        )
    ):
        tube_path(
            f"MachineConduit_{index}",
            (
                start,
                (
                    (start[0] + finish[0]) / 2.0,
                    (start[1] + finish[1]) / 2.0 - 0.040,
                    (start[2] + finish[2]) / 2.0 - 0.050,
                ),
                finish,
            ),
            0.0125,
            ("CableBlack", "CableOrange", "CableBlack")[index],
            target=target,
            parent=root,
        )
    # The status beacon on the left tower.
    beacon_x, beacon_y = FRAME_CORNER_X[0], rear_y
    cylinder(
        "BeaconPole",
        0.011,
        0.150,
        (beacon_x, beacon_y, FRAME_TOP_Z + 0.075),
        "BrushedStainless",
        target=target,
        parent=root,
        vertices=14,
        bevel=0.001,
    )
    cylinder(
        "BeaconBase",
        0.036,
        0.030,
        (beacon_x, beacon_y, FRAME_TOP_Z + 0.165),
        "PowderCoatBlack",
        target=target,
        parent=root,
        vertices=24,
        bevel=0.002,
    )
    for tier, material in enumerate(("BeaconGreen", "BeaconAmber", "BeaconRed")):
        cylinder(
            f"BeaconLens_{tier}",
            0.036,
            0.052,
            (beacon_x, beacon_y, FRAME_TOP_Z + 0.206 + tier * 0.054),
            material,
            target=target,
            parent=root,
            vertices=24,
            bevel=0.003,
        )
    cylinder(
        "BeaconCap",
        0.037,
        0.014,
        (beacon_x, beacon_y, FRAME_TOP_Z + 0.375),
        "PowderCoatBlack",
        target=target,
        parent=root,
        vertices=24,
        bevel=0.003,
    )
    # Emergency stops on the front rail, one at each end of the machine.
    for index, stop_x in enumerate((-1.180, 1.180)):
        rounded_box(
            f"EstopPlate_{index}",
            (0.104, 0.008, 0.104),
            (stop_x, front_y - 0.026, FRAME_DECK_RAIL_Z + 0.010),
            "SafetyYellow",
            target=target,
            parent=root,
            bevel=0.004,
        )
        cylinder(
            f"EstopCollar_{index}",
            0.026,
            0.016,
            (stop_x, front_y - 0.036, FRAME_DECK_RAIL_Z + 0.026),
            "PowderCoatBlack",
            target=target,
            parent=root,
            rotation=(math.pi / 2, 0.0, 0.0),
            vertices=24,
            bevel=0.002,
        )
        cylinder(
            f"EstopHead_{index}",
            0.030,
            0.020,
            (stop_x, front_y - 0.050, FRAME_DECK_RAIL_Z + 0.026),
            "SignalRed",
            target=target,
            parent=root,
            rotation=(math.pi / 2, 0.0, 0.0),
            vertices=28,
            bevel=0.006,
        )
        text_mesh(
            f"EstopText_{index}",
            "EMERGENCY STOP",
            (stop_x, front_y - 0.031, FRAME_DECK_RAIL_Z - 0.026),
            0.0058,
            "PowderCoatBlack",
            target=target,
            parent=root,
        )
        rounded_box(
            f"EstopBracket_{index}",
            (0.060, 0.024, 0.060),
            (stop_x, front_y - 0.012, FRAME_DECK_RAIL_Z + 0.010),
            "PowderCoatGraphite",
            target=target,
            parent=root,
            bevel=0.003,
        )
    # The machine nameplate, on the front rail between the two stops.
    rounded_box(
        "MachineNameplate",
        (0.164, 0.004, 0.030),
        (0.0, front_y - 0.024, FRAME_DECK_RAIL_Z),
        "AnodizedAluminum",
        target=target,
        parent=root,
        bevel=0.002,
    )
    text_mesh(
        "MachineNameplateText",
        "OpenSDL  SDL-01",
        (0.0, front_y - 0.027, FRAME_DECK_RAIL_Z),
        0.0110,
        "PowderCoatGraphite",
        target=target,
        parent=root,
    )
    return root


def build_room() -> None:
    """The plant space the machine is installed in.

    Not a laboratory: a sealed volume with services in the ceiling and one
    service door.  Resin floor over the slab, plain painted panel walls, an
    exposed soffit carrying linear battens, a cable ladder and a duct run.  The
    room exists to be the ground the machine stands on and the dark it reads
    against; nothing in it is here for an occupant.
    """
    target = COLLECTIONS["Environment"]
    width = 2 * ROOM_HALF_X
    depth = ROOM_DEPTH
    center_y = ROOM_WALL_Y - depth / 2.0

    rounded_box(
        "Floor",
        (width, depth, ROOM_BUILD_UP),
        (0.0, center_y, -ROOM_BUILD_UP / 2.0),
        "Floor",
        target=target,
        bevel=0.0,
    )
    # Saw-cut movement joints in the slab, on the machine axis.
    for index, joint_y in enumerate((ROOM_WALL_Y - 1.35, ROOM_WALL_Y - 3.05, ROOM_WALL_Y - 4.60)):
        rounded_box(
            f"FloorJoint_{index}",
            (width, 0.008, 0.0018),
            (0.0, joint_y, 0.0009),
            "CaseworkShadow",
            target=target,
            bevel=0.0,
        )

    walls = (
        ("Rear", (width, ROOM_BUILD_UP, ROOM_CEILING_Z), (0.0, ROOM_WALL_Y + ROOM_BUILD_UP / 2.0)),
        (
            "Front",
            (width, ROOM_BUILD_UP, ROOM_CEILING_Z),
            (0.0, ROOM_FRONT_Y - ROOM_BUILD_UP / 2.0),
        ),
        (
            "Left",
            (ROOM_BUILD_UP, depth, ROOM_CEILING_Z),
            (-ROOM_HALF_X - ROOM_BUILD_UP / 2.0, center_y),
        ),
        (
            "Right",
            (ROOM_BUILD_UP, depth, ROOM_CEILING_Z),
            (ROOM_HALF_X + ROOM_BUILD_UP / 2.0, center_y),
        ),
    )
    for name, size, (x, y) in walls:
        rounded_box(
            f"Wall{name}",
            size,
            (x, y, ROOM_CEILING_Z / 2.0),
            "Wall",
            target=target,
            bevel=0.0,
        )
    # Panel joints, so the walls read as a lined plant space rather than as an
    # infinite backdrop.
    for index in range(1, 6):
        rounded_box(
            f"WallJointRear_{index}",
            (0.010, 0.006, ROOM_CEILING_Z),
            (-ROOM_HALF_X + index * width / 6.0, ROOM_WALL_Y - 0.003, ROOM_CEILING_Z / 2.0),
            "WallLower",
            target=target,
            bevel=0.0,
        )
    for name, size, (x, y) in (
        ("Rear", (width, 0.014, SKIRTING_HEIGHT), (0.0, ROOM_WALL_Y - 0.007)),
        ("Left", (0.014, depth, SKIRTING_HEIGHT), (-ROOM_HALF_X + 0.007, center_y)),
        ("Right", (0.014, depth, SKIRTING_HEIGHT), (ROOM_HALF_X - 0.007, center_y)),
        ("Front", (width, 0.014, SKIRTING_HEIGHT), (0.0, ROOM_FRONT_Y + 0.007)),
    ):
        rounded_box(
            f"Skirting{name}",
            size,
            (x, y, SKIRTING_HEIGHT / 2.0),
            "Floor",
            target=target,
            bevel=0.0,
        )

    # Exposed soffit.
    rounded_box(
        "CeilingSlab",
        (width, depth, 0.140),
        (0.0, center_y, ROOM_CEILING_Z + 0.070),
        "CeilingTile",
        target=target,
        bevel=0.0,
    )
    for index in range(1, 5):
        rounded_box(
            f"CeilingBeam_{index}",
            (width, 0.130, 0.150),
            (0.0, ROOM_WALL_Y - index * depth / 5.0, ROOM_CEILING_Z - 0.075),
            "CeilingTile",
            target=target,
            bevel=0.0,
        )
    for index, (x, y, z) in enumerate(BATTEN_RUNS):
        rounded_box(
            f"BattenBody_{index:02d}",
            (2 * ROOM_HALF_X - 0.60, BATTEN_WIDTH + 0.024, 0.070),
            (x, y, z + 0.035),
            "CeilingGrid",
            target=target,
            bevel=0.004,
        )
        rounded_box(
            f"BattenDiffuser_{index:02d}",
            (2 * ROOM_HALF_X - 0.62, BATTEN_WIDTH, 0.016),
            (x, y, z - 0.008),
            "TrofferDiffuser",
            target=target,
            bevel=0.004,
        )
        for drop in (-2.20, 0.0, 2.20):
            cylinder(
                f"BattenDrop_{index:02d}_{drop:+.2f}",
                0.005,
                ROOM_CEILING_Z - z - 0.070,
                (drop, y, (ROOM_CEILING_Z + z + 0.035) / 2.0),
                "BrushedStainless",
                target=target,
                vertices=8,
                bevel=0.0,
            )
    # Cable ladder over the machine and one duct run behind it.
    ladder_y, ladder_z = ROOM_WALL_Y - 0.42, 2.890
    for side in (-1.0, 1.0):
        rounded_box(
            f"CableLadderRail_{side:+.0f}",
            (2 * ROOM_HALF_X, 0.020, 0.090),
            (0.0, ladder_y + side * 0.140, ladder_z),
            "CeilingGrid",
            target=target,
            bevel=0.003,
        )
    for rung in range(19):
        rounded_box(
            f"CableLadderRung_{rung:02d}",
            (0.028, 0.280, 0.014),
            (-ROOM_HALF_X + 0.20 + rung * 0.32, ladder_y, ladder_z - 0.030),
            "CeilingGrid",
            target=target,
            bevel=0.002,
        )
    for cable in range(3):
        tube_path(
            f"CableLadderRun_{cable}",
            (
                (-ROOM_HALF_X + 0.10, ladder_y - 0.06 + cable * 0.05, ladder_z + 0.016),
                (0.0, ladder_y - 0.06 + cable * 0.05, ladder_z + 0.012),
                (ROOM_HALF_X - 0.10, ladder_y - 0.06 + cable * 0.05, ladder_z + 0.016),
            ),
            0.011,
            "CableBlack" if cable else "CableBlue",
            target=target,
        )
    rounded_box(
        "SupplyDuct",
        (2 * ROOM_HALF_X, 0.420, 0.300),
        (0.0, ROOM_WALL_Y - 2.65, ROOM_CEILING_Z - 0.330),
        "CeilingGrid",
        target=target,
        bevel=0.010,
    )
    for index, duct_x in enumerate((-1.60, 0.40, 2.20)):
        cylinder(
            f"SupplyDuctDrop_{index}",
            0.090,
            0.170,
            (duct_x, ROOM_WALL_Y - 2.65, ROOM_CEILING_Z - 0.560),
            "CeilingGrid",
            target=target,
            vertices=20,
            bevel=0.004,
        )
        rounded_box(
            f"SupplyDuctDiffuser_{index}",
            (0.280, 0.280, 0.024),
            (duct_x, ROOM_WALL_Y - 2.65, ROOM_CEILING_Z - 0.652),
            "CeilingGrid",
            target=target,
            bevel=0.004,
        )
    for index, (x, y) in enumerate(((-2.30, -1.05), (0.85, -2.55), (2.35, -3.60))):
        cylinder(
            f"SprinklerHead_{index:02d}",
            0.007,
            0.060,
            (x, y, ROOM_CEILING_Z - 0.060),
            "MachinedAluminum",
            target=target,
            vertices=12,
            bevel=0.001,
        )
    # The panel board the machine is fed from, and its conduit to the ladder.
    rounded_box(
        "PanelBoard",
        (0.090, 0.520, 0.700),
        (-ROOM_HALF_X + 0.045, -1.30, 1.500),
        "PowderCoatGraphite",
        target=target,
        bevel=0.006,
    )
    rounded_box(
        "PanelBoardDoor",
        (0.014, 0.480, 0.660),
        (-ROOM_HALF_X + 0.096, -1.30, 1.500),
        "PowderCoatGraphite",
        target=target,
        bevel=0.004,
    )
    rounded_box(
        "PanelBoardHandle",
        (0.020, 0.016, 0.090),
        (-ROOM_HALF_X + 0.110, -1.53, 1.500),
        "SignalRed",
        target=target,
        bevel=0.004,
    )
    tube_path(
        "PanelBoardConduit",
        (
            (-ROOM_HALF_X + 0.070, -1.30, 1.860),
            (-ROOM_HALF_X + 0.070, -1.10, 2.400),
            (-ROOM_HALF_X + 0.120, ladder_y, ladder_z - 0.040),
        ),
        0.013,
        "CeilingGrid",
        target=target,
    )
    build_service_door()


def build_service_door() -> None:
    """One flush steel service door in the left wall."""
    target = COLLECTIONS["Environment"]
    x_face = -ROOM_HALF_X
    frame_depth = 0.060
    for side in (-1.0, 1.0):
        rounded_box(
            f"DoorJamb_{side:+.0f}",
            (frame_depth, 0.060, DOOR_HEIGHT + 0.060),
            (
                x_face + frame_depth / 2.0,
                DOOR_CENTER_Y + side * (DOOR_WIDTH / 2.0 + 0.030),
                (DOOR_HEIGHT + 0.060) / 2.0,
            ),
            "DoorFrame",
            target=target,
            bevel=0.004,
        )
    rounded_box(
        "DoorHead",
        (frame_depth, DOOR_WIDTH + 0.120, 0.060),
        (x_face + frame_depth / 2.0, DOOR_CENTER_Y, DOOR_HEIGHT + 0.030),
        "DoorFrame",
        target=target,
        bevel=0.004,
    )
    rounded_box(
        "DoorReveal",
        (0.030, DOOR_WIDTH, DOOR_HEIGHT),
        (x_face - 0.075, DOOR_CENTER_Y, DOOR_HEIGHT / 2.0),
        "CaseworkShadow",
        target=target,
        bevel=0.0,
    )
    rounded_box(
        "DoorLeaf",
        (0.052, DOOR_WIDTH - 0.010, DOOR_HEIGHT - 0.010),
        (x_face - 0.008, DOOR_CENTER_Y, DOOR_HEIGHT / 2.0),
        "DoorLeaf",
        target=target,
        bevel=0.004,
    )
    for rib in range(2):
        rounded_box(
            f"DoorLeafRib_{rib}",
            (0.056, DOOR_WIDTH - 0.140, 0.010),
            (x_face - 0.008, DOOR_CENTER_Y, 0.700 + rib * 0.760),
            "DoorFrame",
            target=target,
            bevel=0.002,
        )
    rounded_box(
        "DoorKickPlate",
        (0.058, DOOR_WIDTH - 0.050, 0.320),
        (x_face - 0.008, DOOR_CENTER_Y, 0.180),
        "BrushedStainless",
        target=target,
        bevel=0.002,
    )
    rounded_box(
        "DoorHandleLever",
        (0.024, 0.140, 0.024),
        (x_face - 0.048, DOOR_CENTER_Y - 0.420, 1.060),
        "BrushedStainless",
        target=target,
        bevel=0.009,
    )
    for side in (-1.0, 1.0):
        cylinder(
            f"DoorHinge_{side:+.0f}",
            0.014,
            0.100,
            (
                x_face - 0.030,
                DOOR_CENTER_Y + DOOR_WIDTH / 2.0 - 0.012,
                DOOR_HEIGHT / 2.0 + side * 0.740,
            ),
            "BrushedStainless",
            target=target,
            vertices=14,
            bevel=0.001,
        )


def slot_position(slot_id: str) -> tuple[float, float]:
    """World (x, y) of a slot, derived from its station rather than stored."""
    station, offset_x, y = SLOT_TABLE[slot_id]
    return STATION_X[station] + offset_x, y


def node_case(identifier: str) -> str:
    """``tip-waste`` -> ``TipWaste``.  Ids are lower-case; node names are not."""
    return "".join(part.capitalize() for part in identifier.split("-"))


def build_stations(cell_root: bpy.types.Object) -> dict[str, tuple[float, float, float]]:
    """Place the five workflow positions and return the world slot table.

    The station empties carry identity and the features that belong to each
    position.  The plate they all sit on is built once, by :func:`build_decks`.
    """
    target = COLLECTIONS["Cell"]
    slots: dict[str, tuple[float, float, float]] = {}
    for slot_id in SLOT_TABLE:
        x, y = slot_position(slot_id)
        slots[slot_id] = (x, y, DECK_Z + 0.004)

    build_decks(cell_root)

    for name in STATION_ORDER:
        station = empty(
            f"Station_{node_case(name)}",
            target=target,
            location=(0.0, 0.0, 0.0),
            parent=cell_root,
        )
        station["opensdlStation"] = name
        deck_ids = [slot for slot in DECK_SLOTS if SLOT_TABLE[slot][0] == name]
        if not deck_ids:
            # A hotel brings its own presentation surface.  It bolts straight to
            # the frame's mounting plane through a machined footplate, which is
            # what puts its nest level with the process deck without any of it
            # standing on a worktop.
            rounded_box(
                f"Station_{node_case(name)}_Footplate",
                (0.34, 0.62, 0.008),
                (STATION_X[name], ROW_FRONT + 0.10, BENCH_Z - 0.004),
                "PowderCoatGraphite",
                target=target,
                parent=station,
                bevel=0.003,
            )
            for corner_x, corner_y in (
                (-0.140, -0.284),
                (0.140, -0.284),
                (-0.140, 0.284),
                (0.140, 0.284),
            ):
                screw(
                    f"Station_{node_case(name)}_Screw_{corner_x:+.3f}_{corner_y:+.3f}",
                    (
                        STATION_X[name] + corner_x,
                        ROW_FRONT + 0.10 + corner_y,
                        BENCH_Z - 0.0005,
                    ),
                    target=target,
                    parent=station,
                    axis="Z",
                    radius=0.006,
                )
            continue

        for slot_id in deck_ids:
            x, y = slot_position(slot_id)
            rounded_box(
                f"Slot_{node_case(slot_id)}",
                (0.128, 0.086, 0.006),
                (x, y, DECK_Z + 0.003),
                "PowderCoatGraphite",
                target=target,
                parent=station,
                bevel=0.004,
            )
            rounded_box(
                f"Slot_{node_case(slot_id)}_Inset",
                (0.118, 0.076, 0.003),
                (x, y, DECK_Z + 0.006),
                "AnodizedAluminum",
                target=target,
                parent=station,
                bevel=0.0025,
            )
            # Seating pads, not proud pins.  Their top face is the seating
            # plane itself, so labware rests on them instead of being held up
            # 3 mm above the slot by four posts standing through its skirt.
            for dx, dy in ((-0.055, -0.034), (0.055, -0.034), (-0.055, 0.034), (0.055, 0.034)):
                cylinder(
                    f"Slot_{node_case(slot_id)}_Pad_{dx:+.3f}_{dy:+.3f}",
                    0.0035,
                    0.0035,
                    (x + dx, y + dy, DECK_SLOT_TOP_Z - 0.00175),
                    "MachinedAluminum",
                    target=target,
                    parent=station,
                    vertices=20,
                    bevel=0.0003,
                )
    return slots


def head_collar(
    name: str,
    y: float,
    target: bpy.types.Collection,
    head: bpy.types.Object,
) -> bpy.types.Object:
    """The tool half of the changer, identical on every head.

    It is the only part of a head the mover and the docks touch: the coupler
    boss passes through it, and the dock arms take the head's weight under it.
    Because both heads carry the same collar at the same height, one dock
    geometry and one coupling test cover both.
    """
    collar = rounded_box(
        name,
        (HEAD_COLLAR_LENGTH, HEAD_COLLAR_DEPTH, HEAD_COLLAR_HEIGHT),
        (0.0, y, HEAD_TOP_Z + HEAD_COLLAR_HEIGHT / 2.0),
        "MachinedAluminum",
        target=target,
        parent=head,
        bevel=0.004,
    )
    for sign in (-1.0, 1.0):
        screw(
            f"{name}Screw{'Left' if sign < 0 else 'Right'}",
            (sign * 0.042, y, HEAD_COLLAR_TOP_Z),
            target=target,
            parent=head,
            axis="Z",
            radius=0.0035,
        )
    return collar


def build_head_dock(label: str, cell_root: bpy.types.Object) -> bpy.types.Object:
    """A cradle an idle head hangs in, standing on the process deck.

    Two bars run along the machine axis, one in front of the head and one
    behind it, and the head's collar lands across both.  They engage from the
    front and rear rather than from the sides because a head arrives straight
    down: anything inboard of the collar's own footprint would be swept through
    by the housing, the cross-rails and the jaws on the way in, which is what
    the first cradle here did.

    ``HEAD_DOCK_ARM_TOP_Z`` is derived from ``HEAD_DOCK_Z``, so the seated
    collar and the bar face are the same number and the head rests on the bars
    instead of hovering over them or sinking into them.
    """
    target = COLLECTIONS["Mechanisms"]
    x = HEAD_DOCK_X[label]
    collar_y = -0.012 if label == "Gripper" else -0.006
    dock = empty(
        f"HeadDock_{label}",
        target=target,
        location=(x, HEAD_DOCK_Y, 0.0),
        parent=cell_root,
    )
    dock["opensdlHeadDock"] = label
    rounded_box(
        f"HeadDock_{label}_Base",
        (0.150, 2.0 * HEAD_DOCK_ARM_Y + 0.040, 0.006),
        (0.0, collar_y, DECK_Z + 0.003),
        "PowderCoatGraphite",
        target=target,
        parent=dock,
        bevel=0.002,
    )
    arm_bottom = HEAD_DOCK_ARM_TOP_Z - HEAD_DOCK_ARM_HEIGHT
    for side, sign in (("Front", -1.0), ("Rear", 1.0)):
        rounded_box(
            f"HeadDock_{label}_Arm{side}",
            (HEAD_DOCK_ARM_LENGTH, HEAD_DOCK_ARM_DEPTH, HEAD_DOCK_ARM_HEIGHT),
            (
                0.0,
                collar_y + sign * HEAD_DOCK_ARM_Y,
                HEAD_DOCK_ARM_TOP_Z - HEAD_DOCK_ARM_HEIGHT / 2.0,
            ),
            "BrushedStainless",
            target=target,
            parent=dock,
            bevel=0.002,
        )
        # A retaining lip on each bar's outboard edge, clear of the collar's
        # own footprint: it traps a seated head without standing in the path
        # the head descends through.
        rounded_box(
            f"HeadDock_{label}_Lip{side}",
            (HEAD_DOCK_ARM_LENGTH - 0.020, 0.006, 0.008),
            (
                0.0,
                collar_y + sign * (HEAD_COLLAR_DEPTH / 2.0 + 0.005),
                HEAD_DOCK_ARM_TOP_Z + 0.004,
            ),
            "BrushedStainless",
            target=target,
            parent=dock,
            bevel=0.0015,
        )
        for end, end_sign in (("Left", -1.0), ("Right", 1.0)):
            rounded_box(
                f"HeadDock_{label}_Post{side}{end}",
                (0.020, HEAD_DOCK_ARM_DEPTH, arm_bottom - (DECK_Z + 0.006)),
                (
                    end_sign * HEAD_DOCK_POST_X,
                    collar_y + sign * HEAD_DOCK_ARM_Y,
                    (arm_bottom + DECK_Z + 0.006) / 2.0,
                ),
                "AnodizedAluminum",
                target=target,
                parent=dock,
                bevel=0.003,
            )
            screw(
                f"HeadDock_{label}_Screw{side}{end}",
                (
                    end_sign * HEAD_DOCK_POST_X,
                    collar_y + sign * HEAD_DOCK_ARM_Y,
                    DECK_Z + 0.006,
                ),
                target=target,
                parent=dock,
                axis="Z",
                radius=0.004,
            )
    return dock


def build_transport(
    cell_root: bpy.types.Object,
) -> tuple[
    bpy.types.Object,
    bpy.types.Object,
    bpy.types.Object,
    bpy.types.Object,
    bpy.types.Object,
    bpy.types.Object,
    bpy.types.Object,
    bpy.types.Object,
]:
    """Build the rail, the bridge, the one mover, and its two heads.

    The mover is the only driven carriage.  ``GripperHead`` and ``PipetteHead``
    are tooling: each one either hangs from ``MoverCoupler`` or waits in its own
    dock, and neither has a drive of its own.  Both heads are parented to the
    cell rather than to the bridge, because a docked head must not follow the
    bridge; a coupled head is keyed from the mover pose instead.
    """
    target = COLLECTIONS["Mechanisms"]
    # The transport is part of the frame, not equipment standing on a bench.
    # Two Y runway beams land directly on the machine's end towers and the
    # bridge spans between them, so the stations stay open on every side and one
    # mover still reaches all of them.
    portal = empty("MoverRail", target=target, location=(0.0, 0.0, 0.0), parent=cell_root)
    for x in (-MOVER_HALF_SPAN, MOVER_HALF_SPAN):
        rounded_box(
            f"MoverRailBeam_{x:+.3f}",
            (0.052, 2 * MOVER_RAIL_POST_Y + 0.13, 0.046),
            (x, 0.0, MOVER_RAIL_Z),
            "AnodizedAluminum",
            target=target,
            parent=portal,
            bevel=0.006,
        )
        rounded_box(
            f"MoverRailTrack_{x:+.3f}",
            (0.016, 2 * MOVER_RAIL_POST_Y + 0.09, 0.014),
            (x, 0.0, MOVER_RAIL_Z - 0.026),
            "BrushedStainless",
            target=target,
            parent=portal,
            bevel=0.002,
        )
        # The runway is bolted to the tower through a machined saddle at each
        # end, so the load goes straight into the frame's corner columns.
        for y in (-MOVER_RAIL_POST_Y, MOVER_RAIL_POST_Y):
            rounded_box(
                f"MoverRailSaddle_{x:+.3f}_{y:+.3f}",
                (0.086, 0.086, 0.020),
                (x, y, MOVER_RAIL_Z - 0.032),
                "PowderCoatGraphite",
                target=target,
                parent=portal,
                bevel=0.004,
            )
            for corner in (-0.030, 0.030):
                screw(
                    f"MoverRailScrew_{x:+.3f}_{y:+.3f}_{corner:+.3f}",
                    (x + corner, y + corner, MOVER_RAIL_Z - 0.020),
                    target=target,
                    parent=portal,
                    axis="Z",
                    radius=0.005,
                )
        # Tie-back struts from the runway ends into the tower columns.
        for y in (-MOVER_RAIL_POST_Y, MOVER_RAIL_POST_Y):
            strut_y = math.copysign(FRAME_POST_Y[1], y)
            length = abs(strut_y - y)
            extrusion(
                f"MoverRailStrut_{x:+.3f}_{y:+.3f}",
                length,
                "Y",
                (x, (y + strut_y) / 2.0, MOVER_RAIL_Z - 0.040),
                target=target,
                parent=portal,
                profile=0.030,
                slots=False,
            )

    bridge = empty("MoverBridge", target=target, location=(0.0, ROW_FRONT, 0.0), parent=cell_root)
    bridge["movable"] = True
    beam_length = 2 * MOVER_HALF_SPAN + 0.10
    rounded_box(
        "MoverBridgeBeam",
        (beam_length, 0.070, 0.096),
        (0.0, 0.0, MOVER_BRIDGE_Z),
        "AnodizedAluminum",
        target=target,
        parent=bridge,
        bevel=0.010,
    )
    rounded_box(
        "MoverBridgeCover",
        (beam_length - 0.10, 0.012, 0.070),
        (0.0, -0.041, MOVER_BRIDGE_Z),
        "PowderCoatGraphite",
        target=target,
        parent=bridge,
        bevel=0.007,
    )
    rounded_box(
        "MoverBridgeTrack",
        (beam_length - 0.14, 0.020, 0.024),
        (0.0, -0.050, MOVER_BRIDGE_Z - 0.030),
        "BrushedStainless",
        target=target,
        parent=bridge,
        bevel=0.003,
    )
    for x in (-MOVER_HALF_SPAN, MOVER_HALF_SPAN):
        rounded_box(
            f"MoverBridgeTruck_{x:+.3f}",
            (0.090, 0.115, 0.120),
            (x, 0.0, MOVER_BRIDGE_Z + 0.010),
            "PowderCoatBlack",
            target=target,
            parent=bridge,
            bevel=0.010,
        )
        screw(
            f"MoverBridgeScrew_{x:+.3f}",
            (x, -0.059, MOVER_BRIDGE_Z + 0.010),
            target=target,
            parent=bridge,
            axis="Y",
        )

    # The energy chain trough: a covered steel channel along the back of the
    # bridge carrying the X-axis umbilical, open only along its top face.  The
    # chain's return run lies inside it for the whole stroke, which is what lets
    # the visible tail be a rigid piece riding the carriage.
    trough_z = MOVER_BRIDGE_Z + 0.062
    for wall, wall_y, wall_size in (
        ("Floor", 0.058, (2 * MOVER_HALF_SPAN - 0.02, 0.076, 0.006)),
        ("Front", 0.022, (2 * MOVER_HALF_SPAN - 0.02, 0.006, 0.048)),
        ("Rear", 0.094, (2 * MOVER_HALF_SPAN - 0.02, 0.006, 0.048)),
    ):
        rounded_box(
            f"MoverTrough{wall}",
            wall_size,
            (0.0, wall_y, trough_z + (0.0 if wall == "Floor" else 0.024)),
            "PowderCoatGraphite",
            target=target,
            parent=bridge,
            bevel=0.002,
        )
    for anchor_x in (-MOVER_HALF_SPAN + 0.02, MOVER_HALF_SPAN - 0.02):
        rounded_box(
            f"MoverTroughEnd_{anchor_x:+.3f}",
            (0.014, 0.088, 0.062),
            (anchor_x, 0.058, trough_z + 0.022),
            "PowderCoatGraphite",
            target=target,
            parent=bridge,
            bevel=0.003,
        )
    tube_path(
        "MoverBridgeCable",
        (
            (-MOVER_HALF_SPAN + 0.06, 0.088, trough_z + 0.052),
            (0.0, 0.092, trough_z + 0.044),
            (MOVER_HALF_SPAN - 0.06, 0.088, trough_z + 0.052),
        ),
        0.0036,
        "CableBlue",
        target=target,
        parent=bridge,
    )

    # The mover: one carriage on the bridge, ending in the changer master plate.
    # It has no jaws and no nozzles.  Whatever it is holding is a head.
    mover = empty(
        "Mover", target=target, location=(STATION_X["characterize"], 0.0, 0.0), parent=bridge
    )
    mover["movable"] = True
    mover["opensdlEntityId"] = "mover"
    rounded_box(
        "MoverCarriage",
        (0.105, 0.075, MOVER_CARRIAGE_HEIGHT),
        (0.0, -0.012, MOVER_CARRIAGE_LOCAL_Z),
        "PowderCoatGraphite",
        target=target,
        parent=mover,
        bevel=0.012,
    )
    rounded_box(
        "MoverFrontPanel",
        (0.086, 0.012, MOVER_CARRIAGE_HEIGHT - 0.039),
        (0.0, -0.055, MOVER_CARRIAGE_LOCAL_Z),
        "AnodizedAluminum",
        target=target,
        parent=mover,
        bevel=0.008,
    )
    cylinder(
        "MoverCamera",
        0.009,
        0.007,
        (0.0, -0.049, MOVER_CARRIAGE_BOTTOM_Z + 0.024),
        "ScreenGlass",
        target=target,
        parent=mover,
        rotation=(math.pi / 2, 0.0, 0.0),
        vertices=32,
        bevel=0.001,
    )
    rounded_box(
        "MoverBadge",
        (0.040, 0.004, 0.011),
        (0.0, -0.062, MOVER_CARRIAGE_TOP_Z - 0.062),
        "AnodizedAluminum",
        target=target,
        parent=mover,
        bevel=0.002,
    )

    # The changer.  MoverCoupler is the master half: a plate under the carriage,
    # a tapered boss that reaches through the head's collar into the head body,
    # and two guide pins that stop just inside the head's top face.  Its bounds
    # overlapping a head on all three axes is what "coupled" means to
    # check_scene, so this geometry is the invariant, not decoration.
    coupler = empty("MoverCoupler", target=target, location=(0.0, 0.0, 0.0), parent=mover)
    rounded_box(
        "MoverCouplerPlate",
        (0.096, 0.070, COUPLER_PLATE_HEIGHT),
        (0.0, -0.012, COUPLER_PLATE_Z),
        "MachinedAluminum",
        target=target,
        parent=coupler,
        bevel=0.003,
    )
    cylinder(
        "MoverCouplerBoss",
        COUPLER_BOSS_RADIUS,
        MOVER_CARRIAGE_BOTTOM_Z - COUPLER_BOSS_BOTTOM_Z,
        (0.0, -0.012, (MOVER_CARRIAGE_BOTTOM_Z + COUPLER_BOSS_BOTTOM_Z) / 2.0),
        "BrushedStainless",
        target=target,
        parent=coupler,
        vertices=28,
        bevel=0.002,
    )
    for side, sign in (("Left", -1.0), ("Right", 1.0)):
        cylinder(
            f"MoverCouplerPin{side}",
            COUPLER_PIN_RADIUS,
            MOVER_CARRIAGE_BOTTOM_Z - COUPLER_PIN_BOTTOM_Z,
            (
                sign * COUPLER_PIN_X,
                -0.012,
                (MOVER_CARRIAGE_BOTTOM_Z + COUPLER_PIN_BOTTOM_Z) / 2.0,
            ),
            "MachinedAluminum",
            target=target,
            parent=coupler,
            vertices=16,
            bevel=0.0008,
        )
        screw(
            f"MoverCouplerScrew{side}",
            (sign * 0.042, -0.012, MOVER_BOTTOM_Z + COUPLER_PLATE_HEIGHT),
            target=target,
            parent=coupler,
            axis="Z",
            radius=0.0035,
        )

    # The pipetting head.  Everything above its collar used to be a second
    # carriage; that carriage is now the mover, and this is only the tool.
    pipette_head = empty(
        "PipetteHead",
        target=target,
        location=(HEAD_DOCK_X["Pipette"], HEAD_DOCK_Y, HEAD_DOCK_Z),
        parent=cell_root,
    )
    pipette_head["movable"] = True
    pipette_head["opensdlEntityId"] = "pipette-head"
    head_collar("PipetteHeadCollar", -0.006, target, pipette_head)
    rounded_box(
        "PipetteEjector",
        (0.074, 0.070, 0.034),
        (0.0, -0.006, 1.340),
        "BlackPolymer",
        target=target,
        parent=pipette_head,
        bevel=0.005,
    )
    rounded_box(
        "PipetteManifold",
        (0.034, 0.068, 0.030),
        (0.0, -0.006, 1.320),
        "MachinedAluminum",
        target=target,
        parent=pipette_head,
        bevel=0.005,
    )
    rounded_box(
        "PipetteBadge",
        (0.028, 0.003, 0.008),
        (0.0, -0.0425, 1.345),
        "AnodizedAluminum",
        target=target,
        parent=pipette_head,
        bevel=0.0015,
    )

    # Eight real nozzle positions at ANSI/SLAS 9 mm row pitch.  The detachable
    # tips live under their own transform so pickup/drop can be synchronized.
    tip_group = empty(
        "AttachedTipColumn",
        target=target,
        location=(0.0, 0.0, NOZZLE_TIP_TOP_LOCAL_Z),
        parent=pipette_head,
    )
    nozzle_mesh: bpy.types.Mesh | None = None
    tip_mesh: bpy.types.Mesh | None = None
    for row in range(8):
        y = (row - 3.5) * 0.009 + NOZZLE_COLUMN_Y
        if nozzle_mesh is None:
            nozzle = cylinder(
                "PipetteNozzle_00",
                0.0012,
                0.022,
                (0.0, y, 1.294),
                "BrushedStainless",
                target=target,
                parent=pipette_head,
                vertices=16,
                bevel=0.0002,
            )
            nozzle_mesh = nozzle.data
            tip = cylinder(
                "AttachedTip_00",
                TIP_RADIUS,
                TIP_LENGTH,
                (0.0, y, -TIP_LENGTH / 2.0),
                "ClearLabware",
                target=target,
                parent=tip_group,
                vertices=14,
                bevel=0.0002,
            )
            tip_mesh = tip.data
        else:
            nozzle = bpy.data.objects.new(f"PipetteNozzle_{row:02d}", nozzle_mesh)
            target.objects.link(nozzle)
            nozzle.location = (0.0, y, 1.294)
            nozzle.parent = pipette_head
            mark_export(nozzle)
            tip = bpy.data.objects.new(f"AttachedTip_{row:02d}", tip_mesh)
            target.objects.link(tip)
            tip.location = (0.0, y, -TIP_LENGTH / 2.0)
            tip.parent = tip_group
            mark_export(tip)
    tip_group.scale = (1.0, 1.0, 0.02)

    # The gripper head.  Same collar as the pipetting head, so the mover cannot
    # tell them apart, and the same dock geometry catches either one.
    gripper_head = empty(
        "GripperHead",
        target=target,
        location=(STATION_X["characterize"], ROW_FRONT, 0.0),
        parent=cell_root,
    )
    gripper_head["movable"] = True
    gripper_head["opensdlEntityId"] = "gripper-head"
    head_collar("GripperHeadCollar", -0.012, target, gripper_head)
    gripper = gripper_head

    # The mechanism between the collar and the paddles.  Without it the
    # paddles read as two bars floating beside the arm, which is exactly what
    # they were: the jaws tracked the carriage correctly and nothing spanned
    # the gap.  Socket, actuator housing, cross-rail and rail end supports are
    # each flush with the stage above, and the rail is long enough that a
    # carrier can never run off it at any authored jaw width.
    rounded_box(
        "GripperHeadSocket",
        (0.086, 0.064, GRIPPER_WRIST_HEIGHT),
        (0.0, -0.012, GRIPPER_WRIST_Z),
        "MachinedAluminum",
        target=target,
        parent=gripper,
        bevel=0.006,
    )
    rounded_box(
        "GripperActuatorHousing",
        (GRIPPER_HOUSING_LENGTH, 0.058, GRIPPER_HOUSING_HEIGHT),
        (0.0, -0.012, GRIPPER_HOUSING_Z),
        "PowderCoatGraphite",
        target=target,
        parent=gripper,
        bevel=0.006,
    )
    rounded_box(
        "GripperActuatorFace",
        (GRIPPER_HOUSING_LENGTH - 0.030, 0.008, GRIPPER_HOUSING_HEIGHT - 0.008),
        (0.0, -0.043, GRIPPER_HOUSING_Z),
        "AnodizedAluminum",
        target=target,
        parent=gripper,
        bevel=0.003,
    )
    for index in range(4):
        rounded_box(
            f"GripperActuatorRib_{index}",
            (0.008, 0.004, 0.014),
            (-0.030 + index * 0.020, -0.047, GRIPPER_HOUSING_Z + 0.002),
            "PowderCoatGraphite",
            target=target,
            parent=gripper,
            bevel=0.001,
        )
    for name, rail_y in (("Front", -0.030), ("Rear", 0.006)):
        rounded_box(
            f"GripperCrossRail{name}",
            (GRIPPER_RAIL_LENGTH, 0.016, GRIPPER_RAIL_HEIGHT),
            (0.0, rail_y, GRIPPER_RAIL_Z),
            "BrushedStainless",
            target=target,
            parent=gripper,
            bevel=0.002,
        )
    cylinder(
        "GripperLeadScrew",
        0.0045,
        GRIPPER_RAIL_LENGTH - 0.030,
        (0.0, -0.012, GRIPPER_RAIL_Z),
        "MachinedAluminum",
        target=target,
        parent=gripper,
        rotation=(0.0, math.pi / 2, 0.0),
        vertices=20,
        bevel=0.0004,
    )
    for side, sign in (("Left", -1.0), ("Right", 1.0)):
        rounded_box(
            f"GripperRailEnd{side}",
            (0.016, JAW_CARRIER_DEPTH, GRIPPER_RAIL_HEIGHT + GRIPPER_HOUSING_HEIGHT * 0.6),
            (
                sign * (GRIPPER_RAIL_LENGTH / 2.0 - 0.008),
                -0.012,
                GRIPPER_RAIL_Z + GRIPPER_HOUSING_HEIGHT * 0.3,
            ),
            "AnodizedAluminum",
            target=target,
            parent=gripper,
            bevel=0.004,
        )

    # Each jaw is a finger carrier riding that rail.  GripperJawLeft/Right is
    # the carrier body: it is the object the animation drives, and the finger
    # and paddle hang from it, so the paddle can only be where the mechanism
    # puts it.  The friction pads are inlaid flush with the paddle faces, which
    # are the surfaces the closed jaw widths are measured against.
    pad_offset = JAW_THICKNESS / 2.0 - JAW_PAD_THICKNESS / 2.0
    jaws: list[bpy.types.Object] = []
    for side, sign in (("Left", -1.0), ("Right", 1.0)):
        carrier = rounded_box(
            f"GripperJaw{side}",
            (JAW_CARRIER_THICKNESS, JAW_CARRIER_DEPTH, JAW_CARRIER_HEIGHT),
            (sign * 0.076, -0.012, JAW_CARRIER_LOCAL_Z),
            "AnodizedAluminum",
            target=target,
            parent=gripper,
            bevel=0.004,
        )
        for screw_y in (-0.018, 0.018):
            screw(
                f"GripperCarrierScrew{side}_{screw_y:+.3f}",
                (0.0, screw_y, JAW_CARRIER_HEIGHT / 2.0),
                target=target,
                parent=carrier,
                axis="Z",
                radius=0.0032,
            )
        rounded_box(
            f"GripperFinger{side}",
            (JAW_FINGER_THICKNESS, 0.034, JAW_FINGER_HEIGHT),
            (0.0, 0.0, JAW_FINGER_LOCAL_Z - JAW_CARRIER_LOCAL_Z),
            "PowderCoatGraphite",
            target=target,
            parent=carrier,
            bevel=0.003,
        )
        paddle = rounded_box(
            f"GripperPaddle{side}",
            (JAW_THICKNESS, 0.070, JAW_PADDLE_HEIGHT),
            (0.0, 0.0, JAW_PADDLE_LOCAL_Z - JAW_CARRIER_LOCAL_Z),
            "PowderCoatBlack",
            target=target,
            parent=carrier,
            bevel=0.004,
        )
        rounded_box(
            f"GripperPad{side}",
            (JAW_PAD_THICKNESS, 0.052, JAW_PAD_HEIGHT),
            (-sign * pad_offset, 0.0, -0.002),
            "Rubber",
            target=target,
            parent=paddle,
            bevel=0.002,
        )
        jaws.append(carrier)
    jaw_left, jaw_right = jaws

    # The visible end of the X-axis energy chain.  It rides the carriage in X
    # only: the Z stroke happens inside the carriage on a real machine, so a
    # chain that bobbed with the tool would be wrong.  ``MoverChain`` therefore
    # gets its own transform, keyed from the same X the carriage is keyed from,
    # and the return run stays down in the covered trough for the whole stroke.
    drag = empty(
        "MoverChain",
        target=target,
        location=(STATION_X["characterize"], 0.0, 0.0),
        parent=bridge,
    )
    drag["movable"] = True
    trough_z = MOVER_BRIDGE_Z + 0.062
    link_pitch = 0.042
    for link in range(9):
        # A flat run out of the trough, then the U-bend up to the carriage.
        travel = link * link_pitch
        if travel <= 0.150:
            position = (-0.230 + travel, 0.058, trough_z + 0.016)
            pitch_angle = 0.0
        else:
            bend = min(1.0, (travel - 0.150) / 0.210)
            angle = bend * math.pi * 0.86
            position = (
                -0.080 + 0.062 * math.sin(angle),
                0.058,
                trough_z + 0.016 + 0.062 * (1.0 - math.cos(angle)),
            )
            pitch_angle = -angle
        rounded_box(
            f"MoverChainLink_{link:02d}",
            (link_pitch - 0.004, 0.052, 0.028),
            position,
            "BlackPolymer",
            target=target,
            parent=drag,
            rotation=(0.0, pitch_angle, 0.0),
            bevel=0.003,
        )
        rounded_box(
            f"MoverChainPin_{link:02d}",
            (0.008, 0.058, 0.008),
            position,
            "PowderCoatGraphite",
            target=target,
            parent=drag,
            rotation=(0.0, pitch_angle, 0.0),
            bevel=0.001,
        )
    rounded_box(
        "MoverChainBracket",
        (0.062, 0.046, 0.030),
        (-0.002, 0.052, trough_z + 0.126),
        "PowderCoatGraphite",
        target=target,
        parent=drag,
        bevel=0.004,
    )
    tube_path(
        "MoverChainUmbilical",
        (
            (-0.010, 0.050, trough_z + 0.138),
            (0.006, 0.010, trough_z + 0.106),
            (0.006, -0.020, MOVER_CARRIAGE_TOP_Z + 0.004),
        ),
        0.0072,
        "CableBlack",
        target=target,
        parent=drag,
    )

    for label in ("Gripper", "Pipette"):
        build_head_dock(label, cell_root)
    return bridge, mover, gripper_head, pipette_head, tip_group, jaw_left, jaw_right, drag


def build_plate(
    name: str,
    location: Sequence[float],
    *,
    target: bpy.types.Collection,
    parent: bpy.types.Object | None = None,
) -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    root = empty(name, target=target, location=location, parent=parent)
    root["opensdlEntityId"] = "sample"
    root["movable"] = True
    rounded_box(
        f"{name}_Skirt",
        (PLATE_LENGTH, PLATE_DEPTH, PLATE_HEIGHT),
        (0.0, 0.0, 0.0),
        "ClearLabware",
        target=target,
        parent=root,
        bevel=0.003,
    )
    rounded_box(
        f"{name}_Top",
        (0.121, 0.079, 0.0032),
        (0.0, 0.0, 0.0072),
        "WhitePolymer",
        target=target,
        parent=root,
        bevel=0.0018,
    )
    well_mesh: bpy.types.Mesh | None = None
    liquid_mesh: bpy.types.Mesh | None = None
    liquid_columns = [
        empty(
            f"{name}_LiquidColumn_{col + 1:02d}",
            target=target,
            location=((col - 5.5) * 0.0090, 0.0, 0.0087),
            parent=root,
        )
        for col in range(12)
    ]
    for column in liquid_columns:
        column.scale = (1.0, 1.0, 0.03)
    for row in range(8):
        for col in range(12):
            x = (col - 5.5) * 0.0090
            y = (row - 3.5) * 0.0090
            if well_mesh is None:
                well = torus(
                    f"{name}_Well_00_00",
                    0.00315,
                    0.00055,
                    (x, y, 0.0092),
                    "ClearLabware",
                    target=target,
                    parent=root,
                )
                well_mesh = well.data
            else:
                well = bpy.data.objects.new(f"{name}_Well_{row:02d}_{col:02d}", well_mesh)
                target.objects.link(well)
                well.location = (x, y, 0.0092)
                well.parent = root
                mark_export(well)
            if liquid_mesh is None:
                liquid = cylinder(
                    f"{name}_Liquid_00_00",
                    0.00265,
                    0.0014,
                    (0.0, y, 0.0),
                    "SampleBlue",
                    target=target,
                    parent=liquid_columns[col],
                    vertices=20,
                    bevel=0.0002,
                )
                liquid_mesh = liquid.data
            else:
                liquid = bpy.data.objects.new(f"{name}_Liquid_{row:02d}_{col:02d}", liquid_mesh)
                target.objects.link(liquid)
                liquid.location = (0.0, y, 0.0)
                liquid.parent = liquid_columns[col]
                mark_export(liquid)
    # A barcode label on the short side.  This is real: every plate in an
    # automated workflow carries one, and it is how the run knows which plate
    # this is.  It is a printed label, not a caption for the camera.
    rounded_box(
        f"{name}_BarcodeLabel",
        (0.052, 0.0008, 0.0088),
        (-0.030, -0.0432, 0.0005),
        "PaperWhite",
        target=target,
        parent=root,
        bevel=0.0004,
    )
    for index in range(17):
        rounded_box(
            f"{name}_BarcodeBar_{index:02d}",
            (0.0008 if index % 3 else 0.0016, 0.0006, 0.0052),
            (-0.0530 + index * 0.0028, -0.0436, 0.0014),
            "PowderCoatBlack",
            target=target,
            parent=root,
            bevel=0.0,
        )
    return root, liquid_columns


def build_tip_rack(
    location: Sequence[float], cell_root: bpy.types.Object
) -> list[bpy.types.Object]:
    target = COLLECTIONS["Labware"]
    root = empty("TipRack", target=target, location=location, parent=cell_root)
    rounded_box(
        "TipRackBase",
        (0.1278, 0.0855, 0.016),
        (0.0, 0.0, 0.008),
        "ClearLabware",
        target=target,
        parent=root,
        bevel=0.003,
    )
    rounded_box(
        "TipRackInsert",
        (0.118, 0.076, 0.004),
        (0.0, 0.0, 0.018),
        "WhitePolymer",
        target=target,
        parent=root,
        bevel=0.002,
    )
    tip_mesh: bpy.types.Mesh | None = None
    tip_columns = [
        empty(
            f"RackTipColumn_{col + 1:02d}",
            target=target,
            location=((col - 5.5) * 0.009, 0.0, 0.018),
            parent=root,
        )
        for col in range(12)
    ]
    # Tips stand on the insert rather than sinking into the rack body, so the
    # mounted tip and the racked tip describe the same volume.
    tip_center_z = (TIP_TOP_Z - TIP_LENGTH / 2.0) - (TIP_RACK_ROOT_Z + 0.018)
    for row in range(8):
        for col in range(12):
            y = (row - 3.5) * 0.009
            if tip_mesh is None:
                tip = cylinder(
                    "RackTip_00_00",
                    TIP_RADIUS,
                    TIP_LENGTH,
                    (0.0, y, tip_center_z),
                    "ClearLabware",
                    target=target,
                    parent=tip_columns[col],
                    vertices=12,
                    bevel=0.0002,
                )
                tip_mesh = tip.data
            else:
                tip = bpy.data.objects.new(f"RackTip_{row:02d}_{col:02d}", tip_mesh)
                target.objects.link(tip)
                tip.location = (0.0, y, tip_center_z)
                tip.parent = tip_columns[col]
                mark_export(tip)
    return tip_columns


def build_reservoir(location: Sequence[float], cell_root: bpy.types.Object) -> None:
    target = COLLECTIONS["Labware"]
    root = empty("ReagentReservoir", target=target, location=location, parent=cell_root)
    rounded_box(
        "ReservoirSkirt",
        (0.1278, 0.0855, 0.021),
        (0.0, 0.0, 0.0105),
        "ClearLabware",
        target=target,
        parent=root,
        bevel=0.003,
    )
    for index in range(12):
        x = (index - 5.5) * RESERVOIR_LANE_PITCH
        rounded_box(
            f"ReservoirChannel_{index + 1:02d}",
            (RESERVOIR_LANE_WIDTH, 0.068, 0.014),
            (x, 0.0, 0.022),
            "SampleViolet" if index == 1 else "SampleBlue",
            target=target,
            parent=root,
            bevel=0.0026,
        )
    # Thirteen dividers bound the twelve lanes and leave each lane open from
    # above, which is how an eight-channel head reaches the reagent.
    for index in range(13):
        rounded_box(
            f"ReservoirDivider_{index + 1:02d}",
            (RESERVOIR_LANE_PITCH - RESERVOIR_LANE_WIDTH, 0.070, 0.010),
            ((index - 6) * RESERVOIR_LANE_PITCH, 0.0, 0.026),
            "WhitePolymer",
            target=target,
            parent=root,
            bevel=0.0006,
        )


def build_mixer(
    location: Sequence[float],
    cell_root: bpy.types.Object,
) -> tuple[bpy.types.Object, tuple[bpy.types.Object, bpy.types.Object], bpy.types.Object]:
    target = COLLECTIONS["Modules"]
    root = empty("MixerModule", target=target, location=location, parent=cell_root)
    rounded_box(
        "MixerBody",
        (0.152, 0.090, 0.061),
        (0.0, 0.0, 0.0305),
        "MachinedAluminum",
        target=target,
        parent=root,
        bevel=0.008,
    )
    rounded_box(
        "MixerRear",
        (0.035, 0.086, 0.065),
        (-0.057, 0.0, 0.033),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.006,
    )
    rounded_box(
        "MixerPanel",
        (0.004, 0.068, 0.044),
        (0.077, 0.0, 0.035),
        "AnodizedAluminum",
        target=target,
        parent=root,
        bevel=0.003,
    )
    cylinder(
        "MixerPower",
        0.008,
        0.005,
        (-0.076, 0.025, 0.031),
        "BlackPolymer",
        target=target,
        parent=root,
        rotation=(0.0, math.pi / 2, 0.0),
        vertices=24,
        bevel=0.001,
    )
    mixer = empty("MixerRotor", target=target, location=(0.0, 0.0, 0.069), parent=root)
    mixer["opensdlEntityId"] = "mixer-rotor"
    mixer["movable"] = True
    rounded_box(
        "MixerPlatform",
        (0.130, 0.078, 0.014),
        (0.0, 0.0, 0.0),
        "PowderCoatGraphite",
        target=target,
        parent=mixer,
        bevel=0.007,
    )
    # The clamp holds the plate by its short ends.  The gripper paddles come
    # down on the long sides, so the two mechanisms never contend for the same
    # space, and the closed bar stops MIXER_LATCH_CLEARANCE outside the plate
    # footprint instead of closing through it.
    latches: list[bpy.types.Object] = []
    for y in (-MIXER_LATCH_CLOSED_Y, MIXER_LATCH_CLOSED_Y):
        side = "Front" if y < 0 else "Rear"
        latch = empty(f"MixerLatch{side}", target=target, location=(0.0, y, 0.014), parent=mixer)
        latch["movable"] = True
        rounded_box(
            f"MixerLatch{side}Bar",
            (0.080, MIXER_LATCH_THICKNESS, 0.018),
            (0.0, 0.0, 0.0),
            "BlackPolymer",
            target=target,
            parent=latch,
            bevel=0.003,
        )
        screw(
            f"MixerLatchScrew_{y:+.3f}",
            (0.030, math.copysign(MIXER_LATCH_THICKNESS / 2.0, y), 0.0),
            target=target,
            parent=latch,
            axis="Y",
            radius=0.0025,
        )
        latches.append(latch)
    status = rounded_box(
        "MixerStatus",
        (0.018, 0.004, 0.005),
        (-0.063, -0.047, 0.044),
        "WhiteIndicator",
        target=target,
        parent=root,
        bevel=0.002,
    )
    return mixer, (latches[0], latches[1]), status


def build_characterizer(
    location: Sequence[float], lid_dock: Sequence[float], cell_root: bpy.types.Object
) -> tuple[bpy.types.Object, bpy.types.Object, bpy.types.Object]:
    target = COLLECTIONS["Modules"]
    reader = empty("CharacterizerHousing", target=target, location=location, parent=cell_root)
    reader["opensdlEntityId"] = "characterizer"
    # The published assembled module is approximately 57-60 mm high.  Its
    # 18.5 mm detector body, labware, and removable lid share that envelope.
    rounded_box(
        "CharacterizerBody",
        (0.1553, 0.0955, 0.0185),
        (0.0, 0.0, 0.00925),
        "MachinedAluminum",
        target=target,
        parent=reader,
        bevel=0.006,
    )
    rounded_box(
        "CharacterizerFascia",
        (0.145, 0.006, 0.014),
        (0.0, -0.0505, 0.010),
        "PowderCoatGraphite",
        target=target,
        parent=reader,
        bevel=0.003,
    )
    rounded_box(
        "CharacterizerDeck",
        (0.130, 0.082, 0.003),
        (0.0, 0.0, 0.0190),
        "PowderCoatBlack",
        target=target,
        parent=reader,
        bevel=0.003,
    )
    # The read window and its detectors are inlaid into the black deck.  The
    # plate seats on that deck, so nothing may stand above it.
    rounded_box(
        "CharacterizerWindow",
        (0.124, 0.076, 0.0012),
        (0.0, 0.0, 0.0199),
        "ReaderIndicator",
        target=target,
        parent=reader,
        bevel=0.0005,
    )
    for row in range(8):
        for col in range(12):
            x = (col - 5.5) * 0.009
            y = (row - 3.5) * 0.009
            cylinder(
                f"CharacterizerDetector_{row:02d}_{col:02d}",
                0.0018,
                0.0010,
                (x, y, 0.0196),
                "ScreenGlass",
                target=target,
                parent=reader,
                vertices=12,
                bevel=0.0002,
            )
    status = rounded_box(
        "CharacterizerStatus",
        (0.034, 0.006, 0.006),
        (0.050, -0.0515, 0.010),
        "ReaderIndicator",
        target=target,
        parent=reader,
        bevel=0.002,
    )

    rounded_box(
        "CharacterizerDoorDock",
        (0.128, 0.086, DOOR_DOCK_HEIGHT),
        (lid_dock[0], lid_dock[1], lid_dock[2] - DOOR_DOCK_HEIGHT / 2.0),
        "PowderCoatGraphite",
        target=target,
        parent=cell_root,
        bevel=0.005,
    )

    lid = empty("CharacterizerDoor", target=target, location=lid_dock, parent=cell_root)
    lid["opensdlEntityId"] = "characterizer-door"
    lid["movable"] = True
    rounded_box(
        "CharacterizerDoorLower",
        (0.139, 0.089, 0.010),
        (0.0, 0.0, 0.005),
        "MachinedAluminum",
        target=target,
        parent=lid,
        bevel=0.006,
    )
    rounded_box(
        "CharacterizerDoorTop",
        (0.132, 0.082, 0.011),
        (0.0, 0.0, 0.0155),
        "PowderCoatGraphite",
        target=target,
        parent=lid,
        bevel=0.006,
    )
    grip_x = DOOR_GRIP_OUTER_X - DOOR_GRIP_DEPTH / 2.0
    for side, x in (("Left", -grip_x), ("Right", grip_x)):
        rounded_box(
            f"CharacterizerDoorGrip{side}",
            (DOOR_GRIP_DEPTH, 0.032, 0.012),
            (x, 0.0, DOOR_GRIP_Z),
            "BlackPolymer",
            target=target,
            parent=lid,
            bevel=0.0025,
        )
    rounded_box(
        "CharacterizerDoorBadge",
        (0.030, 0.009, 0.002),
        (0.0, -0.001, 0.0212),
        "AnodizedAluminum",
        target=target,
        parent=lid,
        bevel=0.0008,
    )
    return reader, lid, status


def build_hotel(
    name: str,
    slot: Sequence[float],
    cell_root: bpy.types.Object,
    *,
    role: str,
) -> bpy.types.Object:
    target = COLLECTIONS["Modules"]
    # Real module envelope: 385.5 mm track length, 106 mm width, 955.5 mm height.
    # On the open bench the module is turned a quarter turn so its tower stands
    # at the back of the station and its shuttle presents labware toward the
    # front: local +X runs to world +Y.
    x, y, _ = slot
    root = empty(name, target=target, location=(x, y, BENCH_Z), parent=cell_root)
    root.rotation_euler = (0.0, 0.0, math.pi / 2)
    root["opensdlRole"] = role
    # The track runs the full presentation stroke, so the shuttle is carried at
    # both ends of its travel instead of hanging off the front of its own rail.
    track_length = 0.560
    track_center = 0.028
    rounded_box(
        f"{name}_Track",
        (track_length, 0.100, 0.030),
        (track_center, 0.0, 0.205),
        "MachinedAluminum",
        target=target,
        parent=root,
        bevel=0.006,
    )
    for rail_side, rail_y in (("Front", -0.045), ("Rear", 0.045)):
        rounded_box(
            f"{name}_TrackRail{rail_side}",
            (track_length - 0.018, 0.009, 0.012),
            (track_center, rail_y, 0.222),
            "BrushedStainless",
            target=target,
            parent=root,
            bevel=0.002,
        )
    # The front of the track is a cantilever off the tower, so it stands on its
    # own leg rather than floating over the worktop.
    leg_x = track_center - track_length / 2.0 + 0.032
    rounded_box(
        f"{name}_TrackLeg",
        (0.052, 0.086, 0.190),
        (leg_x, 0.0, 0.095),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.008,
    )
    rounded_box(
        f"{name}_TrackLegFoot",
        (0.110, 0.110, 0.012),
        (leg_x, 0.0, 0.006),
        "BrushedStainless",
        target=target,
        parent=root,
        bevel=0.004,
    )
    shuttle = rounded_box(
        f"{name}_Shuttle",
        (0.142, 0.094, 0.018),
        (-0.164, 0.0, 0.228),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.005,
    )
    shuttle["movable"] = True
    rounded_box(
        f"{name}_ShuttleNest",
        (0.128, 0.086, 0.005),
        (0.0, 0.0, 0.011),
        "AnodizedAluminum",
        target=target,
        parent=shuttle,
        bevel=0.003,
    )

    # The hotel is a magazine, not a cabinet.  Two extrusion columns, a pair of
    # clear guide plates, an elevator screw and an open front: the queue of
    # plates waiting to run is the point of this module, so it is left visible.
    tower_x = 0.2075
    for side in (-1.0, 1.0):
        extrusion(
            f"{name}_Column_{side:+.0f}",
            0.9555,
            "Z",
            (tower_x + side * 0.082, 0.0, 0.478),
            target=target,
            parent=root,
            profile=0.030,
            slots=False,
        )
        rounded_box(
            f"{name}_Guide_{side:+.0f}",
            (0.150, 0.008, 0.860),
            (tower_x, side * 0.049, 0.520),
            "Polycarbonate",
            target=target,
            parent=root,
            bevel=0.003,
        )
    rounded_box(
        f"{name}_TowerBase",
        (0.212, 0.116, 0.070),
        (tower_x, 0.0, 0.035),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.006,
    )
    rounded_box(
        f"{name}_TowerHead",
        (0.212, 0.116, 0.095),
        (tower_x, 0.0, 0.908),
        "InstrumentGrey",
        target=target,
        parent=root,
        bevel=0.008,
    )
    for strip_side in (-1.0, 1.0):
        rounded_box(
            f"{name}_QueueStripChannel_{strip_side:+.0f}",
            (0.020, 0.018, 0.700),
            (tower_x + 0.068, strip_side * 0.040, 0.500),
            "MachinedAluminum",
            target=target,
            parent=root,
            bevel=0.002,
        )
        rounded_box(
            f"{name}_QueueStripLens_{strip_side:+.0f}",
            (0.010, 0.008, 0.684),
            (tower_x + 0.060, strip_side * 0.038, 0.500),
            "StripCool",
            target=target,
            parent=root,
            bevel=0.001,
        )
    cylinder(
        f"{name}_ElevatorScrew",
        0.0105,
        0.800,
        (tower_x + 0.088, 0.0, 0.470),
        "BrushedStainless",
        target=target,
        parent=root,
        vertices=16,
        bevel=0.001,
    )
    cylinder(
        f"{name}_ElevatorMotor",
        0.030,
        0.086,
        (tower_x + 0.088, 0.0, 0.996),
        "PowderCoatBlack",
        target=target,
        parent=root,
        vertices=20,
        bevel=0.003,
    )
    rounded_box(
        f"{name}_ElevatorNut",
        (0.052, 0.052, 0.030),
        (tower_x + 0.088, 0.0, 0.262),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.004,
    )
    # The queue.  Ten seats in the magazine; the input hotel is loaded and the
    # output hotel is filling, so how much work is left is legible from across
    # the room without anything being written down.
    front_x = tower_x - 0.106
    filled = 10 if role == "input" else 5
    measured = ("SwatchCool", "SwatchMid", "SwatchWarm", "SampleViolet", "SampleBlue")
    for index in range(10):
        seat_z = 0.150 + index * 0.070
        for side in (-1.0, 1.0):
            rounded_box(
                f"{name}_Shelf_{index}_{side:+.0f}",
                (0.140, 0.008, 0.004),
                (tower_x, side * 0.046, seat_z - 0.011),
                "MachinedAluminum",
                target=target,
                parent=root,
                bevel=0.001,
            )
        if index >= filled:
            continue
        stored = rounded_box(
            f"{name}_StoredPlate_{index}",
            (0.1278, 0.0855, 0.0143),
            (tower_x, 0.0, seat_z),
            "PlatePolymer",
            target=target,
            parent=root,
            bevel=0.002,
        )
        del stored
        rounded_box(
            f"{name}_StoredWells_{index}",
            (0.1020, 0.0640, 0.0070),
            (tower_x, 0.0, seat_z - 0.0018),
            measured[index % len(measured)] if role == "output" else "ClearLabware",
            target=target,
            parent=root,
            bevel=0.001,
        )
    # A control fascia on the front column: a blanked keypad and one pilot.
    # Which hotel this is, is the control software's business.
    rounded_box(
        f"{name}_ControlFascia",
        (0.010, 0.076, 0.048),
        (front_x - 0.002, 0.0, 0.960),
        "PowderCoatBlack",
        target=target,
        parent=root,
        bevel=0.004,
    )
    cylinder(
        f"{name}_Status",
        0.0035,
        0.005,
        (front_x - 0.008, 0.0, 0.975),
        "CyanIndicator" if role == "input" else "ScreenGreen",
        target=target,
        parent=root,
        rotation=(0.0, math.pi / 2, 0.0),
        vertices=10,
        bevel=0.0005,
    )
    cylinder(
        f"{name}_CablePort",
        0.011,
        0.009,
        (front_x - 0.002, 0.032, 0.040),
        "BlackPolymer",
        target=target,
        parent=root,
        rotation=(0.0, math.pi / 2, 0.0),
        vertices=24,
        bevel=0.001,
    )
    return shuttle


def build_waste(location: Sequence[float], cell_root: bpy.types.Object) -> None:
    target = COLLECTIONS["Modules"]
    root = empty("WasteChute", target=target, location=location, parent=cell_root)
    rounded_box(
        "WasteChuteRim",
        (0.132, 0.091, 0.020),
        (0.0, 0.0, 0.010),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.006,
    )
    rounded_box(
        "WasteChuteVoid",
        (0.105, 0.065, 0.024),
        (0.0, 0.0, 0.016),
        "ScreenGlass",
        target=target,
        parent=root,
        bevel=0.008,
    )
    # A moulded chamfer around the mouth, not a printed caption.  Deck modules
    # are identified by the control software, not by silkscreen for a camera.
    for side, offset in (("Front", -0.0405), ("Rear", 0.0405)):
        rounded_box(
            f"WasteChuteLip{side}",
            (0.118, 0.010, 0.006),
            (0.0, offset, 0.023),
            "AnodizedAluminum",
            target=target,
            parent=root,
            bevel=0.002,
        )


def _reagent_bottle(
    name: str,
    location: Sequence[float],
    *,
    radius: float,
    height: float,
    glass: str,
    target: bpy.types.Collection,
    parent: bpy.types.Object,
) -> bpy.types.Object:
    """Body, shoulder, neck, cap - the four parts that make a bottle a bottle.

    The bottle is built on its own mount so the caller can turn it.  The body
    is a cylinder and does not care, but the label does, and a shelf of bottles
    whose labels all face the same way is a shelf nobody has ever taken one off.
    """
    x, y, base = location
    body_height = height * 0.66
    mount = empty(f"{name}Mount", target=target, location=(x, y, base), parent=parent)
    cylinder(
        f"{name}Body",
        radius,
        body_height,
        (0.0, 0.0, body_height / 2.0),
        glass,
        target=target,
        parent=mount,
        vertices=20,
        bevel=0.002,
    )
    cylinder(
        f"{name}Shoulder",
        radius * 0.62,
        height * 0.18,
        (0.0, 0.0, body_height + height * 0.09),
        glass,
        target=target,
        parent=mount,
        vertices=20,
        bevel=0.004,
    )
    cylinder(
        f"{name}Neck",
        radius * 0.34,
        height * 0.10,
        (0.0, 0.0, body_height + height * 0.23),
        glass,
        target=target,
        parent=mount,
        vertices=16,
        bevel=0.001,
    )
    cylinder(
        f"{name}Cap",
        radius * 0.40,
        height * 0.09,
        (0.0, 0.0, body_height + height * 0.32),
        "HDPEBlueCap",
        target=target,
        parent=mount,
        vertices=16,
        bevel=0.002,
    )
    rounded_box(
        f"{name}Label",
        (radius * 1.30, 0.002, height * 0.30),
        (0.0, -radius * 0.96, body_height * 0.52),
        "PaperWhite",
        target=target,
        parent=mount,
        bevel=0.001,
    )
    return mount


def _tip_box_stack(
    name: str,
    location: Sequence[float],
    count: int,
    material: str,
    *,
    target: bpy.types.Collection,
    parent: bpy.types.Object,
    yaw: float = 0.0,
    drift: Sequence[tuple[float, float, float]] = (),
    open_top: bool = False,
) -> None:
    """One stack of tip boxes, as a pair of hands would have left it.

    ``yaw`` turns the stack off the bench axis and ``drift`` offsets each box
    within it, because nobody stacks boxes on a shared centreline.  ``open_top``
    takes the lid off the top box and leans it against the stack, which is what
    the box being used looks like.
    """
    x, y, base = location
    for index in range(count):
        z = base + 0.031 + index * 0.062
        offset_x, offset_y, offset_yaw = drift[index] if index < len(drift) else (0.0, 0.0, 0.0)
        box_yaw = yaw + math.radians(offset_yaw)
        rounded_box(
            f"{name}_{index}",
            (0.128, 0.086, 0.058),
            (x + offset_x, y + offset_y, z),
            material,
            target=target,
            parent=parent,
            rotation=(0.0, 0.0, box_yaw),
            bevel=0.004,
        )
        if open_top and index == count - 1:
            # The lid is off and set down flat beside the box it came from,
            # turned further out of square than the box was: it was put down in
            # one motion, not aligned to anything.
            local_x, local_y = -0.150, -0.016
            rounded_box(
                f"{name}LidOff_{index}",
                (0.124, 0.082, 0.006),
                (
                    x + offset_x + local_x * math.cos(box_yaw) - local_y * math.sin(box_yaw),
                    y + offset_y + local_x * math.sin(box_yaw) + local_y * math.cos(box_yaw),
                    base + 0.003,
                ),
                "ClearLabware",
                target=target,
                parent=parent,
                rotation=(0.0, 0.0, box_yaw + math.radians(26.0)),
                bevel=0.002,
            )
            continue
        rounded_box(
            f"{name}Lid_{index}",
            (0.124, 0.082, 0.006),
            (x + offset_x, y + offset_y, z + 0.031),
            "ClearLabware",
            target=target,
            parent=parent,
            rotation=(0.0, 0.0, box_yaw),
            bevel=0.002,
        )


def anchor(
    anchor_id: str, position: Sequence[float], cell_root: bpy.types.Object
) -> bpy.types.Object:
    """An anchor is a semantic workflow point: ``Anchor_<Id>`` carries its id."""
    obj = empty(
        f"Anchor_{node_case(anchor_id)}",
        target=COLLECTIONS["Anchors"],
        location=position,
        parent=cell_root,
    )
    obj["opensdlAnchor"] = True
    obj["opensdlAnchorId"] = anchor_id
    obj.empty_display_type = "SPHERE"
    obj.empty_display_size = 0.018
    return obj


def key_location(obj: bpy.types.Object, frame: int, location: Sequence[float]) -> None:
    obj.location = location
    obj.keyframe_insert(data_path="location", frame=frame, group="Transform")


def key_rotation(obj: bpy.types.Object, frame: int, rotation: Sequence[float]) -> None:
    obj.rotation_euler = rotation
    obj.keyframe_insert(data_path="rotation_euler", frame=frame, group="Transform")


def key_scale(obj: bpy.types.Object, frame: int, scale: Sequence[float]) -> None:
    obj.scale = scale
    obj.keyframe_insert(data_path="scale", frame=frame, group="Transform")


def set_action_name(obj: bpy.types.Object, name: str) -> None:
    if obj.animation_data and obj.animation_data.action:
        obj.animation_data.action.name = name


def set_interpolation(obj: bpy.types.Object, interpolation: str = "BEZIER") -> None:
    for fcurve in action_fcurves(obj):
        for point in fcurve.keyframe_points:
            point.interpolation = interpolation
            if interpolation == "BEZIER":
                point.handle_left_type = "AUTO_CLAMPED"
                point.handle_right_type = "AUTO_CLAMPED"


def animate_scene(
    bridge: bpy.types.Object,
    mover: bpy.types.Object,
    gripper_head: bpy.types.Object,
    pipette_head: bpy.types.Object,
    attached_tips: bpy.types.Object,
    jaw_left: bpy.types.Object,
    jaw_right: bpy.types.Object,
    drag: bpy.types.Object,
    sample: bpy.types.Object,
    liquid_columns: Sequence[bpy.types.Object],
    mixer: bpy.types.Object,
    mixer_latches: Sequence[bpy.types.Object],
    reader_door: bpy.types.Object,
    reader_status: bpy.types.Object,
    rack_tip_columns: Sequence[bpy.types.Object],
    input_shuttle: bpy.types.Object,
    output_shuttle: bpy.types.Object,
    slots: dict[str, tuple[float, float, float]],
) -> None:
    positions = {
        "input": (slots["input-handoff"][0], slots["input-handoff"][1], HOTEL_PLATE_Z),
        "dispense": (slots["stage"][0], slots["stage"][1], DIRECT_DECK_PLATE_Z),
        "mix": (slots["mixer"][0], slots["mixer"][1], MIXER_PLATE_Z),
        "characterize": (slots["reader"][0], slots["reader"][1], CHARACTERIZER_PLATE_Z),
        "door_closed": (slots["reader"][0], slots["reader"][1], DOOR_CLOSED_Z),
        "door_dock": (slots[DOOR_DOCK_SLOT][0], slots[DOOR_DOCK_SLOT][1], DOOR_DOCK_Z),
        "output": (slots["output-handoff"][0], slots["output-handoff"][1], HOTEL_PLATE_Z),
    }
    # Mover heights derive from the grip line and the real seating plane of each
    # station, so a station height can only be changed in one place.
    safe_z = 0.0
    mover_input_z = positions["input"][2] - PLATE_GRIP_LOCAL_Z
    mover_dispense_z = positions["dispense"][2] - PLATE_GRIP_LOCAL_Z
    mover_mix_z = positions["mix"][2] - PLATE_GRIP_LOCAL_Z
    mover_characterize_z = positions["characterize"][2] - PLATE_GRIP_LOCAL_Z
    mover_output_z = positions["output"][2] - PLATE_GRIP_LOCAL_Z
    mover_door_closed_z = positions["door_closed"][2] - DOOR_GRIP_LOCAL_Z
    mover_door_dock_z = positions["door_dock"][2] - DOOR_GRIP_LOCAL_Z
    jaw_open = 0.092
    # The closed widths are the payload half-width plus half the paddle, so the
    # paddle faces meet the plate skirt and the door grips exactly.
    jaw_plate_closed = PLATE_LENGTH / 2.0 + JAW_THICKNESS / 2.0 + 0.00002
    jaw_door_closed = DOOR_GRIP_OUTER_X + JAW_THICKNESS / 2.0
    hotel_stored_x = 0.2075
    # Both hotels are turned a quarter turn, so their shuttle stroke is a
    # local X displacement that reads out along world Y.
    hotel_extended_x = slots["input-handoff"][1] - slots["input-hotel"][1]
    # A payload held by the jaws hangs below the grip line by its own grip
    # offset.  Every carried keyframe is computed from this table.
    carry_offset = {sample: PLATE_GRIP_LOCAL_Z, reader_door: DOOR_GRIP_LOCAL_Z}
    head_dock_pose = {
        gripper_head: (HEAD_DOCK_X["Gripper"], HEAD_DOCK_Y, HEAD_DOCK_Z),
        pipette_head: (HEAD_DOCK_X["Pipette"], HEAD_DOCK_Y, HEAD_DOCK_Z),
    }
    coupler_pins = [bpy.data.objects[f"MoverCouplerPin{side}"] for side in ("Left", "Right")]
    pin_base_z = (MOVER_CARRIAGE_BOTTOM_Z + COUPLER_PIN_BOTTOM_Z) / 2.0

    def key_mover(
        frame: int,
        x: float,
        y: float,
        z: float = safe_z,
        *,
        head: bpy.types.Object | None = None,
        carrying: bpy.types.Object | None = None,
    ) -> None:
        """Key the bridge, the mover, its head and any payload from one pose.

        There is one driven carriage.  A coupled head has no pose of its own:
        it is written from the mover pose here, which is what makes a head
        physically incapable of travelling on its own.
        """
        key_location(bridge, frame, (0.0, y, 0.0))
        key_location(mover, frame, (x, 0.0, z))
        key_location(drag, frame, (x, 0.0, 0.0))
        if head is not None:
            key_location(head, frame, (x, y, z))
        if carrying is not None:
            key_location(carrying, frame, (x, y, z + carry_offset[carrying]))

    def key_head_docked(head: bpy.types.Object, frame: int) -> None:
        """Hold a head at rest in its own dock, hanging by its collar."""
        key_location(head, frame, head_dock_pose[head])

    def key_coupler(frame: int, *, locked: bool) -> None:
        """Extend or retract the changer's guide pins.

        The boss still reaches into the head while the pins are out, which is
        correct: the head is released by the mover rising, not by the pins.
        """
        for pin in coupler_pins:
            key_location(
                pin,
                frame,
                (pin.location.x, pin.location.y, pin_base_z + (0.0 if locked else 0.018)),
            )

    def key_pipette(frame: int, x: float, y: float, z: float = safe_z) -> None:
        """Place the nozzle column, not the mover origin, over (x, y)."""
        key_mover(frame, x, y - NOZZLE_COLUMN_Y, z, head=pipette_head)

    def key_jaws(frame: int, width: float) -> None:
        key_location(jaw_left, frame, (-width, -0.012, JAW_CARRIER_LOCAL_Z))
        key_location(jaw_right, frame, (width, -0.012, JAW_CARRIER_LOCAL_Z))

    def key_plate(frame: int, position: Sequence[float]) -> None:
        key_location(sample, frame, position)

    def key_mixer(frame: int, dx: float, dy: float, *, carrying: bool) -> None:
        """Key the shaker platform, and the plate clamped to it, together."""
        key_location(mixer, frame, (dx, dy, 0.069))
        if carrying:
            key_plate(frame, (positions["mix"][0] + dx, positions["mix"][1] + dy, MIXER_PLATE_Z))

    def key_shuttle(
        shuttle: bpy.types.Object,
        slot: Sequence[float],
        frame: int,
        x: float,
        *,
        carrying: bool,
    ) -> None:
        """Key a hotel shuttle, and the plate resting in its nest, together.

        The module is rotated a quarter turn, so a local +X shuttle move is a
        world +Y move of the plate riding it.
        """
        key_location(shuttle, frame, (x, 0.0, 0.228))
        if carrying:
            key_plate(frame, (slot[0], slot[1] + x, HOTEL_PLATE_Z))

    def key_latches(frame: int, *, opened: bool) -> None:
        for latch, sign in zip(mixer_latches, (-1.0, 1.0), strict=True):
            y = sign * (MIXER_LATCH_OPEN_Y if opened else MIXER_LATCH_CLOSED_Y)
            angle = -sign * MIXER_LATCH_OPEN_ANGLE if opened else 0.0
            key_location(latch, frame, (0.0, y, 0.014))
            key_rotation(latch, frame, (angle, 0.0, 0.0))

    reader_x, reader_y = positions["characterize"][0], positions["characterize"][1]
    door_dock_x, door_dock_y = positions["door_dock"][0], positions["door_dock"][1]

    # ---- Phase 1: transfer input -> dispense -------------------------------
    # The cell starts with the gripper head coupled, the pipetting head in its
    # dock, and the reader closed.  Stage the reader door, then fetch the plate.
    key_mover(BEAT["start"], reader_x, reader_y, head=gripper_head)
    key_coupler(BEAT["start"], locked=True)
    key_jaws(BEAT["start"], jaw_open)
    key_location(reader_door, BEAT["start"], positions["door_closed"])
    key_head_docked(pipette_head, BEAT["start"])
    reader_emission = (
        reader_status.data.materials[0]
        .node_tree.nodes["Principled BSDF"]
        .inputs["Emission Strength"]
    )
    for frame, value in (
        (BEAT["start"], 1.0),
        (8, 7.0),
        (BEAT["door_settle"], 1.0),
        (BEAT["door_close_clear"], 1.0),
        (BEAT["door_close_clear"] + 6, 11.0),
        (BEAT["door_close_clear"] + 12, 4.0),
        (BEAT["door_close_clear"] + 18, 11.0),
        (BEAT["read_hold"], 1.0),
        (FRAME_END, 1.0),
    ):
        reader_emission.default_value = value
        reader_emission.keyframe_insert(data_path="default_value", frame=frame)
    key_mover(BEAT["door_settle"], reader_x, reader_y, head=gripper_head)
    key_mover(BEAT["door_down"], reader_x, reader_y, mover_door_closed_z, head=gripper_head)
    key_jaws(BEAT["door_down"], jaw_open)
    key_jaws(BEAT["door_grip"], jaw_door_closed)
    key_mover(
        BEAT["door_grip"],
        reader_x,
        reader_y,
        mover_door_closed_z,
        head=gripper_head,
        carrying=reader_door,
    )
    key_mover(BEAT["door_lift"], reader_x, reader_y, head=gripper_head, carrying=reader_door)
    key_mover(BEAT["door_cross"], door_dock_x, door_dock_y, head=gripper_head, carrying=reader_door)
    key_mover(
        BEAT["door_seat"],
        door_dock_x,
        door_dock_y,
        mover_door_dock_z,
        head=gripper_head,
        carrying=reader_door,
    )
    key_jaws(BEAT["door_seat"], jaw_door_closed)
    key_jaws(BEAT["door_release"], jaw_open)
    key_mover(BEAT["door_release"], door_dock_x, door_dock_y, mover_door_dock_z, head=gripper_head)
    key_mover(BEAT["door_clear"], door_dock_x, door_dock_y, head=gripper_head)
    key_mover(BEAT["door_row_front"], door_dock_x, positions["characterize"][1], head=gripper_head)

    # Retrieve the input plate: the hotel shuttle extends to the hand-off
    # position at the front of the input station before the mover approaches.
    # The plate rides the shuttle, so its keys derive from the shuttle pose
    # rather than repeating the same travel by hand.
    input_slot = slots["input-hotel"]
    key_shuttle(input_shuttle, input_slot, BEAT["start"], hotel_stored_x, carrying=True)
    key_shuttle(input_shuttle, input_slot, BEAT["door_clear"], hotel_stored_x, carrying=True)
    key_shuttle(
        input_shuttle, input_slot, BEAT["plate_approach"] - 5, hotel_extended_x, carrying=True
    )

    key_mover(
        BEAT["plate_approach"], positions["input"][0], positions["input"][1], head=gripper_head
    )
    key_mover(
        BEAT["plate_down"],
        positions["input"][0],
        positions["input"][1],
        mover_input_z,
        head=gripper_head,
    )
    key_jaws(BEAT["plate_down"], jaw_open)
    key_jaws(BEAT["plate_grip"], jaw_plate_closed)
    key_mover(
        BEAT["plate_grip"],
        positions["input"][0],
        positions["input"][1],
        mover_input_z,
        head=gripper_head,
        carrying=sample,
    )
    key_mover(
        BEAT["plate_lift"],
        positions["input"][0],
        positions["input"][1],
        head=gripper_head,
        carrying=sample,
    )
    # Once the plate has cleared the shuttle, retract the empty presentation
    # tray into the input hotel instead of leaving it across the hand-off.
    key_shuttle(input_shuttle, input_slot, BEAT["plate_lift"], hotel_extended_x, carrying=False)
    key_shuttle(input_shuttle, input_slot, BEAT["plate_seat"], hotel_stored_x, carrying=False)
    key_mover(
        BEAT["plate_cross"],
        positions["dispense"][0],
        positions["dispense"][1],
        head=gripper_head,
        carrying=sample,
    )
    key_mover(
        BEAT["plate_seat"],
        positions["dispense"][0],
        positions["dispense"][1],
        mover_dispense_z,
        head=gripper_head,
        carrying=sample,
    )
    key_jaws(BEAT["plate_seat"], jaw_plate_closed)
    key_jaws(BEAT["plate_release"], jaw_open)
    key_mover(
        BEAT["plate_release"],
        positions["dispense"][0],
        positions["dispense"][1],
        mover_dispense_z,
        head=gripper_head,
    )
    key_mover(
        BEAT["plate_clear"], positions["dispense"][0], positions["dispense"][1], head=gripper_head
    )
    key_mover(
        BEAT["transfer_in_end"],
        positions["dispense"][0],
        positions["dispense"][1],
        head=gripper_head,
    )

    # ---- Head change A: gripper out, pipetting head in ----------------------
    # The mover crosses to the gripper dock at the front row, steps back over
    # the cradle, lowers until the collar takes on the arms, unlocks, and rises
    # away empty.  Nothing about the head moves under its own power.
    gripper_dock_x = HEAD_DOCK_X["Gripper"]
    pipette_dock_x = HEAD_DOCK_X["Pipette"]
    key_mover(BEAT["swap_a_over_gripper"], gripper_dock_x, ROW_FRONT, head=gripper_head)
    key_mover(BEAT["swap_a_row_back"], gripper_dock_x, HEAD_DOCK_Y, head=gripper_head)
    key_mover(BEAT["swap_a_seat"], gripper_dock_x, HEAD_DOCK_Y, HEAD_DOCK_Z, head=gripper_head)
    key_coupler(BEAT["swap_a_seat"], locked=True)
    key_coupler(BEAT["swap_a_unlock"], locked=False)
    key_head_docked(gripper_head, BEAT["swap_a_unlock"])
    key_mover(BEAT["swap_a_lift"], gripper_dock_x, HEAD_DOCK_Y)
    key_head_docked(gripper_head, BEAT["swap_a_lift"])
    key_mover(BEAT["swap_a_traverse"], pipette_dock_x, HEAD_DOCK_Y)
    key_head_docked(gripper_head, BEAT["swap_a_traverse"])
    key_head_docked(pipette_head, BEAT["swap_a_traverse"])
    key_mover(BEAT["swap_a_down"], pipette_dock_x, HEAD_DOCK_Y, HEAD_DOCK_Z, head=pipette_head)
    key_coupler(BEAT["swap_a_down"], locked=False)
    key_coupler(BEAT["swap_a_lock"], locked=True)
    key_mover(BEAT["swap_a_lock"], pipette_dock_x, HEAD_DOCK_Y, HEAD_DOCK_Z, head=pipette_head)
    key_mover(BEAT["swap_a_ready"], pipette_dock_x, HEAD_DOCK_Y, head=pipette_head)

    # ---- Phase 2: dispense --------------------------------------------------
    # Real 8-channel liquid handling. Each pass picks one rack column, aspirates
    # from one reservoir lane, and dispenses A-H column-by-column across all
    # twelve plate columns. The liquid fill transforms are keyed to each touch.
    plate_offsets = [(column - 5.5) * 0.009 for column in range(12)]
    key_scale(attached_tips, BEAT["start"], (1.0, 1.0, 0.02))
    key_scale(rack_tip_columns[0], BEAT["start"], (1.0, 1.0, 1.0))
    key_scale(rack_tip_columns[1], BEAT["start"], (1.0, 1.0, 1.0))
    for pass_index, (letter, column_index) in enumerate((("a", 0), ("b", 1))):
        tip_x = slots["tips"][0] + plate_offsets[column_index]
        reservoir_x = slots["reservoir"][0] + plate_offsets[column_index]
        waste_x, waste_y, _ = slots["tip-waste"]
        key_pipette(BEAT[f"tips_{letter}_approach"], tip_x, slots["tips"][1])
        key_pipette(BEAT[f"tips_{letter}_down"], tip_x, slots["tips"][1], TIP_PICK_Z)
        key_scale(rack_tip_columns[column_index], BEAT[f"tips_{letter}_dwell"], (1.0, 1.0, 1.0))
        key_scale(rack_tip_columns[column_index], BEAT[f"tips_{letter}_taken"], (1.0, 1.0, 0.02))
        key_scale(attached_tips, BEAT[f"tips_{letter}_dwell"], (1.0, 1.0, 0.02))
        key_scale(attached_tips, BEAT[f"tips_{letter}_taken"], (1.0, 1.0, 1.0))
        key_pipette(BEAT[f"tips_{letter}_dwell"], tip_x, slots["tips"][1], TIP_PICK_Z)
        key_pipette(BEAT[f"tips_{letter}_taken"], tip_x, slots["tips"][1], TIP_PICK_Z)
        key_pipette(BEAT[f"tips_{letter}_up"], tip_x, slots["tips"][1])
        key_pipette(BEAT[f"res_{letter}_approach"], reservoir_x, slots["reservoir"][1])
        key_pipette(
            BEAT[f"res_{letter}_down"], reservoir_x, slots["reservoir"][1], RESERVOIR_ASPIRATE_Z
        )
        key_pipette(
            BEAT[f"res_{letter}_hold"], reservoir_x, slots["reservoir"][1], RESERVOIR_ASPIRATE_Z
        )
        key_pipette(BEAT[f"res_{letter}_up"], reservoir_x, slots["reservoir"][1])
        fill_from, fill_to = (0.03, 0.46) if pass_index == 0 else (0.46, 1.0)
        for column, offset in enumerate(plate_offsets):
            frame = BEAT[f"fill_{letter}_start"] + column * WELL_COLUMN_PITCH
            x = positions["dispense"][0] + offset
            key_pipette(frame, x, positions["dispense"][1])
            key_pipette(frame + 3, x, positions["dispense"][1], WELL_ENTRY_Z)
            key_scale(liquid_columns[column], frame + 3, (1.0, 1.0, fill_from))
            key_scale(liquid_columns[column], frame + 5, (1.0, 1.0, fill_to))
            key_pipette(frame + 5, x, positions["dispense"][1], WELL_ENTRY_Z)
            key_pipette(frame + 7, x, positions["dispense"][1])
        key_pipette(BEAT[f"waste_{letter}_approach"], waste_x, waste_y)
        key_pipette(BEAT[f"waste_{letter}_down"], waste_x, waste_y, WASTE_ENTRY_Z)
        key_scale(attached_tips, BEAT[f"waste_{letter}_down"], (1.0, 1.0, 1.0))
        key_scale(attached_tips, BEAT[f"waste_{letter}_drop"], (1.0, 1.0, 0.02))
        key_pipette(BEAT[f"waste_{letter}_drop"], waste_x, waste_y, WASTE_ENTRY_Z)
        key_pipette(BEAT[f"waste_{letter}_up"], waste_x, waste_y)
    key_pipette(BEAT["dispense_end"], slots["tip-waste"][0], slots["tip-waste"][1])

    # ---- Head change B: pipetting head out, gripper in ----------------------
    key_mover(BEAT["swap_b_over_pipette"], pipette_dock_x, HEAD_DOCK_Y, head=pipette_head)
    key_mover(BEAT["swap_b_seat"], pipette_dock_x, HEAD_DOCK_Y, HEAD_DOCK_Z, head=pipette_head)
    key_coupler(BEAT["swap_b_seat"], locked=True)
    key_coupler(BEAT["swap_b_unlock"], locked=False)
    key_head_docked(pipette_head, BEAT["swap_b_unlock"])
    key_mover(BEAT["swap_b_lift"], pipette_dock_x, HEAD_DOCK_Y)
    key_head_docked(pipette_head, BEAT["swap_b_lift"])
    key_mover(BEAT["swap_b_traverse"], gripper_dock_x, HEAD_DOCK_Y)
    key_head_docked(pipette_head, BEAT["swap_b_traverse"])
    key_head_docked(gripper_head, BEAT["swap_b_traverse"])
    key_mover(BEAT["swap_b_down"], gripper_dock_x, HEAD_DOCK_Y, HEAD_DOCK_Z, head=gripper_head)
    key_coupler(BEAT["swap_b_down"], locked=False)
    key_coupler(BEAT["swap_b_lock"], locked=True)
    key_mover(BEAT["swap_b_lock"], gripper_dock_x, HEAD_DOCK_Y, HEAD_DOCK_Z, head=gripper_head)
    key_mover(BEAT["swap_b_lift2"], gripper_dock_x, HEAD_DOCK_Y, head=gripper_head)
    key_mover(BEAT["swap_b_row_front"], gripper_dock_x, ROW_FRONT, head=gripper_head)
    key_head_docked(pipette_head, BEAT["swap_b_row_front"])
    key_head_docked(pipette_head, FRAME_END)
    key_jaws(BEAT["swap_b_row_front"], jaw_open)

    # ---- Phase 3: transfer dispense -> mix ----------------------------------
    # The mixer clamp remains open for placement, closes before the orbital
    # cycle, and opens again before the gripper retrieves the plate.
    key_latches(BEAT["start"], opened=True)
    key_latches(BEAT["mix_cross"], opened=True)
    key_mover(
        BEAT["mix_approach"], positions["dispense"][0], positions["dispense"][1], head=gripper_head
    )
    key_mover(
        BEAT["mix_pick_down"],
        positions["dispense"][0],
        positions["dispense"][1],
        mover_dispense_z,
        head=gripper_head,
    )
    key_jaws(BEAT["mix_pick_down"], jaw_open)
    key_jaws(BEAT["mix_pick_grip"], jaw_plate_closed)
    key_mover(
        BEAT["mix_pick_grip"],
        positions["dispense"][0],
        positions["dispense"][1],
        mover_dispense_z,
        head=gripper_head,
        carrying=sample,
    )
    key_mover(
        BEAT["mix_pick_lift"],
        positions["dispense"][0],
        positions["dispense"][1],
        head=gripper_head,
        carrying=sample,
    )
    key_mover(
        BEAT["mix_cross"],
        positions["mix"][0],
        positions["mix"][1],
        head=gripper_head,
        carrying=sample,
    )
    key_mover(
        BEAT["mix_place_down"],
        positions["mix"][0],
        positions["mix"][1],
        mover_mix_z,
        head=gripper_head,
        carrying=sample,
    )
    key_jaws(BEAT["mix_place_down"], jaw_plate_closed)
    key_jaws(BEAT["mix_place_release"], jaw_open)
    key_mover(
        BEAT["mix_place_release"],
        positions["mix"][0],
        positions["mix"][1],
        mover_mix_z,
        head=gripper_head,
    )
    key_mover(BEAT["mix_place_clear"], positions["mix"][0], positions["mix"][1], head=gripper_head)

    # ---- Phase 4: mix -------------------------------------------------------
    # The plate is now the shaker platform's payload: it is keyed from the
    # platform pose for as long as the clamp holds it.
    key_mixer(BEAT["start"], 0.0, 0.0, carrying=False)
    key_mixer(BEAT["mix_place_clear"], 0.0, 0.0, carrying=True)
    key_latches(BEAT["mix_place_clear"], opened=True)
    key_latches(BEAT["mix_clamp_closed"], opened=False)
    # A 2.0 mm-diameter clockwise orbital translation at 800 rpm, sampled
    # directly at the 24 fps video rate, so the plate never yaws or spins.
    # The demonstration compresses the real 20 second hold.
    orbit_radius = 0.001
    for frame in range(BEAT["mix_clamp_closed"] + 2, BEAT["mix_orbit_end"]):
        revolutions = (frame - BEAT["mix_clamp_closed"] - 2) / FPS * (800.0 / 60.0)
        radians = -2.0 * math.pi * revolutions
        key_mixer(
            frame, orbit_radius * math.cos(radians), orbit_radius * math.sin(radians), carrying=True
        )
    key_mixer(BEAT["mix_orbit_end"], 0.0, 0.0, carrying=True)
    key_latches(BEAT["mix_orbit_end"], opened=False)
    key_latches(BEAT["mix_clamp_open"], opened=True)
    key_mover(BEAT["mix_orbit_end"], positions["mix"][0], positions["mix"][1], head=gripper_head)

    # ---- Phase 5: transfer mix -> characterize ------------------------------
    key_mover(BEAT["mix_settle"], positions["mix"][0], positions["mix"][1], head=gripper_head)
    key_mover(
        BEAT["read_pick_down"],
        positions["mix"][0],
        positions["mix"][1],
        mover_mix_z,
        head=gripper_head,
    )
    key_jaws(BEAT["read_pick_down"], jaw_open)
    key_jaws(BEAT["read_pick_grip"], jaw_plate_closed)
    key_mover(
        BEAT["read_pick_grip"],
        positions["mix"][0],
        positions["mix"][1],
        mover_mix_z,
        head=gripper_head,
        carrying=sample,
    )
    key_latches(BEAT["read_pick_grip"], opened=True)
    key_mover(
        BEAT["read_pick_lift"],
        positions["mix"][0],
        positions["mix"][1],
        head=gripper_head,
        carrying=sample,
    )
    key_mover(BEAT["read_cross"], reader_x, reader_y, head=gripper_head, carrying=sample)
    key_mover(
        BEAT["read_place_down"],
        reader_x,
        reader_y,
        mover_characterize_z,
        head=gripper_head,
        carrying=sample,
    )
    key_jaws(BEAT["read_place_down"], jaw_plate_closed)
    key_jaws(BEAT["read_place_release"], jaw_open)
    key_mover(
        BEAT["read_place_release"], reader_x, reader_y, mover_characterize_z, head=gripper_head
    )
    key_mover(BEAT["read_place_clear"], reader_x, reader_y, head=gripper_head)

    # ---- Phase 6: characterize ---------------------------------------------
    # Close the reader with the physical illumination door from its dock, read
    # all 96 wells, then return the door to the reserved slot.
    key_mover(BEAT["characterize_start"], reader_x, reader_y, head=gripper_head)
    key_mover(BEAT["door_fetch_cross"], door_dock_x, door_dock_y, head=gripper_head)
    key_mover(
        BEAT["door_fetch_down"], door_dock_x, door_dock_y, mover_door_dock_z, head=gripper_head
    )
    key_jaws(BEAT["door_fetch_down"], jaw_open)
    key_jaws(BEAT["door_fetch_grip"], jaw_door_closed)
    key_mover(
        BEAT["door_fetch_grip"],
        door_dock_x,
        door_dock_y,
        mover_door_dock_z,
        head=gripper_head,
        carrying=reader_door,
    )
    key_mover(
        BEAT["door_fetch_lift"], door_dock_x, door_dock_y, head=gripper_head, carrying=reader_door
    )
    key_mover(BEAT["door_close_cross"], reader_x, reader_y, head=gripper_head, carrying=reader_door)
    key_mover(
        BEAT["door_close_down"],
        reader_x,
        reader_y,
        mover_door_closed_z,
        head=gripper_head,
        carrying=reader_door,
    )
    key_jaws(BEAT["door_close_down"], jaw_door_closed)
    key_jaws(BEAT["door_close_release"], jaw_open)
    key_mover(
        BEAT["door_close_release"], reader_x, reader_y, mover_door_closed_z, head=gripper_head
    )
    key_mover(BEAT["door_close_clear"], reader_x, reader_y, head=gripper_head)
    # Stay clear of the closed reader for the read, then descend.
    key_mover(BEAT["read_hold"], reader_x, reader_y, head=gripper_head)
    key_mover(BEAT["door_open_down"], reader_x, reader_y, mover_door_closed_z, head=gripper_head)
    key_jaws(BEAT["door_open_down"], jaw_open)
    key_jaws(BEAT["door_open_grip"], jaw_door_closed)
    key_mover(
        BEAT["door_open_grip"],
        reader_x,
        reader_y,
        mover_door_closed_z,
        head=gripper_head,
        carrying=reader_door,
    )
    key_mover(BEAT["door_open_lift"], reader_x, reader_y, head=gripper_head, carrying=reader_door)
    key_mover(
        BEAT["door_return_cross"], door_dock_x, door_dock_y, head=gripper_head, carrying=reader_door
    )
    key_mover(
        BEAT["door_return_down"],
        door_dock_x,
        door_dock_y,
        mover_door_dock_z,
        head=gripper_head,
        carrying=reader_door,
    )
    key_jaws(BEAT["door_return_down"], jaw_door_closed)
    key_jaws(BEAT["door_return_release"], jaw_open)
    key_mover(
        BEAT["door_return_release"], door_dock_x, door_dock_y, mover_door_dock_z, head=gripper_head
    )
    key_mover(BEAT["door_return_clear"], door_dock_x, door_dock_y, head=gripper_head)
    key_mover(BEAT["characterize_end"], door_dock_x, reader_y, head=gripper_head)

    # ---- Phase 7: transfer characterize -> output ---------------------------
    output_slot = slots["output-hotel"]
    key_shuttle(output_shuttle, output_slot, BEAT["start"], hotel_extended_x, carrying=False)
    key_mover(BEAT["out_start"], reader_x, reader_y, head=gripper_head)
    key_mover(BEAT["out_pick_down"], reader_x, reader_y, mover_characterize_z, head=gripper_head)
    key_jaws(BEAT["out_pick_down"], jaw_open)
    key_jaws(BEAT["out_pick_grip"], jaw_plate_closed)
    key_mover(
        BEAT["out_pick_grip"],
        reader_x,
        reader_y,
        mover_characterize_z,
        head=gripper_head,
        carrying=sample,
    )
    key_mover(BEAT["out_pick_lift"], reader_x, reader_y, head=gripper_head, carrying=sample)
    key_mover(
        BEAT["out_cross"],
        positions["output"][0],
        positions["output"][1],
        head=gripper_head,
        carrying=sample,
    )
    key_mover(
        BEAT["out_place_down"],
        positions["output"][0],
        positions["output"][1],
        mover_output_z,
        head=gripper_head,
        carrying=sample,
    )
    key_jaws(BEAT["out_place_down"], jaw_plate_closed)
    key_jaws(BEAT["out_place_release"], jaw_open)
    key_mover(
        BEAT["out_place_release"],
        positions["output"][0],
        positions["output"][1],
        mover_output_z,
        head=gripper_head,
    )
    key_mover(
        BEAT["out_place_clear"], positions["output"][0], positions["output"][1], head=gripper_head
    )
    # The plate now belongs to the output shuttle, which withdraws it into the
    # hotel; both are keyed from the same shuttle pose.
    key_shuttle(
        output_shuttle, output_slot, BEAT["out_place_clear"], hotel_extended_x, carrying=True
    )
    key_shuttle(output_shuttle, output_slot, BEAT["out_stored"], hotel_stored_x, carrying=True)
    key_mover(FRAME_END, MOVER_PARK_X, ROW_FRONT, head=gripper_head)
    key_latches(FRAME_END, opened=True)

    for obj, action_name in (
        (bridge, "cell_cycle"),
        (mover, "cell_cycle"),
        (gripper_head, "cell_cycle"),
        (pipette_head, "cell_cycle"),
        (attached_tips, "liquid_handling_cycle"),
        (jaw_left, "cell_cycle"),
        (jaw_right, "cell_cycle"),
        (drag, "cell_cycle"),
        (sample, "cell_cycle"),
        (coupler_pins[0], "head_change_cycle"),
        (coupler_pins[1], "head_change_cycle"),
        (mixer, "mix_cycle"),
        (mixer_latches[0], "mixer_clamp_cycle"),
        (mixer_latches[1], "mixer_clamp_cycle"),
        (reader_door, "characterize_cycle"),
        (input_shuttle, "input_hotel_cycle"),
        (output_shuttle, "output_hotel_cycle"),
    ):
        set_action_name(obj, action_name)
        set_interpolation(obj)
    for obj in (*liquid_columns, *rack_tip_columns[:2]):
        set_action_name(obj, "liquid_handling_cycle")
        set_interpolation(obj)


def look_at(obj: bpy.types.Object, point: Sequence[float]) -> None:
    direction = Vector(point) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


# Named camera poses in millimetres, in the scene frame.  A composed room is
# never auto-framed: every pose states its eye, its look point, its lens, the
# frame it reads at, and the object-name prefixes it hides, so any consumer of
# this scene frames it the same way.  These are stills.  The 960-frame render is
# shot by ``CAMERA_SHOTS`` further down, and ``still`` is the pose the published
# preview is framed from, held apart from the edit so the two cannot fight over
# the camera.
#
# Hide lists belong to poses, not to the scene.  Every pose here stands inside
# the room, so the walls behind the camera cull themselves and a hide list is
# only ever used to clear a near object out of a detail view.  Hiding a wall a
# pose can see would render the void behind it.
CAM_RIG: dict[str, dict[str, object]] = {
    "still": {
        "eye": (2280, -3520, 1930),
        "look": (-260, 60, 1240),
        "lens": 28,
        "fstop": 16,
        "frame": BEAT["mix_cross"],
        "hide": (),
        "note": "The published preview still; the whole machine stays in shot.",
    },
    "hero": {
        "eye": (3150, -2960, 1430),
        "look": (-300, 190, 1265),
        "lens": 24,
        "fstop": 8,
        "frame": BEAT["mix_cross"],
        "hide": (),
        "note": (
            "The establishing view: low and wide from the front-right of the aisle, so the "
            "frame converges and the machine reads as a lit, precise piece of engineering "
            "rather than as an elevation."
        ),
    },
    "loop": {
        "eye": (140, -2760, 2360),
        "look": (0, 60, 1210),
        "lens": 24,
        "fstop": 11,
        "frame": BEAT["mix_cross"],
        "hide": (),
        "note": (
            "Raised and square to the machine so the closed loop reads left to right: "
            "load port, input hotel, dispense, mix, read, output hotel, and the rack "
            "under the deck that chooses the next experiment."
        ),
    },
    "compute": {
        "eye": (1010, -1980, 1030),
        "look": (1440, -70, 700),
        "lens": 42,
        "fstop": 16,
        "frame": BEAT["mix_cross"],
        "hide": ("ProcessGuard", "Splash"),
        "note": "The rack inside the frame and the campaign state on its display.",
    },
    "controls": {
        "eye": (-2260, -2540, 1120),
        "look": (-1430, -180, 545),
        "lens": 42,
        "fstop": 16,
        "frame": BEAT["mix_cross"],
        "hide": (),
        "note": "Controls cabinet, isolator, trunking and the frame's left tower.",
    },
    "drives": {
        "eye": (560, -1560, 980),
        "look": (860, 90, 520),
        "lens": 38,
        "fstop": 18,
        "frame": BEAT["mix_cross"],
        "hide": (),
        "note": "The open drive bank: DIN rail, breakers, supplies and wiring duct.",
    },
    "station-input": {
        "eye": (-940, -1300, 1700),
        "look": (-1560, 40, 1210),
        "lens": 44,
        "fstop": 22,
        "frame": BEAT["plate_approach"],
        "hide": ("MoverBridgeBeam", "MoverBridgeCover", "MoverBridgeTrack", "MoverTrough"),
        "note": "Input hotel queue and the shuttle presenting a plate at the hand-off.",
    },
    "station-dispense": {
        "eye": (-260, -1080, 1745),
        "look": (-780, 10, 1290),
        "lens": 44,
        "fstop": 22,
        "frame": BEAT["fill_a_start"] + 40,
        "hide": (),
        "note": "Eight-channel head dispensing into the plate on the staging slot.",
    },
    "station-mix": {
        "eye": (580, -1090, 1680),
        "look": (0, 0, 1230),
        "lens": 44,
        "fstop": 22,
        "frame": BEAT["mix_orbit_end"] - 12,
        "hide": (),
        "note": "Heater-Shaker clamped on the plate during the orbital hold.",
    },
    "station-characterize": {
        "eye": (1360, -1030, 1840),
        "look": (780, 20, 1215),
        "lens": 44,
        "fstop": 22,
        "frame": BEAT["door_close_clear"],
        "hide": (),
        "note": "Absorbance reader loaded and open, its lid parked on the caddy behind it.",
    },
    "station-output": {
        "eye": (2140, -1260, 1700),
        "look": (1560, 40, 1210),
        "lens": 44,
        "fstop": 22,
        "frame": BEAT["out_place_clear"],
        "hide": ("MoverBridgeBeam", "MoverBridgeCover", "MoverBridgeTrack", "MoverTrough"),
        "note": "Output hotel taking the finished plate back into the magazine.",
    },
    "transfer-port": {
        "eye": (-2380, -2620, 1520),
        "look": (-1560, -300, 1170),
        "lens": 44,
        "fstop": 18,
        "frame": BEAT["mix_cross"],
        "hide": (),
        "note": "The one human touchpoint: the interlocked load and unload nest.",
    },
    "gripper-closed": {
        "eye": (330, -520, 1372),
        "look": (0, -60, 1258),
        "lens": 62,
        "fstop": 32,
        "frame": BEAT["mix_place_down"],
        "hide": (),
        "note": "Jaws closed on the plate at the mixer; the mechanism is loaded.",
    },
    "gripper-open": {
        "eye": (330, -520, 1420),
        "look": (0, -60, 1300),
        "lens": 62,
        "fstop": 32,
        "frame": BEAT["mix_place_clear"],
        "hide": (),
        "note": "Jaws at full open width, both carriers still on the cross-rail.",
    },
    "head-change-release": {
        "eye": (927, -836, 1560),
        "look": (300, 54, 1356),
        "lens": 55,
        "fstop": 22,
        "frame": BEAT["swap_a_lift"],
        "hide": (),
        "note": (
            "The mover rising away from the gripper head it has just left hanging in "
            "HeadDock_Gripper: the changer is open, the collar is on the arms, and "
            "nothing is floating."
        ),
    },
    "head-change-couple": {
        "eye": (200, -700, 1540),
        "look": (-300, 54, 1330),
        "lens": 55,
        "fstop": 22,
        "frame": BEAT["swap_a_lock"],
        "hide": (),
        "note": (
            "The same mover twelve frames later, locked onto the pipetting head in "
            "HeadDock_Pipette.  One carriage, two heads, one at a time."
        ),
    },
    "head-docks": {
        "eye": (60, -1180, 1720),
        "look": (0, 54, 1250),
        "lens": 34,
        "fstop": 22,
        "frame": BEAT["fill_a_start"] + 40,
        "hide": (),
        "note": (
            "Both docks in one frame during the dispense pass: the gripper head "
            "waiting on the right, the pipetting head away on the mover."
        ),
    },
}


def apply_camera_pose(camera: bpy.types.Object, pose: dict[str, object]) -> None:
    """Place the camera from a named pose.  Millimetres in, metres out."""
    eye = Vector(tuple(value / 1000.0 for value in pose["eye"]))  # type: ignore[union-attr]
    look = Vector(tuple(value / 1000.0 for value in pose["look"]))  # type: ignore[union-attr]
    camera.location = eye
    camera.rotation_euler = (look - eye).to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = float(pose["lens"])  # type: ignore[arg-type]
    camera.data.dof.focus_distance = (look - eye).length
    camera.data.dof.aperture_fstop = float(pose.get("fstop", 16))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# The edit.
#
# The still poses above frame the machine.  This is the film: the 40-second
# cycle cut into six moving takes.  Two standards decide where a cut may fall,
# and both of them are measured rather than judged by eye.
#
# Shot length.  Architectural-visualisation practice is five to eight seconds a
# shot.  An earlier cut of this sequence ran thirteen shots in forty seconds, an
# average of 3.1 s, and the note on it was that the cutting read as jittery
# while the moves themselves were fine.  So the moves stayed and the edit was
# rebuilt at six shots averaging 6.7 s, every one of them inside the band.
#
# Cut quality.  A cut between two shots of the same subject has to change the
# camera angle by at least thirty degrees, or it reads as a jump cut, and it has
# to change the framing as well: about two steps of the shot-size ladder, or at
# least 20 mm of focal length.  ``validate_camera_shots`` computes both numbers
# for every cut and refuses to build if either fails.  Where a cut could not
# have satisfied them, the two shots were merged into one moving take instead.
# That is why a transfer and the operation that follows it share a shot here,
# and it is also what gets the camera close to the work without spending a cut.
SHOT_MIN_SECONDS = 5.0
SHOT_MAX_SECONDS = 8.0
CUT_MIN_ANGLE_DEGREES = 30.0
CUT_MIN_SIZE_STEPS = 2
CUT_MIN_LENS_CHANGE_MM = 20.0
# The camera stays in the front aisle.  The machine's front-most body is the
# transfer-port guard handle at y = -829 mm and the frame feet reach y = -613 mm,
# both measured from the built scene, so an eye behind this plane is authoring a
# camera inside the machine.
CAMERA_AISLE_Y = -880.0
# The aisle plane is a coarse rule on authored keys.  The built path is then
# flown against the real bodies, because a path can respect one plane and still
# take the camera through a frame member between two keys.  222 mm is the
# clearance the previous edit reported and the standard this one has to match.
CAMERA_MIN_CLEARANCE = 0.222
CAMERA_SENSOR_WIDTH = 36.0
CAMERA_TARGET_NAME = "CameraTarget"
# Shot-size ladder, as the horizontal field width in millimetres at the look
# point.  Each step is a factor of about 1.6, which is what makes "two steps" the
# same claim a director makes when they say a cut goes from a medium to a
# close-up.
SHOT_SIZES: tuple[tuple[str, float], ...] = (
    ("extreme close", 250.0),
    ("close", 400.0),
    ("medium close", 640.0),
    ("medium", 1020.0),
    ("medium long", 1640.0),
    ("long", 2620.0),
    ("extreme long", float("inf")),
)
# Aperture follows shot size rather than being authored per key, so "mild depth
# of field on the close beats only" is true by construction instead of being a
# number that drifts.  A wide frame of a machine wants everything sharp.
SHOT_APERTURES: tuple[tuple[float, float], ...] = ((1020.0, 11.0), (1640.0, 16.0))
SHOT_APERTURE_DEEP = 22.0
# Shot-boundary keys are flattened over this many frames on both sides, which is
# what makes a take start and end at zero camera velocity so the cut lands on a
# settled frame.
CAMERA_HANDLE_SPAN = 8.0

# One authored camera key: the frame it lands on, the eye and the look point in
# millimetres in the scene frame, and the focal length.
CameraKey = tuple[int, tuple[float, float, float], tuple[float, float, float], float]


class Shot(TypedDict):
    """One take.  ``keys[0]`` is at ``start`` and ``keys[-1]`` is at ``end``."""

    name: str
    start: int
    end: int
    note: str
    keys: tuple[CameraKey, ...]


# Six shots, in millimetres, tiling frames 1-960 exactly.  A shot's first and
# last key sit on its first and last frame, which is what lets the validator
# measure a cut from the authored data rather than from a rendered frame.
CAMERA_SHOTS: tuple[Shot, ...] = (
    {
        "name": "establish-and-load",
        "start": 1,
        "end": 150,
        "note": (
            "The establishing take.  Wide from the front right of the aisle, then a "
            "slow dolly in and left across the machine, arriving on the input end as "
            "the mover lifts the plate out of the hotel and carries it to the "
            "dispense stage."
        ),
        "keys": (
            (1, (2950, -4200, 2260), (150, 60, 1300), 26),
            (60, (1900, -3760, 2200), (-500, 55, 1290), 28),
            (110, (700, -3350, 2130), (-1150, 30, 1250), 38),
            (150, (-500, -3000, 2050), (-1250, 20, 1240), 52),
        ),
    },
    {
        "name": "head-change-and-tips",
        "start": 151,
        "end": 330,
        "note": (
            "Head change A, close.  The take opens tight on the gripper dock and the "
            "mover flies into it, seats the gripper head, rises away empty and "
            "crosses left; the camera tracks it to the pipette dock, watches the "
            "coupling, then follows the pipetting head on to the tip rack, the "
            "reservoir and the first fill pass."
        ),
        "keys": (
            (151, (900, -1500, 1600), (300, 45, 1265), 62),
            (183, (700, -1400, 1580), (300, 45, 1275), 58),
            (208, (60, -1300, 1560), (-300, 45, 1270), 58),
            (256, (-620, -1300, 1580), (-980, 40, 1245), 52),
            (330, (-1000, -1300, 1600), (-800, -30, 1200), 52),
        ),
    },
    {
        "name": "reverse-and-fill",
        "start": 331,
        "end": 498,
        "note": (
            "The reverse angle, looking down the length of the machine from the "
            "output end.  It opens wide enough that the pipetting head working and "
            "the gripper head waiting in its dock are in the same frame, which is "
            "the whole one-mover-two-heads claim in one image, then travels the "
            "length of the aisle and pushes in through the tip drop and the second "
            "tip pickup until the nozzles entering the wells fill the frame."
        ),
        "keys": (
            (331, (1400, -2600, 1980), (-500, 20, 1250), 34),
            (384, (600, -2300, 1860), (-700, 30, 1240), 42),
            (440, (-400, -1900, 1740), (-800, 20, 1225), 55),
            (498, (-1180, -1180, 1560), (-800, -40, 1190), 75),
        ),
    },
    {
        "name": "head-change-b-and-to-mix",
        "start": 499,
        "end": 672,
        "note": (
            "Head change B and the transfer that follows it, in one travelling take "
            "from the right.  The camera holds the end of the second fill, moves with "
            "the mover as it parks the pipetting head and picks the gripper back up, "
            "pulls back to catch the plate leaving the dispense stage, and settles as "
            "it lands on the mixer."
        ),
        "keys": (
            (499, (760, -2000, 1700), (-500, 20, 1250), 34),
            (552, (900, -1460, 1560), (-320, 40, 1275), 42),
            (600, (940, -1120, 1480), (300, 45, 1265), 50),
            (634, (420, -1700, 1620), (-680, -20, 1215), 34),
            (672, (560, -1500, 1520), (0, -45, 1230), 38),
        ),
    },
    {
        "name": "mix-and-cross",
        "start": 673,
        "end": 800,
        "note": (
            "Tight on the Heater-Shaker from the left through the clamp close and the "
            "orbit, arcing right as it runs, then travelling one station along with "
            "the plate and settling on the reader as the mover goes for its door."
        ),
        "keys": (
            (673, (-700, -880, 1400), (0, -50, 1235), 66),
            (714, (-520, -930, 1390), (0, -50, 1235), 66),
            (760, (0, -1080, 1450), (600, -45, 1245), 48),
            (800, (100, -900, 1420), (760, -30, 1235), 58),
        ),
    },
    {
        "name": "read-and-out",
        "start": 801,
        "end": 960,
        "note": (
            "The closing take, from the right.  Wide while the door crosses between "
            "the two reader rows, in to the longest lens in the film while the reader "
            "indicates, out again as the plate is picked and carried to the output "
            "hotel, then a rise and a pull back to the closing wide."
        ),
        "keys": (
            (801, (2100, -3000, 2100), (850, -20, 1255), 38),
            (848, (1700, -1200, 1560), (800, -40, 1230), 62),
            (892, (1500, -1750, 1660), (900, -35, 1250), 46),
            (927, (1100, -2450, 1800), (1300, -40, 1270), 42),
            (960, (400, -4150, 2320), (0, 60, 1330), 28),
        ),
    },
)


def frame_width(eye: Sequence[float], look: Sequence[float], lens: float) -> float:
    """Horizontal field width in mm at the look point.  This is the shot size."""
    distance = math.dist(tuple(eye), tuple(look))
    return distance * CAMERA_SENSOR_WIDTH / float(lens)


def shot_size(width: float) -> tuple[int, str]:
    for index, (name, limit) in enumerate(SHOT_SIZES):
        if width < limit:
            return index, name
    return len(SHOT_SIZES) - 1, SHOT_SIZES[-1][0]


def shot_aperture(width: float) -> float:
    for limit, fstop in SHOT_APERTURES:
        if width < limit:
            return fstop
    return SHOT_APERTURE_DEEP


def cut_metrics(before: CameraKey, after: CameraKey) -> dict[str, object]:
    """Measure one cut: the angle swung around the subject, and the size change.

    The angle is the thirty-degree rule read literally, as the angle the two
    eyes subtend at the subject rather than the angle between the two view axes,
    which a pair of parallel cameras a metre apart would pass.  The subject is
    the midpoint of the two look points, so a cut that also changes subject
    still gets a number instead of an exemption.
    """
    _, eye_before, look_before, lens_before = before
    _, eye_after, look_after, lens_after = after
    subject = Vector(tuple((a + b) / 2.0 for a, b in zip(look_before, look_after)))
    first = Vector(tuple(eye_before)) - subject
    second = Vector(tuple(eye_after)) - subject
    angle = math.degrees(first.angle(second)) if first.length and second.length else 0.0
    width_before = frame_width(eye_before, look_before, lens_before)
    width_after = frame_width(eye_after, look_after, lens_after)
    index_before, name_before = shot_size(width_before)
    index_after, name_after = shot_size(width_after)
    return {
        "angle": round(angle, 1),
        "sizeBefore": name_before,
        "sizeAfter": name_after,
        "sizeSteps": abs(index_after - index_before),
        "widthBefore": round(width_before),
        "widthAfter": round(width_after),
        "lensBefore": float(lens_before),
        "lensAfter": float(lens_after),
        "lensChange": round(abs(float(lens_after) - float(lens_before)), 1),
    }


def validate_camera_shots() -> dict[str, object]:
    """Refuse to build an edit that breaks the two standards it claims to meet.

    This runs before anything is built, because a shot list that does not tile
    the timeline, or that cuts every three seconds, is a defect in the edit and
    not something to discover at the end of a forty-minute render.
    """
    failures: list[str] = []
    shots: list[dict[str, object]] = []
    seconds_total = 0.0
    expected_start = 1
    for index, shot in enumerate(CAMERA_SHOTS):
        name = shot["name"]
        start = shot["start"]
        end = shot["end"]
        keys = shot["keys"]
        if start != expected_start:
            failures.append(f"{name}: starts at {start}, expected {expected_start}")
        if end < start:
            failures.append(f"{name}: ends at {end} before it starts at {start}")
        expected_start = end + 1
        seconds = (end - start + 1) / FPS
        seconds_total += seconds
        if not SHOT_MIN_SECONDS <= seconds <= SHOT_MAX_SECONDS:
            failures.append(
                f"{name}: {seconds:.2f} s is outside the "
                f"{SHOT_MIN_SECONDS:.0f}-{SHOT_MAX_SECONDS:.0f} s band"
            )
        frames = [key[0] for key in keys]
        if len(frames) < 2:
            failures.append(f"{name}: a shot needs at least two keys, it has {len(frames)}")
        elif frames[0] != start or frames[-1] != end:
            failures.append(f"{name}: keys run {frames[0]}-{frames[-1]}, not {start}-{end}")
        if any(later <= earlier for earlier, later in zip(frames, frames[1:])):
            failures.append(f"{name}: key frames are not strictly increasing: {frames}")
        for frame, eye, _look, lens in keys:
            if eye[1] > CAMERA_AISLE_Y:
                failures.append(
                    f"{name} frame {frame}: eye y={eye[1]:.0f} mm is behind the aisle "
                    f"plane at {CAMERA_AISLE_Y:.0f} mm"
                )
            if lens <= 0.0:
                failures.append(f"{name} frame {frame}: lens {lens} is not a focal length")
        opens_on = frame_width(keys[0][1], keys[0][2], keys[0][3])
        ends_on = frame_width(keys[-1][1], keys[-1][2], keys[-1][3])
        shots.append(
            {
                "index": index,
                "name": name,
                "start": start,
                "end": end,
                "frames": end - start + 1,
                "seconds": round(seconds, 2),
                "opensOn": shot_size(opens_on)[1],
                "endsOn": shot_size(ends_on)[1],
                "lensRange": [min(key[3] for key in keys), max(key[3] for key in keys)],
                "note": shot["note"],
            }
        )
    if expected_start != FRAME_END + 1:
        failures.append(f"The shot list ends at frame {expected_start - 1}, not {FRAME_END}")

    cuts: list[dict[str, object]] = []
    for before, after in zip(CAMERA_SHOTS, CAMERA_SHOTS[1:]):
        metrics = cut_metrics(before["keys"][-1], after["keys"][0])
        metrics["from"] = before["name"]
        metrics["to"] = after["name"]
        metrics["frame"] = before["end"]
        steps = int(metrics["sizeSteps"])  # type: ignore[call-overload]
        lens_change = float(metrics["lensChange"])  # type: ignore[arg-type]
        angle = float(metrics["angle"])  # type: ignore[arg-type]
        framing_ok = steps >= CUT_MIN_SIZE_STEPS or lens_change >= CUT_MIN_LENS_CHANGE_MM
        angle_ok = angle >= CUT_MIN_ANGLE_DEGREES
        metrics["passed"] = angle_ok and framing_ok
        cuts.append(metrics)
        if not angle_ok:
            failures.append(
                f"cut {before['name']} -> {after['name']}: {angle} deg is under the "
                f"{CUT_MIN_ANGLE_DEGREES:.0f} deg rule"
            )
        if not framing_ok:
            failures.append(
                f"cut {before['name']} -> {after['name']}: {steps} size step(s) and "
                f"{lens_change} mm of lens change is neither {CUT_MIN_SIZE_STEPS} steps "
                f"nor {CUT_MIN_LENS_CHANGE_MM:.0f} mm"
            )

    report: dict[str, object] = {
        "shots": shots,
        "cuts": cuts,
        "meanSeconds": round(seconds_total / len(CAMERA_SHOTS), 2),
    }
    if failures:
        raise RuntimeError("Camera edit validation failed:\n- " + "\n- ".join(failures))
    print("CAMERA EDIT: " + json.dumps(report))
    return report


def action_fcurves(holder: object) -> list[bpy.types.FCurve]:
    """Every f-curve on one datablock's action, on either Action storage model."""
    animation = getattr(holder, "animation_data", None)
    action = getattr(animation, "action", None)
    if action is None:
        return []
    curves = list(getattr(action, "fcurves", ()))
    if curves:
        return curves
    # Blender 5 stores curves in layered Action channel bags.
    for layer in action.layers:
        for strip in layer.strips:
            for channelbag in strip.channelbags:
                curves.extend(channelbag.fcurves)
    return curves


def cut_fcurve(curve: bpy.types.FCurve, boundaries: set[int], cuts: set[int]) -> None:
    """Ease every shot boundary to zero velocity, and make every cut a cut.

    Interior keys keep automatic handles so a multi-leg travel reads as one
    continuous move.  A boundary key gets flat handles, which is what makes a
    take start and stop rather than arrive at speed.  The key that ends a shot
    is CONSTANT, so its value holds to the last frame of the shot and changes on
    the next one; that discontinuity is the cut.
    """
    for point in curve.keyframe_points:
        point.interpolation = "BEZIER"
        point.handle_left_type = "AUTO_CLAMPED"
        point.handle_right_type = "AUTO_CLAMPED"
    for point in curve.keyframe_points:
        frame = int(round(point.co.x))
        if frame in boundaries:
            point.handle_left_type = "FREE"
            point.handle_right_type = "FREE"
            point.handle_left = (point.co.x - CAMERA_HANDLE_SPAN, point.co.y)
            point.handle_right = (point.co.x + CAMERA_HANDLE_SPAN, point.co.y)
        if frame in cuts:
            point.interpolation = "CONSTANT"
    curve.update()


def build_camera_choreography(camera: bpy.types.Object) -> bpy.types.Object:
    """Key the edit onto the camera and its look target.

    Aim is a tracked empty rather than a keyed rotation.  Euler interpolation
    flips and gimbals on an arcing move and a TRACK_TO constraint cannot, and
    the same empty is the depth-of-field focus object, so focus sits on the
    subject by construction instead of on a second animated number that can
    drift away from it.  Neither object is exported.

    It clears whatever it finds first, so the edit can be re-applied to a file
    that is already built without rebuilding the geometry to see a camera change.
    """
    scene = bpy.context.scene
    rig = COLLECTIONS.get("RenderRig") or bpy.data.collections.get("RenderRig")
    target = bpy.data.objects.get(CAMERA_TARGET_NAME)
    if target is None:
        target = empty(
            CAMERA_TARGET_NAME,
            target=rig if rig is not None else scene.collection,
            export=False,
        )
        target.empty_display_type = "PLAIN_AXES"
        target.empty_display_size = 0.05
    camera.animation_data_clear()
    camera.data.animation_data_clear()
    target.animation_data_clear()
    camera.constraints.clear()
    camera.rotation_euler = (0.0, 0.0, 0.0)

    boundaries: set[int] = set()
    cuts: set[int] = set()
    for shot in CAMERA_SHOTS:
        boundaries.add(shot["start"])
        boundaries.add(shot["end"])
        cuts.add(shot["end"])
        for frame, eye, look, lens in shot["keys"]:
            key_location(camera, frame, [value / 1000.0 for value in eye])
            key_location(target, frame, [value / 1000.0 for value in look])
            camera.data.lens = lens
            camera.data.keyframe_insert(data_path="lens", frame=frame)
            camera.data.dof.aperture_fstop = shot_aperture(frame_width(eye, look, lens))
            camera.data.keyframe_insert(data_path="dof.aperture_fstop", frame=frame)

    track = camera.constraints.new("TRACK_TO")
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"
    camera.data.dof.use_dof = True
    camera.data.dof.focus_object = target
    camera.data.sensor_width = CAMERA_SENSOR_WIDTH

    for holder in (camera, target, camera.data):
        for curve in action_fcurves(holder):
            cut_fcurve(curve, boundaries, cuts)
    set_action_name(camera, "CameraEdit")
    set_action_name(target, "CameraTargetEdit")
    scene.frame_set(scene.frame_current)
    return target


def suspend_camera_choreography(camera: bpy.types.Object) -> dict[str, object]:
    """Detach the edit so a named still pose can own the camera instead."""
    actions: list[tuple[object, bpy.types.Action, object]] = []
    constraints = [(constraint, constraint.mute) for constraint in camera.constraints]
    for holder in (camera, camera.data):
        animation = getattr(holder, "animation_data", None)
        action = getattr(animation, "action", None)
        if animation is None or action is None:
            continue
        action.use_fake_user = True
        actions.append((holder, action, getattr(animation, "action_slot", None)))
        animation.action = None
    for constraint, _ in constraints:
        constraint.mute = True
    state: dict[str, object] = {
        "actions": actions,
        "constraints": constraints,
        "focus": camera.data.dof.focus_object,
    }
    camera.data.dof.focus_object = None
    return state


def resume_camera_choreography(camera: bpy.types.Object, state: dict[str, object]) -> None:
    for holder, action, slot in state["actions"]:  # type: ignore[union-attr]
        animation = holder.animation_data or holder.animation_data_create()
        animation.action = action
        if slot is not None:
            try:
                animation.action_slot = slot
            except (AttributeError, TypeError, RuntimeError):
                pass
    for constraint, muted in state["constraints"]:  # type: ignore[union-attr]
        constraint.mute = muted
    camera.data.dof.focus_object = state["focus"]


def validate_camera_path(camera: bpy.types.Object, *, step: int = 1) -> dict[str, object]:
    """Fly the built path and measure how close the camera gets to the machine.

    The shot list is checked against one aisle plane, which is a coarse rule; a
    path can respect it and still take the camera through a frame member, the
    bridge or a hotel between two keys.  This walks every frame and measures the
    eye against the world bounds of every static body plus the bridge, which is
    the only moving body big enough to come to the camera.
    """
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import check_scene

    scene = bpy.context.scene
    original_frame = scene.frame_current

    def body_boxes(root_name: str) -> list[tuple[str, tuple[float, ...]]]:
        root = bpy.data.objects.get(root_name)
        if root is None:
            return []
        depsgraph = bpy.context.evaluated_depsgraph_get()
        boxes: list[tuple[str, tuple[float, ...]]] = []
        for obj in (root, *root.children_recursive):
            if obj.type != "MESH":
                continue
            evaluated = obj.evaluated_get(depsgraph)
            corners = [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]
            boxes.append(
                (
                    obj.name,
                    (
                        min(point.x for point in corners),
                        min(point.y for point in corners),
                        min(point.z for point in corners),
                        max(point.x for point in corners),
                        max(point.y for point in corners),
                        max(point.z for point in corners),
                    ),
                )
            )
        return boxes

    scene.frame_set(1)
    bpy.context.view_layer.update()
    static_boxes: list[tuple[str, tuple[float, ...]]] = []
    for name in check_scene.STATICS:
        static_boxes.extend(body_boxes(name))

    path: list[tuple[int, Vector, list[tuple[str, tuple[float, ...]]]]] = []
    for frame in range(1, FRAME_END + 1, step):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        path.append((frame, camera.matrix_world.translation.copy(), body_boxes("MoverBridge")))

    closest = float("inf")
    closest_frame = 0
    closest_body = ""
    for frame, eye, bridge in path:
        for name, box in (*static_boxes, *bridge):
            gap_x = max(box[0] - eye.x, 0.0, eye.x - box[3])
            gap_y = max(box[1] - eye.y, 0.0, eye.y - box[4])
            gap_z = max(box[2] - eye.z, 0.0, eye.z - box[5])
            squared = gap_x * gap_x + gap_y * gap_y + gap_z * gap_z
            if squared < closest:
                closest = squared
                closest_frame = frame
                closest_body = name
    closest = math.sqrt(closest)
    scene.frame_set(original_frame)
    report = {
        "bodies": len(static_boxes) + len(path[0][2]),
        "frames": len(path),
        "closestApproach": round(closest, 4),
        "closestFrame": closest_frame,
        "closestBody": closest_body,
        "required": CAMERA_MIN_CLEARANCE,
    }
    print("CAMERA PATH: " + json.dumps(report))
    if closest < CAMERA_MIN_CLEARANCE:
        raise RuntimeError(
            f"Camera path passes {closest * 1000:.0f} mm from {closest_body} at frame "
            f"{closest_frame}; {CAMERA_MIN_CLEARANCE * 1000:.0f} mm is the minimum"
        )
    return report


def build_camera_and_lighting() -> bpy.types.Object:
    target = COLLECTIONS["RenderRig"]
    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    target.objects.link(camera)
    camera_data.sensor_width = CAMERA_SENSOR_WIDTH
    camera_data.dof.use_dof = True
    apply_camera_pose(camera, CAM_RIG["still"])
    bpy.context.scene.camera = camera
    mark_export(camera, False)

    def area(
        name: str,
        location: Sequence[float],
        energy: float,
        size: Sequence[float],
        color: Sequence[float],
        target_point: Sequence[float],
    ) -> None:
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "RECTANGLE"
        data.size = size[0]
        data.size_y = size[1]
        data.color = color
        obj = bpy.data.objects.new(name, data)
        target.objects.link(obj)
        obj.location = location
        look_at(obj, target_point)
        mark_export(obj, False)

    # The plant space lights itself.  Each ceiling batten carries an area light
    # of its own length at its own aperture, so the light comes from where the
    # fixture is instead of from a studio key parked outside the room.  4000 K,
    # which is what a plant space is actually lit at.
    # The room is lit cool and the machine is lit warm.  That split is what
    # gives the frame its own light instead of leaving it a grey object in a
    # grey volume, and it is how a real facility reads: cool overhead ambient,
    # warmer practicals inside the equipment.
    lamp_colour = (0.735, 0.862, 1.0)
    practical_colour = (1.0, 0.858, 0.678)
    for index, (light_y, light_z) in enumerate(WORKLIGHT_RUNS):
        area(
            f"WorkLightLamp_{index}",
            (0.0, light_y, light_z - 0.042),
            68.0,
            (2 * DECK_HALF_LENGTH + 0.24, 0.048),
            practical_colour,
            (0.0, light_y * 0.4, DECK_Z),
        )
    for hotel in ("input", "output"):
        hotel_x = STATION_X[hotel]
        area(
            f"HotelStripLamp_{hotel}",
            (hotel_x, ROW_FRONT + HOTEL_PRESENT_Y + 0.205, BENCH_Z + 0.520),
            7.0,
            (0.14, 0.74),
            (0.80, 0.92, 1.0),
            (hotel_x, -0.20, BENCH_Z + 0.500),
        )
    area(
        "MountStripLamp",
        (0.0, FRAME_POST_Y[0] + 0.006, FRAME_MOUNT_Z - 0.062),
        20.0,
        (2 * FRAME_HALF_LENGTH - 0.40, 0.036),
        practical_colour,
        (0.0, 0.05, 0.42),
    )
    for strip_x in BAY_STRIP_X:
        area(
            f"BayStripLamp_{strip_x:+.3f}",
            (strip_x, BAY_STRIP_Y + 0.030, (BAY_STRIP_Z[0] + BAY_STRIP_Z[1]) / 2.0),
            13.0,
            (0.040, BAY_STRIP_Z[1] - BAY_STRIP_Z[0]),
            practical_colour,
            (strip_x * 0.55, 0.10, 0.480),
        )
    for index, (x, y, z) in enumerate(BATTEN_RUNS):
        area(
            f"BattenLamp_{index:02d}",
            (x, y, z - 0.024),
            40.0,
            (2 * ROOM_HALF_X - 0.70, BATTEN_WIDTH * 0.9),
            lamp_colour,
            (x, y, 0.0),
        )
    # Low-energy fills stand in for the interreflection this engine does not
    # carry.  The upward fill is scaled to a dark resin floor: left at a
    # pale-floor value it lifts every shadow off the soffit and leaves the frame
    # with no true dark in it.
    area(
        "RoomBounceCeiling",
        (0.0, -1.40, ROOM_CEILING_Z - 0.42),
        6.0,
        (5.6, 4.4),
        (0.94, 0.96, 1.0),
        (0.0, -1.40, 0.0),
    )
    area(
        "RoomBounceFloor",
        (0.0, -1.70, 0.55),
        15.0,
        (5.4, 3.8),
        (0.92, 0.94, 0.98),
        (0.0, -1.70, ROOM_CEILING_Z),
    )
    # The frame is a lattice of thin members, and a lattice lit only from above
    # goes to silhouette.  One very wide, very soft wrap off the aisle puts a
    # readable edge back on every column and rail without flattening them.
    area(
        "RoomWrapFront",
        (0.0, -2.40, 1.55),
        7.0,
        (3.8, 1.6),
        (0.95, 0.96, 1.0),
        (0.0, -0.40, 1.25),
    )
    # A tight fill under the deck, because the service bays are the half of this
    # machine that says it is self-driving and they sit in the deck's shadow.
    # The service-bay strip under the deck lip, matched to its fixture.
    area(
        "MachineUnderdeckLamp",
        (0.0, UNDERDECK_RUN[0], UNDERDECK_RUN[1] - 0.014),
        58.0,
        (2 * DECK_HALF_LENGTH + 0.30, 0.044),
        practical_colour,
        (0.0, 0.14, 0.42),
    )
    # Rim definition.  The frame is a lattice of 45 mm members, and a lattice
    # lit only from the front and above loses its edges against the room.  Two
    # low grazing kickers from behind put a light line back on every column and
    # rail, which is what makes the structure read crisply.
    for side in (-1.0, 1.0):
        area(
            f"MachineRimKicker_{side:+.0f}",
            (side * 3.35, 0.86, 1.05),
            34.0,
            (1.9, 1.7),
            (0.72, 0.855, 1.0),
            (side * 0.30, -0.20, 1.15),
        )
    # The frame is a lattice, and a lattice reads by its edges.  One long, very
    # soft grazing fill down the machine axis keeps every column and rail
    # separated from the bay behind it instead of merging into one dark mass.
    area(
        "MachineAxisFill",
        (-3.40, -1.10, 1.85),
        10.0,
        (2.2, 1.6),
        (0.95, 0.96, 1.0),
        (1.60, 0.10, 1.20),
    )
    return camera


def configure_eevee(scene: bpy.types.Scene) -> None:
    """Turn on the raytraced passes this room needs, and report what stuck.

    A room lit only by its own ceiling fixtures has no contact shadow and no
    ambient occlusion without a raytraced pass, and a scene without those reads
    as objects placed near a floor rather than standing on it.  Every property
    is assigned in its own ``try`` and read back afterwards, because a guard
    that cannot tell "unavailable" from "unintrospectable" turns a loud failure
    into a quiet wrong answer.
    """
    eevee = scene.eevee
    settings: tuple[tuple[str, object], ...] = (
        ("use_raytracing", True),
        ("ray_tracing_method", "SCREEN"),
        ("use_fast_gi", True),
        ("fast_gi_method", "GLOBAL_ILLUMINATION"),
        ("fast_gi_resolution", "2"),
        ("fast_gi_ray_count", 2),
        ("fast_gi_step_count", 8),
        # A short fast-GI ray gathers occlusion close to the surface instead of
        # averaging the whole room into it, which is what puts a dark line back
        # under the worktop, in the knee space and inside the open bay.
        ("fast_gi_distance", 1.15),
        ("use_shadows", True),
        ("shadow_ray_count", 2),
        ("shadow_step_count", 8),
        # Twenty area lights over a 2300-node scene overflow the default shadow
        # pool on the close shots. EEVEE then drops shadow maps and only says so
        # on stderr, so a render can look finished and be wrong. Measured on the
        # previous build: frame 75 reported 2252/2048 at the 512 default and was
        # clean at 2048, and a full pass went from 5568 overflow lines to 0.
        ("shadow_pool_size", "2048"),
        # Indirect light is clamped hard for the same reason: a room whose
        # bounce is uncapped fills its own recesses and loses every true dark.
        ("clamp_surface_indirect", 2.2),
    )
    for name, value in settings:
        try:
            setattr(eevee, name, value)
        except (AttributeError, TypeError, ValueError):
            print(f"EEVEE WARNING: {name}={value!r} rejected by this build", file=sys.stderr)
    options = getattr(eevee, "ray_tracing_options", None)
    if options is not None:
        for name, value in (
            ("resolution_scale", "2"),
            ("use_denoise", True),
            ("screen_trace_quality", 0.4),
        ):
            try:
                setattr(options, name, value)
            except (AttributeError, TypeError, ValueError):
                print(f"EEVEE WARNING: ray_tracing.{name} rejected", file=sys.stderr)
    print(
        "EEVEE APPLIED: "
        + json.dumps(
            {
                name: getattr(eevee, name, None)
                if not isinstance(getattr(eevee, name, None), float)
                else round(float(getattr(eevee, name)), 3)
                for name, _ in settings
            }
        )
    )


def configure_render(options: argparse.Namespace) -> None:
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    width, height = (int(value) for value in options.resolution.lower().split("x", 1))
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.resolution_percentage = 100
    scene.render.engine = "BLENDER_EEVEE" if options.engine == "eevee" else "CYCLES"
    if options.engine == "cycles":
        scene.cycles.samples = options.samples
        scene.cycles.use_denoising = True
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = 0.02
        scene.cycles.preview_samples = min(options.samples, 32)
        scene.cycles.device = "GPU"
        try:
            preferences = bpy.context.preferences.addons["cycles"].preferences
            preferences.compute_device_type = "OPTIX"
            preferences.get_devices()
            for device in preferences.devices:
                device.use = device.type != "CPU"
        except (KeyError, TypeError):
            pass
    if options.engine == "eevee":
        configure_eevee(scene)
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(PREVIEW_PATH)
    # The world is a soft cool grey rather than black.  A scene whose world is
    # black has no ambient at all, so every shadow crushes and the image reads
    # as a dark room instead of as a lit one.
    scene.world.color = (0.058, 0.066, 0.078)
    # Colour management is assigned one property at a time and read back.  A
    # shared try would let a rejected value be swallowed and the render would
    # ship silently mis-graded.
    for name, value in (
        ("view_transform", "AgX"),
        ("look", "AgX - Medium High Contrast"),
        ("exposure", -0.28),
    ):
        try:
            setattr(scene.view_settings, name, value)
        except TypeError:
            print(f"GRADE WARNING: {name}={value!r} rejected by this build", file=sys.stderr)
    print(
        "GRADE APPLIED: "
        + json.dumps(
            {
                "view_transform": scene.view_settings.view_transform,
                "look": scene.view_settings.look,
                "exposure": round(float(scene.view_settings.exposure), 4),
                "engine": scene.render.engine,
            }
        )
    )
    scene.render.use_file_extension = True


def export_glb() -> None:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.context.scene.objects:
        if obj.get("opensdlExport", False) and obj.type not in {"LIGHT", "CAMERA"}:
            obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=str(GLB_PATH),
        export_format="GLB",
        use_selection=True,
        export_apply=False,
        export_extras=True,
        export_animations=True,
        export_frame_range=True,
        export_force_sampling=True,
        export_optimize_animation_size=True,
        export_materials="EXPORT",
        export_texcoords=False,
        export_cameras=False,
        export_lights=False,
        export_yup=True,
    )
    bpy.ops.object.select_all(action="DESELECT")


def validate_motion(
    slots: dict[str, tuple[float, float, float]],
    *,
    mover: bpy.types.Object,
    gripper_head: bpy.types.Object,
    pipette_head: bpy.types.Object,
    sample: bpy.types.Object,
    mixer: bpy.types.Object,
    mixer_latches: Sequence[bpy.types.Object],
    reader_door: bpy.types.Object,
    attached_tips: bpy.types.Object,
    liquid_columns: Sequence[bpy.types.Object],
    input_shuttle: bpy.types.Object,
    output_shuttle: bpy.types.Object,
) -> list[dict[str, object]]:
    scene = bpy.context.scene
    original_frame = scene.frame_current
    checks: list[dict[str, object]] = []
    failures: list[str] = []

    def record(name: str, passed: bool, actual: object, expected: object) -> None:
        checks.append({"name": name, "passed": passed, "actual": actual, "expected": expected})
        if not passed:
            failures.append(f"{name}: expected {expected!r}, got {actual!r}")

    def vector_at(obj: bpy.types.Object, frame: int, *, attribute: str = "location") -> list[float]:
        scene.frame_set(frame)
        value = getattr(obj, attribute)
        return [round(float(component), 6) for component in value]

    def near(actual: Sequence[float], expected: Sequence[float], tolerance: float = 1e-5) -> bool:
        return len(actual) == len(expected) and all(
            abs(a - b) <= tolerance for a, b in zip(actual, expected, strict=True)
        )

    record(
        "deck horizontal pitch",
        abs((slots["tips"][0] - slots["reservoir"][0]) - 0.164) < 1e-9,
        slots["tips"][0] - slots["reservoir"][0],
        0.164,
    )
    record(
        "deck vertical pitch",
        abs((slots["reservoir"][1] - slots["stage"][1]) - 0.107) < 1e-9,
        slots["reservoir"][1] - slots["stage"][1],
        0.107,
    )
    record(
        "attached tip count",
        len([obj for obj in bpy.data.objects if obj.name.startswith("AttachedTip_")]) == 8,
        len([obj for obj in bpy.data.objects if obj.name.startswith("AttachedTip_")]),
        8,
    )
    record(
        "rack tip count",
        len([obj for obj in bpy.data.objects if obj.name.startswith("RackTip_")]) == 96,
        len([obj for obj in bpy.data.objects if obj.name.startswith("RackTip_")]),
        96,
    )
    record("liquid column count", len(liquid_columns) == 12, len(liquid_columns), 12)

    expected_sample_positions = {
        BEAT["plate_approach"]: [
            slots["input-handoff"][0],
            slots["input-handoff"][1],
            HOTEL_PLATE_Z,
        ],
        BEAT["plate_seat"]: [slots["stage"][0], slots["stage"][1], DIRECT_DECK_PLATE_Z],
        BEAT["mix_place_down"]: [slots["mixer"][0], slots["mixer"][1], MIXER_PLATE_Z],
        BEAT["read_place_down"]: [
            slots["reader"][0],
            slots["reader"][1],
            CHARACTERIZER_PLATE_Z,
        ],
        BEAT["out_place_down"]: [
            slots["output-handoff"][0],
            slots["output-handoff"][1],
            HOTEL_PLATE_Z,
        ],
        BEAT["out_stored"]: [
            slots["output-hotel"][0],
            slots["output-hotel"][1] + 0.2075,
            HOTEL_PLATE_Z,
        ],
    }
    for frame, expected in expected_sample_positions.items():
        actual = vector_at(sample, frame)
        record(f"sample checkpoint frame {frame}", near(actual, expected), actual, expected)

    carried_frames = tuple(
        BEAT[name]
        for name in (
            "plate_lift",
            "plate_cross",
            "mix_pick_lift",
            "mix_cross",
            "read_pick_lift",
            "read_cross",
            "out_pick_lift",
            "out_cross",
        )
    )
    for frame in carried_frames:
        scene.frame_set(frame)
        relative_z = round(float(sample.location.z - mover.location.z), 6)
        record(
            f"plate follows the mover frame {frame}",
            abs(relative_z - PLATE_GRIP_LOCAL_Z) <= 1e-5,
            relative_z,
            PLATE_GRIP_LOCAL_Z,
        )
    gripped_frames = tuple(
        BEAT[name]
        for name in (
            "plate_grip",
            "plate_seat",
            "mix_pick_grip",
            "mix_place_down",
            "read_pick_grip",
            "read_place_down",
            "out_pick_grip",
            "out_place_down",
        )
    )
    for frame in gripped_frames:
        scene.frame_set(frame)
        grip_center_z = round(float(sample.location.z - mover.location.z), 6)
        record(
            f"plate aligns with jaw center frame {frame}",
            abs(grip_center_z - PLATE_GRIP_LOCAL_Z) <= 1e-5,
            grip_center_z,
            PLATE_GRIP_LOCAL_Z,
        )

    expected_door_positions = {
        BEAT["start"]: [slots["reader"][0], slots["reader"][1], DOOR_CLOSED_Z],
        BEAT["door_seat"]: [slots[DOOR_DOCK_SLOT][0], slots[DOOR_DOCK_SLOT][1], DOOR_DOCK_Z],
        BEAT["door_close_down"]: [slots["reader"][0], slots["reader"][1], DOOR_CLOSED_Z],
        BEAT["door_return_down"]: [
            slots[DOOR_DOCK_SLOT][0],
            slots[DOOR_DOCK_SLOT][1],
            DOOR_DOCK_Z,
        ],
    }
    for frame, expected in expected_door_positions.items():
        actual = vector_at(reader_door, frame)
        record(f"reader door checkpoint frame {frame}", near(actual, expected), actual, expected)
    door_carried = tuple(
        BEAT[name]
        for name in (
            "door_lift",
            "door_cross",
            "door_fetch_lift",
            "door_close_cross",
            "door_open_lift",
            "door_return_cross",
        )
    )
    for frame in door_carried:
        scene.frame_set(frame)
        grip_alignment = round(float(reader_door.location.z + DOOR_GRIP_Z - mover.location.z), 6)
        record(
            f"door follows the mover frame {frame}",
            abs(grip_alignment - PLATE_GRIP_LOCAL_Z) <= 1e-5,
            grip_alignment,
            PLATE_GRIP_LOCAL_Z,
        )
    door_gripped = tuple(
        BEAT[name]
        for name in (
            "door_grip",
            "door_seat",
            "door_fetch_grip",
            "door_close_down",
            "door_open_grip",
            "door_return_down",
        )
    )
    for frame in door_gripped:
        scene.frame_set(frame)
        grip_alignment = round(float(reader_door.location.z + DOOR_GRIP_Z - mover.location.z), 6)
        record(
            f"door aligns with jaw center frame {frame}",
            abs(grip_alignment - PLATE_GRIP_LOCAL_Z) <= 1e-5,
            grip_alignment,
            PLATE_GRIP_LOCAL_Z,
        )

    input_extended = vector_at(input_shuttle, BEAT["plate_approach"])
    input_stored = vector_at(input_shuttle, BEAT["plate_seat"])
    output_stored = vector_at(output_shuttle, BEAT["out_stored"])
    record(
        "input shuttle extends to the hand-off",
        near(input_extended, [-0.164, 0.0, 0.228]),
        input_extended,
        [-0.164, 0.0, 0.228],
    )
    record(
        "input shuttle retracts after pickup",
        near(input_stored, [0.2075, 0.0, 0.228]),
        input_stored,
        [0.2075, 0.0, 0.228],
    )
    record(
        "output shuttle retracts",
        near(output_stored, [0.2075, 0.0, 0.228]),
        output_stored,
        [0.2075, 0.0, 0.228],
    )

    direct_deck_gap = round(DIRECT_DECK_PLATE_Z - PLATE_HALF_HEIGHT - DECK_SLOT_TOP_Z, 6)
    stacker_gap = round(HOTEL_PLATE_Z - PLATE_HALF_HEIGHT - HOTEL_NEST_TOP_Z, 6)
    reader_height = round(DOOR_CLOSED_Z + DOOR_HEIGHT_M - CHARACTERIZER_ROOT_Z, 6)
    record(
        "direct-deck plate seats without gap", abs(direct_deck_gap) <= 1e-6, direct_deck_gap, 0.0
    )
    record("hotel plate seats without gap", abs(stacker_gap) <= 1e-6, stacker_gap, 0.0)
    record(
        "closed reader stays within published envelope",
        0.057 <= reader_height <= 0.060,
        reader_height,
        "0.057 to 0.060 m",
    )

    for frame, opened in (
        (BEAT["mix_place_clear"], True),
        (BEAT["mix_clamp_closed"], False),
        (BEAT["mix_orbit_end"], False),
        (BEAT["mix_clamp_open"], True),
        (BEAT["read_pick_grip"], True),
    ):
        for index, latch in enumerate(mixer_latches):
            location = vector_at(latch, frame)
            rotation = vector_at(latch, frame, attribute="rotation_euler")
            sign = -1.0 if index == 0 else 1.0
            expected_y = sign * (MIXER_LATCH_OPEN_Y if opened else MIXER_LATCH_CLOSED_Y)
            expected_angle = -sign * MIXER_LATCH_OPEN_ANGLE if opened else 0.0
            record(
                f"mixer latch {index + 1} {'open' if opened else 'closed'} frame {frame}",
                abs(location[1] - expected_y) <= 1e-5 and abs(rotation[0] - expected_angle) <= 1e-5,
                {"y": location[1], "rotationX": rotation[0]},
                {"y": round(expected_y, 6), "rotationX": round(expected_angle, 6)},
            )
    clamp_gap = round(MIXER_LATCH_CLOSED_Y - MIXER_LATCH_THICKNESS / 2.0 - PLATE_DEPTH / 2.0, 6)
    record(
        "closed shaker clamp stops outside the plate",
        0.0 < clamp_gap <= 0.002,
        clamp_gap,
        f"0 to 0.002 m outside the {PLATE_DEPTH} m plate",
    )

    for frame, expected_scale in (
        (BEAT["start"], 0.02),
        (BEAT["tips_a_taken"], 1.0),
        (BEAT["waste_a_drop"], 0.02),
        (BEAT["tips_b_taken"], 1.0),
        (BEAT["waste_b_drop"], 0.02),
    ):
        actual = vector_at(attached_tips, frame, attribute="scale")
        record(
            f"tip state frame {frame}",
            abs(actual[2] - expected_scale) <= 1e-5,
            actual[2],
            expected_scale,
        )
    for frame, expected_scale in (
        (BEAT["fill_a_start"] + 3, 0.03),
        (BEAT["fill_a_start"] + 5, 0.46),
        (BEAT["fill_b_start"] + 3, 0.46),
        (BEAT["fill_b_start"] + 5, 1.0),
    ):
        actual = vector_at(liquid_columns[0], frame, attribute="scale")
        record(
            f"column 1 fill frame {frame}",
            abs(actual[2] - expected_scale) <= 1e-5,
            actual[2],
            expected_scale,
        )

    radii: list[float] = []
    yaw_values: list[float] = []
    for frame in range(BEAT["mix_clamp_closed"] + 2, BEAT["mix_orbit_end"]):
        scene.frame_set(frame)
        radii.append(math.hypot(float(mixer.location.x), float(mixer.location.y)))
        yaw_values.append(abs(float(sample.rotation_euler.z)))
    record(
        "shaker orbit radius",
        max(abs(radius - 0.001) for radius in radii) <= 2e-6,
        max(radii),
        0.001,
    )
    record("plate does not yaw", max(yaw_values) <= 1e-9, max(yaw_values), 0.0)

    # One mover, two heads.  These are the scalar half of that claim: each head
    # is exactly at its own dock pose while the other one is working, and a
    # coupled head is at the mover pose to the last micron because it is written
    # from it.  check_scene proves the geometric half.
    for head, label in ((gripper_head, "Gripper"), (pipette_head, "Pipette")):
        dock_pose = [HEAD_DOCK_X[label], HEAD_DOCK_Y, HEAD_DOCK_Z]
        idle_frames = (
            (BEAT["swap_a_lift"], BEAT["fill_a_start"], BEAT["swap_b_lift"])
            if label == "Gripper"
            else (BEAT["start"], BEAT["read_hold"], FRAME_END)
        )
        for frame in idle_frames:
            actual = vector_at(head, frame)
            record(
                f"{label} head rests in its dock frame {frame}",
                near(actual, dock_pose),
                actual,
                dock_pose,
            )
        coupled_frames = (
            (BEAT["plate_cross"], BEAT["mix_cross"], BEAT["out_cross"])
            if label == "Gripper"
            else (BEAT["res_a_down"], BEAT["fill_b_start"], BEAT["waste_b_up"])
        )
        for frame in coupled_frames:
            scene.frame_set(frame)
            offset = [
                round(float(head.location[axis] - mover.location[axis]), 6) for axis in (0, 2)
            ]
            record(
                f"{label} head tracks the mover frame {frame}",
                near(offset, [0.0, 0.0]),
                offset,
                [0.0, 0.0],
            )
    dock_separation = round(abs(HEAD_DOCK_X["Gripper"] - HEAD_DOCK_X["Pipette"]), 6)
    record(
        "head docks stand clear of each other",
        dock_separation >= 0.30,
        dock_separation,
        ">= 0.30 m apart",
    )

    scene.frame_set(original_frame)
    if failures:
        raise RuntimeError("Digital-twin motion validation failed:\n- " + "\n- ".join(failures))
    return checks


def validate_spatial_invariants(step: int = 2) -> list[dict[str, object]]:
    """Check carry rigidity, grip contact, and interpenetration.

    ``validate_motion`` above proves scalar facts about single objects.  These
    checks live in ``check_scene.py`` because they compare bodies to each other,
    which is the only way to see a payload leaving the gripper or a mover
    entering a fixed assembly.  A failure raises before anything is exported.
    """
    if str(HERE) not in sys.path:
        sys.path.insert(0, str(HERE))
    import check_scene

    return check_scene.validate_spatial(step=step)


def write_validation(checks: Sequence[dict[str, object]]) -> None:
    digest = hashlib.sha256(GLB_PATH.read_bytes()).hexdigest() if GLB_PATH.exists() else None
    report = {
        "sha256": digest,
        "passed": all(check["passed"] for check in checks),
        "frameRange": {"start": 1, "end": FRAME_END, "fps": FPS},
        "checks": list(checks),
    }
    VALIDATION_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def write_inventory() -> None:
    # The nodes ../twin.yaml binds: one per entity, one per anchor.  The
    # vocabulary they carry across the twin boundary is cell, mover, head, dock,
    # station, slot, hotel, carrier, anchor.
    required = (
        "CellRoot",
        "SampleCarrier",
        "Mover",
        "GripperHead",
        "PipetteHead",
        "MixerRotor",
        "CharacterizerHousing",
        "CharacterizerDoor",
        "Anchor_Input",
        "Anchor_Dispense",
        "Anchor_Mix",
        "Anchor_Characterize",
        "Anchor_Output",
    )
    missing = [name for name in required if bpy.data.objects.get(name) is None]
    if missing:
        raise RuntimeError(f"Missing required digital-twin nodes: {', '.join(missing)}")
    digest = hashlib.sha256(GLB_PATH.read_bytes()).hexdigest() if GLB_PATH.exists() else None
    inventory = {
        "scene": GLB_PATH.name,
        "sha256": digest,
        # The export is byte-reproducible for a given Blender version, so the digest above is only
        # a reproducibility claim when paired with the generator that produced it.
        "generator": {"blender": ".".join(str(part) for part in bpy.app.version)},
        "coordinateFrame": {"unit": "m", "handedness": "right", "upAxis": "Z"},
        "frameRange": {"start": 1, "end": FRAME_END, "fps": FPS},
        "requiredNodes": list(required),
        "nodes": sorted(
            obj.name for obj in bpy.context.scene.objects if obj.get("opensdlExport", False)
        ),
        "sourceBasis": {
            "equipmentClass": "Flex-class liquid-handling workstation",
            "manufacturerCadIncluded": False,
            "modelType": "original reference reconstruction",
        },
    }
    INVENTORY_PATH.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")


def write_camera_rig() -> None:
    """Publish the still poses and the edit so every consumer frames it the same."""
    CAMERA_RIG_PATH.write_text(
        json.dumps(
            {
                "unit": "mm",
                "sensorWidth": CAMERA_SENSOR_WIDTH,
                "resolution": [1280, 720],
                "stillPose": "still",
                "poses": CAM_RIG,
                "shots": [
                    {
                        "name": shot["name"],
                        "start": shot["start"],
                        "end": shot["end"],
                        "seconds": round((shot["end"] - shot["start"] + 1) / FPS, 2),
                        "note": shot["note"],
                        "keys": [
                            {"frame": frame, "eye": eye, "look": look, "lens": lens}
                            for frame, eye, look, lens in shot["keys"]
                        ],
                    }
                    for shot in CAMERA_SHOTS
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def render_poses(options: argparse.Namespace) -> None:
    """Render the named poses, honouring each pose's own hide list."""
    scene = bpy.context.scene
    camera = scene.camera
    out_dir = Path(options.poses_dir) if options.poses_dir else RENDER_DIR / "poses"
    out_dir.mkdir(parents=True, exist_ok=True)
    selected = [name.strip() for name in options.poses.split(",") if name.strip()] or list(CAM_RIG)
    original_frame = scene.frame_current
    suspended = suspend_camera_choreography(camera)
    for name in selected:
        pose = CAM_RIG[name]
        hidden: list[bpy.types.Object] = []
        for prefix in pose.get("hide", ()):  # type: ignore[union-attr]
            for obj in scene.objects:
                if obj.name.startswith(prefix) and not obj.hide_render:
                    obj.hide_render = True
                    hidden.append(obj)
        apply_camera_pose(camera, pose)
        scene.frame_set(int(pose.get("frame", options.frame)))  # type: ignore[arg-type]
        scene.render.filepath = str(out_dir / f"pose-{name}.png")
        bpy.ops.render.render(write_still=True)
        for obj in hidden:
            obj.hide_render = False
        print(f"POSE RENDERED: {name} -> {out_dir / f'pose-{name}.png'}")
    resume_camera_choreography(camera, suspended)
    scene.frame_set(original_frame)
    scene.render.filepath = str(PREVIEW_PATH)


def render_outputs(options: argparse.Namespace) -> None:
    scene = bpy.context.scene
    if options.render_poses:
        render_poses(options)
    if options.render_still:
        # The preview is a portrait of the machine rather than a frame of the
        # film, so it is shot from the ``still`` pose with the edit suspended.
        camera = scene.camera
        suspended = suspend_camera_choreography(camera)
        apply_camera_pose(camera, CAM_RIG["still"])
        scene.frame_set(max(1, min(FRAME_END, options.frame)))
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(PREVIEW_PATH)
        bpy.ops.render.render(write_still=True)
        resume_camera_choreography(camera, suspended)
    if options.render_animation:
        scene.frame_set(1)
        FRAME_DIR.mkdir(parents=True, exist_ok=True)
        for old_frame in FRAME_DIR.glob("frame_*.png"):
            old_frame.unlink()
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(FRAME_DIR / "frame_")
        bpy.ops.render.render(animation=True)
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-framerate",
                str(FPS),
                "-i",
                str(FRAME_DIR / "frame_%04d.png"),
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(VIDEO_PATH),
            ],
            check=True,
        )
        for frame_path in FRAME_DIR.glob("frame_*.png"):
            frame_path.unlink()


def build_scene(options: argparse.Namespace) -> None:
    # The edit is checked before any geometry exists.  A shot list that does not
    # tile the timeline, or that cuts faster than the standard allows, is a
    # defect worth refusing in a second rather than at the end of a render.
    validate_camera_shots()
    reset_scene()
    init_materials()
    for name in (
        "Environment",
        "Frame",
        "Cell",
        "Mechanisms",
        "Modules",
        "Labware",
        "Anchors",
        "RenderRig",
    ):
        collection(name)

    build_room()
    cell_root = empty("CellRoot", target=COLLECTIONS["Cell"])
    cell_root["opensdlEntityId"] = "cell"
    build_frame(cell_root)
    slots = build_stations(cell_root)
    (
        bridge,
        mover,
        gripper_head,
        pipette_head,
        attached_tips,
        jaw_left,
        jaw_right,
        drag,
    ) = build_transport(cell_root)

    build_reservoir((slots["reservoir"][0], slots["reservoir"][1], DECK_Z + 0.008), cell_root)
    rack_tip_columns = build_tip_rack(
        (slots["tips"][0], slots["tips"][1], DECK_Z + 0.008), cell_root
    )
    mixer, mixer_latches, _mixer_status = build_mixer(
        (slots["mixer"][0], slots["mixer"][1], DECK_Z + 0.008), cell_root
    )
    _reader, reader_door, reader_status = build_characterizer(
        (slots["reader"][0], slots["reader"][1], CHARACTERIZER_ROOT_Z),
        (slots[DOOR_DOCK_SLOT][0], slots[DOOR_DOCK_SLOT][1], DOOR_DOCK_Z),
        cell_root,
    )
    build_waste((slots["tip-waste"][0], slots["tip-waste"][1], DECK_Z + 0.008), cell_root)
    input_shuttle = build_hotel("Hotel_Input", slots["input-hotel"], cell_root, role="input")
    output_shuttle = build_hotel("Hotel_Output", slots["output-hotel"], cell_root, role="output")
    build_service_deck(cell_root)
    build_controls(cell_root)
    build_compute(cell_root)
    build_fluidics(cell_root)
    build_waste_column(cell_root)
    build_transfer_port(cell_root)
    build_machine_services(cell_root)

    sample, liquid_columns = build_plate(
        "SampleCarrier",
        (slots["input-handoff"][0], slots["input-handoff"][1], HOTEL_PLATE_Z),
        target=COLLECTIONS["Labware"],
        parent=cell_root,
    )

    for anchor_id, slot_id, height in (
        ("input", "input-handoff", HOTEL_PLATE_Z),
        ("dispense", "stage", DIRECT_DECK_PLATE_Z),
        ("mix", "mixer", MIXER_PLATE_Z),
        ("characterize", "reader", CHARACTERIZER_PLATE_Z),
        ("output", "output-handoff", HOTEL_PLATE_Z),
    ):
        anchor(anchor_id, (slots[slot_id][0], slots[slot_id][1], height), cell_root)

    camera = build_camera_and_lighting()
    animate_scene(
        bridge,
        mover,
        gripper_head,
        pipette_head,
        attached_tips,
        jaw_left,
        jaw_right,
        drag,
        sample,
        liquid_columns,
        mixer,
        mixer_latches,
        reader_door,
        reader_status,
        rack_tip_columns,
        input_shuttle,
        output_shuttle,
        slots,
    )
    build_camera_choreography(camera)
    validate_camera_path(camera)
    configure_render(options)
    motion_checks = validate_motion(
        slots,
        mover=mover,
        gripper_head=gripper_head,
        pipette_head=pipette_head,
        sample=sample,
        mixer=mixer,
        mixer_latches=mixer_latches,
        reader_door=reader_door,
        attached_tips=attached_tips,
        liquid_columns=liquid_columns,
        input_shuttle=input_shuttle,
        output_shuttle=output_shuttle,
    )
    motion_checks.extend(validate_spatial_invariants())
    bpy.context.scene.frame_set(max(1, min(FRAME_END, options.frame)))
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    if not options.no_export:
        export_glb()
    write_inventory()
    write_validation(motion_checks)
    write_camera_rig()
    render_outputs(options)


if __name__ == "__main__":
    build_scene(args_from_blender())
