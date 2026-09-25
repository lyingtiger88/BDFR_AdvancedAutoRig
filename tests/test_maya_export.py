"""Test the Maya FBX adapter without installing or mocking the Maya package."""

import copy
from math import cos, radians, sin
import os
import tempfile
import unittest

from maya_autorig import (BuiltRig, ExportOptions, Options, Part, analyze,
                          export_game_fbx, forward_correction)


def converted_forward(opts, engine):
    source = [opts.forward_sign if a == opts.forward_axis else 0 for a in 'XYZ']
    angle = radians(forward_correction(opts, engine))
    if opts.up_axis == 'Y':
        x, y, z = source
        source = [cos(angle)*x + sin(angle)*z, y,
                  -sin(angle)*x + cos(angle)*z]
    else:
        x, y, z = source
        source = [cos(angle)*x - sin(angle)*y,
                  sin(angle)*x + cos(angle)*y, z]
    if opts.up_axis == 'Y' and engine == 'UNREAL':
        x, y, z = source
        source = [x, -z, y]
    elif opts.up_axis == 'Z' and engine == 'UNITY':
        x, y, z = source
        source = [x, z, -y]
    return source


class FakeMel:
    def __init__(self):
        self.settings = dict(FBXExportUpAxis='y', FBXExportAxisConversionMethod='none',
                             FBXExportBakeComplexStart=1, FBXExportBakeComplexEnd=100,
                             FBXExportBakeComplexStep=1, FBXExportBakeComplexAnimation=False,
                             FBXExportInputConnections=True, FBXExportSkins=False,
                             FBXExportAnimationOnly=True, FBXExportIncludeChildren=False)
        self.initial = self.settings.copy()
        self.calls = []

    def eval(self, command):
        self.calls.append(command)
        name, *args = command.rstrip(';').split()
        if args == ['-q']:
            return self.settings[name]
        if args[0] == '-v':
            value = args[1]
            if value in ('true', 'false'):
                value = value == 'true'
            elif name in ('FBXExportBakeComplexStart', 'FBXExportBakeComplexEnd',
                          'FBXExportBakeComplexStep'):
                value = int(value)
        else:
            value = args[0]
        self.settings[name] = value


class FakeCmds:
    def __init__(self, axis='Y', fail=False):
        self.axis = axis
        self.fail = fail
        self.plugin_loaded = False
        self.selection = ['|car']
        self.time = 8
        self.nodes = {'|car', '|Rig', '|Rig|Body', '|Rig|Wheel', '|Rig|BDFR_FRONT'}
        self.rotations = {}
        self.group_name = None
        self.bakes = []
        self.exports = []
        self.undo_count = 0
        self.snap = None
        self.chunk = False

    def upAxis(self, **kwargs):
        return self.axis.lower()

    def undoInfo(self, **kwargs):
        if kwargs.get('query'):
            return True
        if kwargs.get('openChunk'):
            self.snap = (self.nodes.copy(), self.selection.copy(),
                         copy.deepcopy(self.rotations), self.time)
            self.chunk = True
        if kwargs.get('closeChunk'):
            self.chunk = False

    def undo(self):
        assert not self.chunk
        self.nodes, self.selection, self.rotations, self.time = self.snap
        self.undo_count += 1

    def objExists(self, name):
        return name in self.nodes

    def playbackOptions(self, **kwargs):
        return 1 if kwargs.get('minTime') else 24

    def pluginInfo(self, *args, **kwargs):
        return self.plugin_loaded

    def loadPlugin(self, *args, **kwargs):
        self.plugin_loaded = True

    def ls(self, *args, **kwargs):
        if kwargs.get('selection'):
            return self.selection.copy()
        return list(args)

    def currentTime(self, value=None, **kwargs):
        if kwargs.get('query'):
            return self.time
        self.time = value

    def group(self, **kwargs):
        self.group_name = '|BDFR_EXPORT_ORIENT'
        self.nodes.add(self.group_name)
        return self.group_name

    def parent(self, child, parent, **kwargs):
        assert child == '|Rig' and kwargs.get('absolute')
        self.nodes.add(parent + '|Rig')

    def setAttr(self, name, value):
        self.rotations[name] = value

    def delete(self, name):
        self.nodes.remove(name)

    def listRelatives(self, *args, **kwargs):
        return [self.group_name + '|Rig', self.group_name + '|Rig|Body',
                self.group_name + '|Rig|Wheel']

    def bakeResults(self, joints, **kwargs):
        self.bakes.append((tuple(joints), kwargs))
        if self.fail == 'bake':
            raise RuntimeError('bake failed')

    def select(self, nodes=None, **kwargs):
        self.selection = [] if kwargs.get('clear') else list(nodes)

    def file(self, path, **kwargs):
        self.exports.append((path, self.selection.copy(), kwargs))
        if self.fail == 'export':
            raise RuntimeError('FBX failed')
        with open(path, 'wb') as stream:
            stream.write(b'FAKE-FBX-ONLY-FOR-CONTRACT-TEST')


