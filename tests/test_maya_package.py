"""Verify the downloadable Maya ZIP installs and resolves the Python core."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
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
