"""Vehicle Auto Rig: editable geometric component detection and rigid mechanical rigging."""

bl_info = {
    "name": "BDFR Advanced AutoRig",
    "author": "BDFR contributors",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "location": "View3D > Sidebar > Vehicle Rig",
    "description": "Analyze separate objects or disconnected mesh islands and create a vehicle armature",
    "category": "Rigging",
}

import re
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
]
PART_ITEMS = [
    ('BODY', 'Body', 'Chassis, engine and static parts'),
    ('WHEEL', 'Wheel', 'Spinning wheel (front wheels also steer)'),
    ('DOOR', 'Door', 'Door or hatch hinge'),
    ('HOOD', 'Hood', 'Front hood hinge'),
    ('TRUNK', 'Trunk', 'Rear trunk hinge'),
    ('IGNORE', 'Ignore', 'Do not add armature weights'),
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


def name_hint(ob):
    override = ob.get('vehicle_rig_part', '')
    if override in {v[0] for v in PART_ITEMS}:
        return override
    for part, regex in NAME_RULES:
        if regex.search(ob.name):
            return part
    return None


def classify(ob, lo, hi, global_lo, global_hi, settings, component_count):
    hint = name_hint(ob)
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
    if settings.vehicle_type in {'CAR', 'TRUCK'}:
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
    if settings.vehicle_type in {'BICYCLE', 'MOTORCYCLE'}:
        return {i: ('Front' if j == 0 else 'Rear' if j == len(physical) - 1
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
    for axle_n, (_, members) in enumerate(axles):
        prefix = ('F' if axle_n == 0 else 'R' if axle_n == len(axles) - 1
                  else f'M{axle_n}')
        side_count = defaultdict(int)
        for group_index, center in members:
            side = 'L' if (center - origin).dot(left) >= 0 else 'R'
            side_count[side] += 1
            suffix = f'{side}{side_count[side]:02d}' if side_count[side] > 1 else side
            for index in physical[group_index][1]:
                names[index] = prefix + suffix
    return names


def create_rig(context):
    settings = context.scene.vehicle_auto_rig
    if not settings.has_analysis or not settings.parts:
        raise ValueError('Run Analyze first')
    if settings.analysis_config != config_key(settings):
        raise ValueError('Vehicle settings changed; Analyze again')
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
    names = wheel_labels(parts, settings)
    lo, hi = Vector(settings.bounds_min), Vector(settings.bounds_max)
    center = (lo + hi) * .5
    height = max(hi.z - lo.z, .1)
    reach = max(.07 * height, .02)
    forward, left = axes(settings)
    arm_data = bpy.data.armatures.new('Vehicle_Rig_Data')
    rig = bpy.data.objects.new('Vehicle_Rig', arm_data)
    context.collection.objects.link(rig)
    rig.show_in_front = True
    rig['vehicle_auto_rig_version'] = '0.1.0'
    rig['vehicle_type'] = settings.vehicle_type
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
        for i, part in enumerate(parts):
            if part.kind in {'BODY', 'IGNORE'}:
                assignment[i] = 'Body' if part.kind == 'BODY' else None
                continue
            p = Vector(part.center)
            if part.kind == 'WHEEL':
                label = names[i]
                wheel_name = 'Wheel.' + label
                is_front = label.startswith('F')
                parent = 'Root'
                if wheel_name not in created_wheels:
                    if is_front:
                        steer_name = 'Steer.' + label
                        bone(eb, steer_name, p, p + Vector((0, 0, reach)), 'Root', False)
                        parent = steer_name
                    bone(eb, wheel_name, p, p + left * reach, parent)
                    created_wheels.add(wheel_name)
                assignment[i] = wheel_name
            else:
                prefix = part.kind.title()
                bname = f'{prefix}.{i + 1:03d}'
                # Pivot near outer edge for doors, at front/back end for lids.
                pivot = p.copy()
                half_span = abs((Vector(part.maximum) - Vector(part.minimum)).dot(forward)) * .45
                if part.kind == 'HOOD':
                    pivot -= forward * half_span
                else:
                    pivot += forward * half_span
                bone(eb, bname, pivot, pivot + Vector((0, 0, reach)), 'Body')
                assignment[i] = bname
        bpy.ops.object.mode_set(mode='OBJECT')
        # Animatable controls. Bone local Y follows the axle for wheels and
        # world Z for steering pivots, so the same Euler channel is sufficient.
        rig['steer_degrees'] = 0.0
        rig['wheel_roll_degrees'] = 0.0
        rig.id_properties_ui('steer_degrees').update(min=-55.0, max=55.0,
                                                     description='Front wheel steering in degrees')
        rig.id_properties_ui('wheel_roll_degrees').update(
            description='All wheel rotation in degrees')
        for name in created_wheels:
            pb = rig.pose.bones[name]
            pb.rotation_mode = 'XYZ'
            drv = pb.driver_add('rotation_euler', 1).driver
            drv.expression = 'var*0.017453292519943295'
            var = drv.variables.new()
            var.name = 'var'; var.targets[0].id_type = 'OBJECT'
            var.targets[0].id = rig
            var.targets[0].data_path = '["wheel_roll_degrees"]'
            steer_name = 'Steer.' + name.split('.', 1)[1]
            if steer_name in rig.pose.bones:
                sb = rig.pose.bones[steer_name]
                sb.rotation_mode = 'XYZ'
                drv = sb.driver_add('rotation_euler', 1).driver
                drv.expression = 'var*0.017453292519943295'
                var = drv.variables.new()
                var.name = 'var'; var.targets[0].id_type = 'OBJECT'
                var.targets[0].id = rig
                var.targets[0].data_path = '["steer_degrees"]'
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
            for ob in objects:
                for m in list(ob.modifiers):
                    if m.type == 'ARMATURE' and m.object == rig:
                        ob.modifiers.remove(m)
            bpy.data.objects.remove(rig, do_unlink=True)
        raise


class VAR_Part(bpy.types.PropertyGroup):
    source: PointerProperty(type=bpy.types.Object)
    region_index: IntProperty()
    first_vertex: IntProperty()
    vertex_count: IntProperty()
    kind: EnumProperty(items=PART_ITEMS, name='Part')
    reason: StringProperty()
    center: bpy.props.FloatVectorProperty(size=3)
    minimum: bpy.props.FloatVectorProperty(size=3)
    maximum: bpy.props.FloatVectorProperty(size=3)


class VAR_Settings(bpy.types.PropertyGroup):
    vehicle_type: EnumProperty(items=TYPE_ITEMS, name='Vehicle')
    forward_axis: EnumProperty(items=[('Y', 'Y', ''), ('X', 'X', '')], name='Forward axis')
    forward_sign: EnumProperty(items=[('PLUS', '+', ''), ('MINUS', '-', '')], name='Direction')
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
    bl_description = 'Detect wheels and named moving parts; inspect and correct the list below'
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


class VAR_PT_Panel(bpy.types.Panel):
    bl_label = 'Vehicle Auto Rig'
    bl_idname = 'VAR_PT_vehicle_auto_rig'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Vehicle Rig'

    def draw(self, context):
        layout = self.layout
        s = context.scene.vehicle_auto_rig
        layout.prop(s, 'vehicle_type')
        row = layout.row(align=True)
        row.prop(s, 'forward_axis'); row.prop(s, 'forward_sign')
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
            for p in list(s.parts)[:100]:
                row = box.row(align=True)
                row.label(text=f'{p.source.name[:19]} #{p.region_index}' if p.source else 'Missing')
                row.prop(p, 'kind', text='')
            if len(s.parts) > 100:
                box.label(text=f'{len(s.parts) - 100} more; use object overrides')
            layout.operator('vehicle_auto_rig.build', icon='ARMATURE_DATA')
        box = layout.box()
        box.label(text='Object override (select parts):')
        for part in ('WHEEL', 'BODY', 'DOOR', 'HOOD', 'TRUNK', 'IGNORE'):
            op = box.operator('vehicle_auto_rig.mark', text='Mark ' + part.title())
            op.part = part
        layout.label(text='Pose Root / Body bones for vehicle motion.')
        rig = context.active_object
        if rig and rig.type == 'ARMATURE' and rig.get('vehicle_auto_rig_version'):
            box = layout.box()
            box.label(text='Animate rig controls:')
            box.prop(rig, '["steer_degrees"]', text='Steering (degrees)')
            box.prop(rig, '["wheel_roll_degrees"]', text='Wheel roll (degrees)')


CLASSES = (VAR_Part, VAR_Settings, VAR_OT_Analyze, VAR_OT_Rig, VAR_OT_Mark, VAR_PT_Panel)


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
