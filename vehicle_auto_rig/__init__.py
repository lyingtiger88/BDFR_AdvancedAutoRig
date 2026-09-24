"""Vehicle Auto Rig: editable geometric component detection and rigid mechanical rigging."""

bl_info = {
    "name": "BDFR Advanced AutoRig",
    "author": "BDFR contributors",
    "version": (0, 6, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Vehicle Rig",
    "description": "Analyze separate objects or disconnected mesh islands and create a vehicle armature",
    "category": "Rigging",
}

import re
import json
import math
from collections import defaultdict

import bpy
from bpy.props import (BoolProperty, CollectionProperty, EnumProperty, FloatProperty,
                       IntProperty, PointerProperty, StringProperty)
from mathutils import Vector


TYPE_ITEMS = [
    ('CAR', 'Car / SUV', 'Four or more side wheels'),
    ('TRUCK', 'Truck / Bus', 'Multiple axles supported'),
    ('MOTORCYCLE', 'Motorcycle', 'Two inline wheels'),
    ('BICYCLE', 'Bicycle', 'Two inline wheels'),
    ('AIRPLANE', 'Airplane', 'Landing wheels, propellers and flight control surfaces'),
]
PART_ITEMS = [
    ('BODY', 'Body', 'Chassis, engine and static parts'),
    ('WHEEL', 'Wheel', 'Spinning wheel (front wheels also steer)'),
    ('DOOR', 'Door', 'Door or hatch hinge'),
    ('HOOD', 'Hood', 'Front hood hinge'),
    ('TRUNK', 'Trunk', 'Rear trunk hinge'),
    ('PROPELLER', 'Propeller', 'Spin around the aircraft forward axis'),
    ('AILERON', 'Aileron', 'Wing roll control surface'),
    ('ELEVATOR', 'Elevator', 'Horizontal tail pitch surface'),
    ('RUDDER', 'Rudder', 'Vertical tail yaw surface'),
    ('FLAP', 'Flap', 'Wing flap control surface'),
    ('IGNORE', 'Ignore', 'Do not add armature weights'),
]
AXLE_ITEMS = [('AUTO', 'Auto', 'Determine the axle from the wheel position'),
              ('FRONT', 'Front', 'Front steering axle'),
              ('REAR', 'Rear', 'Rear axle')]
STEER_ITEMS = [('AUTO', 'Auto', 'Steer the lone nose or tail landing wheel'),
               ('YES', 'Yes', 'Make this landing wheel steerable'),
               ('NO', 'No', 'Do not steer this landing wheel')]
AIRCRAFT_SURFACES = {'AILERON', 'ELEVATOR', 'RUDDER', 'FLAP'}
AIRCRAFT_RULES = [
    ('PROPELLER', re.compile(r'propeller|prop[_ .-]|\bprop\b|hélice|ملخ', re.I)),
    ('AILERON', re.compile(r'aileron|شهپر', re.I)),
    ('ELEVATOR', re.compile(r'elevator|stabilator|سکان افقی', re.I)),
    ('RUDDER', re.compile(r'rudder|سکان عمودی', re.I)),
    ('FLAP', re.compile(r'flap|فلپ', re.I)),
    ('WHEEL', re.compile(r'nose[_ .-]?gear|main[_ .-]?gear|tail[_ .-]?wheel|landing[_ .-]?wheel', re.I)),
]
NAME_RULES = [
    ('WHEEL', re.compile(r'wheel|tire|tyre|rim|roue|rad|چرخ|لاستیک', re.I)),
    ('DOOR', re.compile(r'door|porte|در[ب]?', re.I)),
    ('HOOD', re.compile(r'hood|bonnet|کاپوت', re.I)),
    ('TRUNK', re.compile(r'trunk|boot|tailgate|صندوق', re.I)),
]


def root_objects(context):
    """Selected meshes, or meshes inside selected parent hierarchies."""
    result = {}
    for ob in context.selected_objects:
        family = [ob, *ob.children_recursive] if ob.type != 'MESH' else [ob]
        for item in family:
            if item.type == 'MESH' and len(item.data.vertices):
                result[item.name] = item
    return list(result.values())


def components(ob, scan_islands, vertex_limit):
    """Stable vertex-index components, computed on the original mesh (no modifiers)."""
    mesh = ob.data
    n = len(mesh.vertices)
    if not scan_islands or n > vertex_limit:
        return [list(range(n))]
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for edge in mesh.edges:
        a, b = edge.vertices
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    groups = defaultdict(list)
    for index in range(n):
        groups[find(index)].append(index)
    return sorted(groups.values(), key=lambda v: v[0])


def bbox(ob, indices):
    mat = ob.matrix_world
    verts = ob.data.vertices
    low = [float('inf')] * 3
    high = [float('-inf')] * 3
    for index in indices:
        p = mat @ verts[index].co
        for axis in range(3):
            low[axis] = min(low[axis], p[axis])
            high[axis] = max(high[axis], p[axis])
    return Vector(low), Vector(high)


def axes(settings):
    sign = 1 if settings.forward_sign == 'PLUS' else -1
    if settings.forward_axis == 'Y':
        return Vector((0, sign, 0)), Vector((-sign, 0, 0))
    return Vector((sign, 0, 0)), Vector((0, sign, 0))


def front_arrow(context, bounds_min, bounds_max, forward, existing=None):
    """Place a viewport-only arrow above the front of the vehicle."""
    lo, hi = Vector(bounds_min), Vector(bounds_max)
    size = hi - lo
    center = (lo + hi) * .5
    radius = max(size.length * .14, .12)
    front = center + forward * (abs(forward.x) * size.x + abs(forward.y) * size.y) * .5
    front.z = hi.z + max(radius * .5, .06)
    arrow = existing if existing and existing.type == 'EMPTY' else None
    if arrow is None:
        arrow = bpy.data.objects.new('BDFR FRONT', None)
        context.collection.objects.link(arrow)
    arrow['bdfr_forward_indicator'] = True
    arrow.name = 'BDFR FRONT (' + ('+' if forward.x + forward.y > 0 else '-') + (
        'X' if abs(forward.x) > .5 else 'Y') + ')'
    arrow.empty_display_type = 'SINGLE_ARROW'
    arrow.empty_display_size = radius
    arrow.show_name = True
    arrow.show_in_front = True
    arrow.hide_render = True
    arrow.hide_select = True
    arrow.rotation_mode = 'QUATERNION'
    arrow.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(forward)
    arrow.location = front
    arrow.hide_set(not context.scene.vehicle_auto_rig.show_forward_indicator)
    context.view_layer.update()
    return arrow


def refresh_front_arrow(settings, context):
    """Update the unrigged preview, or toggle the arrow on an existing rig."""
    if context is None or context.scene is None:
        return
    rig = context.active_object
    if rig and rig.type == 'ARMATURE' and rig.get('vehicle_auto_rig_version'):
        name = rig.get('forward_indicator_name', '')
        arrow = bpy.data.objects.get(name) if name else None
        if arrow and arrow.get('bdfr_forward_indicator'):
            arrow.hide_set(not settings.show_forward_indicator)
        return
    arrow = settings.indicator_object
    if arrow and arrow.name in bpy.data.objects and arrow.get('bdfr_forward_indicator'):
        if settings.has_analysis:
            front_arrow(context, settings.bounds_min, settings.bounds_max,
                        axes(settings)[0], arrow)
        arrow.hide_set(not settings.show_forward_indicator)


def name_hint(ob, vehicle_type=None):
    override = ob.get('vehicle_rig_part', '')
    if override in {v[0] for v in PART_ITEMS}:
        return override
    rules = (AIRCRAFT_RULES + NAME_RULES) if vehicle_type == 'AIRPLANE' else NAME_RULES
    for part, regex in rules:
        if regex.search(ob.name):
            return part
    return None


def classify(ob, lo, hi, global_lo, global_hi, settings, component_count):
    hint = name_hint(ob, settings.vehicle_type)
    if hint:
        return hint, 'name / override'
    forward, left = axes(settings)
    center = (lo + hi) * 0.5
    size = hi - lo
    total = global_hi - global_lo
    long_axis = settings.forward_axis == 'Y'
    lateral = 0 if long_axis else 1
    depth = 1 if long_axis else 0
    global_center = (global_lo + global_hi) * 0.5
    radius = (size[depth] + size.z) / 4
    roundish = abs(size[depth] - size.z) / max(size[depth], size.z, 1e-6) < .42
    thin = size[lateral] < 0.85 * max(size[depth], size.z)
    at_bottom = center.z < global_lo.z + total.z * .72
    within_scale = total[depth] * .045 <= radius <= total[depth] * .34
    if settings.vehicle_type == 'AIRPLANE':
        on_side = True  # A nose or tail landing wheel lies on the centerline.
    elif settings.vehicle_type in {'CAR', 'TRUCK'}:
        on_side = abs((center - global_center).dot(left)) > total[lateral] * .17
    else:
        on_side = abs((center - global_center).dot(left)) < total[lateral] * .35 + 1e-5
    plausible = roundish and thin and at_bottom and within_scale and on_side
    # A contiguous full-body mesh cannot be reliably dissected into moving parts.
    if plausible and component_count > 1:
        return 'WHEEL', 'shape / position'
    if plausible and max(size) < .45 * max(total):
        return 'WHEEL', 'shape / position'
    return 'BODY', 'default'


def analyze(context):
    settings = context.scene.vehicle_auto_rig
    objects = root_objects(context)
    if not objects:
        raise ValueError('Select vehicle meshes or a parent containing vehicle meshes')
    if any(any(m.type == 'ARMATURE' for m in ob.modifiers) for ob in objects):
        raise ValueError('Selection contains an existing armature modifier; use an unrigged model')
    if any(ob.library or ob.data.library for ob in objects):
        raise ValueError('Linked library meshes are read-only; make them local first')
    low, high = [float('inf')] * 3, [float('-inf')] * 3
    regions = []
    skipped = []
    for ob in objects:
        if len(ob.data.vertices) > settings.vertex_limit and settings.scan_islands:
            skipped.append(ob.name)
        islands = components(ob, settings.scan_islands, settings.vertex_limit)
        for ri, indices in enumerate(islands):
            lo, hi = bbox(ob, indices)
            for j in range(3):
                low[j] = min(low[j], lo[j]); high[j] = max(high[j], hi[j])
            regions.append((ob, ri, indices, lo, hi, len(islands)))
    if len(regions) > 1000:
        raise ValueError('Over 1000 disconnected parts; join tiny details or disable island scanning')
    global_lo, global_hi = Vector(low), Vector(high)
    settings.parts.clear()
    for ob, ri, indices, lo, hi, count in regions:
        kind, reason = classify(ob, lo, hi, global_lo, global_hi, settings, count)
        part = settings.parts.add()
        part.source = ob
        part.region_index = ri
        part.first_vertex = indices[0]
        part.vertex_count = len(indices)
        part.kind = kind
        part.reason = reason
        part.center = (lo + hi) * .5
        part.minimum = lo
        part.maximum = hi
    settings.selection_names = '|'.join(sorted(ob.name for ob in objects))
    settings.bounds_min, settings.bounds_max = global_lo, global_hi
    settings.analysis_config = config_key(settings)
    settings.has_analysis = True
    settings.warning = ('Island scan skipped for: ' + ', '.join(skipped[:3])) if skipped else ''
    previous = settings.indicator_object
    if previous and previous.parent:
        previous = None
    settings.indicator_object = front_arrow(context, global_lo, global_hi,
                                            axes(settings)[0], previous)
    return len(objects), len(regions)


def config_key(settings):
    return '|'.join((settings.vehicle_type, settings.forward_axis,
                     settings.forward_sign, str(settings.scan_islands),
                     str(settings.vertex_limit)))


def bone(edit_bones, name, head, tail, parent=None, deform=True):
    b = edit_bones.new(name)
    b.head, b.tail = head, tail
    b.use_deform = deform
    if parent:
        b.parent = edit_bones[parent]
        b.use_connect = False
    return b


def vehicle_parent_roots(meshes, selected_objects, rig):
    """Use selected vehicle hierarchy roots rather than flattening their children."""
    allowed = set(meshes) | set(selected_objects)
    roots = set()
    for ob in meshes:
        root = ob
        while root.parent in allowed and root.parent != rig:
            root = root.parent
        roots.add(root)
    return [ob for ob in roots if not any(a != ob and ob in a.children_recursive
                                         for a in roots)]


def parent_vehicle_to_rig(rig, meshes, selected_objects, changes):
    """Keep each hierarchy's world transform and attach it to the rig object."""
    for ob in vehicle_parent_roots(meshes, selected_objects, rig):
        if ob.parent == rig:
            continue
        world = ob.matrix_world.copy()
        changes.append((ob, ob.parent, ob.parent_type, ob.parent_bone,
                        ob.matrix_parent_inverse.copy(), world))
        ob.parent = rig
        ob.parent_type = 'OBJECT'
        ob.matrix_parent_inverse = rig.matrix_world.inverted()
        ob.matrix_world = world


def restore_parents(changes):
    for ob, parent, parent_type, parent_bone, parent_inverse, world in reversed(changes):
        ob.parent = parent
        ob.parent_type = parent_type
        if parent_type == 'BONE':
            ob.parent_bone = parent_bone
        ob.matrix_parent_inverse = parent_inverse
        ob.matrix_world = world


def wheel_labels(parts, settings):
    forward, left = axes(settings)
    origin = (Vector(settings.bounds_min) + Vector(settings.bounds_max)) * .5
    wheels = [(i, Vector(p.center)) for i, p in enumerate(parts) if p.kind == 'WHEEL']
    wheels.sort(key=lambda x: -(x[1] - origin).dot(forward))
    # Tire, rim and hub may be distinct meshes at the same physical wheel.
    physical = []
    span = (Vector(settings.bounds_max) - Vector(settings.bounds_min)).length
    for index, center in wheels:
        size = Vector(parts[index].maximum) - Vector(parts[index].minimum)
        radius = max(size) * .5
        match = next((group for group in physical
                      if (center - group[0]).length < max(.15 * radius, .02 * span)), None)
        if match is None:
            physical.append([center, [index]])
        else:
            match[1].append(index)
    def axle_override(indices):
        choices = {getattr(parts[i], 'wheel_axle', 'AUTO') for i in indices} - {'AUTO'}
        if len(choices) > 1:
            raise ValueError('Conflicting Front/Rear overrides on the same wheel')
        return next(iter(choices), None)

    if settings.vehicle_type in {'BICYCLE', 'MOTORCYCLE'}:
        return {i: ('Front' if axle_override(indices) == 'FRONT' else
                    'Rear' if axle_override(indices) == 'REAR' else
                    'Front' if j == 0 else 'Rear' if j == len(physical) - 1
                    else f'Mid{j:02d}')
                for j, (_, indices) in enumerate(physical) for i in indices}
    # Nearby wheels share an axle. This also accommodates 6x6/8x8 layouts.
    axles = []
    total = Vector(settings.bounds_max) - Vector(settings.bounds_min)
    tolerance = max(.04 * total.length, .10 * total.z)
    for group_index, (center, _) in enumerate(physical):
        projection = (center - origin).dot(forward)
        group = next((a for a in axles if abs(a[0] - projection) < tolerance), None)
        if group is None:
            group = [projection, []]
            axles.append(group)
        group[1].append((group_index, center))
    names = {}
    prefix_count = defaultdict(int)
    for axle_n, (_, members) in enumerate(axles):
        overrides = {axle_override(physical[gi][1]) for gi, _ in members} - {None}
        if len(overrides) > 1:
            raise ValueError('Conflicting Front/Rear overrides on one axle')
        override = next(iter(overrides), None)
        prefix = ('F' if override == 'FRONT' else 'R' if override == 'REAR' else
                  'F' if axle_n == 0 else 'R' if axle_n == len(axles) - 1
                  else f'M{axle_n}')
        prefix_count[prefix] += 1
        if prefix_count[prefix] > 1:
            prefix = f'{prefix}{prefix_count[prefix]}'
        side_count = defaultdict(int)
        for group_index, center in members:
            side = 'L' if (center - origin).dot(left) >= 0 else 'R'
            side_count[side] += 1
            suffix = f'{side}{side_count[side]:02d}' if side_count[side] > 1 else side
            for index in physical[group_index][1]:
                names[index] = prefix + suffix
    return names


def steering_labels(parts, settings, labels):
    """Choose aircraft nose/tail steering without steering its main landing gear."""
    if settings.vehicle_type != 'AIRPLANE':
        return {label for label in labels.values()
                if label.startswith('F') or label == 'Front'}
    members = defaultdict(list)
    for index, label in labels.items():
        members[label].append(parts[index])
    front = {label for label in members if label.startswith('F') or label == 'Front'}
    rear = {label for label in members if label.startswith('R') or label == 'Rear'}
    steering = set()
    for label, group in members.items():
        choices = {getattr(p, 'wheel_steer', 'AUTO') for p in group} - {'AUTO'}
        if len(choices) > 1:
            raise ValueError('Conflicting steering overrides on the same landing wheel')
        if choices:
            if 'YES' in choices:
                steering.add(label)
            continue
        if any(re.search(r'nose|tail[_ .-]?wheel|tail[_ .-]?gear',
                         getattr(getattr(p, 'source', None), 'name', ''), re.I)
               for p in group):
            steering.add(label)
        elif (len(front) == 1 and len(rear) > 1 and label in front or
              len(rear) == 1 and len(front) > 1 and label in rear):
            steering.add(label)
    return steering


def rig_bone_plan(parts, settings):
    """Count required controls and distribute extra spring bones across wheels."""
    labels = wheel_labels(parts, settings)
    wheels = sorted(set(labels.values()))
    steering = steering_labels(parts, settings, labels)
    advanced = settings.rig_mode == 'ADVANCED'
    moving = {'DOOR', 'HOOD', 'TRUNK'} | (AIRCRAFT_SURFACES if settings.vehicle_type == 'AIRPLANE' else set())
    hinges = sum(p.kind in moving for p in parts) if advanced else 0
    propellers = sum(p.kind == 'PROPELLER' for p in parts) if settings.vehicle_type == 'AIRPLANE' else 0
    required = 2 + len(wheels) + len(steering) + hinges + propellers
    spring_segments = {label: 0 for label in wheels}
    if advanced:
        required += len(wheels)
        for label in wheels:
            spring_segments[label] = 1
        extra = max(0, settings.bone_count - required)
        # Each added bone is part of an actual wheel suspension control chain.
        for i in range(extra):
            if wheels:
                spring_segments[wheels[i % len(wheels)]] += 1
            else:
                break
    return labels, spring_segments, required, required + (max(0, settings.bone_count - required)
                                                         if advanced and wheels else 0)


def create_rig(context):
    settings = context.scene.vehicle_auto_rig
    if not settings.has_analysis or not settings.parts:
        raise ValueError('Run Analyze first')
    if settings.analysis_config != config_key(settings):
        raise ValueError('Vehicle settings changed; Analyze again')
    selected_objects = list(context.selected_objects)
    objects = root_objects(context)
    if sorted(o.name for o in objects) != settings.selection_names.split('|'):
        raise ValueError('Selection changed; select the original vehicle and Analyze again')
    # Validate all source topology BEFORE creating/modifying data.
    indexed = {}
    for ob in objects:
        indexed[ob.name] = components(ob, settings.scan_islands, settings.vertex_limit)
    for p in settings.parts:
        if p.source is None or p.source.name not in indexed:
            raise ValueError('A source object was deleted; Analyze again')
        seq = indexed[p.source.name]
        if p.region_index >= len(seq):
            raise ValueError('Mesh topology changed; Analyze again')
        indices = seq[p.region_index]
        if len(indices) != p.vertex_count or indices[0] != p.first_vertex:
            raise ValueError('Mesh topology changed; Analyze again')
        actual_lo, actual_hi = bbox(p.source, indices)
        if ((actual_lo - Vector(p.minimum)).length > 1e-4 or
                (actual_hi - Vector(p.maximum)).length > 1e-4):
            raise ValueError('A mesh moved or changed shape; Analyze again')
    parts = list(settings.parts)
    names, spring_segments, required, actual = rig_bone_plan(parts, settings)
    steering = steering_labels(parts, settings, names)
    lo, hi = Vector(settings.bounds_min), Vector(settings.bounds_max)
    center = (lo + hi) * .5
    height = max(hi.z - lo.z, .1)
    reach = max(.07 * height, .02)
    forward, left = axes(settings)
    arm_data = bpy.data.armatures.new('Vehicle_Rig_Data')
    rig = bpy.data.objects.new('Vehicle_Rig', arm_data)
    context.collection.objects.link(rig)
    rig.show_in_front = True
    rig['vehicle_auto_rig_version'] = '0.6.0'
    rig['vehicle_type'] = settings.vehicle_type
    rig['rig_mode'] = settings.rig_mode
    rig['forward_axis'] = settings.forward_axis
    rig['forward_sign'] = settings.forward_sign
    rig['bone_count'] = actual
    rig['bound_mesh_names'] = json.dumps([ob.name for ob in objects])
    parent_changes = []
    try:
        bpy.ops.object.mode_set(mode='OBJECT') if context.object and context.object.mode != 'OBJECT' else None
        bpy.ops.object.select_all(action='DESELECT')
        rig.select_set(True)
        context.view_layer.objects.active = rig
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm_data.edit_bones
        ground = Vector((center.x, center.y, lo.z))
        bone(eb, 'Root', ground, ground + Vector((0, 0, reach)), deform=False)
        bone(eb, 'Body', center, center + Vector((0, 0, reach)), 'Root')
        assignment = {}
        created_wheels = set()
        spring_controls = {}
        for i, part in enumerate(parts):
            if part.kind in {'BODY', 'IGNORE'} or (settings.rig_mode == 'SIMPLE' and
                                                  part.kind in {'DOOR', 'HOOD', 'TRUNK'} |
                                                  AIRCRAFT_SURFACES) or (settings.vehicle_type != 'AIRPLANE' and
                                                  part.kind in AIRCRAFT_SURFACES | {'PROPELLER'}):
                assignment[i] = None if part.kind == 'IGNORE' else 'Body'
                continue
            p = Vector(part.center)
            if part.kind == 'WHEEL':
                label = names[i]
                wheel_name = 'Wheel.' + label
                is_front = label in steering
                parent = 'Root'
                if wheel_name not in created_wheels:
                    segments = spring_segments[label]
                    for segment in range(segments):
                        spring_name = f'Suspension.{label}.{segment + 1:02d}'
                        start = p + Vector((0, 0, reach * segment / segments))
                        end = p + Vector((0, 0, reach * (segment + 1) / segments))
                        bone(eb, spring_name, start, end, parent, False)
                        if segment == 0:
                            spring_controls[label] = spring_name
                        parent = spring_name
                    if is_front:
                        steer_name = 'Steer.' + label
                        bone(eb, steer_name, p, p + Vector((0, 0, reach)), parent, False)
                        parent = steer_name
                    bone(eb, wheel_name, p, p + left * reach, parent)
                    created_wheels.add(wheel_name)
                assignment[i] = wheel_name
            elif part.kind == 'PROPELLER':
                bname = f'Propeller.{i + 1:03d}'
                bone(eb, bname, p, p + forward * reach, 'Body')
                assignment[i] = bname
            else:
                prefix = part.kind.title()
                bname = f'{prefix}.{i + 1:03d}'
                # Pivot near outer edge for doors, at front/back end for lids.
                pivot = p.copy()
                half_span = abs((Vector(part.maximum) - Vector(part.minimum)).dot(forward)) * .45
                if part.kind in AIRCRAFT_SURFACES:
                    pivot += forward * half_span  # leading edge of a control surface
                    axis = Vector((0, 0, 1)) if part.kind == 'RUDDER' else left
                elif part.kind == 'HOOD':
                    pivot -= forward * half_span
                    axis = Vector((0, 0, 1))
                else:
                    pivot += forward * half_span
                    axis = Vector((0, 0, 1))
                bone(eb, bname, pivot, pivot + axis * reach, 'Body')
                assignment[i] = bname
        bpy.ops.object.mode_set(mode='OBJECT')
        # Front steering and suspension remain animatable controls. Wheel
        # rotation is keyed directly on the bones in Test Rig Functionality.
        # Drive the pose from Armature data properties. Pointing pose drivers
        # back at properties on the same Object makes a dependency cycle and
        # leaves controls unevaluated in Blender's dependency graph.
        arm_data['steer_degrees'] = 0.0
        if spring_controls:
            arm_data['suspension_front'] = 0.0
            arm_data['suspension_rear'] = 0.0
            for prop in ('suspension_front', 'suspension_rear'):
                arm_data.id_properties_ui(prop).update(
                    description='Wheel suspension travel in scene units; positive raises wheels')
        arm_data.id_properties_ui('steer_degrees').update(min=-55.0, max=55.0,
                                                          description='Front wheel steering in degrees')
        for name in created_wheels:
            pb = rig.pose.bones[name]
            pb.rotation_mode = 'XYZ'
            steer_name = 'Steer.' + name.split('.', 1)[1]
            if steer_name in rig.pose.bones:
                sb = rig.pose.bones[steer_name]
                sb.rotation_mode = 'XYZ'
                drv = sb.driver_add('rotation_euler', 1).driver
                drv.expression = 'var*0.017453292519943295'
                var = drv.variables.new()
                var.name = 'var'; var.targets[0].id_type = 'ARMATURE'
                var.targets[0].id = arm_data
                var.targets[0].data_path = '["steer_degrees"]'
        for pb in rig.pose.bones:
            if pb.name.startswith('Propeller.'):
                pb.rotation_mode = 'XYZ'
        for label, name in spring_controls.items():
            pb = rig.pose.bones[name]
            prop = 'suspension_front' if label.startswith('F') else 'suspension_rear'
            drv = pb.driver_add('location', 1).driver
            drv.expression = 'var'
            var = drv.variables.new()
            var.name = 'var'; var.targets[0].id_type = 'ARMATURE'
            var.targets[0].id = arm_data
            var.targets[0].data_path = f'["{prop}"]'
        # Rigid 1.0 weights keep separate parts solid and preserve object transforms.
        by_object = defaultdict(list)
        for i, part in enumerate(parts):
            if assignment[i] is not None:
                by_object[part.source.name].append((assignment[i], indexed[part.source.name][part.region_index]))
        for name, assignments in by_object.items():
            ob = bpy.data.objects[name]
            collision = next((bone_name for bone_name, _ in assignments
                              if ob.vertex_groups.get(bone_name)), None)
            if collision:
                raise ValueError(f'{name} already has group {collision}; rename it and retry')
        for name, assignments in by_object.items():
            ob = bpy.data.objects[name]
            if ob.data.users > 1:
                ob.data = ob.data.copy()  # avoid changing an unrelated instance's groups
            for bone_name, indices in assignments:
                vg = ob.vertex_groups.get(bone_name) or ob.vertex_groups.new(name=bone_name)
                for start in range(0, len(indices), 10000):
                    vg.add(indices[start:start + 10000], 1.0, 'REPLACE')
            mod = ob.modifiers.new('Vehicle Auto Rig', 'ARMATURE')
            mod.object = rig
            mod.use_vertex_groups = True
            mod.use_bone_envelopes = False
        # Meshes must also be children of the armature object so moving the
        # rig in Object Mode moves the whole vehicle, as users expect.
        parent_vehicle_to_rig(rig, objects, selected_objects, parent_changes)
        arrow = settings.indicator_object
        if arrow and arrow.name in bpy.data.objects and arrow.get('bdfr_forward_indicator'):
            world = arrow.matrix_world.copy()
            arrow.parent = rig
            arrow.matrix_parent_inverse = rig.matrix_world.inverted()
            arrow.matrix_world = world
            rig['forward_indicator_name'] = arrow.name
            settings.indicator_object = None
        for obj in objects:
            obj.select_set(True)
        rig.select_set(True)
        context.view_layer.objects.active = rig
        settings.has_analysis = False
        return rig, len(created_wheels), len(by_object)
    except Exception:
        if rig.name in bpy.data.objects:
            try:
                if context.object and context.object.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass
            marker = bpy.data.objects.get(rig.get('forward_indicator_name', ''))
            if marker and marker.parent == rig:
                world = marker.matrix_world.copy()
                marker.parent = None
                marker.matrix_world = world
                settings.indicator_object = marker
            restore_parents(parent_changes)
            for ob in objects:
                for m in list(ob.modifiers):
                    if m.type == 'ARMATURE' and m.object == rig:
                        ob.modifiers.remove(m)
            bpy.data.objects.remove(rig, do_unlink=True)
        raise


def ensure_rig_front_arrow(context, rig):
    """Add a visible front direction arrow to a rig from an earlier version."""
    name = rig.get('forward_indicator_name', '')
    existing = bpy.data.objects.get(name) if name else None
    if existing and existing.get('bdfr_forward_indicator'):
        existing.hide_set(False)
        return existing
    meshes = [ob for ob in bpy.data.objects if ob.type == 'MESH' and
              any(mod.type == 'ARMATURE' and mod.object == rig for mod in ob.modifiers)]
    if not meshes:
        raise ValueError('No meshes bound to this rig; bind the vehicle meshes first')
    corners = [ob.matrix_world @ Vector(corner) for ob in meshes for corner in ob.bound_box]
    lo = Vector(tuple(min(p[i] for p in corners) for i in range(3)))
    hi = Vector(tuple(max(p[i] for p in corners) for i in range(3)))
    settings = context.scene.vehicle_auto_rig
    sign = 1 if rig.get('forward_sign', settings.forward_sign) == 'PLUS' else -1
    forward = (Vector((sign, 0, 0)) if rig.get('forward_axis', settings.forward_axis) == 'X'
               else Vector((0, sign, 0)))
    arrow = front_arrow(context, lo, hi, forward)
    world = arrow.matrix_world.copy()
    arrow.parent = rig
    arrow.matrix_parent_inverse = rig.matrix_world.inverted()
    arrow.matrix_world = world
    arrow.hide_set(False)
    rig['forward_indicator_name'] = arrow.name
    return arrow


def repair_rig_parenting(rig):
    """Attach meshes from a v0.1.0 rig without rebuilding their vertex groups."""
    meshes = [ob for ob in bpy.data.objects if ob.type == 'MESH' and
              any(mod.type == 'ARMATURE' and mod.object == rig for mod in ob.modifiers)]
    if not meshes:
        raise ValueError('No meshes with an Armature modifier targeting this rig')
    bound = set(meshes)
    # Preserve imported empty hierarchies when all mesh descendants belong to
    # this vehicle; never pull another vehicle's meshes under this rig.
    ancestors = set()
    for ob in meshes:
        ancestor = ob.parent
        while ancestor and ancestor != rig and ancestor.type != 'ARMATURE':
            if any(item.type == 'MESH' and item not in bound
                   for item in ancestor.children_recursive):
                break
            ancestors.add(ancestor)
            ancestor = ancestor.parent
    changes = []
    try:
        parent_vehicle_to_rig(rig, meshes, ancestors, changes)
    except Exception:
        restore_parents(changes)
        raise
    return len(changes), len(meshes)


def binding_status(rig):
    """Count meshes driven by this rig and the ones following its Object transform."""
    meshes = [ob for ob in bpy.data.objects if ob.type == 'MESH' and
              any(mod.type == 'ARMATURE' and mod.object == rig for mod in ob.modifiers)]
    attached = 0
    for ob in meshes:
        parent = ob.parent
        while parent and parent != rig:
            parent = parent.parent
        attached += parent == rig
    try:
        expected = json.loads(rig.get('bound_mesh_names', '[]'))
    except (ValueError, TypeError):
        expected = []
    missing = [name for name in expected if not any(ob.name == name for ob in meshes)]
    return len(meshes), attached, missing


def bind_selected_meshes(rig, meshes):
    """Explicitly bind separate selected meshes to an existing generated rig."""
    if not meshes:
        raise ValueError('Select vehicle meshes together with the rig; keep the rig active')
    choices = {kind: [b for b in rig.data.bones if b.name.startswith(prefix)]
               for kind, prefix in (('WHEEL', 'Wheel.'), ('DOOR', 'Door.'),
                                    ('HOOD', 'Hood.'), ('TRUNK', 'Trunk.'))}
    if 'Body' not in rig.data.bones:
        raise ValueError('This rig has no Body bone')
    for ob in meshes:
        if ob.library or ob.data.library:
            raise ValueError(f'{ob.name} is linked; make it local first')
        if any(mod.type == 'ARMATURE' and mod.object != rig for mod in ob.modifiers):
            raise ValueError(f'{ob.name} uses another armature')
        if ob.data.users > 1:
            raise ValueError(f'{ob.name} shares mesh data; make it single-user first')
        if any(item.type == 'MESH' for item in ob.children_recursive):
            raise ValueError(f'{ob.name} has child meshes; select its vehicle hierarchy instead')
    for ob in meshes:
        indices = {vg.index for vg in ob.vertex_groups if vg.name in rig.data.bones}
        has_weights = any(any(group.group in indices for group in vertex.groups)
                          for vertex in ob.data.vertices)
        if not has_weights:
            hint = name_hint(ob)
            candidates = choices.get(hint) or [rig.data.bones['Body']]
            center = ob.matrix_world @ Vector(tuple(sum(v[i] for v in ob.bound_box) / 8
                                                    for i in range(3)))
            nearest = min(candidates, key=lambda b: ((rig.matrix_world @ b.head_local) - center).length)
            vg = ob.vertex_groups.get(nearest.name) or ob.vertex_groups.new(name=nearest.name)
            for start in range(0, len(ob.data.vertices), 10000):
                vg.add(list(range(start, min(start + 10000, len(ob.data.vertices)))), 1.0, 'REPLACE')
        if not any(mod.type == 'ARMATURE' and mod.object == rig for mod in ob.modifiers):
            mod = ob.modifiers.new('Vehicle Auto Rig', 'ARMATURE')
            mod.object = rig
            mod.use_vertex_groups = True
            mod.use_bone_envelopes = False
    roots, count = repair_rig_parenting(rig)
    try:
        known = set(json.loads(rig.get('bound_mesh_names', '[]')))
    except (ValueError, TypeError):
        known = set()
    rig['bound_mesh_names'] = json.dumps(sorted(known | {ob.name for ob in meshes}))
    return roots, count


TEST_STATE_KEY = '_bdfr_test_rig_state'


def test_controls(rig):
    """Legacy builds drove wheel rotation through an ID property."""
    return (rig.data if 'wheel_roll_degrees' in rig.data else
            rig if 'wheel_roll_degrees' in rig else None)


def test_hinges(rig):
    forward = Vector((0, 1, 0)) if rig.get('forward_axis', 'Y') == 'Y' else Vector((1, 0, 0))
    if rig.get('forward_sign', 'PLUS') == 'MINUS':
        forward.negate()
    left = Vector((-forward.y, forward.x, 0))
    body = rig.data.bones.get('Body')
    body_center = body.head_local if body else Vector((0, 0, 0))
    for pb in rig.pose.bones:
        name = pb.name
        if name.startswith('Door.'):
            axis, angle = Vector((0, 0, 1)), (-65 if (pb.bone.head_local - body_center).dot(left) >= 0 else 65)
        elif name.startswith('Hood.'):
            axis, angle = left, -55
        elif name.startswith('Trunk.'):
            axis, angle = left, 55
        elif name.startswith('Aileron.'):
            axis = left
            angle = 25 if (pb.bone.head_local - body_center).dot(left) >= 0 else -25
        elif name.startswith('Elevator.'):
            axis, angle = left, 20
        elif name.startswith('Rudder.'):
            axis, angle = Vector((0, 0, 1)), 28
        elif name.startswith('Flap.'):
            axis, angle = left, -35
        else:
            continue
        # Pose rotations use each bone's rest-local coordinates.
        local_axis = (pb.bone.matrix_local.to_3x3().inverted() @ axis).normalized()
        yield pb, local_axis, math.radians(angle)


def clear_test_animation(rig, scene):
    if TEST_STATE_KEY not in rig:
        raise ValueError('No test animation exists on this rig')
    state = json.loads(rig[TEST_STATE_KEY])
    controls = test_controls(rig)
    for owner, name in ((rig, state.get('rig_action')), (controls, state.get('controls_action'))):
        if not name or owner is None:
            continue
        action = bpy.data.actions.get(name)
        animation = owner.animation_data
        if action and animation and animation.action == action:
            animation.action = None
        if action and action.users == 0:
            bpy.data.actions.remove(action)
    if controls and 'wheel_roll' in state:
        controls['wheel_roll_degrees'] = state['wheel_roll']
        controls.update_tag()
    for name, saved in {**state['hinges'], **state.get('wheels', {})}.items():
        pb = rig.pose.bones.get(name)
        if pb:
            pb.rotation_mode = saved['mode']
            pb.rotation_axis_angle = saved['axis_angle']
            pb.rotation_euler = saved['euler']
            pb.rotation_quaternion = saved['quaternion']
    scene.frame_start, scene.frame_end = state['frame_start'], state['frame_end']
    scene.frame_set(state['frame'])
    del rig[TEST_STATE_KEY]


def create_test_animation(rig, scene):
    if TEST_STATE_KEY in rig:
        raise ValueError('Remove the current test animation before generating another')
    controls = test_controls(rig)
    wheels = [pb for pb in rig.pose.bones
              if pb.name.startswith(('Wheel.', 'Propeller.'))]
    if not wheels:
        raise ValueError('No wheel or propeller bones found on this rig')
    for owner in (rig, controls) if controls and controls != rig else (rig,):
        animation = owner.animation_data
        if animation and (animation.action or len(animation.nla_tracks)):
            raise ValueError('This rig already has animation; test on an unanimated copy')
    hinges = list(test_hinges(rig))
    state = {
        'frame': scene.frame_current, 'frame_start': scene.frame_start,
        'frame_end': scene.frame_end,
        'hinges': {pb.name: {'mode': pb.rotation_mode,
                             'axis_angle': list(pb.rotation_axis_angle),
                             'euler': list(pb.rotation_euler),
                             'quaternion': list(pb.rotation_quaternion)}
                   for pb, _, _ in hinges},
        'wheels': {pb.name: {'mode': pb.rotation_mode,
                             'axis_angle': list(pb.rotation_axis_angle),
                             'euler': list(pb.rotation_euler),
                             'quaternion': list(pb.rotation_quaternion)}
                   for pb in wheels if controls is None},
    }
    if controls:
        state['wheel_roll'] = float(controls['wheel_roll_degrees'])
    rig[TEST_STATE_KEY] = json.dumps(state)
    try:
        for pb, axis, angle in hinges:
            pb.rotation_mode = 'AXIS_ANGLE'
            for frame, value in ((1, 0), (19, angle), (37, angle), (55, 0), (73, 0)):
                pb.rotation_axis_angle = (value, *axis)
                pb.keyframe_insert(data_path='rotation_axis_angle', frame=frame,
                                   group='Test Rig Functionality')
        for frame, value in ((1, 0), (19, 90), (37, 180), (55, 270), (73, 360)):
            if controls:
                controls['wheel_roll_degrees'] = value
                controls.keyframe_insert(data_path='["wheel_roll_degrees"]', frame=frame,
                                         group='Test Rig Functionality')
            else:
                for pb in wheels:
                    pb.rotation_mode = 'XYZ'
                    pb.rotation_euler[1] = math.radians(value)
                    pb.keyframe_insert(data_path='rotation_euler', index=1, frame=frame,
                                       group='Test Rig Functionality')
        state['rig_action'] = rig.animation_data.action.name if rig.animation_data and rig.animation_data.action else None
        state['controls_action'] = (controls.animation_data.action.name if controls
                                    and controls != rig and controls.animation_data
                                    and controls.animation_data.action else None)
        rig[TEST_STATE_KEY] = json.dumps(state)
        scene.frame_start, scene.frame_end = 1, 73
        scene.frame_set(1)
        return len(hinges)
    except Exception:
        state['rig_action'] = rig.animation_data.action.name if rig.animation_data and rig.animation_data.action else None
        state['controls_action'] = (controls.animation_data.action.name if controls
                                     and controls != rig and controls.animation_data
                                     and controls.animation_data.action else None)
        rig[TEST_STATE_KEY] = json.dumps(state)
        clear_test_animation(rig, scene)
        raise


class VAR_Part(bpy.types.PropertyGroup):
    source: PointerProperty(type=bpy.types.Object)
    region_index: IntProperty()
    first_vertex: IntProperty()
    vertex_count: IntProperty()
    kind: EnumProperty(items=PART_ITEMS, name='Part')
    wheel_axle: EnumProperty(items=AXLE_ITEMS, name='Axle', default='AUTO')
    wheel_steer: EnumProperty(items=STEER_ITEMS, name='Landing gear steering', default='AUTO')
    reason: StringProperty()
    center: bpy.props.FloatVectorProperty(size=3)
    minimum: bpy.props.FloatVectorProperty(size=3)
    maximum: bpy.props.FloatVectorProperty(size=3)


class VAR_Settings(bpy.types.PropertyGroup):
    vehicle_type: EnumProperty(items=TYPE_ITEMS, name='Vehicle')
    rig_mode: EnumProperty(items=[('SIMPLE', 'Simple', 'Body, wheel, steering and propeller controls'),
                               ('ADVANCED', 'Advanced', 'Suspension, hinges and flight surfaces')],
                           name='Rig Mode', default='SIMPLE')
    bone_count: IntProperty(name='Bone Count', default=16, min=2, max=128,
                            description='Target total bones in Advanced mode; required controls are always kept')
    forward_axis: EnumProperty(items=[('Y', 'Y', ''), ('X', 'X', '')], name='Forward axis',
                               update=refresh_front_arrow)
    forward_sign: EnumProperty(items=[('PLUS', '+', ''), ('MINUS', '-', '')], name='Direction',
                               update=refresh_front_arrow)
    show_forward_indicator: BoolProperty(name='Show FRONT Arrow', default=True,
                                          update=refresh_front_arrow)
    indicator_object: PointerProperty(type=bpy.types.Object)
    scan_islands: BoolProperty(name='Find disconnected parts', default=True)
    vertex_limit: IntProperty(name='Per mesh scan limit', default=300000, min=1000, max=2000000)
    parts: CollectionProperty(type=VAR_Part)
    has_analysis: BoolProperty(default=False)
    selection_names: StringProperty()
    analysis_config: StringProperty()
    bounds_min: bpy.props.FloatVectorProperty(size=3)
    bounds_max: bpy.props.FloatVectorProperty(size=3)
    warning: StringProperty()


class VAR_OT_Analyze(bpy.types.Operator):
    bl_idname = 'vehicle_auto_rig.analyze'
    bl_label = '1. Analyze Vehicle'
    bl_description = 'Detect wheels, propellers and named moving parts; inspect the list below'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            objects, regions = analyze(context)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, f'Found {regions} parts in {objects} meshes; review the assignments')
        return {'FINISHED'}