class MayaExportTests(unittest.TestCase):
    def rig(self, axis='Y', forward=None, sign=1):
        opts = Options(up_axis=axis, forward_axis=forward or ('Z' if axis == 'Y' else 'Y'),
                       forward_sign=sign)
        analysis = analyze((Part('|car', (0, 0, 0), (1, 2, 3), 100, kind='BODY'),), opts)
        return BuiltRig('|Rig', {'Root': '|Rig', 'Body': '|Rig|Body',
                                  'Wheel': '|Rig|Wheel'}, {'|car': 'skin1'},
                        '|Rig|BDFR_FRONT', analysis)

    def test_all_forward_up_combinations(self):
        for up in ('Y', 'Z'):
            for forward in (('X', 'Z') if up == 'Y' else ('X', 'Y')):
                for sign in (-1, 1):
                    for engine, expected in (('UNREAL', (1, 0, 0)),
                                             ('UNITY', (0, 0, 1))):
                        with self.subTest(up=up, forward=forward, sign=sign, engine=engine):
                            opts = Options(up_axis=up, forward_axis=forward, forward_sign=sign)
                            actual = converted_forward(opts, engine)
                            for a, e in zip(actual, expected):
                                self.assertAlmostEqual(a, e)

    def test_bake_and_scene_cleanup(self):
        for engine in ('UNREAL', 'UNITY'):
            with self.subTest(engine=engine), tempfile.TemporaryDirectory() as directory:
                cmds, mel = FakeCmds(), FakeMel()
                before = (cmds.nodes.copy(), cmds.selection.copy(), cmds.time)
                path = os.path.join(directory, 'vehicle.fbx')
                result = export_game_fbx(self.rig(), path, ExportOptions(
                    engine=engine, start=3, end=9, step=2), cmds, mel)
                self.assertEqual((result.up_axis, result.forward_axis),
                                 ('Z', 'X') if engine == 'UNREAL' else ('Y', 'Z'))
                self.assertEqual(result.frame_range, (3, 9))
                self.assertEqual(len(cmds.bakes), 1)
                self.assertEqual(cmds.bakes[0][1]['time'], (3, 9))
                self.assertEqual(cmds.bakes[0][1]['sampleBy'], 2)
                self.assertEqual(cmds.exports[0][1], ['|BDFR_EXPORT_ORIENT', '|car'])
                self.assertEqual((cmds.nodes, cmds.selection, cmds.time), before)
                self.assertEqual(cmds.undo_count, 1)
                self.assertEqual(mel.settings, mel.initial)
                self.assertTrue(os.path.getsize(path))
                self.assertEqual(os.listdir(directory), ['vehicle.fbx'])

    def test_no_bake_and_existing_file_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            cmds, mel = FakeCmds(), FakeMel()
            path = os.path.join(directory, 'car.fbx')
            with open(path, 'wb') as stream:
                stream.write(b'ORIGINAL')
            with self.assertRaises(FileExistsError):
                export_game_fbx(self.rig(), path, cmds=cmds, mel=mel)
            self.assertFalse(cmds.exports)
            with open(path, 'rb') as stream:
                self.assertEqual(stream.read(), b'ORIGINAL')
            result = export_game_fbx(self.rig(), path, ExportOptions(
                engine='UNITY', bake=False, overwrite=True), cmds, mel)
            self.assertEqual(result.frame_range, (1, 24))
            self.assertFalse(cmds.bakes)
            self.assertIn('FBXExportBakeComplexAnimation -v false;', mel.calls)
            self.assertEqual(mel.settings, mel.initial)

    def test_export_and_bake_errors_undo_and_remove_partial_file(self):
        for failure in ('bake', 'export'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                cmds, mel = FakeCmds(fail=failure), FakeMel()
                path = os.path.join(directory, 'vehicle.fbx')
                with self.assertRaisesRegex(RuntimeError, 'failed'):
                    export_game_fbx(self.rig(), path, cmds=cmds, mel=mel)
                self.assertEqual(os.listdir(directory), [])
                self.assertEqual(cmds.nodes, {'|car', '|Rig', '|Rig|Body', '|Rig|Wheel',
                                              '|Rig|BDFR_FRONT'})
                self.assertEqual(cmds.selection, ['|car'])
                self.assertEqual(cmds.undo_count, 1)
                self.assertEqual(mel.settings, mel.initial)

    def test_validation(self):
        for kwargs in ({'engine': 'OTHER'}, {'step': 0}, {'start': 1},
                       {'start': 10, 'end': 1}):
            with self.assertRaises(ValueError):
                ExportOptions(**kwargs)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'up axis changed'):
                export_game_fbx(self.rig(), os.path.join(directory, 'a.fbx'),
                                cmds=FakeCmds(axis='Z'), mel=FakeMel())


if __name__ == '__main__':
    unittest.main()
