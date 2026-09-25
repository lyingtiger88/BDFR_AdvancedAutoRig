"""UI state and export recovery contracts without requiring a Maya installation."""

import sys
import types
import unittest
from unittest.mock import patch

from maya_autorig import analyze_selection, build_rig
from maya_autorig import ui
from test_maya_scene import FakeCmds


class WindowCmds:
    def __init__(self):
        self.open = False
        self.shown = 0

    def window(self, name, exists=False):
        return self.open

    def showWindow(self, name):
        self.shown += 1


class ExportCmds(FakeCmds):
    def fileDialog2(self, **kwargs):
        return ['/tmp/test-existing-rig.fbx']

    def optionMenu(self, name, query=False, value=False):
        return 'UNREAL'

    def intField(self, name, query=False, value=False):
        return {'start': 1, 'end': 120}[name]

    def checkBox(self, name, query=False, value=False):
        return name == 'bake'

    def text(self, name, edit=False, label=''):
        self.status_message = label

    def warning(self, message):
        self.last_warning = message


class MayaWindowTests(unittest.TestCase):
    def test_reopening_tool_does_not_discard_built_rig(self):
        cmds = WindowCmds()
        maya = types.ModuleType('maya')
        maya.cmds = cmds
        old_active = ui._active
        ui._active = None
        try:
            with patch.dict(sys.modules, {'maya': maya}), patch.object(
                    ui._RigWindow, 'create', autospec=True) as create:
                ui.show()
                original = ui._active
                original.built = 'kept rig'
                cmds.open = True
                ui.show()
                self.assertIs(ui._active, original)
                self.assertEqual(ui._active.built, 'kept rig')
                self.assertEqual(create.call_count, 1)
                self.assertEqual(cmds.shown, 1)
        finally:
            ui._active = old_active

    def test_export_recovers_previously_built_scene_rig(self):
        cmds = ExportCmds()
        built = build_rig(analyze_selection(cmds=cmds), cmds=cmds)
        cmds.selected = [built.root]
        window = ui._RigWindow(cmds)
        window.engine, window.start, window.end = 'engine', 'start', 'end'
        window.bake, window.overwrite, window.status = 'bake', 'overwrite', 'status'
        captured = []

        def exported(recovered, path, opts, cmds=None):
            captured.append((recovered, path, opts))
            return types.SimpleNamespace(path=path)

        with patch.object(ui, 'export_game_fbx', side_effect=exported):
            window.export()
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][0].root, built.root)
        self.assertEqual(captured[0][0].skin_clusters, built.skin_clusters)
        self.assertEqual(captured[0][1], '/tmp/test-existing-rig.fbx')
        self.assertEqual(cmds.status_message, 'Exported: /tmp/test-existing-rig.fbx')


if __name__ == '__main__':
    unittest.main()
