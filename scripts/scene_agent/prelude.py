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

#: Names a caller might reasonably use for a parameter, mapped to the one the helper declares.
#: A model that writes `center=` where the signature says `xy` is not wrong about what it means,
#: and a TypeError for a synonym costs a whole attempt. It has cost three.
_ALIASES = {
    "center": "xy", "centre": "xy", "position": "xy", "at": "xy", "location": "xy",
    "color": "colour", "mat": "material_", "material": "material_",
    "surface_z": "surface", "on": "surface", "height": "surface",
    "size_xyz": "size", "dimensions": "size", "dims": "size",
    "target_location": "target", "look_at": "target",
}

def _by_type(value, signature, taken):
    """Where a value of this kind belongs, when its name gave nothing away."""
    import inspect

    free = [n for n in signature.parameters if n not in taken]
    if isinstance(value, bpy.types.Material):
        for name in free:
            if "material" in name:
                return name
        return None
    if isinstance(value, (bpy.types.Object, list, tuple, set)):
        for name in free:
            if "surface" in name or "on" == name:
                return name
        for name in free:
            if signature.parameters[name].default is inspect.Parameter.empty:
                return name
        return None
    if isinstance(value, (int, float)):
        for name in free:
            default = signature.parameters[name].default
            if isinstance(default, (int, float)) and not isinstance(default, bool):
                return name
        for name in free:
            if "surface" in name:
                return name
    return None

def _tolerant(func):
    """Accept the obvious synonyms for a parameter name rather than failing on one."""
    import difflib
    import functools
    import inspect

    names = set(inspect.signature(func).parameters)

    signature = inspect.signature(func)
    material_params = [
        n for n, param in signature.parameters.items()
        if n.startswith("material") or n.endswith("material") or n.endswith("material_")
    ]

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        for given in list(kwargs):
            if given in names:
                # A valid name is not the same as a valid value. `cylinder(..., segments=mat)`
                # names a real parameter and hands it a Material, which dies inside bmesh with an
                # error naming the wrong thing entirely. If the value cannot be what the parameter
                # takes, it belongs somewhere else.
                default = signature.parameters[given].default
                mismatched = isinstance(kwargs[given], bpy.types.Material) and isinstance(
                    default, (int, float)
                )
                if not mismatched:
                    continue
                moved = _by_type(kwargs[given], signature, kwargs)
                if moved and moved != given:
                    kwargs[moved] = kwargs.pop(given)
                continue
            wanted = _ALIASES.get(given)
            if wanted not in names:
                # A fixed alias table does not keep up. The model has now invented `center`,
                # `center_xy`, `surface_z` and `look_at` for parameters called `xy`, `surface` and
                # `target`, and it will invent more. Match on containment first, since a compound
                # name almost always contains the real one, then fall back to nearest spelling.
                free = [n for n in names if n not in kwargs]
                token = given.strip("_").lower()
                hits = [
                    n for n in free
                    if n.strip("_").lower() in token or token in n.strip("_").lower()
                ]
                if hits:
                    wanted = min(hits, key=len)
                else:
                    close = difflib.get_close_matches(token, free, n=1, cutoff=0.72)
                    wanted = close[0] if close else None
            if wanted is None:
                # Name matching has a limit: `rests_on` does not resemble `surface` in any way a
                # string comparison can see. What the value IS still says where it belongs.
                wanted = _by_type(kwargs[given], signature, kwargs)
            if wanted and wanted in names and wanted not in kwargs:
                kwargs[wanted] = kwargs.pop(given)

        # A material handed to a numeric parameter is a positional slip, not a type error worth
        # dying on: `bench(name, w, d, top_material, leg_material)` skips `top_z` and `thickness`
        # and lands a Material where a float belongs. Move it to the first free material slot and
        # let the numeric parameter keep its default.
        if material_params:
            bound = list(args)
            positional = [
                n for n in signature.parameters
                if signature.parameters[n].kind
                in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
            ]
            spare = [n for n in material_params if n not in kwargs]
            keep = []
            for index, value in enumerate(bound):
                slot = positional[index] if index < len(positional) else None
                if (
                    isinstance(value, bpy.types.Material)
                    and slot is not None
                    and slot not in material_params
                    and spare
                ):
                    kwargs[spare.pop(0)] = value
                    continue
                keep.append(value)
            bound = keep
            return func(*bound, **kwargs)
        return func(*args, **kwargs)

    return wrapper

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
    "steel":    ((0.420, 0.430, 0.450), 0.18, 1.0),
    "aluminium":((0.560, 0.570, 0.585), 0.14, 1.0),
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

