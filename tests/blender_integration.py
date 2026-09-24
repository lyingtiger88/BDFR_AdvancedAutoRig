"""Run with Blender's bpy module: python tests/blender_integration.py."""
import sys
import os
import traceback
from pathlib import Path


def fail_fast(kind, error, stack):
    traceback.print_exception(kind, error, stack)
    os._exit(1)  # bpy may hang during interpreter shutdown after an exception.


sys.excepthook = fail_fast

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


def setup(parented=False, mode='SIMPLE', bone_count=16, with_door=False,
          with_hinges=False):
    print(f'Building synthetic vehicle, parented={parented}, mode={mode}', flush=True)
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
    door = box('Door_L', (-.92, .1, 1), (.1, .8, .7), holder) if (with_door or with_hinges) else None
    hood = box('Hood', (0, 1.1, 1.2), (1.5, .8, .12), holder) if with_hinges else None
    trunk = box('Trunk', (0, -1.2, 1.1), (1.5, .6, .12), holder) if with_hinges else None
    bpy.ops.object.select_all(action='DESELECT')
    for item in ([holder] if holder else [body, *wheels,
                                         *([door] if door else []),
                                         *([hood, trunk] if with_hinges else [])]):
        item.select_set(True)
    bpy.context.view_layer.objects.active = holder or body
    s = bpy.context.scene.vehicle_auto_rig
    s.vehicle_type, s.forward_axis, s.forward_sign = 'CAR', 'Y', 'PLUS'
    s.rig_mode, s.bone_count = mode, bone_count
    objects, parts = addon.analyze(bpy.context)
    assert objects == 5 + bool(door) + 2 * with_hinges and parts >= objects
    print('Analysis complete', flush=True)
    rig, wheel_count, bound_count = addon.create_rig(bpy.context)
    print('Rig construction complete', flush=True)
    assert wheel_count == 4 and bound_count == objects
    return holder, body, wheels, door, rig


# Fresh unparented model: all meshes must follow the rig exactly once.
holder, body, wheels, door, rig = setup(False, with_door=True)
print('Checking separate meshes', flush=True)
assert all(ob.parent == rig for ob in [body, *wheels, door])
assert len(rig.data.bones) == 8
assert not any(b.name.startswith(('Suspension.', 'Door.')) for b in rig.data.bones)
assert door.vertex_groups.get('Body')
assert_move(body, lambda: setattr(rig.location, 'x', rig.location.x + 2), (2, 0, 0))
assert_move(wheels[0], lambda: setattr(rig.location, 'y', rig.location.y - 1), (0, -1, 0))
# Driver controls must actually affect the mesh (not merely exist in the UI).
wheel_before = world_vertex(wheels[0])
rig.data['wheel_roll_degrees'] = 40
# Programmatic ID-property changes need an explicit dependency graph tag;
# editing the control in Blender's UI supplies that update automatically.
rig.data.update_tag()
bpy.context.view_layer.update()
assert (world_vertex(wheels[0]) - wheel_before).length > .05
# A Root pose control must still move weighted mesh vertices in Pose Mode.
before_pose = world_vertex(body)
rig.pose.bones['Root'].location.x = .5
bpy.context.view_layer.update()
assert .49 < (world_vertex(body) - before_pose).length < .51

# Preserve an imported Empty hierarchy while attaching its root to the rig.
holder, body, wheels, door, rig = setup(True)
print('Checking imported hierarchy', flush=True)
assert holder.parent == rig and body.parent == holder
assert all(w.parent == holder for w in wheels)
assert_move(body, lambda: setattr(rig.location, 'y', 1), (0, 1, 0))

# Simulate v0.1.0: imported meshes retain their Empty hierarchy, but that
# Empty was never attached to the generated rig object.
transform = holder.matrix_world.copy()
holder.parent = None
holder.matrix_world = transform
roots, count = addon.repair_rig_parenting(rig)
print('Checking v0.1.0 repair', flush=True)
assert roots == 1 and count == 5
assert holder.parent == rig and body.parent == holder
assert_move(wheels[0], lambda: setattr(rig.location, 'x', 1), (1, 0, 0))

# Advanced adds driven suspension chains and hinges. The slider sets the
# requested total; required wheel/steer/hinge bones remain even below minimum.
holder, body, wheels, door, rig = setup(False, mode='ADVANCED', bone_count=18,
                                        with_door=True)
print('Checking advanced rig budget and suspension', flush=True)
assert len(rig.data.bones) == 18 and rig['bone_count'] == 18
assert sum(b.name.startswith('Suspension.') for b in rig.data.bones) == 9
assert any(b.name.startswith('Door.') for b in rig.data.bones)
front = next(w for w in wheels if w.location.y > 0)
rear = next(w for w in wheels if w.location.y < 0)
front_before, rear_before, body_before = map(world_vertex, (front, rear, body))
rig.data['suspension_front'] = .25
rig.data.update_tag()
bpy.context.view_layer.update()
assert ((world_vertex(front) - front_before) - Vector((0, 0, .25))).length < 1e-4
assert (world_vertex(rear) - rear_before).length < 1e-4
assert (world_vertex(body) - body_before).length < 1e-4

holder, body, wheels, door, rig = setup(False, mode='ADVANCED', bone_count=2,
                                        with_door=True)
print('Checking minimum bone count', flush=True)
assert len(rig.data.bones) == 13 and rig['bone_count'] == 13

# Preview generates and removes dedicated actions, leaving body and timeline
# intact while cycling all three hinges and the wheel roll driver.
holder, body, wheels, door, rig = setup(False, mode='ADVANCED', bone_count=18,
                                        with_hinges=True)
scene = bpy.context.scene
scene.frame_start, scene.frame_end = 12, 180
scene.frame_set(48)
hood, trunk = bpy.data.objects['Hood'], bpy.data.objects['Trunk']
count = addon.create_test_animation(rig, scene)
print('Checking Test Rig Functionality animation', flush=True)
assert count == 3 and scene.frame_start == 1 and scene.frame_end == 73
assert rig.animation_data.action and rig.data.animation_data.action
closed = [world_vertex(ob) for ob in (door, hood, trunk, wheels[0], body)]
scene.frame_set(19)
opened = [world_vertex(ob) for ob in (door, hood, trunk, wheels[0], body)]
assert all((opened[i] - closed[i]).length > .03 for i in range(4)), (
    [(opened[i] - closed[i]).length for i in range(4)])
assert (opened[4] - closed[4]).length < 1e-4
addon.clear_test_animation(rig, scene)
assert not rig.animation_data.action and not rig.data.animation_data.action
assert (scene.frame_start, scene.frame_end, scene.frame_current) == (12, 180, 48)
assert '_bdfr_test_rig_state' not in rig
assert all((world_vertex(ob) - closed[i]).length < 1e-4
           for i, ob in enumerate((door, hood, trunk, wheels[0], body)))
print('PASS: simple/advanced rigs, bone budget, suspension, hierarchy and repair', flush=True)
# Standalone bpy can spend a long time in native shutdown even after success.
os._exit(0)