class VAR_OT_Rig(bpy.types.Operator):
    bl_idname = 'vehicle_auto_rig.build'
    bl_label = '2. Build Rig'
    bl_description = 'Create an armature and rigid vertex weights without changing mesh geometry'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        try:
            _, wheels, meshes = create_rig(context)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, f'Rig built: {wheels} wheels, {meshes} bound meshes')
        return {'FINISHED'}


class VAR_OT_Mark(bpy.types.Operator):
    bl_idname = 'vehicle_auto_rig.mark'
    bl_label = 'Mark Selected Objects'
    bl_description = 'Override automatic classification for selected separate mesh objects'
    bl_options = {'REGISTER', 'UNDO'}
    part: EnumProperty(items=PART_ITEMS, name='Part')

    def execute(self, context):
        targets = [o for o in context.selected_objects if o.type == 'MESH']
        if not targets:
            self.report({'WARNING'}, 'Select one or more separate mesh objects')
            return {'CANCELLED'}
        for ob in targets:
            ob['vehicle_rig_part'] = self.part
        context.scene.vehicle_auto_rig.has_analysis = False
        self.report({'INFO'}, f'Marked {len(targets)} object(s); Analyze again')
        return {'FINISHED'}


class VAR_OT_Repair(bpy.types.Operator):
    bl_idname = 'vehicle_auto_rig.repair_parenting'
    bl_label = 'Repair Existing Rig Binding'
    bl_description = 'Make meshes attached to this rig follow it in Object Mode (also repairs v0.1.0 rigs)'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ob = context.active_object
        return bool(ob and ob.type == 'ARMATURE' and ob.get('vehicle_auto_rig_version'))

    def execute(self, context):
        try:
            roots, meshes = repair_rig_parenting(context.active_object)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, f'Attached {roots} hierarchy roots ({meshes} meshes) to the rig')
        return {'FINISHED'}


