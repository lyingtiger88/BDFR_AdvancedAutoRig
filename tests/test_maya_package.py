"""Verify the downloadable Maya ZIP installs and resolves the Python core."""

import os
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from maya_packaging.build import FILES, build_zip
from maya_packaging.install import install


class FakeCmds:
    def __init__(self, root):
        self.root = root

    def internalVar(self, userAppDir=False):
        assert userAppDir
        return str(self.root)

    def about(self, batch=False):
        assert batch
        return True


class MayaPackageTests(unittest.TestCase):
    def test_plugin_registers_with_legacy_mobject_passed_by_maya(self):
        # Maya's initializePlugin argument is an API 1.0 MObject. API 2.0's
        # MFnPlugin rejects it with "argument 1 must be OpenMaya.MObject".
        class LegacyMObject:
            pass

        registrations = []

        class MFnPlugin:
            def __init__(self, obj, *details):
                if not isinstance(obj, LegacyMObject):
                    raise TypeError('argument 1 must be OpenMaya.MObject, not MObject')
                self.obj = obj
                if details:
                    self.details = details

            def registerCommand(self, name, creator):
                registrations.append((name, creator()))

            def deregisterCommand(self, name):
                registrations.append(('removed', name))

        ommpx = types.ModuleType('maya.OpenMayaMPx')
        ommpx.MPxCommand = type('MPxCommand', (), {})
        ommpx.MFnPlugin = MFnPlugin
        ommpx.asMPxPtr = lambda command: ('Maya command pointer', command)
        maya = types.ModuleType('maya')
        maya.__path__ = []
        maya.OpenMayaMPx = ommpx
        maya.cmds = FakeCmds(None)
        source = Path(__file__).resolve().parents[1] / 'maya_packaging' / 'bdfr_advanced_autorig.py'
        spec = importlib.util.spec_from_file_location('bdfr_advanced_autorig_test', source)
        plugin = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'maya': maya, 'maya.OpenMayaMPx': ommpx}):
            spec.loader.exec_module(plugin)
            obj = LegacyMObject()
            plugin.initializePlugin(obj)
            self.assertEqual(registrations[0][0], 'bdfrAutoRig')
            self.assertIsInstance(registrations[0][1][1], plugin.ShowAutoRig)
            plugin.uninitializePlugin(obj)
        self.assertEqual(registrations[-1], ('removed', 'bdfrAutoRig'))

    def test_zip_installs_and_imports_without_repo_path(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            zip_path = build_zip(root / 'maya.zip')
            with ZipFile(zip_path) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(set(archive.namelist()), set(FILES))
                for name, source in FILES.items():
                    self.assertEqual(archive.read(name), source.read_bytes())
                archive.extractall(root / 'download')
            cmds = FakeCmds(root / 'maya_user')
            target = install(source=root / 'download', cmds=cmds)
            mod = (root / 'maya_user' / 'modules' / 'BDFR_AdvancedAutoRig.mod').read_text()
            self.assertIn('./BDFR_AdvancedAutoRig', mod)
            self.assertTrue((target / 'plug-ins' / 'bdfr_advanced_autorig.py').is_file())
            scripts = target / 'scripts'
            env = os.environ.copy()
            env['PYTHONPATH'] = str(scripts)
            result = subprocess.run([sys.executable, '-c',
                                     'from maya_autorig import Options, plan_rig; '
                                     'assert Options(front_wheels=2, rear_wheels=4).mode == "SIMPLE"'],
                                    cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_reinstall_and_incomplete_extract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with ZipFile(build_zip(root / 'maya.zip')) as archive:
                archive.extractall(root / 'download')
            cmds = FakeCmds(root / 'maya_user')
            first = install(source=root / 'download', cmds=cmds)
            self.assertEqual(first, install(source=root / 'download', cmds=cmds))
            with self.assertRaisesRegex(ValueError, 'Extract the entire Maya ZIP'):
                install(source=root, cmds=cmds)
            self.assertTrue((first / 'scripts' / 'maya_autorig' / 'core.py').is_file())


if __name__ == '__main__':
    unittest.main()
