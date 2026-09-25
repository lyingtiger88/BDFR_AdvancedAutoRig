"""Contract tests for the Maya adapter using a narrow fake cmds implementation."""

import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maya_autorig import (Options, analyze_selection, build_rig,
                          drivecore_wheel_bones)


class FakeCmds:
    def __init__(self, up='z'):
        self.up = up
        self.meshes = {
            '|Vehicle|Chassis': ((-1, -1.5, .6, 1, 1.5, 1.4) if up == 'z'
                                else (-1, .6, -1.5, 1, 1.4, 1.5)),
            '|Vehicle|Wheel_FL': ((-.95, .8, 0, -.65, 1.4, .7) if up == 'z'
                                 else (-.95, 0, .8, -.65, .7, 1.4)),
            '|Vehicle|Wheel_FR': ((.65, .8, 0, .95, 1.4, .7) if up == 'z'
                                 else (.65, 0, .8, .95, .7, 1.4)),
            '|Vehicle|Wheel_RL': ((-.95, -1.4, 0, -.65, -.8, .7) if up == 'z'
                                 else (-.95, 0, -1.4, -.65, .7, -.8)),
            '|Vehicle|Wheel_RR': ((.65, -1.4, 0, .95, -.8, .7) if up == 'z'
                                 else (.65, 0, -1.4, .95, .7, -.8)),
        }
        self.selected = ['|Vehicle']
        self.joints = {}
        self.curves = {}
        self.clusters = {}
        self.skin_calls = []
        self.fail_bind = None
        self.rename_wheel = False
        self.skin_string = False
        self.shells = {key: 1 for key in self.meshes}
        self.undo_enabled = True
        self.undo_count = 0
        self.snapshot = None
        self.attrs = {}

    def upAxis(self, query=False, axis=False):
        assert query and axis
        return self.up

    def objExists(self, node):
        return (node in self.meshes or node == '|Vehicle' or node in self.joints or
                node in self.curves or node.endswith('Shape') and node[:-5] in self.meshes)

    def nodeType(self, node):
        return 'mesh' if node.endswith('Shape') else 'joint' if node in self.joints else 'transform'

    def ls(self, items=None, selection=False, long=False, objectsOnly=False, type=None):
        if type == 'skinCluster':
            return [item for item in (items or []) if item in self.clusters]
        if selection:
            return list(self.selected)
        if items is None:
            return []
        return [items] if isinstance(items, str) else list(items)

    def listRelatives(self, node, parent=False, allParents=False, shapes=False,
                      allDescendents=False, fullPath=False, type=None, noIntermediate=False):
        if parent or allParents:
            return [node[:-5]] if node.endswith('Shape') else []
        if shapes:
            return [node + 'Shape'] if node in self.meshes else []
        if allDescendents and node == '|Vehicle':
            return list(self.meshes)
        return []

    def referenceQuery(self, node, isNodeReferenced=False):
        return False

    def lockNode(self, node, query=False, lock=False):
        return [False]

    def listHistory(self, node, pruneDagObjects=False):
        return [name for name, (_, mesh) in self.clusters.items() if mesh == node]

    def polyEvaluate(self, node, vertex=False, shell=False):
        return 8 if vertex else self.shells[node]

    def exactWorldBoundingBox(self, node):
        return list(self.meshes[node])

    def undoInfo(self, query=False, state=False, openChunk=False, closeChunk=False,
                 chunkName=None):
        if query:
            return self.undo_enabled
        if openChunk:
            self.snapshot = copy.deepcopy((self.joints, self.curves, self.clusters,
                                           self.selected, self.attrs, self.skin_calls))
        if closeChunk:
            assert self.snapshot is not None

    def undo(self):
        (self.joints, self.curves, self.clusters, self.selected, self.attrs,
         self.skin_calls) = self.snapshot
        self.snapshot = None
        self.undo_count += 1

    def createNode(self, kind, name=None, parent=None):
        assert kind == 'joint'
        if self.rename_wheel and name == 'wheel_fl':
            name = 'wheel_fl1'
        node = (parent + '|' if parent else '|') + name
        self.joints[node] = {'parent': parent, 'position': None}
        return node

    def xform(self, node, worldSpace=False, translation=None):
        assert worldSpace
        if node in self.joints:
            self.joints[node]['position'] = tuple(translation)
        else:
            self.curves[node]['position'] = tuple(translation)

    def skinCluster(self, joint, mesh, name=None, **flags):
        if mesh == self.fail_bind:
            raise RuntimeError('Injected Maya skin failure')
        assert joint in self.joints and flags['maximumInfluences'] == 1
        cluster = name + str(len(self.clusters)+1)
        self.clusters[cluster] = (joint, mesh)
        return cluster if self.skin_string else [cluster]

    def skinPercent(self, cluster, vertices, transformValue=None, normalize=False,
                    zeroRemainingInfluences=False, query=False, transform=None):
        assert cluster in self.clusters
        if query:
            return 1.0 if transform == self.clusters[cluster][0] else 0.0
        assert transformValue == [(self.clusters[cluster][0], 1.0)]
        assert vertices.endswith('.vtx[0:7]') and normalize and zeroRemainingInfluences
        self.skin_calls.append((cluster, vertices))

    def curve(self, name=None, degree=None, point=None):
        assert degree == 1 and len(point) == 5
        node = '|' + name
        self.curves[node] = {'points': point}
        return node

    def setAttr(self, attribute, value):
        self.attrs[attribute] = value

    def parent(self, node, root):
        self.curves[node]['parent'] = root
        return [node]

    def select(self, nodes=None, replace=False, clear=False):
        self.selected = [] if clear else list(nodes)