class VAR_OT_BindSelected(bpy.types.Operator):
    bl_idname = 'vehicle_auto_rig.bind_selected'
    bl_label = 'Bind Selected Meshes'
    bl_description = 'Attach explicitly selected vehicle meshes to the active rig, preserving world positions'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        rig = context.active_object
        return bool(rig and rig.type == 'ARMATURE' and rig.get('vehicle_auto_rig_version')
                    and any(ob.type == 'MESH' for ob in context.selected_objects))

    def execute(self, context):
        rig = context.active_object
        try:
            _, count = bind_selected_meshes(rig, [ob for ob in context.selected_objects
                                                  if ob.type == 'MESH'])
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, f'{count} meshes now follow {rig.name}')
        return {'FINISHED'}


class VAR_OT_FrontArrow(bpy.types.Operator):
    bl_idname = 'vehicle_auto_rig.show_front_arrow'
    bl_label = 'Show FRONT Arrow'
    bl_description = 'Show the front direction above this existing vehicle rig'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        rig = context.active_object
        return bool(rig and rig.type == 'ARMATURE' and rig.get('vehicle_auto_rig_version'))

    def execute(self, context):
        try:
            ensure_rig_front_arrow(context, context.active_object)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        context.scene.vehicle_auto_rig.show_forward_indicator = True
        return {'FINISHED'}


