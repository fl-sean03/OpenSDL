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

def on_surface(name, size, xy, surface_z, material_=None, sink=0.002):
    """A body standing on a surface at `surface_z`, sunk 2 mm so the faces do not z-fight.

    This is the most common placement in a lab scene and the easiest to get wrong: an instrument
    whose underside sits at exactly the height of the bench top shares a plane with it, and the two
    surfaces flicker against each other. Sinking it slightly is what a real object does anyway,
    since nothing rests on a surface without deforming into it a little.

    `xy` is the centre in plan; the height is computed, so there is no arithmetic to get wrong.
    """
    return box(name, size, (xy[0], xy[1], surface_z + size[2] / 2.0 - sink), material_)

def plane(name, size, location=(0.0, 0.0, 0.0), material_=None):
    """A flat square, for floors."""
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=size / 2.0)
    return _mesh_object(name, bm, location, material_)

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

def frame_all(cam, margin=1.04, floor_names=("Floor",)):
    """Pull `cam` back until every body fits the frame, then re-aim at their centre.

    Fits the actual bounding-box corners rather than a bounding sphere. A sphere is simple and
    badly wrong for a bench: a 1.8 m wide, 0.9 m tall object has a 1.08 m bounding radius, and
    fitting that radius to the *vertical* field of view puts the camera five metres away with the
    subject small in a wide empty floor. Projecting the eight corners and solving for the worst one
    is exact, and it is what a person framing a shot actually does.

    Iterative because moving the camera changes the projection. It converges in two or three passes.
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