class AdapterTests(unittest.TestCase):
    def test_build_rigid_weights_and_front_arrow(self):
        cmds = FakeCmds()
        analysis = analyze_selection(cmds=cmds)
        self.assertEqual(len(analysis.parts), 5)
        result = build_rig(analysis, cmds=cmds)
        self.assertEqual(len(result.skin_clusters), 5)
        self.assertEqual(len(cmds.skin_calls), 5)
        self.assertEqual(len(result.joints), 8)
        expected = {slot: 'wheel_' + slot.lower() for slot in ('FL', 'FR', 'RL', 'RR')}
        self.assertEqual({slot: path.rsplit('|', 1)[-1]
                          for slot, path in drivecore_wheel_bones(result).items()}, expected)
        for mesh, slot in (('Wheel_FL', 'FL'), ('Wheel_FR', 'FR'),
                           ('Wheel_RL', 'RL'), ('Wheel_RR', 'RR')):
            bound = cmds.clusters[result.skin_clusters['|Vehicle|' + mesh]][0]
            self.assertEqual(bound, result.joints['Wheel.' + slot])
        self.assertEqual(cmds.selected, ['|Vehicle'])
        self.assertEqual(cmds.curves[result.front_arrow]['parent'], result.root)
        self.assertEqual(cmds.undo_count, 0)
        with self.assertRaisesRegex(ValueError, 'existing skinCluster'):
            build_rig(analysis, cmds=cmds)

    def test_y_up_scene_and_direction(self):
        cmds = FakeCmds(up='y')
        cmds.skin_string = True  # Maya command wrappers may return a string or a list.
        analysis = analyze_selection(cmds=cmds)
        self.assertEqual(analysis.options.up_axis, 'Y')
        self.assertEqual(analysis.options.forward_axis, 'Z')
        result = build_rig(analysis, cmds=cmds)
        self.assertEqual({slot: node.rsplit('|', 1)[-1]
                          for slot, node in drivecore_wheel_bones(result).items()},
                         {slot: 'wheel_' + slot.lower() for slot in ('FL', 'FR', 'RL', 'RR')})
        self.assertIn('|BDFR_FRONT.rotateY', cmds.attrs)
        self.assertGreater(cmds.curves[result.front_arrow]['position'][2], 0)
        self.assertGreater(cmds.curves[result.front_arrow]['position'][1], 0)

    def test_advanced_keeps_steering_and_suspension_names(self):
        cmds = FakeCmds()
        result = build_rig(analyze_selection(Options(mode='ADVANCED', bone_count=16),
                                             cmds=cmds), cmds=cmds)
        self.assertEqual(result.joints['Wheel.FL'].rsplit('|', 1)[-1], 'wheel_fl')
        self.assertEqual(result.joints['Steer.FL'].rsplit('|', 1)[-1], 'BDFR_Steer_FL')
        self.assertEqual(result.joints['Suspension.FL.01'].rsplit('|', 1)[-1],
                         'BDFR_Suspension_FL_01')

    def test_airplane_wheels_keep_existing_names(self):
        cmds = FakeCmds()
        result = build_rig(analyze_selection(Options(vehicle='AIRPLANE'), cmds=cmds),
                           cmds=cmds)
        self.assertEqual(result.joints['Wheel.FL'].rsplit('|', 1)[-1], 'BDFR_Wheel_FL')
        with self.assertRaisesRegex(ValueError, 'car or four-wheel truck'):
            drivecore_wheel_bones(result)

    def test_reverse_and_x_front(self):
        cmds = FakeCmds()
        analysis = analyze_selection(Options(forward_axis='X', forward_sign=-1), cmds=cmds)
        result = build_rig(analysis, cmds=cmds)
        self.assertEqual(cmds.attrs['|BDFR_FRONT.rotateZ'], 90)
        self.assertLess(cmds.curves[result.front_arrow]['position'][0], 0)

    def test_rollback_and_preflight(self):
        cmds = FakeCmds()
        analysis = analyze_selection(cmds=cmds)
        cmds.fail_bind = '|Vehicle|Wheel_RL'
        with self.assertRaisesRegex(RuntimeError, 'Injected'):
            build_rig(analysis, cmds=cmds)
        self.assertEqual(cmds.undo_count, 1)
        self.assertFalse(cmds.joints or cmds.clusters or cmds.curves)
        self.assertEqual(cmds.selected, ['|Vehicle'])
        cmds.fail_bind = None
        cmds.meshes['|Vehicle|Wheel_FL'] = (-.95, .8, 0, -.65, 1.5, .7)
        with self.assertRaisesRegex(ValueError, 'changed since analysis'):
            build_rig(analysis, cmds=cmds)
        self.assertEqual(cmds.undo_count, 1)

    def test_drivecore_rejects_missing_wheel_or_renamed_joint(self):
        cmds = FakeCmds()
        analysis = analyze_selection(cmds=cmds)
        cmds.rename_wheel = True
        with self.assertRaisesRegex(ValueError, 'Maya renamed joint wheel_fl'):
            build_rig(analysis, cmds=cmds)
        self.assertEqual(cmds.undo_count, 1)
        self.assertFalse(cmds.joints or cmds.clusters)
        cmds.rename_wheel = False
        built = build_rig(analysis, cmds=cmds)
        del built.joints['Wheel.RR']
        with self.assertRaisesRegex(ValueError, 'exactly FL/FR/RL/RR'):
            drivecore_wheel_bones(built)

    def test_simple_six_wheel_build_and_mismatch_before_edits(self):
        cmds = FakeCmds()
        cmds.meshes['|Vehicle|Wheel_ML'] = (-.95, -2.5, 0, -.65, -1.9, .7)
        cmds.meshes['|Vehicle|Wheel_MR'] = (.65, -2.5, 0, .95, -1.9, .7)
        cmds.shells.update({node: 1 for node in ('|Vehicle|Wheel_ML', '|Vehicle|Wheel_MR')})
        bad = analyze_selection(Options(front_wheels=2, rear_wheels=2), cmds=cmds)
        with self.assertRaisesRegex(ValueError, 'detected physical wheels'):
            build_rig(bad, cmds=cmds)
        self.assertFalse(cmds.joints or cmds.clusters)
        good = analyze_selection(Options(front_wheels=2, rear_wheels=4), cmds=cmds)
        built = build_rig(good, cmds=cmds)
        self.assertEqual(built.joints['Wheel.RL'].rsplit('|', 1)[-1], 'wheel_rl')
        self.assertEqual(built.joints['Wheel.RL2'].rsplit('|', 1)[-1], 'BDFR_Wheel_RL2')
        self.assertEqual(len(built.skin_clusters), 7)
        with self.assertRaisesRegex(ValueError, 'exactly FL/FR/RL/RR'):
            drivecore_wheel_bones(built)

    def test_reject_unsafe_input_without_writes(self):
        cmds = FakeCmds()
        cmds.shells['|Vehicle|Chassis'] = 2
        with self.assertRaisesRegex(ValueError, 'disconnected shells'):
            analyze_selection(cmds=cmds)
        self.assertFalse(cmds.joints)
        cmds.shells['|Vehicle|Chassis'] = 1
        analysis = analyze_selection(cmds=cmds)
        cmds.undo_enabled = False
        with self.assertRaisesRegex(RuntimeError, 'Enable Maya Undo'):
            build_rig(analysis, cmds=cmds)
        self.assertFalse(cmds.joints)
        with self.assertRaisesRegex(ValueError, 'up_axis differs'):
            analyze_selection(Options(up_axis='Y', forward_axis='Z'), cmds=cmds)


if __name__ == '__main__':
    unittest.main()
