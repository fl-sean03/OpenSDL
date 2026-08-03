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

FPS = 24
FRAME_END = 960
BENCH_Z = 0.92
DECK_Z = 1.135
DECK_X = {1: -0.164, 2: 0.0, 3: 0.164, 4: 0.328}
DECK_Y = {"A": 0.1605, "B": 0.0535, "C": -0.0535, "D": -0.1605}

# Physical seating planes.  The plate root is at the vertical center of its
# 14.3 mm envelope, so every station defines the actual supporting surface
# rather than using one visually convenient Z value for the whole deck.
PLATE_HEIGHT = 0.0143
PLATE_HALF_HEIGHT = PLATE_HEIGHT / 2.0
DECK_SLOT_TOP_Z = DECK_Z + 0.0075
DIRECT_DECK_PLATE_Z = DECK_SLOT_TOP_Z + PLATE_HALF_HEIGHT
STACKER_NEST_TOP_Z = BENCH_Z + 0.228 + 0.011 + 0.0025
STACKER_PLATE_Z = STACKER_NEST_TOP_Z + PLATE_HALF_HEIGHT
MIXER_PLATFORM_TOP_Z = DECK_Z + 0.008 + 0.069 + 0.007
MIXER_PLATE_Z = MIXER_PLATFORM_TOP_Z + PLATE_HALF_HEIGHT

# Published reader dimensions describe an assembled envelope of roughly
# 57-60 mm.  The detector body is 18.5 mm high; the plate and removable lid
# occupy the remainder without stacking two full-height housings.
READER_ROOT_Z = DECK_Z + 0.008
READER_DECK_TOP_Z = READER_ROOT_Z + 0.0205
READER_PLATE_Z = READER_DECK_TOP_Z + PLATE_HALF_HEIGHT
READER_LID_CLOSED_Z = READER_ROOT_Z + 0.0350
READER_LID_DOCK_Z = DECK_SLOT_TOP_Z
READER_LID_HEIGHT = 0.0220
READER_LID_GRIP_Z = 0.0140

MATERIALS: dict[str, bpy.types.Material] = {}
COLLECTIONS: dict[str, bpy.types.Collection] = {}


def args_from_blender() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--render-still", action="store_true")
    parser.add_argument("--render-animation", action="store_true")
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
        (0.012, 0.015, 0.018, 1.0),
        roughness=0.31,
        coat=0.18,
        microtexture=0.10,
    )
    make_material(
        "PowderCoatGraphite",
        (0.038, 0.044, 0.050, 1.0),
        metallic=0.08,
        roughness=0.34,
        microtexture=0.08,
    )
    make_material(
        "AnodizedAluminum",
        (0.53, 0.57, 0.60, 1.0),
        metallic=0.82,
        roughness=0.25,
        microtexture=0.035,
    )
    make_material(
        "BrushedStainless",
        (0.46, 0.50, 0.52, 1.0),
        metallic=0.93,
        roughness=0.20,
        microtexture=0.025,
    )
    make_material(
        "MachinedAluminum",
        (0.66, 0.70, 0.72, 1.0),
        metallic=0.9,
        roughness=0.16,
    )
    make_material("BlackPolymer", (0.018, 0.021, 0.024, 1.0), roughness=0.42)
    make_material("WhitePolymer", (0.76, 0.79, 0.80, 1.0), roughness=0.32)
    make_material("Rubber", (0.006, 0.007, 0.008, 1.0), roughness=0.72)
    make_material(
        "Polycarbonate",
        (0.15, 0.20, 0.23, 0.12),
        roughness=0.08,
        transmission=0.94,
        ior=1.585,
        coat=0.2,
    )
    make_material(
        "ClearLabware",
        (0.56, 0.67, 0.72, 0.24),
        roughness=0.12,
        transmission=0.82,
        ior=1.49,
    )
    make_material("ScreenGlass", (0.004, 0.008, 0.012, 1.0), roughness=0.08, coat=0.35)
    make_material("ScreenBlue", (0.005, 0.26, 0.45, 1.0), roughness=0.28, emission=1.2)
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
    make_material("BenchTop", (0.17, 0.19, 0.20, 1.0), roughness=0.30, microtexture=0.05)
    make_material("Cabinet", (0.31, 0.33, 0.34, 1.0), metallic=0.2, roughness=0.38)
    make_material("Wall", (0.58, 0.60, 0.59, 1.0), roughness=0.68)
    make_material("Floor", (0.20, 0.21, 0.21, 1.0), roughness=0.55)
    make_material("CableBlue", (0.018, 0.10, 0.17, 1.0), roughness=0.46)
    make_material("CableBlack", (0.008, 0.009, 0.010, 1.0), roughness=0.58)


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


def rounded_panel_frame(
    prefix: str,
    center: Sequence[float],
    outer: Sequence[float],
    border: float,
    depth: float,
    material: str,
    *,
    target: bpy.types.Collection,
    parent: bpy.types.Object | None = None,
    plane: str = "XZ",
) -> list[bpy.types.Object]:
    x, y, z = center
    width, height = outer
    parts: list[bpy.types.Object] = []
    if plane == "XZ":
        parts.extend(
            [
                rounded_box(
                    f"{prefix}_Top",
                    (width, depth, border),
                    (x, y, z + (height - border) / 2),
                    material,
                    target=target,
                    parent=parent,
                    bevel=border * 0.26,
                ),
                rounded_box(
                    f"{prefix}_Bottom",
                    (width, depth, border),
                    (x, y, z - (height - border) / 2),
                    material,
                    target=target,
                    parent=parent,
                    bevel=border * 0.26,
                ),
                rounded_box(
                    f"{prefix}_Left",
                    (border, depth, height - 2 * border),
                    (x - (width - border) / 2, y, z),
                    material,
                    target=target,
                    parent=parent,
                    bevel=border * 0.26,
                ),
                rounded_box(
                    f"{prefix}_Right",
                    (border, depth, height - 2 * border),
                    (x + (width - border) / 2, y, z),
                    material,
                    target=target,
                    parent=parent,
                    bevel=border * 0.26,
                ),
            ]
        )
    elif plane == "YZ":
        parts.extend(
            [
                rounded_box(
                    f"{prefix}_Top",
                    (depth, width, border),
                    (x, y, z + (height - border) / 2),
                    material,
                    target=target,
                    parent=parent,
                    bevel=border * 0.26,
                ),
                rounded_box(
                    f"{prefix}_Bottom",
                    (depth, width, border),
                    (x, y, z - (height - border) / 2),
                    material,
                    target=target,
                    parent=parent,
                    bevel=border * 0.26,
                ),
                rounded_box(
                    f"{prefix}_Front",
                    (depth, border, height - 2 * border),
                    (x, y - (width - border) / 2, z),
                    material,
                    target=target,
                    parent=parent,
                    bevel=border * 0.26,
                ),
                rounded_box(
                    f"{prefix}_Rear",
                    (depth, border, height - 2 * border),
                    (x, y + (width - border) / 2, z),
                    material,
                    target=target,
                    parent=parent,
                    bevel=border * 0.26,
                ),
            ]
        )
    return parts


def build_room() -> None:
    target = COLLECTIONS["Environment"]
    rounded_box("Floor", (5.6, 4.2, 0.06), (0.0, 0.55, -0.03), "Floor", target=target, bevel=0.0)
    rounded_box("RearWall", (5.6, 0.08, 2.9), (0.0, 1.72, 1.42), "Wall", target=target, bevel=0.0)
    rounded_box("LeftWall", (0.08, 4.2, 2.9), (-2.76, 0.55, 1.42), "Wall", target=target, bevel=0.0)

    rounded_box(
        "BenchTop",
        (2.25, 0.90, 0.055),
        (0.0, 0.04, BENCH_Z - 0.0275),
        "BenchTop",
        target=target,
        bevel=0.008,
    )
    rounded_box(
        "BenchBacksplash",
        (2.25, 0.035, 0.16),
        (0.0, 0.47, BENCH_Z + 0.055),
        "BrushedStainless",
        target=target,
        bevel=0.004,
    )
    for x in (-0.73, 0.0, 0.73):
        rounded_box(
            f"Cabinet_{x:+.2f}",
            (0.68, 0.73, 0.78),
            (x, 0.06, 0.49),
            "Cabinet",
            target=target,
            bevel=0.008,
        )
        for drawer in range(3):
            z = 0.70 - drawer * 0.19
            rounded_box(
                f"Drawer_{x:+.2f}_{drawer}",
                (0.62, 0.012, 0.15),
                (x, -0.311, z),
                "PowderCoatGraphite",
                target=target,
                bevel=0.006,
            )
            rounded_box(
                f"DrawerPull_{x:+.2f}_{drawer}",
                (0.18, 0.018, 0.012),
                (x, -0.323, z + 0.045),
                "AnodizedAluminum",
                target=target,
                bevel=0.005,
            )

    rounded_box(
        "OverheadRail",
        (2.4, 0.08, 0.08),
        (0.0, 1.62, 2.23),
        "AnodizedAluminum",
        target=target,
        bevel=0.008,
    )
    rounded_box(
        "PowerRaceway",
        (2.1, 0.045, 0.115),
        (0.0, 1.665, 1.04),
        "WhitePolymer",
        target=target,
        bevel=0.004,
    )
    for x in (-0.78, -0.26, 0.26, 0.78):
        rounded_box(
            f"Outlet_{x:+.2f}",
            (0.10, 0.008, 0.065),
            (x, 1.638, 1.04),
            "LabelWhite",
            target=target,
            bevel=0.006,
        )
        for offset in (-0.019, 0.019):
            cylinder(
                f"OutletPort_{x:+.2f}_{offset:+.2f}",
                0.004,
                0.004,
                (x + offset, 1.632, 1.045),
                "BlackPolymer",
                target=target,
                rotation=(math.pi / 2, 0.0, 0.0),
                vertices=16,
                bevel=0.0,
            )


