"""Run with Blender's bpy module: python tests/blender_integration.py."""
import sys
from pathlib import Path

print('Starting Blender module', flush=True)
import bpy
print('Blender module loaded', flush=True)
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vehicle_auto_rig as addon
addon.register()


def box(name, center, size, parent=None):
    x, y, z = (v * .5 for v in size)
    verts = [(a*x, b*y, c*z) for a in (-1, 1) for b in (-1, 1)
             for c in (-1, 1)]
    faces = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4),
             (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    ob = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(ob)
    ob.location = center
    if parent:
        ob.parent = parent
        ob.matrix_parent_inverse = parent.matrix_world.inverted()
    return ob


def world_vertex(ob):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    evaluated = ob.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh()
    try:
        return evaluated.matrix_world @ mesh.vertices[0].co
    finally:
        evaluated.to_mesh_clear()


def assert_move(ob, move_rig, expected):
    before = world_vertex(ob)
    move_rig()
    bpy.context.view_layer.update()
    after = world_vertex(ob)
    actual = after - before
    assert (actual - Vector(expected)).length < 1e-4, (
        ob.name, tuple(actual), expected)


def setup(parented=False):
    print(f'Building synthetic vehicle, parented={parented}', flush=True)
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    holder = bpy.data.objects.new('Vehicle Import Root', None) if parented else None
    if holder:
        bpy.context.collection.objects.link(holder)
        holder.location = (4, -2, .2)
    body = box('Chassis', (0, 0, 1), (1.8, 3.2, .7), holder)
    wheels = []
    for side in (-1, 1):
        for fore in (-1, 1):
            wheels.append(box(f'Wheel_{side}_{fore}', (side * .9, fore * 1.1, .42),
                              (.22, .82, .82), holder))
    bpy.ops.object.select_all(action='DESELECT')
    for item in ([holder] if holder else [body, *wheels]):
        item.select_set(True)
    bpy.context.view_layer.objects.active = holder or body
    s = bpy.context.scene.vehicle_auto_rig
    s.vehicle_type, s.forward_axis, s.forward_sign = 'CAR', 'Y', 'PLUS'
    objects, parts = addon.analyze(bpy.context)
    assert objects == 5 and parts >= 5
    print('Analysis complete', flush=True)
    rig, wheel_count, bound_count = addon.create_rig(bpy.context)
    print('Rig construction complete', flush=True)
    assert wheel_count == 4 and bound_count == 5
    return holder, body, wheels, rig


# Fresh unparented model: all meshes must follow the rig exactly once.
holder, body, wheels, rig = setup(False)
print('Checking separate meshes', flush=True)
assert all(ob.parent == rig for ob in [body, *wheels])
assert_move(body, lambda: setattr(rig.location, 'x', rig.location.x + 2), (2, 0, 0))
assert_move(wheels[0], lambda: setattr(rig.location, 'y', rig.location.y - 1), (0, -1, 0))
# A deforming Root bone must still move weighted mesh vertices in Pose Mode.
assert_move(body, lambda: setattr(rig.pose.bones['Root'].location, 'x', .5), (.5, 0, 0))

# Preserve an imported Empty hierarchy while attaching its root to the rig.
holder, body, wheels, rig = setup(True)
print('Checking imported hierarchy', flush=True)
assert holder.parent == rig and body.parent == holder
assert all(w.parent == holder for w in wheels)
assert_move(body, lambda: setattr(rig.location, 'y', 1), (0, 1, 0))

# Simulate old v0.1.0 binding with a modifier but without object parenting.
for ob in [body, *wheels]:
    transform = ob.matrix_world.copy()
    ob.parent = None
    ob.matrix_world = transform
transform = holder.matrix_world.copy()
holder.parent = None
holder.matrix_world = transform
roots, count = addon.repair_rig_parenting(rig)
print('Checking v0.1.0 repair', flush=True)
assert roots == 1 and count == 5
assert holder.parent == rig and body.parent == holder
assert_move(wheels[0], lambda: setattr(rig.location, 'x', 1), (1, 0, 0))
print('PASS: object-mode rig motion, pose deformation, hierarchy, v0.1.0 repair', flush=True)