def lab_lighting(target=(0.0, 0.0, 1.0), cam=None, key=300.0, fill=75.0, rim=45.0,
                 side="left"):
    """A three-point rig placed relative to the CAMERA, so the light always models the form.

    Lighting positioned in world space only works if the camera happens to be somewhere flattering.
    A key that lands near the camera-to-subject axis lights everything frontally, kills every
    shading gradient, and the render comes out looking like a diagram of the scene rather than a
    photograph of it. That is a real critique this rig earned, twice.

    `side` decides which way the key sits as seen from the camera, so a brief asking for a
    front-left key gets one. The rig has been marked down for lighting from the right when the
    brief said left, which is a real note about a real photograph and not a technicality.

    So the key goes 50 degrees off the view axis and above; the fill goes to the other side at a
    quarter of the power and slightly cool; a low rim behind picks the subject off the background.
    Pass the camera returned by `camera()` or `frame_all()`. Call this AFTER framing.

    The sources are large on purpose. A metal with nothing to reflect looks like paint: the legs
    were repeatedly marked down as "painted plastic, not steel" until the lights were big enough to
    give them a specular gradient to pick up. Big soft sources are what product photography uses on
    metal, for exactly this reason, and the energies rise with the area.

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

    hand = 1.0 if str(side).lower().startswith("l") else -1.0
    k = area_light("Key", _at(50.0 * hand, reach * 0.95, reach * 1.05), target,
                   energy=key, size=3.5)
    f = area_light("Fill", _at(-75.0 * hand, reach * 0.45, reach * 1.15), target,
                   energy=fill, size=2.8, color=(0.84, 0.89, 1.0))
    r = area_light("Rim", _at(165.0 * hand, reach * 0.85, reach * 0.95), target,
                   energy=rim, size=2.0, color=(0.92, 0.94, 1.0))
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

def top_of(thing):
    """The world-space height of the upper face of an object, or of a group of them.

    Accepts an object, a list or tuple of objects, or a number passed straight through. `bench()`
    and `studio()` both return tuples, so the natural thing to write is
    `on_surface(..., surface=my_bench)` — and rejecting that costs an attempt for no reason. A
    group returns its highest top, which is what "on top of the bench" means.
    """
    if isinstance(thing, (int, float)):
        return float(thing)
    bpy.context.view_layer.update()
    if isinstance(thing, (list, tuple, set)):
        tops = [top_of(item) for item in thing if item is not None]
        if not tops:
            raise ValueError("top_of was given an empty group")
        return max(tops)
    return max((thing.matrix_world @ mathutils.Vector(c)).z for c in thing.bound_box)

def on_surface(name, size, xy, surface, material_=None, sink=0.002):
    """A body standing on `surface`, sunk 2 mm so the faces do not z-fight.

    `surface` is either a height in metres or **another object**, in which case its upper face is
    measured. Passing the object is what you want when stacking: a shaker is a base, then a platform
    on the base, then a plate on the platform, then clamps on the platform, and every one of those
    heights is a chance to bury a body inside the one below it. That has happened — a platform and a
    microplate both ended up inside the shaker base, which renders as a plain block.

    `xy` is the centre in plan. Nothing here needs `surface_z + height/2` written by hand.
    """
    surface_z = top_of(surface)
    return box(name, size, (xy[0], xy[1], surface_z + size[2] / 2.0 - sink), material_)

def face_detail(name, parent, size, where="front", offset=(0.0, 0.0),
                material_=None, proud=0.004):
    """A slot, panel or vent on one FACE of a body, standing slightly proud of it.

    Three things have to be right at once and the model has got each of them wrong: the feature has
    to be on a face the camera can see, it has to break the surface rather than sit inside the
    solid, and it must not end flush with the parent or the two will z-fight. All three follow from
    the parent's own bounding box, so none of them needs deciding.

    `where` is "front", "back", "left", "right" or "top" in scene terms, where front is -Y, which
    is the side a three-quarter view looks at. `offset` shifts the feature across that face.

    Pass `where="camera"` to put it on whichever face the scene camera is actually looking at.
    """
    bpy.context.view_layer.update()
    pts = [parent.matrix_world @ mathutils.Vector(c) for c in parent.bound_box]
    lo = mathutils.Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = mathutils.Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    mid = (lo + hi) / 2.0

    face = str(where).lower()
    if face == "camera":
        cam = bpy.context.scene.camera
        if cam is None:
            face = "front"
        else:
            view = cam.matrix_world.translation - mid
            face = ("right" if view.x > 0 else "left") if abs(view.x) > abs(view.y) else (
                "back" if view.y > 0 else "front"
            )

    depth = size[1] if face in ("front", "back") else size[0] if face in ("left", "right") else size[2]
    place = {
        "front": (mid.x + offset[0], lo.y - depth / 2.0 + proud, mid.z + offset[1]),
        "back": (mid.x + offset[0], hi.y + depth / 2.0 - proud, mid.z + offset[1]),
        "left": (lo.x - depth / 2.0 + proud, mid.y + offset[0], mid.z + offset[1]),
        "right": (hi.x + depth / 2.0 - proud, mid.y + offset[0], mid.z + offset[1]),
        "top": (mid.x + offset[0], mid.y + offset[1], hi.z + depth / 2.0 - proud),
    }[face]
    return box(name, size, place, material_)

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

def studio(size=60.0, material_=None, sweep=True):
    """A ground plane large enough that its edge never enters frame, with an optional sweep.

    A 10 m floor looks generous until the camera tilts up and catches its far edge, which reads as
    a hard diagonal seam across the background. A product photograph solves this with a cyclorama:
    floor and wall meeting in a curve so there is no horizon at all. The cheap version is a very
    large floor plus a wall far enough back to fall outside the frame, sharing one material so no
    join is visible.
    """
    ground = plane("Floor", size, (0.0, 0.0, 0.0), material_)
    if sweep:
        wall = box("Backdrop", (size, 0.05, size * 0.4), (0.0, size * 0.25, size * 0.2), material_)
        return ground, wall
    return ground, None

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

def frame_all(cam, margin=1.04, distance=None, floor_names=("Floor", "Backdrop")):
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
        # Scenery is not subject. A floor or a backdrop is there to be behind things, and
        # including it in the fit sends the camera far enough away to see all sixty metres of it.
        if obj.name in floor_names or max(obj.dimensions) > 5.0:
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

def three_quarter(target=(0.0, 0.0, 1.0), side="left", distance=3.2, height=1.6, lens=42.0):
    """A three-quarter view from the named side, set as the scene camera.

    The scene faces -Y, so front-left is negative in both X and Y. The model has placed the camera
    front-right on a brief asking for front-left more than once, which is not a hard sum but is an
    easy one to invert, and the answer is visible in every pixel of the result.

    Follow with `frame_all(cam, distance=...)` to fit what you built.
    """
    centre = mathutils.Vector(target)
    hand = -1.0 if str(side).lower().startswith("l") else 1.0
    reach = distance / (2.0 ** 0.5)
    return camera(
        (centre.x + hand * reach, centre.y - reach, height), target, lens=lens
    )

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
for _name in (
    "material", "box", "cylinder", "plane", "on_surface", "bench", "strut", "joint",
    "gripper", "camera", "area_light", "lab_lighting", "frame_all", "studio",
):
    globals()[_name] = _tolerant(globals()[_name])
'''