def build_sign() -> None:
    target = COLLECTIONS["Cell"]
    sign = rounded_box(
        "OpenSDLSign",
        (0.62, 0.036, 0.17),
        (0.0, 0.59, 2.04),
        "PowderCoatBlack",
        target=target,
        bevel=0.018,
    )
    rounded_box(
        "SignInset",
        (0.56, 0.008, 0.112),
        (0.0, 0.568, 2.04),
        "ScreenGlass",
        target=target,
        parent=None,
        bevel=0.008,
    )
    text_mesh(
        "SignOpenSDL",
        "OPENSDL",
        (0.0, 0.559, 2.072),
        0.054,
        "LabelWhite",
        target=target,
        rotation=(math.pi / 2, 0.0, 0.0),
    )
    text_mesh(
        "SignSubtitle",
        "SURROGATE CELL 01",
        (0.0, 0.558, 2.017),
        0.021,
        "CyanIndicator",
        target=target,
        rotation=(math.pi / 2, 0.0, 0.0),
    )
    for x in (-0.275, 0.275):
        tube_path(
            f"SignStandoff_{x:+.3f}",
            ((x, 0.61, 1.91), (x, 0.61, 2.02)),
            0.006,
            "AnodizedAluminum",
            target=target,
        )
    sign["opensdlRole"] = "cell-sign"


def build_flex_frame(cell_root: bpy.types.Object) -> None:
    target = COLLECTIONS["Cell"]
    # Full-scale 0.87 x 0.69 x 0.84 m envelope.
    rounded_box(
        "FlexBase",
        (0.87, 0.69, 0.145),
        (0.0, 0.04, 1.0125),
        "PowderCoatBlack",
        target=target,
        parent=cell_root,
        bevel=0.028,
        segments=5,
    )
    rounded_box(
        "FlexDeckTub",
        (0.75, 0.57, 0.042),
        (0.0, 0.045, 1.107),
        "PowderCoatGraphite",
        target=target,
        parent=cell_root,
        bevel=0.012,
    )
    rounded_box(
        "FlexDeck",
        (0.71, 0.545, 0.018),
        (0.0, 0.045, DECK_Z - 0.009),
        "BrushedStainless",
        target=target,
        parent=cell_root,
        bevel=0.005,
    )

    # Structural enclosure: black powder-coated outer frame and bright metal
    # working cavity, matching the construction language of real benchtop
    # liquid handlers without copying vendor-owned CAD.
    for x in (-0.402, 0.402):
        rounded_box(
            f"OuterPillar_{x:+.3f}",
            (0.066, 0.67, 0.69),
            (x, 0.04, 1.435),
            "PowderCoatBlack",
            target=target,
            parent=cell_root,
            bevel=0.022,
            segments=5,
        )
        rounded_box(
            f"InnerPillar_{x:+.3f}",
            (0.041, 0.605, 0.61),
            (x - math.copysign(0.011, x), 0.012, 1.43),
            "PowderCoatBlack",
            target=target,
            parent=cell_root,
            bevel=0.012,
        )
    rounded_box(
        "TopShell",
        (0.87, 0.69, 0.135),
        (0.0, 0.04, 1.7125),
        "PowderCoatBlack",
        target=target,
        parent=cell_root,
        bevel=0.026,
        segments=5,
    )
    rounded_box(
        "RearPanel",
        (0.74, 0.052, 0.57),
        (0.0, 0.358, 1.42),
        "BrushedStainless",
        target=target,
        parent=cell_root,
        bevel=0.012,
    )
    rounded_box(
        "FrontLowerBezel",
        (0.75, 0.046, 0.065),
        (0.0, -0.311, 1.165),
        "PowderCoatBlack",
        target=target,
        parent=cell_root,
        bevel=0.014,
    )

    # Side windows remain fixed.  Two original, side-hinged access doors open
    # out of the work envelope.  Their vertical pivots, framed glazing, and
    # fixed hinge barrels make the opening mechanically legible without
    # reproducing manufacturer-owned door geometry.
    rounded_box(
        "LeftWindow",
        (0.006, 0.535, 0.47),
        (-0.369, 0.055, 1.43),
        "Polycarbonate",
        target=target,
        parent=cell_root,
        bevel=0.010,
    )
    rounded_box(
        "RightWindow",
        (0.006, 0.535, 0.47),
        (0.369, 0.055, 1.43),
        "Polycarbonate",
        target=target,
        parent=cell_root,
        bevel=0.010,
    )
    door_specs = (
        ("Left", -0.354, 1.0, math.radians(-102.0)),
        ("Right", 0.354, -1.0, math.radians(102.0)),
    )
    for side, pivot_x, inward_sign, open_angle in door_specs:
        door = empty(
            f"AccessDoor{side}Pivot",
            target=target,
            location=(pivot_x, -0.292, 1.43),
            parent=cell_root,
        )
        door.rotation_euler = (0.0, 0.0, open_angle)
        panel_center_x = inward_sign * 0.177
        rounded_panel_frame(
            f"AccessDoor{side}Frame",
            (panel_center_x, 0.0, 0.0),
            (0.354, 0.475),
            0.018,
            0.020,
            "PowderCoatGraphite",
            target=target,
            parent=door,
        )
        rounded_box(
            f"AccessDoor{side}Glazing",
            (0.316, 0.006, 0.437),
            (panel_center_x, -0.002, 0.0),
            "Polycarbonate",
            target=target,
            parent=door,
            bevel=0.009,
        )
        handle_x = inward_sign * 0.315
        rounded_box(
            f"AccessDoor{side}Handle",
            (0.022, 0.038, 0.145),
            (handle_x, -0.025, 0.0),
            "AnodizedAluminum",
            target=target,
            parent=door,
            bevel=0.007,
        )
        for hinge_z in (1.285, 1.575):
            cylinder(
                f"AccessDoor{side}Hinge_{hinge_z:.3f}",
                0.010,
                0.060,
                (pivot_x, -0.301, hinge_z),
                "PowderCoatGraphite",
                target=target,
                parent=cell_root,
                vertices=28,
                bevel=0.002,
            )
            for screw_z in (hinge_z - 0.018, hinge_z + 0.018):
                screw(
                    f"AccessDoor{side}HingeScrew_{screw_z:.3f}",
                    (pivot_x - inward_sign * 0.014, -0.316, screw_z),
                    target=target,
                    parent=cell_root,
                    axis="Y",
                    radius=0.0028,
                )

    # Feet and front service caps.
    for x in (-0.35, 0.35):
        for y in (-0.245, 0.315):
            cylinder(
                f"Foot_{x:+.2f}_{y:+.2f}",
                0.017,
                0.022,
                (x, y, 0.929),
                "Rubber",
                target=target,
                parent=cell_root,
                vertices=32,
                bevel=0.003,
            )
    for x in (-0.33, -0.24, 0.24, 0.33):
        rounded_box(
            f"ServiceCap_{x:+.2f}",
            (0.052, 0.018, 0.052),
            (x, -0.323, 1.015),
            "BlackPolymer",
            target=target,
            parent=cell_root,
            bevel=0.009,
        )

    # Status lighting and identity without copying vendor trademarks.
    rounded_box(
        "FrontStatusRail",
        (0.50, 0.012, 0.013),
        (-0.085, -0.318, 1.722),
        "WhiteIndicator",
        target=target,
        parent=cell_root,
        bevel=0.006,
    )
    text_mesh(
        "CellModelLabel",
        "OPENSDL  FLEX-CLASS REFERENCE",
        (-0.16, -0.325, 1.752),
        0.017,
        "LabelWhite",
        target=target,
        parent=cell_root,
        align="CENTER",
    )
    text_mesh(
        "CellSerial",
        "FLX-01 / DIGITAL SURROGATE",
        (0.0, -0.324, 1.122),
        0.010,
        "LabelGray",
        target=target,
        parent=cell_root,
        align="CENTER",
    )

    # Fasteners and realistic panel seams.
    for x in (-0.385, 0.385):
        for z in (1.14, 1.34, 1.55, 1.69):
            screw(
                f"FrameScrew_{x:+.3f}_{z:.2f}",
                (x, -0.327, z),
                target=target,
                parent=cell_root,
                axis="Y",
                radius=0.0034,
            )
    for y in (-0.22, 0.10, 0.30):
        for z in (1.21, 1.62):
            screw(
                f"SideScrewL_{y:+.2f}_{z:.2f}",
                (-0.438, y, z),
                target=target,
                parent=cell_root,
                axis="X",
                radius=0.0034,
            )
            screw(
                f"SideScrewR_{y:+.2f}_{z:.2f}",
                (0.438, y, z),
                target=target,
                parent=cell_root,
                axis="X",
                radius=0.0034,
            )


def build_deck_slots(cell_root: bpy.types.Object) -> dict[str, tuple[float, float, float]]:
    target = COLLECTIONS["Cell"]
    slots: dict[str, tuple[float, float, float]] = {}
    # Published Flex geometry: 164 mm horizontal and 107 mm vertical slot
    # pitch. Columns 1-3 are the working deck; column 4 is a gripper-only
    # staging area used here by the Stackers and reader lid caddy.
    for row, y in DECK_Y.items():
        for col_index, x in DECK_X.items():
            slot_id = f"{row}{col_index}"
            slots[slot_id] = (x, y, DECK_Z + 0.004)
            material = "PowderCoatGraphite" if col_index < 4 else "BlackPolymer"
            rounded_box(
                f"DeckSlot_{slot_id}",
                (0.128, 0.086, 0.006),
                (x, y, DECK_Z + 0.003),
                material,
                target=target,
                parent=cell_root,
                bevel=0.004,
            )
            rounded_box(
                f"DeckSlotInset_{slot_id}",
                (0.118, 0.076, 0.003),
                (x, y, DECK_Z + 0.006),
                "AnodizedAluminum",
                target=target,
                parent=cell_root,
                bevel=0.0025,
            )
            text_mesh(
                f"DeckLabel_{slot_id}",
                slot_id,
                (x - 0.050, y - 0.034, DECK_Z + 0.009),
                0.009,
                "LabelGray",
                target=target,
                parent=cell_root,
                rotation=(0.0, 0.0, 0.0),
                align="LEFT",
                extrude=0.00008,
            )
            for dx, dy in ((-0.055, -0.034), (0.055, -0.034), (-0.055, 0.034), (0.055, 0.034)):
                cylinder(
                    f"SlotPin_{slot_id}_{dx:+.3f}_{dy:+.3f}",
                    0.0020,
                    0.004,
                    (x + dx, y + dy, DECK_Z + 0.009),
                    "MachinedAluminum",
                    target=target,
                    parent=cell_root,
                    vertices=16,
                    bevel=0.0003,
                )
    return slots