class VAR_OT_TestRig(bpy.types.Operator):
    bl_idname = 'vehicle_auto_rig.test_functionality'
    bl_label = 'Create Test Animation'
    bl_description = 'Preview hinges, flight surfaces, wheels and propellers'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        rig = context.active_object
        return bool(rig and rig.type == 'ARMATURE' and rig.get('vehicle_auto_rig_version'))

    def execute(self, context):
        try:
            hinges = create_test_animation(context.active_object, context.scene)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        if (context.screen and not context.screen.is_animation_playing and
                bpy.ops.screen.animation_play.poll()):
            bpy.ops.screen.animation_play()
        self.report({'INFO'}, f'Test animation: {hinges} moving surfaces and wheel/propeller rotation, frames 1–73')
        return {'FINISHED'}


class VAR_OT_ClearTestRig(bpy.types.Operator):
    bl_idname = 'vehicle_auto_rig.clear_test_functionality'
    bl_label = 'Remove Test Animation'
    bl_description = 'Remove preview keyframes and restore the previous timeline and pose'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        rig = context.active_object
        return bool(rig and rig.type == 'ARMATURE' and TEST_STATE_KEY in rig)

    def execute(self, context):
        try:
            if context.screen and context.screen.is_animation_playing:
                bpy.ops.screen.animation_cancel(restore_frame=False)
            clear_test_animation(context.active_object, context.scene)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, 'Test animation removed; timeline and pose restored')
        return {'FINISHED'}


