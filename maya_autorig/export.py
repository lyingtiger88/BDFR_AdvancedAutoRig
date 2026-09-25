"""Non-destructive FBX export of an existing Maya vehicle rig."""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, degrees
import os
import tempfile

from .core import Options
from .scene import BuiltRig, _maya, _scene_up


ENGINE_AXES = {'UNREAL': ('Z', 'X'), 'UNITY': ('Y', 'Z')}
_FBX_SETTINGS = ('FBXExportUpAxis', 'FBXExportAxisConversionMethod',
                 'FBXExportBakeComplexAnimation', 'FBXExportBakeComplexStart',
                 'FBXExportBakeComplexEnd', 'FBXExportBakeComplexStep',
                 'FBXExportInputConnections',
                 'FBXExportSkins', 'FBXExportAnimationOnly',
                 'FBXExportIncludeChildren')


@dataclass(frozen=True)
class ExportOptions:
    engine: str = 'UNREAL'
    start: int | None = None
    end: int | None = None
    step: int = 1
    bake: bool = True
    overwrite: bool = False

    def __post_init__(self):
        if self.engine not in ENGINE_AXES:
            raise ValueError('engine must be UNREAL or UNITY')
        if type(self.step) is not int or self.step < 1:
            raise ValueError('step must be a positive integer')
        if (self.start is None) != (self.end is None):
            raise ValueError('Provide both start and end, or neither')
        if self.start is not None and (type(self.start) is not int or
                                       type(self.end) is not int or self.start > self.end):
            raise ValueError('start and end must be ascending integer frames')


@dataclass(frozen=True)
class ExportResult:
    path: str
    engine: str
    up_axis: str
    forward_axis: str
    correction_degrees: float
    frame_range: tuple[int, int]


def _cross(a, b):
    return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])


def forward_correction(options: Options, engine: str) -> float:
    """Yaw around the Maya up axis before FBX converts its up axis."""
    if engine not in ENGINE_AXES:
        raise ValueError('engine must be UNREAL or UNITY')
    dest_up, dest_forward = ENGINE_AXES[engine]
    source_up = (0, 1, 0) if options.up_axis == 'Y' else (0, 0, 1)
    source_forward = tuple(options.forward_sign if axis == options.forward_axis else 0
                           for axis in 'XYZ')
    # Inverse of Maya FBX's Y<->Z up-axis rotation around world X.
    wanted = (1, 0, 0) if dest_forward == 'X' else (0, 0, 1)
    if options.up_axis != dest_up and dest_forward == 'Z':
        wanted = (0, -1, 0)  # Z-up -> Y-up maps -Y onto +Z.
    dot = sum(a*b for a, b in zip(source_forward, wanted))
    sine = sum(a*b for a, b in zip(_cross(source_forward, wanted), source_up))
    return float(degrees(atan2(sine, dot)))


def _mel_api(mel):
    if mel is not None:
        return mel
    try:
        from maya import mel as maya_mel
    except ImportError as exc:
        raise RuntimeError('Run FBX export inside Autodesk Maya') from exc
    return maya_mel


def _set_fbx(mel, name, value):
    if name in ('FBXExportUpAxis', 'FBXExportAxisConversionMethod'):
        if value not in ('y', 'z', 'none', 'convertAnimation', 'addFbxRoot'):
            raise ValueError('Unexpected FBX export setting: ' + str(value))
        mel.eval(name + ' ' + value + ';')
    elif name in ('FBXExportBakeComplexStart', 'FBXExportBakeComplexEnd',
                  'FBXExportBakeComplexStep'):
        mel.eval(name + ' -v ' + str(int(value)) + ';')
    else:
        mel.eval(name + ' -v ' + ('true' if value else 'false') + ';')


def _restore_fbx(mel, saved):
    for name, value in reversed(tuple(saved.items())):
        _set_fbx(mel, name, value)


