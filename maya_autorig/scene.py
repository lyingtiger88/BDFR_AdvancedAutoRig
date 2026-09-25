"""Maya scene adapter. Importing this module does not require a Maya installation."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from .core import Analysis, Options, Part, analyze, plan_rig, _distance


@dataclass(frozen=True)
class BuiltRig:
    root: str
    joints: dict[str, str]
    skin_clusters: dict[str, str]
    front_arrow: str
    analysis: Analysis | None = None


# Matches AAdvancedVehiclePawn::WheelSetups in BDFR_DriveCore. Keep the
# planner's logical names stable so existing animation scripts still work.
DRIVECORE_WHEEL_NAMES = {
    'Wheel.FL': 'wheel_fl',
    'Wheel.FR': 'wheel_fr',
    'Wheel.RL': 'wheel_rl',
    'Wheel.RR': 'wheel_rr',
}
_RIG_OPTIONS_ATTRIBUTE = 'BDFR_autoRigOptions'


def _legacy_forward(cmds, arrow, up):
    if not cmds.objExists(arrow):
        raise ValueError('Older rig has no FRONT arrow; rebuild to recover export direction')
    angle = float(cmds.getAttr(arrow + ('.rotateY' if up == 'Y' else '.rotateZ')))
    by_axis = ({0: ('Z', 1), 180: ('Z', -1), 90: ('X', 1), -90: ('X', -1)}
               if up == 'Y' else
               {0: ('Y', 1), 180: ('Y', -1), -90: ('X', 1), 90: ('X', -1)})
    for expected, direction in by_axis.items():
        if abs((angle - expected + 180) % 360 - 180) < .01:
            return direction
    raise ValueError('FRONT arrow was rotated since rigging; cannot infer export direction')


def recover_built_rig(cmds=None, root=None) -> BuiltRig:
    """Reconnect an existing skinned rig for export after reopening the UI or scene."""
    cmds = _maya(cmds)
    joints = set(cmds.ls(type='joint', long=True) or [])
    roots = sorted(node for node in joints if (
        cmds.objExists(node + '.' + _RIG_OPTIONS_ATTRIBUTE) or
        node.rsplit('|', 1)[-1].rsplit(':', 1)[-1] == 'BDFR_Root'))
    selected = cmds.ls(selection=True, long=True, objectsOnly=True) or []
    selected_roots = [root for root in roots if any(
        node == root or node.startswith(root + '|') for node in selected)]
    if root is not None:
        if root not in roots:
            raise ValueError('The rig from this window is no longer in this scene')
    elif len(selected_roots) == 1:
        root = selected_roots[0]
    elif len(selected_roots) > 1 or len(roots) != 1:
        raise ValueError('Select one BDFR_Root joint in the Outliner before exporting')
    else:
        root = roots[0]
    members = {root, *(cmds.listRelatives(root, allDescendents=True,
                                         type='joint', fullPath=True) or [])}
    if len(members) < 2:
        raise ValueError('The selected rig has no child joints to export')
    arrow = root + '|BDFR_FRONT'
    if cmds.objExists(root + '.' + _RIG_OPTIONS_ATTRIBUTE):
        try:
            saved = json.loads(cmds.getAttr(root + '.' + _RIG_OPTIONS_ATTRIBUTE))
            if saved['schema'] != 1:
                raise ValueError('Unsupported BDFR rig metadata version')
            options = Options(**saved['options'])
        except (TypeError, KeyError, json.JSONDecodeError) as exc:
            raise ValueError('BDFR rig metadata is damaged; rebuild the rig') from exc
    else:
        up = _scene_up(cmds)
        forward_axis, forward_sign = _legacy_forward(cmds, arrow, up)
        options = Options(up_axis=up, forward_axis=forward_axis,
                          forward_sign=forward_sign)
    if options.up_axis != _scene_up(cmds):
        raise ValueError('Maya up axis changed since rigging; rebuild before exporting')
    clusters = {}
    for shape in cmds.ls(type='mesh', long=True, noIntermediate=True) or []:
        parents = cmds.listRelatives(shape, parent=True, fullPath=True) or []
        if len(parents) != 1:
            continue
        mesh = parents[0]
        for cluster in cmds.ls(cmds.listHistory(mesh, pruneDagObjects=True) or [],
                               type='skinCluster') or []:
            influences = cmds.skinCluster(cluster, query=True, influence=True) or []
            resolved = set(cmds.ls(influences, long=True) or [])
            if resolved and resolved <= members:
                if mesh in clusters and clusters[mesh] != cluster:
                    raise ValueError('Multiple BDFR skinClusters on mesh: ' + mesh)
                clusters[mesh] = cluster
    if not clusters:
        raise ValueError('No meshes skinned to this BDFR rig; select its root or rebuild')
    # The exporter reads only options from Analysis; mesh ownership comes from
    # the validated skinCluster influences above, not from stale saved paths.
    analysis = Analysis(options, (), (0., 0., 0.), (0., 0., 0.))
    return BuiltRig(root, {node: node for node in members}, clusters, arrow, analysis)


def _joint_node_name(joint, options):
    if options.vehicle in {'CAR', 'TRUCK'} and joint.name in DRIVECORE_WHEEL_NAMES:
        return DRIVECORE_WHEEL_NAMES[joint.name]
    return 'BDFR_' + joint.name.replace('.', '_')


def drivecore_wheel_bones(built: BuiltRig) -> dict[str, str]:
    """Return FL/FR/RL/RR DAG paths, or reject an incompatible four-wheel rig."""
    if built.analysis is None or built.analysis.options.vehicle not in {'CAR', 'TRUCK'}:
        raise ValueError('BDFR_DriveCore requires a car or four-wheel truck rig')
    wheel_keys = {key for key in built.joints if key.startswith('Wheel.')}
    if wheel_keys != set(DRIVECORE_WHEEL_NAMES):
        raise ValueError('BDFR_DriveCore default WheelSetups require exactly FL/FR/RL/RR; '
                         'review detected axles or customize WheelSetups')
    result = {}
    for key, expected in DRIVECORE_WHEEL_NAMES.items():
        node = built.joints[key]
        if node.rsplit('|', 1)[-1] != expected:
            raise ValueError('Wheel joint ' + key + ' must be named ' + expected +
                             '; rebuild the rig with the current Maya core')
        result[key.split('.')[1]] = node
    return result


def _maya(cmds):
    if cmds is not None:
        return cmds
    try:
        from maya import cmds as maya_cmds
    except ImportError as exc:
        raise RuntimeError('Run Maya scene operations inside Autodesk Maya') from exc
    return maya_cmds


def _canonical(point, up_axis):
    """Use XYZ with Z-up within the planner; convert Y-up by swapping Y/Z."""
    return tuple(point) if up_axis == 'Z' else (point[0], point[2], point[1])


def _scene_up(cmds):
    up = cmds.upAxis(query=True, axis=True).upper()
    if up not in {'Y', 'Z'}:
        raise ValueError('Only Maya Y-up and Z-up scenes are supported')
    return up


def _mesh_nodes(cmds, selected):
    found = set()
    for node in selected:
        if not cmds.objExists(node):
            raise ValueError('Selected object was removed: ' + node)
        if cmds.nodeType(node) == 'mesh':
            parents = cmds.listRelatives(node, parent=True, fullPath=True) or []
            if parents:
                found.add(parents[0])
            continue
        candidates = [node]
        candidates.extend(cmds.listRelatives(node, allDescendents=True,
                                             fullPath=True, type='transform') or [])
        for candidate in candidates:
            if cmds.nodeType(candidate) != 'transform':
                continue
            shapes = cmds.listRelatives(candidate, shapes=True, fullPath=True,
                                        type='mesh', noIntermediate=True) or []
            if shapes:
                found.add(candidate)
    if not found:
        raise ValueError('Select separate mesh transforms or their parent group')
    return tuple(sorted(found))


def _part(cmds, node, up_axis, override=None):
    shapes = cmds.listRelatives(node, shapes=True, fullPath=True,
                                type='mesh', noIntermediate=True) or []
    if len(shapes) != 1:
        raise ValueError(node + ': expected exactly one visible mesh shape')
    if len(cmds.listRelatives(shapes[0], allParents=True, fullPath=True) or []) != 1:
        raise ValueError(node + ': instanced geometry must be made unique first')
    locked = cmds.lockNode(node, query=True, lock=True)
    locked = locked[0] if isinstance(locked, (tuple, list)) else locked
    if cmds.referenceQuery(node, isNodeReferenced=True) or locked:
        raise ValueError(node + ': referenced or locked meshes cannot be skinned')
    if cmds.ls(cmds.listHistory(node, pruneDagObjects=True) or [], type='skinCluster'):
        raise ValueError(node + ': existing skinCluster found; use an unrigged copy')
    count = int(cmds.polyEvaluate(node, vertex=True))
    shells = int(cmds.polyEvaluate(node, shell=True))
    bounds = tuple(float(v) for v in cmds.exactWorldBoundingBox(node))
    if len(bounds) != 6:
        raise ValueError(node + ': cannot read world-space bounds')
    bounds = _canonical(bounds[:3], up_axis) + _canonical(bounds[3:], up_axis)
    override = override or {}
    invalid = set(override) - {'kind', 'axle', 'steer'}
    if invalid:
        raise ValueError('Unknown override keys: ' + ', '.join(sorted(invalid)))
    return Part(node, bounds[:3], bounds[3:], count, shells=shells, **override)


def analyze_selection(options=None, overrides=None, cmds=None):
    """Read-only assessment. Override keys must be full DAG paths of selected meshes."""
    cmds = _maya(cmds)
    up = _scene_up(cmds)
    options = options if options is not None else Options(
        up_axis=up, forward_axis='Z' if up == 'Y' else 'Y')
    if options.up_axis != up:
        raise ValueError('Options up_axis differs from the Maya scene; analyze again')
    selected = cmds.ls(selection=True, long=True, objectsOnly=True) or []
    nodes = _mesh_nodes(cmds, selected)
    overrides = overrides or {}
    unknown = set(overrides) - set(nodes)
    if unknown:
        raise ValueError('Overrides must use selected full DAG paths: ' + ', '.join(sorted(unknown)))
    return analyze((_part(cmds, node, up, overrides.get(node)) for node in nodes), options)


def _preflight(cmds, analysis):
    if _scene_up(cmds) != analysis.options.up_axis:
        raise ValueError('Maya up axis changed since analysis; analyze again')
    for original in analysis.parts:
        if not cmds.objExists(original.node):
            raise ValueError('Mesh removed since analysis: ' + original.node)
        current = _part(cmds, original.node, analysis.options.up_axis)
        if current.vertices != original.vertices or current.shells != original.shells or (
                _distance(current.minimum, original.minimum) > 1e-5) or (
                _distance(current.maximum, original.maximum) > 1e-5):
            raise ValueError('Mesh changed since analysis; analyze again: ' + original.node)


def _create_joints(cmds, plan):
    pending = list(plan.joints)
    created = {}
    while pending:
        previous = len(pending)
        for joint in pending[:]:
            if joint.parent is not None and joint.parent not in created:
                continue
            expected_name = _joint_node_name(joint, plan.analysis.options)
            args = {'name': expected_name}
            if joint.parent is not None:
                args['parent'] = created[joint.parent]
            node = cmds.createNode('joint', **args)
            full_node = cmds.ls(node, long=True)[0]
            if full_node.rsplit('|', 1)[-1] != expected_name:
                raise ValueError('Maya renamed joint ' + expected_name + ' to ' + full_node +
                                 '; resolve the naming conflict before building')
            cmds.xform(node, worldSpace=True,
                       translation=_canonical(joint.position, plan.analysis.options.up_axis))
            created[joint.name] = full_node
            pending.remove(joint)
        if len(pending) == previous:
            raise ValueError('Joint plan contains a cyclic or missing parent')
    return created


def _front_arrow(cmds, plan, root):
    span = _distance(plan.analysis.minimum, plan.analysis.maximum)
    scale = max(.12, span * .07)
    pts = ((0, -1, 0), (0, 1, 0), (-.35, .5, 0), (0, 1, 0),
           (.35, .5, 0))
    opts = plan.analysis.options
    node = cmds.curve(name='BDFR_FRONT', degree=1,
                      point=[_canonical(tuple(v * scale for v in p), opts.up_axis) for p in pts])
    if opts.up_axis == 'Z':
        angle = {('Y', 1): 0, ('Y', -1): 180, ('X', 1): -90, ('X', -1): 90}[
            (opts.forward_axis, opts.forward_sign)]
        rotation = '.rotateZ'
    else:
        angle = {('Z', 1): 0, ('Z', -1): 180, ('X', 1): 90, ('X', -1): -90}[
            (opts.forward_axis, opts.forward_sign)]
        rotation = '.rotateY'
    cmds.xform(node, worldSpace=True, translation=_canonical(plan.front_position, opts.up_axis))
    cmds.setAttr(node + rotation, angle)
    node = cmds.parent(node, root)[0]  # Maya preserves the world transform by default.
    return cmds.ls(node, long=True)[0]


def build_rig(analysis: Analysis, cmds=None):
    """Build, rigidly skin and verify; roll back the entire operation on failure."""
    cmds = _maya(cmds)
    plan = plan_rig(analysis)
    _preflight(cmds, analysis)
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError('Enable Maya Undo before building (required for safe rollback)')
    original_selection = cmds.ls(selection=True, long=True, objectsOnly=True) or []
    cmds.undoInfo(openChunk=True, chunkName='BDFR Maya AutoRig')
    failed = False
    try:
        joints = _create_joints(cmds, plan)
        clusters = {}
        parts = {p.node: p for p in analysis.parts}
        for node, joint_name in plan.bindings:
            joint = joints[joint_name]
            created_cluster = cmds.skinCluster(joint, node, name='BDFR_skin',
                                               toSelectedBones=True, bindMethod=0,
                                               skinMethod=0, normalizeWeights=1,
                                               maximumInfluences=1, obeyMaxInfluences=True)
            cluster = (created_cluster[0] if isinstance(created_cluster, (tuple, list))
                       else created_cluster)
            vertex_range = '%s.vtx[0:%d]' % (node, parts[node].vertices - 1)
            cmds.skinPercent(cluster, vertex_range, transformValue=[(joint, 1.0)],
                             normalize=True, zeroRemainingInfluences=True)
            value = cmds.skinPercent(cluster, node + '.vtx[0]', query=True,
                                     transform=joint)
            if isinstance(value, (tuple, list)):
                value = value[0]
            if abs(float(value) - 1) > 1e-5:
                raise RuntimeError('Skin weights could not be verified on ' + node)
            raw = tuple(float(v) for v in cmds.exactWorldBoundingBox(node))
            new_bounds = (_canonical(raw[:3], analysis.options.up_axis) +
                          _canonical(raw[3:], analysis.options.up_axis))
            tolerance = max(1e-4, _distance(parts[node].minimum, parts[node].maximum)*1e-5)
            if (_distance(new_bounds[:3], parts[node].minimum) > tolerance or
                    _distance(new_bounds[3:], parts[node].maximum) > tolerance):
                raise RuntimeError('Skin bind moved mesh: ' + node)
            clusters[node] = cluster
        arrow = _front_arrow(cmds, plan, joints['Root'])
        cmds.addAttr(joints['Root'], longName=_RIG_OPTIONS_ATTRIBUTE, dataType='string')
        cmds.setAttr(joints['Root'] + '.' + _RIG_OPTIONS_ATTRIBUTE,
                     json.dumps({'schema': 1, 'options': asdict(analysis.options)}),
                     type='string')
        if original_selection:
            cmds.select(original_selection, replace=True)
        else:
            cmds.select(clear=True)
        result = BuiltRig(joints['Root'], joints, clusters, arrow, analysis)
    except BaseException:
        failed = True
        raise
    finally:
        cmds.undoInfo(closeChunk=True)
        if failed:
            cmds.undo()
    return result
