"""Tested helpers injected ahead of every candidate script.

Each function here exists because the generator got the same thing wrong more than once. Prose
guidance did not fix any of them: telling the model that `scene.world` starts as None produced a
script that checked `world.use_nodes` anyway, and giving it a camera-aiming recipe in words produced
`tuple - Vector`. Working code is not misread the way a sentence is.

This is the scene equivalent of a standard library. The model composes bodies out of primitives that
are known to run, so its attention goes to arrangement, proportion and light rather than to
rediscovering that `bmesh.ops.create_cylinder` does not exist.

Injected before the candidate, so every name below is already defined when its first line runs.
"""

PRELUDE = '''
import bmesh
import bpy
import math
import mathutils

def new_scene():
    """An empty scene with a world, which an empty factory reset does not give you."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    return scene

def ambient(strength=0.1, color=(0.05, 0.05, 0.06)):
    """Weak world light so shadows are not pure black. Keep strength between 0.05 and 0.2."""
    world = bpy.context.scene.world
    bg = world.node_tree.nodes.get("Background")
    if bg is not None:
        bg.inputs["Color"].default_value = (*color, 1.0)
        bg.inputs["Strength"].default_value = strength
    return world

def material(name, color, roughness=0.6, metallic=0.0):
    """A Principled material. Materials already have nodes in 5.2; `use_nodes` is deprecated."""
    mat = bpy.data.materials.new(name)
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat

#: Measured, not guessed. A swatch ramp from 0.03 to 0.22 albedo was rendered against floors at
#: 0.55, 0.30 and 0.18, and the finding was that the floor dominates: at 0.55 it bounces so much
#: light that even a 0.03 surface reads mid-grey and no "dark" material can look dark. These values
#: are the ones where a dark bench reads dark, steel reads metallic, and labware still reads light.
PALETTE = {
    "bench":    ((0.090, 0.090, 0.100), 0.80, 0.0),
    "polymer":  ((0.055, 0.055, 0.060), 0.85, 0.0),
    "steel":    ((0.420, 0.430, 0.450), 0.30, 1.0),
    "aluminium":((0.560, 0.570, 0.585), 0.22, 1.0),
    "floor":    ((0.300, 0.300, 0.310), 0.90, 0.0),
    "labware":  ((0.620, 0.620, 0.630), 0.45, 0.0),
    "glass":    ((0.800, 0.850, 0.860), 0.05, 0.0),
}

def palette():
    """Every preset material, ready to use. `p = palette(); box(..., p['steel'])`."""
    return {
        name: material(name, colour, roughness, metallic)
        for name, (colour, roughness, metallic) in PALETTE.items()
    }

def lab_lighting(target=(0.0, 0.0, 1.0), cam=None, key=240.0, fill=60.0, rim=36.0):
    """A three-point rig placed relative to the CAMERA, so the light always models the form.

    Lighting positioned in world space only works if the camera happens to be somewhere flattering.
    A key that lands near the camera-to-subject axis lights everything frontally, kills every
    shading gradient, and the render comes out looking like a diagram of the scene rather than a
    photograph of it. That is a real critique this rig earned, twice.

    So the key goes 50 degrees off the view axis and above; the fill goes to the other side at a
    quarter of the power and slightly cool; a low rim behind picks the subject off the background.
    Pass the camera returned by `camera()` or `frame_all()`. Call this AFTER framing.

    The energies are set for lights standing off at roughly the camera distance. They are higher
    than the earlier fixed-position rig because these sit further out, and light falls off with the
    square of that distance.
    """
    import math

    ambient(0.06)
    centre = mathutils.Vector(target)
    if cam is None:
        cam = bpy.context.scene.camera
    if cam is None:
        offset = mathutils.Vector((-2.4, -2.4, 0.0))
    else:
        offset = cam.location - centre
    reach = max(mathutils.Vector((offset.x, offset.y, 0.0)).length, 1.5)

    def _at(degrees, height, distance):
        angle = math.atan2(offset.y, offset.x) + math.radians(degrees)
        return centre + mathutils.Vector(
            (math.cos(angle) * distance, math.sin(angle) * distance, height)
        )

    k = area_light("Key", _at(50.0, reach * 0.95, reach * 1.05), target, energy=key, size=1.5)
    f = area_light("Fill", _at(-75.0, reach * 0.45, reach * 1.15), target,
                   energy=fill, size=1.1, color=(0.84, 0.89, 1.0))
    r = area_light("Rim", _at(165.0, reach * 0.85, reach * 0.95), target,
                   energy=rim, size=0.8, color=(0.92, 0.94, 1.0))
    return k, f, r

def _mesh_object(name, bm, location, material_):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = mathutils.Vector(location)
    if material_ is not None:
        obj.data.materials.append(material_)
    bpy.context.collection.objects.link(obj)
    return obj

def box(name, size, location, material_=None):
    """A box of the given (x, y, z) size in metres, centred on `location`."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for vert in bm.verts:
        vert.co.x *= size[0]
        vert.co.y *= size[1]
        vert.co.z *= size[2]
    return _mesh_object(name, bm, location, material_)

def cylinder(name, radius, depth, location, material_=None, segments=32):
    """An upright cylinder. `bmesh.ops.create_cylinder` does not exist; this is create_cone."""
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm, cap_ends=True, cap_tris=False, segments=segments,
        radius1=radius, radius2=radius, depth=depth,
    )
    return _mesh_object(name, bm, location, material_)

def top_of(obj):
    """The world-space height of an object's upper face."""
    bpy.context.view_layer.update()
    return max((obj.matrix_world @ mathutils.Vector(c)).z for c in obj.bound_box)

def on_surface(name, size, xy, surface, material_=None, sink=0.002):
    """A body standing on `surface`, sunk 2 mm so the faces do not z-fight.

    `surface` is either a height in metres or **another object**, in which case its upper face is
    measured. Passing the object is what you want when stacking: a shaker is a base, then a platform
    on the base, then a plate on the platform, then clamps on the platform, and every one of those
    heights is a chance to bury a body inside the one below it. That has happened — a platform and a
    microplate both ended up inside the shaker base, which renders as a plain block.

    `xy` is the centre in plan. Nothing here needs `surface_z + height/2` written by hand.
    """
    surface_z = surface if isinstance(surface, (int, float)) else top_of(surface)
    return box(name, size, (xy[0], xy[1], surface_z + size[2] / 2.0 - sink), material_)

def plane(name, size, location=(0.0, 0.0, 0.0), material_=None):
    """A flat square, for floors."""
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size / 2.0)
    return _mesh_object(name, bm, location, material_)

def bench(name, width, depth, top_z=0.90, thickness=0.04, leg=0.05,
          top_material=None, leg_material=None, inset=0.05):
    """A bench whose top SURFACE is at `top_z`, with legs that reach up into it.

    Three recurring errors disappear here. The top is placed by its surface rather than its centre,
    so `top_z + thickness/2` is never written by hand and the bench does not end up 40 mm too tall.
    The legs run from the floor to just under the surface and overlap the top by a third of its
    thickness, so their faces never share a plane with it and cannot z-fight. And the leg inset is
    handled, so feet sit under the top rather than flush with its edge.

    Returns (top, [legs]).
    """
    top = box(name, (width, depth, thickness), (0.0, 0.0, top_z - thickness / 2.0), top_material)
    overlap = thickness / 3.0
    leg_height = top_z - thickness + overlap
    x = width / 2.0 - inset - leg / 2.0
    y = depth / 2.0 - inset - leg / 2.0
    legs = []
    for tag, (lx, ly) in {
        "FL": (-x, -y), "FR": (x, -y), "BL": (-x, y), "BR": (x, y),
    }.items():
        legs.append(
            box(f"{name}_Leg_{tag}", (leg, leg, leg_height), (lx, ly, leg_height / 2.0), leg_material)
        )
    return top, legs

def strut(name, a, b, thickness=0.06, material_=None, overlap=0.0):
    """A square limb spanning from point `a` to point `b`, correctly oriented.

    An articulated arm is the case where hand-written orientation goes wrong every time: the model
    has to pick a rotation for each segment, and a rotation that is wrong by a sign puts the forearm
    through the bench. Given two points there is no rotation to choose.

    `overlap` extends the segment past both ends, which is how you make joints look continuous
    instead of leaving daylight between a limb and its hub.

    Returns the object, so a chain is just a sequence of struts between joint positions.
    """
    start = mathutils.Vector(a)
    end = mathutils.Vector(b)
    span = end - start
    length = span.length
    if length < 1e-6:
        return box(name, (thickness, thickness, thickness), start, material_)
    obj = box(name, (thickness, thickness, length + overlap * 2.0), (0.0, 0.0, 0.0), material_)
    obj.location = (start + end) / 2.0
    obj.rotation_euler = span.to_track_quat("Z", "Y").to_euler()
    bpy.context.view_layer.update()
    return obj

def joint(name, at, radius=0.045, depth=None, material_=None, axis="Z"):
    """A cylindrical hub at a joint position, so limbs meet in something rather than in mid-air."""
    obj = cylinder(name, radius, depth if depth is not None else radius * 2.2, at, material_)
    if axis.upper() == "Y":
        obj.rotation_euler = (math.radians(90.0), 0.0, 0.0)
    elif axis.upper() == "X":
        obj.rotation_euler = (0.0, math.radians(90.0), 0.0)
    bpy.context.view_layer.update()
    return obj

def gripper(name, at, opening, depth=0.09, thickness=0.012, height=0.05,
            material_=None, along="x"):
    """Two parallel fingers `opening` apart, centred on `at`, bracketing whatever sits between them.

    Made as a pair because the failure it prevents is jaws that close on empty air: give it the
    width of the thing being held and the fingers land on its faces.
    """
    centre = mathutils.Vector(at)
    half = opening / 2.0 + thickness / 2.0
    offsets = (
        (mathutils.Vector((-half, 0.0, 0.0)), mathutils.Vector((half, 0.0, 0.0)))
        if along == "x"
        else (mathutils.Vector((0.0, -half, 0.0)), mathutils.Vector((0.0, half, 0.0)))
    )
    size = (thickness, depth, height) if along == "x" else (depth, thickness, height)
    return [
        box(f"{name}_{tag}", size, centre + offset, material_)
        for tag, offset in zip(("L", "R"), offsets)
    ]

def aim(obj, target):
    """Point an object's -Z at `target`. Accepts a tuple or a Vector, which is the whole point."""
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    return obj

def camera(location, target, lens=42.0):
    """A camera at `location` looking at `target`, set as the scene camera."""
    data = bpy.data.cameras.new("Camera")
    data.lens = lens
    obj = bpy.data.objects.new("Camera", data)
    obj.location = mathutils.Vector(location)
    bpy.context.collection.objects.link(obj)
    aim(obj, target)
    bpy.context.scene.camera = obj
    return obj

def frame_all(cam, margin=1.04, distance=None, floor_names=("Floor",)):
    """Pull `cam` back until every body fits the frame, then re-aim at their centre.

    Fits the actual bounding-box corners rather than a bounding sphere. A sphere is simple and
    badly wrong for a bench: a 1.8 m wide, 0.9 m tall object has a 1.08 m bounding radius, and
    fitting that radius to the *vertical* field of view puts the camera five metres away with the
    subject small in a wide empty floor. Projecting the eight corners and solving for the worst one
    is exact, and it is what a person framing a shot actually does.

    Iterative because moving the camera changes the projection. It converges in two or three passes.

    Pass `distance` to stand at a chosen range and solve for the LENS instead of moving. That is how
    a brief specifying "3.2 m from the bench" should be met, and it removes an interaction that is
    easy to get backwards: a longer lens is narrower, so it needs MORE room, not less. One attempt
    reached for a 65 mm lens reasoning that it would let the camera come closer, and ended up at
    5.4 m on a brief asking for 3.2.
    """
    import math

    bpy.context.view_layer.update()
    points = []
    for obj in bpy.data.objects:
        if obj.type != "MESH" or not obj.data.vertices:
            continue
        if obj.name in floor_names or (
            obj.dimensions.z < 0.02 and max(obj.dimensions.x, obj.dimensions.y) > 4.0
        ):
            continue
        points.extend(obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box)
    if not points:
        return cam

    lo = mathutils.Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = mathutils.Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    centre = (lo + hi) / 2.0

    direction = cam.location - centre
    if direction.length < 1e-6:
        direction = mathutils.Vector((-1.0, -1.0, 0.6))
    direction = direction.normalized()

    from bpy_extras.object_utils import world_to_camera_view

    scene = bpy.context.scene

    if distance is not None:
        # Stand at the requested range and choose the lens that fits. Widen until nothing is
        # outside the frame; the sensor is 36 mm, so lens = 18 / tan(half-angle).
        cam.location = centre + direction * float(distance)
        aim(cam, centre)
        for _ in range(8):
            bpy.context.view_layer.update()
            worst = 0.0
            for point in points:
                ndc = world_to_camera_view(scene, cam, point)
                if ndc.z <= 0.0:
                    worst = max(worst, 4.0)
                    continue
                worst = max(worst, abs(ndc.x - 0.5) * 2.0, abs(ndc.y - 0.5) * 2.0)
            if abs(worst * margin - 1.0) < 0.02:
                break
            half = math.atan(18.0 / max(cam.data.lens, 1.0))
            half = math.atan(math.tan(half) * worst * margin)
            cam.data.lens = max(8.0, min(200.0, 18.0 / max(math.tan(half), 1e-6)))
        bpy.context.view_layer.update()
        return cam

    distance = max((cam.location - centre).length, 0.5)
    for _ in range(6):
        cam.location = centre + direction * distance
        aim(cam, centre)
        bpy.context.view_layer.update()
        worst = 0.0
        for point in points:
            ndc = world_to_camera_view(scene, cam, point)
            if ndc.z <= 0.0:
                worst = max(worst, 4.0)
                continue
            worst = max(worst, abs(ndc.x - 0.5) * 2.0, abs(ndc.y - 0.5) * 2.0)
        if worst <= 1e-6:
            break
        scale = worst * margin
        if 0.98 < scale < 1.02:
            break
        distance *= scale
    cam.location = centre + direction * distance
    aim(cam, centre)
    bpy.context.view_layer.update()
    return cam

def area_light(name, location, target, energy=120.0, size=1.2, color=(1.0, 0.98, 0.95)):
    """An area light aimed at `target`. 80-150 W for a key, 20-40 W for a fill, at 2-3 m."""
    data = bpy.data.lights.new(name=name, type="AREA")
    data.energy = energy
    data.size = size
    data.color = color
    obj = bpy.data.objects.new(name, data)
    obj.location = mathutils.Vector(location)
    bpy.context.collection.objects.link(obj)
    aim(obj, target)
    return obj
'''