def export_game_fbx(built: BuiltRig, path: str | os.PathLike, options: ExportOptions = ExportOptions(),
                    cmds=None, mel=None) -> ExportResult:
    """Bake joints and export meshes+skins in engine axes; undo all scene edits.

    The FBX is atomically installed only after the Maya scene and FBX settings
    have been restored. The visible FRONT curve is excluded from the export.
    """
    cmds = _maya(cmds)
    if built.analysis is None:
        raise ValueError('Rig has no analysis metadata; rebuild with this Maya core')
    if _scene_up(cmds) != built.analysis.options.up_axis:
        raise ValueError('Maya up axis changed since the rig was built')
    if not cmds.undoInfo(query=True, state=True):
        raise RuntimeError('Enable Maya Undo before exporting (required for safe rollback)')
    nodes = (built.root, *built.skin_clusters)
    if not all(cmds.objExists(node) for node in nodes):
        raise ValueError('Rig or skinned mesh was removed; rebuild before exporting')
    destination = os.path.abspath(os.fspath(path))
    if not destination.lower().endswith('.fbx'):
        raise ValueError('Export path must end in .fbx')
    if not os.path.isdir(os.path.dirname(destination)):
        raise ValueError('Export directory does not exist')
    if os.path.exists(destination) and not options.overwrite:
        raise FileExistsError(destination)
    start, end = ((options.start, options.end) if options.start is not None else
                  (int(cmds.playbackOptions(query=True, minTime=True)),
                   int(cmds.playbackOptions(query=True, maxTime=True))))
    if start > end:
        raise ValueError('Playback range is reversed')
    correction = forward_correction(built.analysis.options, options.engine)
    up, forward = ENGINE_AXES[options.engine]
    mel = _mel_api(mel)
    if not cmds.pluginInfo('fbxmaya', query=True, loaded=True):
        cmds.loadPlugin('fbxmaya', quiet=True)
    saved = {}
    temp_path = None
    chunk_open = False
    scene_restored = False
    exported = False
    try:
        for name in _FBX_SETTINGS:
            saved[name] = mel.eval(name + ' -q;')
        _set_fbx(mel, 'FBXExportUpAxis', up.lower())
        _set_fbx(mel, 'FBXExportAxisConversionMethod', 'addFbxRoot')
        for name, value in (('FBXExportBakeComplexStart', start),
                            ('FBXExportBakeComplexEnd', end),
                            ('FBXExportBakeComplexStep', options.step),
                            ('FBXExportBakeComplexAnimation', options.bake),
                            ('FBXExportInputConnections', False),
                            ('FBXExportSkins', True),
                            ('FBXExportAnimationOnly', False),
                            ('FBXExportIncludeChildren', True)):
            _set_fbx(mel, name, value)
        original_selection = cmds.ls(selection=True, long=True, objectsOnly=True) or []
        original_time = cmds.currentTime(query=True)
        cmds.undoInfo(openChunk=True, chunkName='BDFR game FBX export')
        chunk_open = True
        try:
            group = cmds.group(empty=True, name='BDFR_EXPORT_ORIENT')
            group = cmds.ls(group, long=True)[0]
            if cmds.objExists(built.front_arrow):
                cmds.delete(built.front_arrow)  # Viewport helper is not game geometry.
            cmds.parent(built.root, group, absolute=True)
            if abs(correction) > 1e-9:
                cmds.setAttr(group + ('.rotateY' if built.analysis.options.up_axis == 'Y'
                                      else '.rotateZ'), correction)
            joints = cmds.listRelatives(group, allDescendents=True,
                                        type='joint', fullPath=True) or []
            if len(joints) < len(built.joints):
                raise RuntimeError('Some rig joints are missing; cannot bake safely')
            if options.bake:
                cmds.bakeResults(joints, time=(start, end), simulation=True,
                                 sampleBy=options.step,
                                 attribute=('translateX', 'translateY', 'translateZ',
                                            'rotateX', 'rotateY', 'rotateZ',
                                            'scaleX', 'scaleY', 'scaleZ'),
                                 shape=False, preserveOutsideKeys=True)
            cmds.select([group, *built.skin_clusters], replace=True)
            fd, temp_path = tempfile.mkstemp(prefix='.bdfr_', suffix='.fbx',
                                              dir=os.path.dirname(destination))
            os.close(fd)
            os.unlink(temp_path)
            cmds.file(temp_path, force=True, options='v=0;', type='FBX export',
                      exportSelected=True)
            if not os.path.isfile(temp_path) or os.path.getsize(temp_path) == 0:
                raise RuntimeError('FBX exporter did not write a nonempty file')
            exported = True
        finally:
            try:
                cmds.currentTime(original_time)
                if original_selection:
                    cmds.select(original_selection, replace=True)
                else:
                    cmds.select(clear=True)
            finally:
                try:
                    cmds.undoInfo(closeChunk=True)
                    chunk_open = False
                finally:
                    cmds.undo()
                    scene_restored = True
    finally:
        if chunk_open:
            cmds.undoInfo(closeChunk=True)
            cmds.undo()
        try:
            _restore_fbx(mel, saved)
        except BaseException:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)
            raise
        if (not scene_restored or not exported) and temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)
    try:
        if options.overwrite:
            os.replace(temp_path, destination)
        else:
            os.link(temp_path, destination)  # Exclusive: never replace a competing file.
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
    return ExportResult(destination, options.engine, up, forward, correction, (start, end))
