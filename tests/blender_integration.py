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
    marker = s.indicator_object
    assert marker and marker.type == 'EMPTY' and marker.name == 'BDFR FRONT (+Y)'
    assert marker.hide_render and marker.hide_select and marker.show_name
    assert (marker.rotation_quaternion @ Vector((0, 0, 1)) - Vector((0, 1, 0))).length < 1e-5
    assert marker.matrix_world.translation.y > body.matrix_world.translation.y
    if not parented:
        s.forward_sign = 'MINUS'
        assert marker.name == 'BDFR FRONT (-Y)'
        assert (marker.rotation_quaternion @ Vector((0, 0, 1)) - Vector((0, -1, 0))).length < 1e-5
        s.forward_axis, s.forward_sign = 'X', 'PLUS'
        assert marker.name == 'BDFR FRONT (+X)'
        assert (marker.rotation_quaternion @ Vector((0, 0, 1)) - Vector((1, 0, 0))).length < 1e-5
        s.forward_axis = 'Y'
    print('Analysis complete', flush=True)
    rig, wheel_count, bound_count = addon.create_rig(bpy.context)
    print('Rig construction complete', flush=True)
    assert wheel_count == 4 and bound_count == objects
    assert marker.parent == rig and rig['forward_indicator_name'] == marker.name
    assert s.indicator_object is None
    return holder, body, wheels, door, rig


# Fresh unparented model: all meshes must follow the rig exactly once.
holder, body, wheels, door, rig = setup(False, with_door=True)
print('Checking separate meshes', flush=True)
assert all(ob.parent == rig for ob in [body, *wheels, door])
assert len(rig.data.bones) == 8
assert not any(b.name.startswith(('Suspension.', 'Door.')) for b in rig.data.bones)
assert door.vertex_groups.get('Body')
marker = bpy.data.objects[rig['forward_indicator_name']]
before_marker = marker.matrix_world.translation.copy()
assert_move(body, lambda: setattr(rig.location, 'x', rig.location.x + 2), (2, 0, 0))
assert ((marker.matrix_world.translation - before_marker) - Vector((2, 0, 0))).length < 1e-4
s = bpy.context.scene.vehicle_auto_rig
s.show_forward_indicator = False
assert marker.hide_get()
s.show_forward_indicator = True
assert not marker.hide_get()
assert_move(wheels[0], lambda: setattr(rig.location, 'y', rig.location.y - 1), (0, -1, 0))
# Wheel rotation can be posed directly; there is no extra Roll slider.
assert 'wheel_roll_degrees' not in rig.data
wheel_before = world_vertex(wheels[0])
label = next(vg.name for vg in wheels[0].vertex_groups if vg.name.startswith('Wheel.'))
rig.pose.bones[label].rotation_euler[1] = .7
bpy.context.view_layer.update()
assert (world_vertex(wheels[0]) - wheel_before).length > .05
# Explicitly selected meshes can be rebound to an older rig if their modifier
# is missing, and the sidebar reports missing / disconnected meshes.
addon_mesh = box('Accessory', (0, 0, 1.6), (.2, .2, .2))
assert addon.binding_status(rig)[:2] == (6, 6)
roots, count = addon.bind_selected_meshes(rig, [addon_mesh])
assert count == 7 and addon_mesh.parent == rig
assert addon_mesh.vertex_groups.get('Body')
assert_move(addon_mesh, lambda: setattr(rig.location, 'z', rig.location.z + 1), (0, 0, 1))
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
old_marker = bpy.data.objects[rig['forward_indicator_name']]
bpy.data.objects.remove(old_marker, do_unlink=True)
restored_marker = addon.ensure_rig_front_arrow(bpy.context, rig)
assert restored_marker.parent == rig and rig['forward_indicator_name'] == restored_marker.name
assert (restored_marker.rotation_quaternion @ Vector((0, 0, 1)) - Vector((0, 1, 0))).length < 1e-5

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
assert rig.animation_data.action
closed = [world_vertex(ob) for ob in (door, hood, trunk, wheels[0], body)]
scene.frame_set(19)
opened = [world_vertex(ob) for ob in (door, hood, trunk, wheels[0], body)]
assert all((opened[i] - closed[i]).length > .03 for i in range(4)), (
    [(opened[i] - closed[i]).length for i in range(4)])
assert (opened[4] - closed[4]).length < 1e-4
addon.clear_test_animation(rig, scene)
assert not rig.animation_data.action
assert (scene.frame_start, scene.frame_end, scene.frame_current) == (12, 180, 48)
assert '_bdfr_test_rig_state' not in rig
assert all((world_vertex(ob) - closed[i]).length < 1e-4
           for i, ob in enumerate((door, hood, trunk, wheels[0], body)))
print('PASS: simple/advanced rigs, bone budget, suspension, hierarchy and repair', flush=True)
# Standalone bpy can spend a long time in native shutdown even after success.
os._exit(0)