class VAR_OT_PlayTestRig(bpy.types.Operator):
    bl_idname = 'vehicle_auto_rig.play_test_functionality'
    bl_label = 'Play / Stop Preview'
    bl_description = 'Toggle test animation playback in the current Blender window'
    bl_options = {'REGISTER'}

    @classmethod
    def poll(cls, context):
        return bool(context.screen and context.active_object and
                    TEST_STATE_KEY in context.active_object)

    def execute(self, context):
        if context.screen.is_animation_playing:
            bpy.ops.screen.animation_cancel(restore_frame=False)
        else:
            bpy.ops.screen.animation_play()
        return {'FINISHED'}


class VAR_PT_Panel(bpy.types.Panel):
    bl_label = 'Vehicle Auto Rig'
    bl_idname = 'VAR_PT_vehicle_auto_rig'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Vehicle Rig'

    def draw(self, context):
        layout = self.layout
        s = context.scene.vehicle_auto_rig
        layout.label(text='BDFR Advanced AutoRig v0.6.0')
        layout.prop(s, 'vehicle_type')
        layout.prop(s, 'rig_mode', expand=True)
        if s.rig_mode == 'ADVANCED':
            layout.prop(s, 'bone_count', slider=True)
            if s.has_analysis:
                _, _, required, actual = rig_bone_plan(list(s.parts), s)
                layout.label(text=f'Minimum: {required}  /  Built: {actual} bones')
        row = layout.row(align=True)
        row.prop(s, 'forward_axis'); row.prop(s, 'forward_sign')
        direction = ('+' if s.forward_sign == 'PLUS' else '-') + s.forward_axis
        layout.label(text=f'FRONT: {direction}')
        layout.prop(s, 'show_forward_indicator')
        layout.prop(s, 'scan_islands')
        if s.scan_islands:
            layout.prop(s, 'vertex_limit')
        layout.operator('vehicle_auto_rig.analyze', icon='VIEWZOOM')
        if s.has_analysis:
            wheel_count = sum(p.kind == 'WHEEL' for p in s.parts)
            layout.label(text=f'{len(s.parts)} parts  /  {wheel_count} wheels')
            if s.warning:
                layout.label(text=s.warning[:55], icon='ERROR')
            box = layout.box()
            try:
                wheel_names = wheel_labels(list(s.parts), s)
            except ValueError as exc:
                wheel_names = {}
                box.label(text=str(exc)[:55], icon='ERROR')
            for i, p in enumerate(list(s.parts)[:100]):
                row = box.row(align=True)
                row.label(text=f'{p.source.name[:19]} #{p.region_index}' if p.source else 'Missing')
                row.prop(p, 'kind', text='')
                if p.kind == 'WHEEL':
                    box.label(text='Wheel ' + wheel_names.get(i, '?'))
                    box.prop(p, 'wheel_axle', text='Front / Rear')
                    if s.vehicle_type == 'AIRPLANE':
                        box.prop(p, 'wheel_steer', text='Steering')
            if len(s.parts) > 100:
                box.label(text=f'{len(s.parts) - 100} more; use object overrides')
            layout.operator('vehicle_auto_rig.build', icon='ARMATURE_DATA')
        box = layout.box()
        box.label(text='Object override (select parts):')
        available = (('WHEEL', 'BODY', 'PROPELLER', 'AILERON', 'ELEVATOR', 'RUDDER',
                      'FLAP', 'DOOR', 'IGNORE') if s.vehicle_type == 'AIRPLANE' else
                     ('WHEEL', 'BODY', 'DOOR', 'HOOD', 'TRUNK', 'IGNORE'))
        for part in available:
            op = box.operator('vehicle_auto_rig.mark', text='Mark ' + part.title())
            op.part = part
        layout.label(text='Pose Root / Body bones for vehicle motion.')
        rig = context.active_object
        if rig and rig.type == 'ARMATURE' and rig.get('vehicle_auto_rig_version'):
            binding = layout.box()
            binding.label(text=f'Rig version: {rig.get("vehicle_auto_rig_version")}')
            rig_dir = ('+' if rig.get('forward_sign', 'PLUS') == 'PLUS' else '-') + rig.get('forward_axis', 'Y')
            binding.label(text=f'Rig FRONT: {rig_dir}')
            marker = bpy.data.objects.get(rig.get('forward_indicator_name', ''))
            if marker is None:
                binding.operator('vehicle_auto_rig.show_front_arrow')
            bound, attached, missing = binding_status(rig)
            binding.label(text=f'Mesh binding: {attached}/{bound} follow the rig',
                          icon='CHECKMARK' if bound and bound == attached and not missing else 'ERROR')
            if missing:
                binding.label(text=f'{len(missing)} original mesh(es) missing modifiers', icon='ERROR')
            binding.operator('vehicle_auto_rig.repair_parenting', text='Fix Existing Binding',
                             icon='CON_ARMATURE')
            binding.operator('vehicle_auto_rig.bind_selected', icon='OUTLINER_OB_MESH')
            binding.label(text='Select rig + meshes; keep rig active')
            box = layout.box()
            box.label(text='Animate rig controls:')
            controls = rig.data if 'steer_degrees' in rig.data else rig
            is_plane = rig.get('vehicle_type') == 'AIRPLANE'
            if not is_plane or any(b.name.startswith('Steer.') for b in rig.data.bones):
                box.prop(controls, '["steer_degrees"]',
                         text='Nose / tail steering' if is_plane else 'Steering (degrees)')
            if 'suspension_front' in controls:
                box.prop(controls, '["suspension_front"]', text='Front suspension')
                box.prop(controls, '["suspension_rear"]', text='Rear suspension')
            front_count = sum(b.name.startswith('Wheel.F') for b in rig.data.bones)
            rear_count = sum(b.name.startswith(('Wheel.R', 'Wheel.Rear')) for b in rig.data.bones)
            box.label(text=(f'Front gear: {front_count}  /  Rear gear: {rear_count}' if is_plane
                            else f'Front wheels: {front_count}  /  Rear wheels: {rear_count}'))
            if is_plane:
                box.label(text='Pose Propeller / Aileron / Elevator / Rudder / Flap bones')
            preview = layout.box()
            preview.label(text='Test Rig Functionality', icon='PLAY')
            if TEST_STATE_KEY in rig:
                preview.operator('vehicle_auto_rig.play_test_functionality', icon='PLAY')
                preview.operator('vehicle_auto_rig.clear_test_functionality', icon='TRASH')
                preview.label(text=('Frames 1-73: controls, gear, propellers' if is_plane
                                    else 'Frames 1-73: doors, hood, trunk, wheels'))
            else:
                preview.operator('vehicle_auto_rig.test_functionality', text='Create & Play Test',
                                 icon='ACTION')
                if rig.get('rig_mode') != 'ADVANCED':
                    preview.label(text=('Use Advanced for flight controls' if is_plane
                                        else 'Use Advanced rig for doors and hatches'))


CLASSES = (VAR_Part, VAR_Settings, VAR_OT_Analyze, VAR_OT_Rig, VAR_OT_Mark,
           VAR_OT_Repair, VAR_OT_BindSelected, VAR_OT_FrontArrow,
           VAR_OT_TestRig, VAR_OT_ClearTestRig,
           VAR_OT_PlayTestRig, VAR_PT_Panel)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.vehicle_auto_rig = PointerProperty(type=VAR_Settings)


def unregister():
    del bpy.types.Scene.vehicle_auto_rig
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


if __name__ == '__main__':
    register()