def build_gantry(
    cell_root: bpy.types.Object,
) -> tuple[
    bpy.types.Object,
    bpy.types.Object,
    bpy.types.Object,
    bpy.types.Object,
    bpy.types.Object,
    bpy.types.Object,
]:
    target = COLLECTIONS["Mechanisms"]
    # Two precision Y rails and a cable chain at the true machine scale.
    for x in (-0.334, 0.334):
        rounded_box(
            f"YRail_{x:+.3f}",
            (0.028, 0.535, 0.034),
            (x, 0.045, 1.618),
            "MachinedAluminum",
            target=target,
            parent=cell_root,
            bevel=0.004,
        )
        rounded_box(
            f"YRailTrack_{x:+.3f}",
            (0.012, 0.49, 0.012),
            (x, 0.045, 1.607),
            "BrushedStainless",
            target=target,
            parent=cell_root,
            bevel=0.002,
        )
    gantry_y = empty("GantryY", target=target, location=(0.0, DECK_Y["D"], 0.0), parent=cell_root)
    gantry_y["movable"] = True
    rounded_box(
        "GantryCrossbeam",
        (0.665, 0.055, 0.084),
        (0.0, 0.0, 1.565),
        "AnodizedAluminum",
        target=target,
        parent=gantry_y,
        bevel=0.010,
    )
    rounded_box(
        "GantryFrontCover",
        (0.62, 0.012, 0.062),
        (0.0, -0.034, 1.565),
        "PowderCoatGraphite",
        target=target,
        parent=gantry_y,
        bevel=0.007,
    )
    rounded_box(
        "GantryLinearTrack",
        (0.59, 0.018, 0.022),
        (0.0, -0.042, 1.535),
        "BrushedStainless",
        target=target,
        parent=gantry_y,
        bevel=0.003,
    )
    for x in (-0.315, 0.315):
        rounded_box(
            f"GantryEndBlock_{x:+.3f}",
            (0.046, 0.075, 0.10),
            (x, 0.0, 1.565),
            "PowderCoatBlack",
            target=target,
            parent=gantry_y,
            bevel=0.009,
        )
        screw(
            f"GantryEndScrew_{x:+.3f}", (x, -0.039, 1.565), target=target, parent=gantry_y, axis="Y"
        )

    # Visible segmented cable carrier.
    for index in range(18):
        x = -0.285 + index * 0.0335
        rounded_box(
            f"CableCarrier_{index:02d}",
            (0.026, 0.034, 0.012),
            (x, 0.026, 1.618),
            "BlackPolymer",
            target=target,
            parent=gantry_y,
            bevel=0.003,
        )
    tube_path(
        "GantryDataCable",
        ((-0.30, 0.03, 1.62), (-0.05, 0.03, 1.63), (0.29, 0.03, 1.62)),
        0.0032,
        "CableBlue",
        target=target,
        parent=gantry_y,
    )

    dispenser = empty(
        "DispenserHead", target=target, location=(DECK_X[1], 0.0, 0.0), parent=gantry_y
    )
    dispenser["movable"] = True
    rounded_box(
        "PipetteCarriage",
        (0.074, 0.105, 0.205),
        (0.0, -0.006, 1.455),
        "PowderCoatGraphite",
        target=target,
        parent=dispenser,
        bevel=0.011,
    )
    rounded_box(
        "PipetteFrontPanel",
        (0.061, 0.012, 0.169),
        (0.0, -0.064, 1.455),
        "AnodizedAluminum",
        target=target,
        parent=dispenser,
        bevel=0.007,
    )
    rounded_box(
        "PipetteEjector",
        (0.050, 0.092, 0.024),
        (0.0, -0.006, 1.345),
        "BlackPolymer",
        target=target,
        parent=dispenser,
        bevel=0.005,
    )
    rounded_box(
        "PipetteManifold",
        (0.034, 0.084, 0.030),
        (0.0, -0.006, 1.320),
        "MachinedAluminum",
        target=target,
        parent=dispenser,
        bevel=0.005,
    )
    text_mesh(
        "PipetteLabel",
        "8-CHANNEL",
        (0.0, -0.071, 1.47),
        0.009,
        "LabelGray",
        target=target,
        parent=dispenser,
    )

    # Eight real nozzle positions at ANSI/SLAS 9 mm row pitch.  The detachable
    # tips live under their own transform so pickup/drop can be synchronized.
    tip_group = empty(
        "AttachedTipColumn", target=target, location=(0.0, 0.0, 1.286), parent=dispenser
    )
    nozzle_mesh: bpy.types.Mesh | None = None
    tip_mesh: bpy.types.Mesh | None = None
    for row in range(8):
        y = (row - 3.5) * 0.009 - 0.006
        if nozzle_mesh is None:
            nozzle = cylinder(
                "PipetteNozzle_00",
                0.0012,
                0.022,
                (0.0, y, 1.294),
                "BrushedStainless",
                target=target,
                parent=dispenser,
                vertices=16,
                bevel=0.0002,
            )
            nozzle_mesh = nozzle.data
            tip = cylinder(
                "AttachedTip_00",
                0.00155,
                0.046,
                (0.0, y, -0.023),
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
            nozzle.parent = dispenser
            mark_export(nozzle)
            tip = bpy.data.objects.new(f"AttachedTip_{row:02d}", tip_mesh)
            target.objects.link(tip)
            tip.location = (0.0, y, -0.023)
            tip.parent = tip_group
            mark_export(tip)
    tip_group.scale = (1.0, 1.0, 0.02)

    gripper = empty("RobotCarriage", target=target, location=(DECK_X[3], 0.0, 0.0), parent=gantry_y)
    gripper["movable"] = True
    rounded_box(
        "GripperCarriage",
        (0.105, 0.075, 0.205),
        (0.0, -0.012, 1.46),
        "PowderCoatGraphite",
        target=target,
        parent=gripper,
        bevel=0.012,
    )
    rounded_box(
        "GripperFrontPanel",
        (0.086, 0.012, 0.166),
        (0.0, -0.055, 1.46),
        "AnodizedAluminum",
        target=target,
        parent=gripper,
        bevel=0.008,
    )
    rounded_box(
        "GripperWrist",
        (0.075, 0.064, 0.055),
        (0.0, -0.012, 1.335),
        "MachinedAluminum",
        target=target,
        parent=gripper,
        bevel=0.008,
    )
    cylinder(
        "GripperCamera",
        0.009,
        0.007,
        (0.0, -0.049, 1.38),
        "ScreenGlass",
        target=target,
        parent=gripper,
        rotation=(math.pi / 2, 0.0, 0.0),
        vertices=32,
        bevel=0.001,
    )
    text_mesh(
        "GripperLabel",
        "GRIPPER",
        (0.0, -0.063, 1.48),
        0.010,
        "LabelGray",
        target=target,
        parent=gripper,
    )
    jaw_left = rounded_box(
        "GripperJawLeft",
        (0.016, 0.070, 0.085),
        (-0.076, -0.012, 1.267),
        "PowderCoatBlack",
        target=target,
        parent=gripper,
        bevel=0.004,
    )
    jaw_right = rounded_box(
        "GripperJawRight",
        (0.016, 0.070, 0.085),
        (0.076, -0.012, 1.267),
        "PowderCoatBlack",
        target=target,
        parent=gripper,
        bevel=0.004,
    )
    rounded_box(
        "GripperPadLeft",
        (0.006, 0.052, 0.035),
        (0.011, 0.0, -0.022),
        "Rubber",
        target=target,
        parent=jaw_left,
        bevel=0.002,
    )
    rounded_box(
        "GripperPadRight",
        (0.006, 0.052, 0.035),
        (-0.011, 0.0, -0.022),
        "Rubber",
        target=target,
        parent=jaw_right,
        bevel=0.002,
    )
    return gantry_y, dispenser, tip_group, gripper, jaw_left, jaw_right


def build_touchscreen(cell_root: bpy.types.Object) -> None:
    target = COLLECTIONS["Cell"]
    rounded_box(
        "TouchscreenArm",
        (0.025, 0.055, 0.19),
        (0.286, -0.275, 1.485),
        "PowderCoatGraphite",
        target=target,
        parent=cell_root,
        bevel=0.007,
    )
    rounded_box(
        "TouchscreenBody",
        (0.205, 0.035, 0.135),
        (0.244, -0.318, 1.49),
        "PowderCoatBlack",
        target=target,
        parent=cell_root,
        bevel=0.014,
    )
    rounded_box(
        "TouchscreenGlass",
        (0.180, 0.006, 0.110),
        (0.244, -0.339, 1.49),
        "ScreenGlass",
        target=target,
        parent=cell_root,
        bevel=0.008,
    )
    rounded_box(
        "ScreenHeader",
        (0.160, 0.003, 0.018),
        (0.244, -0.343, 1.527),
        "ScreenBlue",
        target=target,
        parent=cell_root,
        bevel=0.004,
    )
    text_mesh(
        "ScreenTitle",
        "SURROGATE CELL 01",
        (0.244, -0.347, 1.526),
        0.010,
        "LabelWhite",
        target=target,
        parent=cell_root,
    )
    for index, (label, mat) in enumerate(
        (
            ("EQUIPMENT READY", "ScreenGreen"),
            ("TWIN CONNECTED", "ScreenBlue"),
            ("RUN  /  IDLE", "LabelGray"),
        )
    ):
        z = 1.497 - index * 0.025
        rounded_box(
            f"ScreenRow_{index}",
            (0.154, 0.002, 0.018),
            (0.244, -0.343, z),
            mat,
            target=target,
            parent=cell_root,
            bevel=0.003,
        )
        text_mesh(
            f"ScreenRowText_{index}",
            label,
            (0.244, -0.347, z),
            0.008,
            "LabelWhite",
            target=target,
            parent=cell_root,
        )
    rounded_box(
        "FrontUSB",
        (0.018, 0.008, 0.010),
        (0.355, -0.332, 1.383),
        "ScreenGlass",
        target=target,
        parent=cell_root,
        bevel=0.002,
    )


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
        (0.12776, 0.08548, 0.0143),
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
    text_mesh(
        f"{name}_Barcode",
        "SDL-PLATE-001",
        (-0.038, -0.043, 0.001),
        0.006,
        "LabelGray",
        target=target,
        parent=root,
        rotation=(math.pi / 2, 0.0, 0.0),
        align="LEFT",
        extrude=0.00005,
    )
    return root, liquid_columns


def build_tip_rack(
    location: Sequence[float], cell_root: bpy.types.Object
) -> list[bpy.types.Object]:
    target = COLLECTIONS["Labware"]
    root = empty("TipRack_A2", target=target, location=location, parent=cell_root)
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
    for row in range(8):
        for col in range(12):
            y = (row - 3.5) * 0.009
            if tip_mesh is None:
                tip = cylinder(
                    "RackTip_00_00",
                    0.00155,
                    0.027,
                    (0.0, y, 0.0135),
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
                tip.location = (0.0, y, 0.0135)
                tip.parent = tip_columns[col]
                mark_export(tip)
    return tip_columns


def build_reservoir(location: Sequence[float], cell_root: bpy.types.Object) -> None:
    target = COLLECTIONS["Labware"]
    root = empty("ReagentReservoir_A1", target=target, location=location, parent=cell_root)
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
        x = (index - 5.5) * 0.009
        rounded_box(
            f"ReservoirChannel_{index + 1:02d}",
            (0.0073, 0.068, 0.014),
            (x, 0.0, 0.022),
            "SampleViolet" if index == 1 else "SampleBlue",
            target=target,
            parent=root,
            bevel=0.0026,
        )
        rounded_box(
            f"ReservoirRim_{index + 1:02d}",
            (0.0084, 0.070, 0.003),
            (x, 0.0, 0.031),
            "WhitePolymer",
            target=target,
            parent=root,
            bevel=0.0015,
        )


def build_heater_shaker(
    location: Sequence[float],
    cell_root: bpy.types.Object,
) -> tuple[bpy.types.Object, tuple[bpy.types.Object, bpy.types.Object], bpy.types.Object]:
    target = COLLECTIONS["Modules"]
    root = empty("HeaterShaker", target=target, location=location, parent=cell_root)
    root["opensdlEntityId"] = "mixer"
    rounded_box(
        "HeaterShakerBody",
        (0.152, 0.090, 0.061),
        (0.0, 0.0, 0.0305),
        "MachinedAluminum",
        target=target,
        parent=root,
        bevel=0.008,
    )
    rounded_box(
        "HeaterShakerRear",
        (0.035, 0.086, 0.065),
        (-0.057, 0.0, 0.033),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.006,
    )
    rounded_box(
        "HeaterShakerPanel",
        (0.004, 0.068, 0.044),
        (0.077, 0.0, 0.035),
        "AnodizedAluminum",
        target=target,
        parent=root,
        bevel=0.003,
    )
    cylinder(
        "HeaterShakerPower",
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
    mixer["opensdlEntityId"] = "mixer"
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
    latches: list[bpy.types.Object] = []
    for x in (-0.058, 0.058):
        side = "Left" if x < 0 else "Right"
        latch = empty(f"MixerLatch{side}", target=target, location=(x, 0.0, 0.014), parent=mixer)
        latch["movable"] = True
        rounded_box(
            f"MixerLatch{side}Bar",
            (0.012, 0.080, 0.018),
            (0.0, 0.0, 0.0),
            "BlackPolymer",
            target=target,
            parent=latch,
            bevel=0.004,
        )
        screw(
            f"MixerLatchScrew_{x:+.3f}",
            (x, -0.032, 0.025),
            target=target,
            parent=mixer,
            axis="Y",
            radius=0.0025,
        )
        latches.append(latch)
    status = rounded_box(
        "HeaterShakerStatus",
        (0.018, 0.004, 0.005),
        (-0.063, -0.047, 0.044),
        "WhiteIndicator",
        target=target,
        parent=root,
        bevel=0.002,
    )
    return mixer, (latches[0], latches[1]), status


def build_plate_reader(
    location: Sequence[float], lid_dock: Sequence[float], cell_root: bpy.types.Object
) -> tuple[bpy.types.Object, bpy.types.Object, bpy.types.Object]:
    target = COLLECTIONS["Modules"]
    reader = empty("ColorimeterHousing", target=target, location=location, parent=cell_root)
    reader["opensdlEntityId"] = "characterizer"
    # The published assembled module is approximately 57-60 mm high.  Its
    # 18.5 mm detector body, labware, and removable lid share that envelope.
    rounded_box(
        "ReaderDetectionBody",
        (0.1553, 0.0955, 0.0185),
        (0.0, 0.0, 0.00925),
        "MachinedAluminum",
        target=target,
        parent=reader,
        bevel=0.006,
    )
    rounded_box(
        "ReaderFrontFascia",
        (0.145, 0.006, 0.014),
        (0.0, -0.0505, 0.010),
        "PowderCoatGraphite",
        target=target,
        parent=reader,
        bevel=0.003,
    )
    rounded_box(
        "ReaderBlackDeck",
        (0.130, 0.082, 0.003),
        (0.0, 0.0, 0.0190),
        "PowderCoatBlack",
        target=target,
        parent=reader,
        bevel=0.003,
    )
    rounded_box(
        "ReaderReadWindow",
        (0.124, 0.076, 0.0012),
        (0.0, 0.0, 0.0208),
        "ReaderIndicator",
        target=target,
        parent=reader,
        bevel=0.002,
    )
    for row in range(8):
        for col in range(12):
            x = (col - 5.5) * 0.009
            y = (row - 3.5) * 0.009
            cylinder(
                f"ReaderDetector_{row:02d}_{col:02d}",
                0.0018,
                0.0010,
                (x, y, 0.0216),
                "ScreenGlass",
                target=target,
                parent=reader,
                vertices=12,
                bevel=0.0002,
            )
    status = rounded_box(
        "ReaderStatus",
        (0.034, 0.006, 0.006),
        (0.050, -0.0515, 0.010),
        "ReaderIndicator",
        target=target,
        parent=reader,
        bevel=0.002,
    )
    text_mesh(
        "ReaderStatusLabel",
        "READ",
        (0.020, -0.054, 0.010),
        0.0045,
        "ReaderIndicator",
        target=target,
        parent=reader,
        extrude=0.00015,
    )

    lid = empty("ColorimeterDoor", target=target, location=lid_dock, parent=cell_root)
    lid["opensdlEntityId"] = "characterizer-door"
    lid["movable"] = True
    rounded_box(
        "ReaderLidLower",
        (0.139, 0.089, 0.010),
        (0.0, 0.0, 0.005),
        "MachinedAluminum",
        target=target,
        parent=lid,
        bevel=0.006,
    )
    rounded_box(
        "ReaderLidTop",
        (0.132, 0.082, 0.011),
        (0.0, 0.0, 0.0155),
        "PowderCoatGraphite",
        target=target,
        parent=lid,
        bevel=0.006,
    )
    for side, x in (("Left", -0.0735), ("Right", 0.0735)):
        rounded_box(
            f"ReaderLidGrip{side}",
            (0.008, 0.032, 0.012),
            (x, 0.0, READER_LID_GRIP_Z),
            "BlackPolymer",
            target=target,
            parent=lid,
            bevel=0.0025,
        )
    text_mesh(
        "ReaderLidLabel",
        "ABSORBANCE",
        (0.0, -0.001, 0.0212),
        0.006,
        "LabelGray",
        target=target,
        parent=lid,
        rotation=(0.0, 0.0, 0.0),
    )
    return reader, lid, status


def build_stacker(
    name: str,
    slot: Sequence[float],
    cell_root: bpy.types.Object,
    *,
    role: str,
) -> bpy.types.Object:
    target = COLLECTIONS["Modules"]
    # Real module envelope: 385.5 mm track length, 106 mm width, 955.5 mm height.
    x, y, _ = slot
    root = empty(name, target=target, location=(x, y, BENCH_Z), parent=cell_root)
    root["opensdlRole"] = role
    rounded_box(
        f"{name}_Track",
        (0.3855, 0.100, 0.030),
        (0.0928, 0.0, 0.205),
        "MachinedAluminum",
        target=target,
        parent=root,
        bevel=0.006,
    )
    rounded_box(
        f"{name}_TrackRailFront",
        (0.368, 0.009, 0.012),
        (0.0928, -0.045, 0.222),
        "BrushedStainless",
        target=target,
        parent=root,
        bevel=0.002,
    )
    rounded_box(
        f"{name}_TrackRailRear",
        (0.368, 0.009, 0.012),
        (0.0928, 0.045, 0.222),
        "BrushedStainless",
        target=target,
        parent=root,
        bevel=0.002,
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

    # The production Stacker is a slim white tower with a tall front loading
    # window, not a generic opaque cabinet.
    tower_x = 0.2075
    rounded_box(
        f"{name}_Tower",
        (0.1945, 0.106, 0.9555),
        (tower_x, 0.0, 0.47775),
        "WhitePolymer",
        target=target,
        parent=root,
        bevel=0.018,
        segments=6,
    )
    rounded_box(
        f"{name}_TowerSpine",
        (0.022, 0.097, 0.850),
        (tower_x - 0.076, 0.0, 0.520),
        "AnodizedAluminum",
        target=target,
        parent=root,
        bevel=0.008,
    )
    rounded_box(
        f"{name}_Window",
        (0.062, 0.008, 0.720),
        (tower_x + 0.020, -0.056, 0.590),
        "ScreenGlass",
        target=target,
        parent=root,
        bevel=0.027,
        segments=8,
    )
    rounded_box(
        f"{name}_WindowReveal",
        (0.074, 0.013, 0.742),
        (tower_x + 0.020, -0.052, 0.590),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.031,
        segments=8,
    )
    # Re-add the glass in front of the dark reveal so the opening reads with
    # real thickness and reflections.
    rounded_box(
        f"{name}_WindowGlass",
        (0.058, 0.006, 0.704),
        (tower_x + 0.020, -0.060, 0.590),
        "Polycarbonate",
        target=target,
        parent=root,
        bevel=0.025,
        segments=8,
    )
    rounded_box(
        f"{name}_DoorLatch",
        (0.078, 0.022, 0.065),
        (tower_x + 0.020, -0.066, 0.505),
        "BlackPolymer",
        target=target,
        parent=root,
        bevel=0.008,
    )
    rounded_box(
        f"{name}_BaseServicePanel",
        (0.142, 0.010, 0.115),
        (tower_x, -0.057, 0.105),
        "PowderCoatGraphite",
        target=target,
        parent=root,
        bevel=0.010,
    )
    rounded_box(
        f"{name}_Status",
        (0.030, 0.006, 0.008),
        (tower_x + 0.050, -0.064, 0.152),
        "CyanIndicator" if role == "input" else "ScreenGreen",
        target=target,
        parent=root,
        bevel=0.003,
    )
    for index in range(8):
        stored = rounded_box(
            f"{name}_StoredPlate_{index}",
            (0.1278, 0.082, 0.011),
            (tower_x, 0.0, 0.31 + index * 0.070),
            "ClearLabware",
            target=target,
            parent=root,
            bevel=0.002,
        )
        apply_material(stored, "SampleViolet" if role == "input" and index % 2 else "ClearLabware")
    text_mesh(
        f"{name}_Label",
        role.upper(),
        (tower_x - 0.050, -0.063, 0.790),
        0.008,
        "LabelGray",
        target=target,
        parent=root,
    )
    cylinder(
        f"{name}_CablePort",
        0.011,
        0.009,
        (tower_x + 0.050, -0.057, 0.050),
        "BlackPolymer",
        target=target,
        parent=root,
        rotation=(math.pi / 2, 0.0, 0.0),
        vertices=24,
        bevel=0.001,
    )
    return shuttle


def build_waste(location: Sequence[float], cell_root: bpy.types.Object) -> None:
    target = COLLECTIONS["Modules"]
    root = empty("WasteChute_D1", target=target, location=location, parent=cell_root)
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
    text_mesh(
        "WasteLabel",
        "WASTE",
        (0.0, -0.041, 0.023),
        0.008,
        "LabelGray",
        target=target,
        parent=root,
        rotation=(0.0, 0.0, 0.0),
    )


def build_cables(cell_root: bpy.types.Object) -> None:
    target = COLLECTIONS["Cell"]
    tube_path(
        "CellPowerCable",
        ((0.37, 0.34, 1.02), (0.55, 0.43, 0.98), (0.76, 0.47, 0.96), (0.86, 0.47, 1.02)),
        0.005,
        "CableBlack",
        target=target,
        parent=cell_root,
    )
    tube_path(
        "CellEthernet",
        ((0.32, 0.35, 1.05), (0.48, 0.46, 1.00), (0.70, 0.47, 1.02), (0.78, 0.47, 1.05)),
        0.003,
        "CableBlue",
        target=target,
        parent=cell_root,
    )
    rounded_box(
        "RearServiceBox",
        (0.18, 0.045, 0.09),
        (0.33, 0.355, 1.02),
        "PowderCoatGraphite",
        target=target,
        parent=cell_root,
        bevel=0.008,
    )
    for index in range(5):
        rounded_box(
            f"RearUSB_{index}",
            (0.018, 0.006, 0.009),
            (0.29 + index * 0.021, 0.331, 1.03),
            "ScreenGlass",
            target=target,
            parent=cell_root,
            bevel=0.001,
        )

    # Dedicated Stacker power/data hub and physically routed module cables.
    rounded_box(
        "StackerHub",
        (0.180, 0.120, 0.310),
        (0.73, 0.315, 1.075),
        "AnodizedAluminum",
        target=target,
        parent=cell_root,
        bevel=0.014,
    )
    rounded_box(
        "StackerHubFront",
        (0.148, 0.008, 0.250),
        (0.73, 0.251, 1.075),
        "PowderCoatGraphite",
        target=target,
        parent=cell_root,
        bevel=0.010,
    )
    text_mesh(
        "StackerHubLabel",
        "POWER / DATA",
        (0.73, 0.245, 1.170),
        0.009,
        "LabelGray",
        target=target,
        parent=cell_root,
    )
    for index in range(4):
        rounded_box(
            f"StackerHubPort_{index + 1}",
            (0.026, 0.006, 0.015),
            (0.685 + index * 0.030, 0.244, 1.095),
            "ScreenGlass",
            target=target,
            parent=cell_root,
            bevel=0.002,
        )
    for index, y in enumerate((DECK_Y["A"], DECK_Y["B"]), start=1):
        tube_path(
            f"StackerCable_{index}",
            (
                (0.585, y - 0.057, 0.970),
                (0.650, y - 0.085, 0.955),
                (0.740, 0.225, 0.970),
                (0.700 + index * 0.030, 0.245, 1.095),
            ),
            0.0045,
            "CableBlack",
            target=target,
            parent=cell_root,
        )


def anchor(name: str, position: Sequence[float], cell_root: bpy.types.Object) -> bpy.types.Object:
    obj = empty(name, target=COLLECTIONS["Anchors"], location=position, parent=cell_root)
    obj["opensdlAnchor"] = True
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
    if not obj.animation_data or not obj.animation_data.action:
        return
    action = obj.animation_data.action
    fcurves = list(getattr(action, "fcurves", ()))
    if not fcurves:
        # Blender 5 stores curves in layered Action channel bags.
        for layer in action.layers:
            for strip in layer.strips:
                for channelbag in strip.channelbags:
                    fcurves.extend(channelbag.fcurves)
    for fcurve in fcurves:
        for point in fcurve.keyframe_points:
            point.interpolation = interpolation
            if interpolation == "BEZIER":
                point.handle_left_type = "AUTO_CLAMPED"
                point.handle_right_type = "AUTO_CLAMPED"


def animate_scene(
    gantry: bpy.types.Object,
    dispenser: bpy.types.Object,
    attached_tips: bpy.types.Object,
    gripper: bpy.types.Object,
    jaw_left: bpy.types.Object,
    jaw_right: bpy.types.Object,
    sample: bpy.types.Object,
    liquid_columns: Sequence[bpy.types.Object],
    mixer: bpy.types.Object,
    mixer_latches: Sequence[bpy.types.Object],
    reader_lid: bpy.types.Object,
    reader_status: bpy.types.Object,
    rack_tip_columns: Sequence[bpy.types.Object],
    input_shuttle: bpy.types.Object,
    output_shuttle: bpy.types.Object,
    slots: dict[str, tuple[float, float, float]],
    camera: bpy.types.Object,
) -> None:
    positions = {
        "input": (slots["A3"][0], slots["A3"][1], STACKER_PLATE_Z),
        "dispenser": (slots["B1"][0], slots["B1"][1], DIRECT_DECK_PLATE_Z),
        "mixer": (slots["C1"][0], slots["C1"][1], MIXER_PLATE_Z),
        "reader": (slots["D3"][0], slots["D3"][1], READER_PLATE_Z),
        "lid_closed": (slots["D3"][0], slots["D3"][1], READER_LID_CLOSED_Z),
        "lid_dock": (slots["D4"][0], slots["D4"][1], READER_LID_DOCK_Z),
        "output": (slots["B3"][0], slots["B3"][1], STACKER_PLATE_Z),
    }
    # The jaw center is authored at local z=1.267 m.  Station-specific tool Z
    # values therefore derive from the actual plate seating planes above.
    safe_plate_z = 1.267
    safe_lid_z = 1.267 - READER_LID_GRIP_Z
    gripper_safe_z = 0.0
    gripper_input_z = positions["input"][2] - 1.267
    gripper_dispenser_z = positions["dispenser"][2] - 1.267
    gripper_mixer_z = positions["mixer"][2] - 1.267
    gripper_reader_z = positions["reader"][2] - 1.267
    gripper_output_z = positions["output"][2] - 1.267
    gripper_lid_closed_z = positions["lid_closed"][2] + READER_LID_GRIP_Z - 1.267
    gripper_lid_dock_z = positions["lid_dock"][2] + READER_LID_GRIP_Z - 1.267
    jaw_open = 0.092
    jaw_plate_closed = 0.0719
    jaw_lid_closed = 0.0855
    stacker_stored_x = 0.2075
    stacker_extended_x = slots["A3"][0] - slots["A4"][0]

    def key_gantry(frame: int, x: float, y: float, z: float = gripper_safe_z) -> None:
        key_location(gantry, frame, (0.0, y, 0.0))
        key_location(gripper, frame, (x, 0.0, z))

    def key_dispenser(frame: int, x: float, y: float, z: float = 0.0) -> None:
        key_location(gantry, frame, (0.0, y, 0.0))
        key_location(dispenser, frame, (x, 0.0, z))

    def key_jaws(frame: int, width: float) -> None:
        key_location(jaw_left, frame, (-width, -0.012, 1.267))
        key_location(jaw_right, frame, (width, -0.012, 1.267))

    def key_plate(frame: int, position: Sequence[float]) -> None:
        key_location(sample, frame, position)

    def key_latches(frame: int, *, opened: bool) -> None:
        for latch, sign in zip(mixer_latches, (-1.0, 1.0), strict=True):
            x = sign * (0.068 if opened else 0.058)
            angle = -sign * math.radians(35.0) if opened else 0.0
            key_location(latch, frame, (x, 0.0, 0.014))
            key_rotation(latch, frame, (0.0, angle, 0.0))

    # The real reader begins empty and closed. Initialize it, then move the
    # illumination lid from D3 to its dedicated D4 dock.
    key_gantry(1, positions["reader"][0], positions["reader"][1])
    key_jaws(1, jaw_open)
    key_location(reader_lid, 1, positions["lid_closed"])
    reader_emission = (
        reader_status.data.materials[0]
        .node_tree.nodes["Principled BSDF"]
        .inputs["Emission Strength"]
    )
    for frame, value in (
        (1, 1.0),
        (8, 7.0),
        (18, 1.0),
        (752, 1.0),
        (758, 11.0),
        (770, 4.0),
        (782, 11.0),
        (792, 1.0),
        (960, 1.0),
    ):
        reader_emission.default_value = value
        reader_emission.keyframe_insert(data_path="default_value", frame=frame)
    key_gantry(22, positions["reader"][0], positions["reader"][1])
    key_gantry(30, positions["reader"][0], positions["reader"][1], gripper_lid_closed_z)
    key_jaws(30, jaw_open)
    key_jaws(36, jaw_lid_closed)
    key_gantry(36, positions["reader"][0], positions["reader"][1], gripper_lid_closed_z)
    key_location(reader_lid, 36, positions["lid_closed"])
    key_gantry(46, positions["reader"][0], positions["reader"][1])
    key_location(
        reader_lid, 46, (positions["lid_closed"][0], positions["lid_closed"][1], safe_lid_z)
    )
    key_gantry(58, positions["lid_dock"][0], positions["lid_dock"][1])
    key_location(reader_lid, 58, (positions["lid_dock"][0], positions["lid_dock"][1], safe_lid_z))
    key_gantry(68, positions["lid_dock"][0], positions["lid_dock"][1], gripper_lid_dock_z)
    key_location(reader_lid, 68, positions["lid_dock"])
    key_jaws(68, jaw_lid_closed)
    key_jaws(74, jaw_open)
    key_gantry(74, positions["lid_dock"][0], positions["lid_dock"][1], gripper_lid_dock_z)
    key_gantry(82, positions["lid_dock"][0], positions["lid_dock"][1])

    # Retrieve the input plate: the Stacker shuttle extends into A3 before the
    # gripper approaches. The plate and shuttle share the same physical path.
    stored_input = (slots["A4"][0] + stacker_stored_x, slots["A4"][1], positions["input"][2])
    key_location(input_shuttle, 1, (stacker_stored_x, 0.0, 0.228))
    key_location(input_shuttle, 70, (stacker_stored_x, 0.0, 0.228))
    key_location(input_shuttle, 92, (stacker_extended_x, 0.0, 0.228))
    key_plate(1, stored_input)
    key_plate(70, stored_input)
    key_plate(92, positions["input"])

    # Input A3 -> pipetting stage B1.
    key_gantry(100, positions["input"][0], positions["input"][1])
    key_gantry(108, positions["input"][0], positions["input"][1], gripper_input_z)
    key_jaws(108, jaw_open)
    key_jaws(114, jaw_plate_closed)
    key_gantry(114, positions["input"][0], positions["input"][1], gripper_input_z)
    key_plate(114, positions["input"])
    key_gantry(124, positions["input"][0], positions["input"][1])
    key_plate(124, (positions["input"][0], positions["input"][1], safe_plate_z))
    # Once the plate has cleared the shuttle, retract the empty presentation
    # tray into the input tower instead of leaving it across slot A3.
    key_location(input_shuttle, 124, (stacker_extended_x, 0.0, 0.228))
    key_location(input_shuttle, 144, (stacker_stored_x, 0.0, 0.228))
    key_gantry(138, positions["dispenser"][0], positions["dispenser"][1])
    key_plate(138, (positions["dispenser"][0], positions["dispenser"][1], safe_plate_z))
    key_gantry(148, positions["dispenser"][0], positions["dispenser"][1], gripper_dispenser_z)
    key_plate(148, positions["dispenser"])
    key_jaws(148, jaw_plate_closed)
    key_jaws(154, jaw_open)
    key_gantry(154, positions["dispenser"][0], positions["dispenser"][1], gripper_dispenser_z)
    key_gantry(160, positions["dispenser"][0], positions["dispenser"][1])

    # Real 8-channel liquid handling. Each pass picks one rack column, aspirates
    # from one reservoir lane, and dispenses A-H column-by-column across all
    # twelve plate columns. The liquid fill transforms are keyed to each touch.
    plate_offsets = [(column - 5.5) * 0.009 for column in range(12)]
    tip_pick_x = slots["A2"][0] + plate_offsets[0]
    key_scale(attached_tips, 1, (1.0, 1.0, 0.02))
    key_scale(rack_tip_columns[0], 1, (1.0, 1.0, 1.0))
    key_dispenser(164, tip_pick_x, slots["A2"][1])
    key_dispenser(172, tip_pick_x, slots["A2"][1], -0.095)
    key_scale(rack_tip_columns[0], 175, (1.0, 1.0, 1.0))
    key_scale(rack_tip_columns[0], 178, (1.0, 1.0, 0.02))
    key_scale(attached_tips, 175, (1.0, 1.0, 0.02))
    key_scale(attached_tips, 178, (1.0, 1.0, 1.0))
    key_dispenser(178, tip_pick_x, slots["A2"][1], -0.095)
    key_dispenser(184, tip_pick_x, slots["A2"][1])
    reservoir_a_x = slots["A1"][0] + plate_offsets[0]
    key_dispenser(192, reservoir_a_x, slots["A1"][1])
    key_dispenser(200, reservoir_a_x, slots["A1"][1], -0.083)
    key_dispenser(203, reservoir_a_x, slots["A1"][1], -0.083)
    key_dispenser(206, reservoir_a_x, slots["A1"][1])
    for column, offset in enumerate(plate_offsets):
        frame = 214 + column * 8
        x = positions["dispenser"][0] + offset
        key_dispenser(frame, x, positions["dispenser"][1])
        key_dispenser(frame + 3, x, positions["dispenser"][1], -0.083)
        key_scale(liquid_columns[column], frame + 3, (1.0, 1.0, 0.03))
        key_scale(liquid_columns[column], frame + 5, (1.0, 1.0, 0.46))
        key_dispenser(frame + 5, x, positions["dispenser"][1], -0.083)
        key_dispenser(frame + 7, x, positions["dispenser"][1])

    waste_x, waste_y, _ = slots["D1"]
    key_dispenser(318, waste_x, waste_y)
    key_dispenser(326, waste_x, waste_y, -0.082)
    key_scale(attached_tips, 326, (1.0, 1.0, 1.0))
    key_scale(attached_tips, 329, (1.0, 1.0, 0.02))
    key_dispenser(329, waste_x, waste_y, -0.082)
    key_dispenser(334, waste_x, waste_y)

    second_tip_x = slots["A2"][0] + plate_offsets[1]
    key_scale(rack_tip_columns[1], 1, (1.0, 1.0, 1.0))
    key_dispenser(342, second_tip_x, slots["A2"][1])
    key_dispenser(350, second_tip_x, slots["A2"][1], -0.095)
    key_scale(rack_tip_columns[1], 351, (1.0, 1.0, 1.0))
    key_scale(rack_tip_columns[1], 354, (1.0, 1.0, 0.02))
    key_scale(attached_tips, 351, (1.0, 1.0, 0.02))
    key_scale(attached_tips, 354, (1.0, 1.0, 1.0))
    key_dispenser(354, second_tip_x, slots["A2"][1], -0.095)
    key_dispenser(358, second_tip_x, slots["A2"][1])
    reservoir_b_x = slots["A1"][0] + plate_offsets[1]
    key_dispenser(366, reservoir_b_x, slots["A1"][1])
    key_dispenser(374, reservoir_b_x, slots["A1"][1], -0.083)
    key_dispenser(377, reservoir_b_x, slots["A1"][1], -0.083)
    key_dispenser(380, reservoir_b_x, slots["A1"][1])
    for column, offset in enumerate(plate_offsets):
        frame = 388 + column * 8
        x = positions["dispenser"][0] + offset
        key_dispenser(frame, x, positions["dispenser"][1])
        key_dispenser(frame + 3, x, positions["dispenser"][1], -0.083)
        key_scale(liquid_columns[column], frame + 3, (1.0, 1.0, 0.46))
        key_scale(liquid_columns[column], frame + 5, (1.0, 1.0, 1.0))
        key_dispenser(frame + 5, x, positions["dispenser"][1], -0.083)
        key_dispenser(frame + 7, x, positions["dispenser"][1])
    key_dispenser(492, waste_x, waste_y)
    key_dispenser(500, waste_x, waste_y, -0.082)
    key_scale(attached_tips, 500, (1.0, 1.0, 1.0))
    key_scale(attached_tips, 503, (1.0, 1.0, 0.02))
    key_dispenser(503, waste_x, waste_y, -0.082)
    key_dispenser(508, waste_x, waste_y)

    # The Heater-Shaker clamp remains open for placement, closes before the
    # orbital cycle, and opens again before the gripper retrieves the plate.
    key_latches(1, opened=True)
    key_latches(552, opened=True)

    # Pipetting stage B1 -> Heater-Shaker C1.
    key_gantry(516, positions["dispenser"][0], positions["dispenser"][1])
    key_gantry(524, positions["dispenser"][0], positions["dispenser"][1], gripper_dispenser_z)
    key_jaws(524, jaw_open)
    key_jaws(530, jaw_plate_closed)
    key_gantry(530, positions["dispenser"][0], positions["dispenser"][1], gripper_dispenser_z)
    key_plate(530, positions["dispenser"])
    key_gantry(540, positions["dispenser"][0], positions["dispenser"][1])
    key_plate(540, (positions["dispenser"][0], positions["dispenser"][1], safe_plate_z))
    key_gantry(552, positions["mixer"][0], positions["mixer"][1])
    key_plate(552, (positions["mixer"][0], positions["mixer"][1], safe_plate_z))
    key_gantry(560, positions["mixer"][0], positions["mixer"][1], gripper_mixer_z)
    key_plate(560, positions["mixer"])
    key_jaws(560, jaw_plate_closed)
    key_jaws(566, jaw_open)
    key_gantry(566, positions["mixer"][0], positions["mixer"][1], gripper_mixer_z)
    key_gantry(574, positions["mixer"][0], positions["mixer"][1])
    key_plate(574, positions["mixer"])
    key_latches(574, opened=True)
    key_latches(580, opened=False)

    # Heater-Shaker GEN1 uses a 2.0 mm-diameter clockwise orbital translation.
    # At 800 rpm, sampled directly at the 24 fps video rate, the plate never
    # yaws or spins. The demonstration compresses the real 20 second hold.
    orbit_radius = 0.001
    for frame in range(580, 629):
        revolutions = (frame - 580) / FPS * (800.0 / 60.0)
        radians = -2.0 * math.pi * revolutions
        dx = orbit_radius * math.cos(radians)
        dy = orbit_radius * math.sin(radians)
        key_location(mixer, frame, (dx, dy, 0.069))
        key_plate(
            frame, (positions["mixer"][0] + dx, positions["mixer"][1] + dy, positions["mixer"][2])
        )
    key_location(mixer, 630, (0.0, 0.0, 0.069))
    key_plate(630, positions["mixer"])
    key_latches(630, opened=False)
    key_latches(634, opened=True)

    # Heater-Shaker C1 -> open reader detection bed D3.
    key_gantry(634, positions["mixer"][0], positions["mixer"][1], gripper_mixer_z)
    key_jaws(634, jaw_open)
    key_jaws(640, jaw_plate_closed)
    key_gantry(640, positions["mixer"][0], positions["mixer"][1], gripper_mixer_z)
    key_plate(640, positions["mixer"])
    key_latches(640, opened=True)
    key_gantry(648, positions["mixer"][0], positions["mixer"][1])
    key_plate(648, (positions["mixer"][0], positions["mixer"][1], safe_plate_z))
    key_gantry(662, positions["reader"][0], positions["reader"][1])
    key_plate(662, (positions["reader"][0], positions["reader"][1], safe_plate_z))
    key_gantry(670, positions["reader"][0], positions["reader"][1], gripper_reader_z)
    key_plate(670, positions["reader"])
    key_jaws(670, jaw_plate_closed)
    key_jaws(676, jaw_open)
    key_gantry(676, positions["reader"][0], positions["reader"][1], gripper_reader_z)
    key_gantry(684, positions["reader"][0], positions["reader"][1])

    # Close the reader with the physical illumination lid from D4, read all 96
    # wells, then return the lid to the reserved dock.
    key_gantry(692, positions["lid_dock"][0], positions["lid_dock"][1])
    key_gantry(700, positions["lid_dock"][0], positions["lid_dock"][1], gripper_lid_dock_z)
    key_jaws(700, jaw_open)
    key_jaws(706, jaw_lid_closed)
    key_gantry(706, positions["lid_dock"][0], positions["lid_dock"][1], gripper_lid_dock_z)
    key_location(reader_lid, 706, positions["lid_dock"])
    key_gantry(716, positions["lid_dock"][0], positions["lid_dock"][1])
    key_location(reader_lid, 716, (positions["lid_dock"][0], positions["lid_dock"][1], safe_lid_z))
    key_gantry(728, positions["reader"][0], positions["reader"][1])
    key_location(reader_lid, 728, (positions["reader"][0], positions["reader"][1], safe_lid_z))
    key_gantry(736, positions["reader"][0], positions["reader"][1], gripper_lid_closed_z)
    key_location(reader_lid, 736, positions["lid_closed"])
    key_jaws(736, jaw_lid_closed)
    key_jaws(742, jaw_open)
    key_gantry(742, positions["reader"][0], positions["reader"][1], gripper_lid_closed_z)
    key_gantry(750, positions["reader"][0], positions["reader"][1])
    key_gantry(796, positions["reader"][0], positions["reader"][1], gripper_lid_closed_z)
    key_jaws(796, jaw_open)
    key_jaws(802, jaw_lid_closed)
    key_gantry(802, positions["reader"][0], positions["reader"][1], gripper_lid_closed_z)
    key_location(reader_lid, 802, positions["lid_closed"])
    key_gantry(810, positions["reader"][0], positions["reader"][1])
    key_location(reader_lid, 810, (positions["reader"][0], positions["reader"][1], safe_lid_z))
    key_gantry(822, positions["lid_dock"][0], positions["lid_dock"][1])
    key_location(reader_lid, 822, (positions["lid_dock"][0], positions["lid_dock"][1], safe_lid_z))
    key_gantry(834, positions["lid_dock"][0], positions["lid_dock"][1], gripper_lid_dock_z)
    key_location(reader_lid, 834, positions["lid_dock"])
    key_jaws(834, jaw_lid_closed)
    key_jaws(840, jaw_open)
    key_gantry(840, positions["lid_dock"][0], positions["lid_dock"][1], gripper_lid_dock_z)
    key_gantry(848, positions["lid_dock"][0], positions["lid_dock"][1])

    # Reader D3 -> output presentation B3, followed by the Stacker store cycle.
    key_location(output_shuttle, 1, (stacker_extended_x, 0.0, 0.228))
    key_location(output_shuttle, 918, (stacker_extended_x, 0.0, 0.228))
    key_gantry(854, positions["reader"][0], positions["reader"][1])
    key_gantry(862, positions["reader"][0], positions["reader"][1], gripper_reader_z)
    key_jaws(862, jaw_open)
    key_jaws(868, jaw_plate_closed)
    key_gantry(868, positions["reader"][0], positions["reader"][1], gripper_reader_z)
    key_plate(868, positions["reader"])
    key_gantry(876, positions["reader"][0], positions["reader"][1])
    key_plate(876, (positions["reader"][0], positions["reader"][1], safe_plate_z))
    key_gantry(888, positions["output"][0], positions["output"][1])
    key_plate(888, (positions["output"][0], positions["output"][1], safe_plate_z))
    key_gantry(896, positions["output"][0], positions["output"][1], gripper_output_z)
    key_plate(896, positions["output"])
    key_jaws(896, jaw_plate_closed)
    key_jaws(902, jaw_open)
    key_gantry(902, positions["output"][0], positions["output"][1], gripper_output_z)
    key_gantry(910, positions["output"][0], positions["output"][1])
    stored_output = (slots["B4"][0] + stacker_stored_x, slots["B4"][1], positions["output"][2])
    key_location(output_shuttle, 948, (stacker_stored_x, 0.0, 0.228))
    key_plate(918, positions["output"])
    key_plate(948, stored_output)
    key_gantry(960, 0.0, DECK_Y["C"])
    key_latches(960, opened=True)

    # Begin at the established front-right overview, then cross above the
    # centerline to a front-left reveal for the reader lid and output Stacker.
    # The move stays continuous and restrained rather than cutting between
    # disconnected promotional angles.
    camera_target = Vector((0.08, 0.01, 1.46))
    camera_start = Vector((1.90, -3.05, 1.82))
    camera_mid = Vector((0.20, -3.20, 2.00))
    camera_end = Vector((-2.40, -3.00, 2.25))
    key_location(camera, 1, camera_start)
    key_rotation(camera, 1, (camera_target - camera_start).to_track_quat("-Z", "Y").to_euler())
    key_location(camera, 640, camera_mid)
    key_rotation(camera, 640, (camera_target - camera_mid).to_track_quat("-Z", "Y").to_euler())
    key_location(camera, 960, camera_end)
    key_rotation(camera, 960, (camera_target - camera_end).to_track_quat("-Z", "Y").to_euler())

    for obj, action_name in (
        (gantry, "cell_cycle"),
        (dispenser, "cell_cycle"),
        (attached_tips, "liquid_handling_cycle"),
        (gripper, "cell_cycle"),
        (jaw_left, "cell_cycle"),
        (jaw_right, "cell_cycle"),
        (sample, "cell_cycle"),
        (mixer, "mix_cycle"),
        (mixer_latches[0], "mixer_clamp_cycle"),
        (mixer_latches[1], "mixer_clamp_cycle"),
        (reader_lid, "characterize_cycle"),
        (input_shuttle, "input_stacker_cycle"),
        (output_shuttle, "output_stacker_cycle"),
        (camera, "camera_cycle"),
    ):
        set_action_name(obj, action_name)
        set_interpolation(obj)
    for obj in (*liquid_columns, *rack_tip_columns[:2]):
        set_action_name(obj, "liquid_handling_cycle")
        set_interpolation(obj)


def look_at(obj: bpy.types.Object, point: Sequence[float]) -> None:
    direction = Vector(point) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def build_camera_and_lighting() -> bpy.types.Object:
    target = COLLECTIONS["RenderRig"]
    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    target.objects.link(camera)
    camera.location = (1.90, -3.05, 1.82)
    camera_data.lens = 48
    camera_data.sensor_width = 36
    camera_data.dof.use_dof = True
    camera_data.dof.aperture_fstop = 10.0
    camera_data.dof.focus_distance = 3.42
    look_at(camera, (0.08, 0.01, 1.50))
    bpy.context.scene.camera = camera
    mark_export(camera, False)

    def area(
        name: str,
        location: Sequence[float],
        energy: float,
        size: float,
        color: Sequence[float],
        target_point: Sequence[float],
    ) -> None:
        data = bpy.data.lights.new(name, "AREA")
        data.energy = energy
        data.shape = "RECTANGLE"
        data.size = size
        data.size_y = size * 0.55
        data.color = color
        obj = bpy.data.objects.new(name, data)
        target.objects.link(obj)
        obj.location = location
        look_at(obj, target_point)
        mark_export(obj, False)

    area("CeilingKey", (-0.65, -0.55, 2.55), 155.0, 1.5, (1.0, 0.96, 0.90), (0.0, 0.0, 1.2))
    area("CeilingFill", (1.2, -0.15, 2.25), 90.0, 1.15, (0.88, 0.94, 1.0), (0.05, 0.0, 1.3))
    area("RearSoftbox", (-0.75, 1.35, 1.85), 105.0, 1.0, (0.88, 0.94, 1.0), (0.0, 0.05, 1.35))
    area("FrontFill", (0.1, -1.25, 1.25), 48.0, 0.85, (1.0, 0.98, 0.95), (0.0, 0.0, 1.25))
    area("BenchBounce", (0.0, 0.15, 0.42), 24.0, 0.75, (0.86, 0.92, 1.0), (0.0, 0.0, 1.2))
    area("WorkcellLight", (0.0, 0.12, 1.64), 32.0, 0.52, (0.88, 0.95, 1.0), (0.0, 0.02, 1.16))
    return camera


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
    scene.render.image_settings.file_format = "PNG"
    scene.render.filepath = str(PREVIEW_PATH)
    scene.world.color = (0.025, 0.028, 0.030)
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.35
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
    gripper: bpy.types.Object,
    sample: bpy.types.Object,
    mixer: bpy.types.Object,
    mixer_latches: Sequence[bpy.types.Object],
    reader_lid: bpy.types.Object,
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
        abs((slots["A2"][0] - slots["A1"][0]) - 0.164) < 1e-9,
        slots["A2"][0] - slots["A1"][0],
        0.164,
    )
    record(
        "deck vertical pitch",
        abs((slots["A1"][1] - slots["B1"][1]) - 0.107) < 1e-9,
        slots["A1"][1] - slots["B1"][1],
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
        92: [slots["A3"][0], slots["A3"][1], STACKER_PLATE_Z],
        148: [slots["B1"][0], slots["B1"][1], DIRECT_DECK_PLATE_Z],
        560: [slots["C1"][0], slots["C1"][1], MIXER_PLATE_Z],
        670: [slots["D3"][0], slots["D3"][1], READER_PLATE_Z],
        896: [slots["B3"][0], slots["B3"][1], STACKER_PLATE_Z],
        948: [slots["B4"][0] + 0.2075, slots["B4"][1], STACKER_PLATE_Z],
    }
    for frame, expected in expected_sample_positions.items():
        actual = vector_at(sample, frame)
        record(f"sample checkpoint frame {frame}", near(actual, expected), actual, expected)

    for frame in (124, 138, 540, 552, 648, 662, 876, 888):
        scene.frame_set(frame)
        relative_z = round(float(sample.location.z - gripper.location.z), 6)
        record(
            f"plate follows gripper frame {frame}",
            abs(relative_z - 1.267) <= 1e-5,
            relative_z,
            1.267,
        )
    for frame in (114, 148, 530, 560, 640, 670, 868, 896):
        scene.frame_set(frame)
        grip_center_z = round(float(sample.location.z - gripper.location.z), 6)
        record(
            f"plate aligns with jaw center frame {frame}",
            abs(grip_center_z - 1.267) <= 1e-5,
            grip_center_z,
            1.267,
        )

    expected_lid_positions = {
        1: [slots["D3"][0], slots["D3"][1], READER_LID_CLOSED_Z],
        68: [slots["D4"][0], slots["D4"][1], READER_LID_DOCK_Z],
        736: [slots["D3"][0], slots["D3"][1], READER_LID_CLOSED_Z],
        834: [slots["D4"][0], slots["D4"][1], READER_LID_DOCK_Z],
    }
    for frame, expected in expected_lid_positions.items():
        actual = vector_at(reader_lid, frame)
        record(f"reader lid checkpoint frame {frame}", near(actual, expected), actual, expected)
    for frame in (46, 58, 716, 728, 810, 822):
        scene.frame_set(frame)
        grip_alignment = round(
            float(reader_lid.location.z + READER_LID_GRIP_Z - gripper.location.z), 6
        )
        record(
            f"lid follows gripper frame {frame}",
            abs(grip_alignment - 1.267) <= 1e-5,
            grip_alignment,
            1.267,
        )
    for frame in (36, 68, 706, 736, 802, 834):
        scene.frame_set(frame)
        grip_alignment = round(
            float(reader_lid.location.z + READER_LID_GRIP_Z - gripper.location.z), 6
        )
        record(
            f"lid aligns with jaw center frame {frame}",
            abs(grip_alignment - 1.267) <= 1e-5,
            grip_alignment,
            1.267,
        )

    input_extended = vector_at(input_shuttle, 92)
    input_stored = vector_at(input_shuttle, 144)
    output_stored = vector_at(output_shuttle, 948)
    record(
        "input shuttle extends to A3",
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
    stacker_gap = round(STACKER_PLATE_Z - PLATE_HALF_HEIGHT - STACKER_NEST_TOP_Z, 6)
    reader_height = round(READER_LID_CLOSED_Z + READER_LID_HEIGHT - READER_ROOT_Z, 6)
    record(
        "direct-deck plate seats without gap", abs(direct_deck_gap) <= 1e-6, direct_deck_gap, 0.0
    )
    record("Stacker plate seats without gap", abs(stacker_gap) <= 1e-6, stacker_gap, 0.0)
    record(
        "closed reader stays within published envelope",
        0.057 <= reader_height <= 0.060,
        reader_height,
        "0.057 to 0.060 m",
    )

    latch_angle = math.radians(35.0)
    for frame, opened in ((574, True), (580, False), (628, False), (634, True), (640, True)):
        for index, latch in enumerate(mixer_latches):
            location = vector_at(latch, frame)
            rotation = vector_at(latch, frame, attribute="rotation_euler")
            expected_x = (-1.0 if index == 0 else 1.0) * (0.068 if opened else 0.058)
            expected_angle = (1.0 if index == 0 else -1.0) * latch_angle if opened else 0.0
            record(
                f"mixer latch {index + 1} {'open' if opened else 'closed'} frame {frame}",
                abs(location[0] - expected_x) <= 1e-5 and abs(rotation[1] - expected_angle) <= 1e-5,
                {"x": location[0], "rotationY": rotation[1]},
                {"x": round(expected_x, 6), "rotationY": round(expected_angle, 6)},
            )

    for frame, expected_scale in ((1, 0.02), (178, 1.0), (329, 0.02), (354, 1.0), (503, 0.02)):
        actual = vector_at(attached_tips, frame, attribute="scale")
        record(
            f"tip state frame {frame}",
            abs(actual[2] - expected_scale) <= 1e-5,
            actual[2],
            expected_scale,
        )
    for frame, expected_scale in ((217, 0.03), (219, 0.46), (391, 0.46), (393, 1.0)):
        actual = vector_at(liquid_columns[0], frame, attribute="scale")
        record(
            f"column 1 fill frame {frame}",
            abs(actual[2] - expected_scale) <= 1e-5,
            actual[2],
            expected_scale,
        )

    radii: list[float] = []
    yaw_values: list[float] = []
    for frame in range(580, 629):
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

    scene.frame_set(original_frame)
    if failures:
        raise RuntimeError("Digital-twin motion validation failed:\n- " + "\n- ".join(failures))
    return checks


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
    required = (
        "CellRoot",
        "SampleCarrier",
        "RobotCarriage",
        "DispenserHead",
        "MixerRotor",
        "ColorimeterHousing",
        "ColorimeterDoor",
        "Anchor_Input",
        "Anchor_Dispenser",
        "Anchor_Mixer",
        "Anchor_Colorimeter",
        "Anchor_Output",
    )
    missing = [name for name in required if bpy.data.objects.get(name) is None]
    if missing:
        raise RuntimeError(f"Missing required digital-twin nodes: {', '.join(missing)}")
    digest = hashlib.sha256(GLB_PATH.read_bytes()).hexdigest() if GLB_PATH.exists() else None
    inventory = {
        "scene": GLB_PATH.name,
        "sha256": digest,
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


def render_outputs(options: argparse.Namespace) -> None:
    scene = bpy.context.scene
    if options.render_still:
        scene.frame_set(max(1, min(FRAME_END, options.frame)))
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(PREVIEW_PATH)
        bpy.ops.render.render(write_still=True)
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
    reset_scene()
    init_materials()
    for name in ("Environment", "Cell", "Mechanisms", "Modules", "Labware", "Anchors", "RenderRig"):
        collection(name)

    build_room()
    cell_root = empty("CellRoot", target=COLLECTIONS["Cell"])
    cell_root["opensdlEntityId"] = "cell"
    build_sign()
    build_flex_frame(cell_root)
    slots = build_deck_slots(cell_root)
    build_touchscreen(cell_root)
    gantry, dispenser, attached_tips, gripper, jaw_left, jaw_right = build_gantry(cell_root)

    build_reservoir((slots["A1"][0], slots["A1"][1], DECK_Z + 0.008), cell_root)
    rack_tip_columns = build_tip_rack((slots["A2"][0], slots["A2"][1], DECK_Z + 0.008), cell_root)
    mixer, mixer_latches, _mixer_status = build_heater_shaker(
        (slots["C1"][0], slots["C1"][1], DECK_Z + 0.008), cell_root
    )
    _reader, reader_lid, reader_status = build_plate_reader(
        (slots["D3"][0], slots["D3"][1], READER_ROOT_Z),
        (slots["D4"][0], slots["D4"][1], READER_LID_DOCK_Z),
        cell_root,
    )
    build_waste((slots["D1"][0], slots["D1"][1], DECK_Z + 0.008), cell_root)
    input_shuttle = build_stacker("InputStacker", slots["A4"], cell_root, role="input")
    output_shuttle = build_stacker("OutputStacker", slots["B4"], cell_root, role="output")
    build_cables(cell_root)

    sample, liquid_columns = build_plate(
        "SampleCarrier",
        (slots["A3"][0], slots["A3"][1], STACKER_PLATE_Z),
        target=COLLECTIONS["Labware"],
        parent=cell_root,
    )

    anchor("Anchor_Input", (slots["A3"][0], slots["A3"][1], STACKER_PLATE_Z), cell_root)
    anchor("Anchor_Dispenser", (slots["B1"][0], slots["B1"][1], DIRECT_DECK_PLATE_Z), cell_root)
    anchor("Anchor_Mixer", (slots["C1"][0], slots["C1"][1], MIXER_PLATE_Z), cell_root)
    anchor("Anchor_Colorimeter", (slots["D3"][0], slots["D3"][1], READER_PLATE_Z), cell_root)
    anchor("Anchor_Output", (slots["B3"][0], slots["B3"][1], STACKER_PLATE_Z), cell_root)

    camera = build_camera_and_lighting()
    animate_scene(
        gantry,
        dispenser,
        attached_tips,
        gripper,
        jaw_left,
        jaw_right,
        sample,
        liquid_columns,
        mixer,
        mixer_latches,
        reader_lid,
        reader_status,
        rack_tip_columns,
        input_shuttle,
        output_shuttle,
        slots,
        camera,
    )
    configure_render(options)
    motion_checks = validate_motion(
        slots,
        gripper=gripper,
        sample=sample,
        mixer=mixer,
        mixer_latches=mixer_latches,
        reader_lid=reader_lid,
        attached_tips=attached_tips,
        liquid_columns=liquid_columns,
        input_shuttle=input_shuttle,
        output_shuttle=output_shuttle,
    )
    bpy.context.scene.frame_set(max(1, min(FRAME_END, options.frame)))
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))
    if not options.no_export:
        export_glb()
    write_inventory()
    write_validation(motion_checks)
    render_outputs(options)


if __name__ == "__main__":
    build_scene(args_from_blender())
