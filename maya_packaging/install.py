"""Drag this extracted file onto Maya's viewport to install BDFR AutoRig."""

from pathlib import Path
import shutil
import sys
import tempfile


MODULE = 'BDFR_AdvancedAutoRig'


def install(source=None, cmds=None):
    if cmds is None:
        from maya import cmds
    source = Path(source or Path(__file__).resolve().parent)
    mod = source / (MODULE + '.mod')
    package = source / MODULE
    if not mod.is_file() or not (package / 'scripts' / 'maya_autorig' / '__init__.py').is_file() or not (
            package / 'plug-ins' / 'bdfr_advanced_autorig.py').is_file():
        raise ValueError('Extract the entire Maya ZIP before running install.py')
    modules = Path(cmds.internalVar(userAppDir=True)) / 'modules'
    modules.mkdir(parents=True, exist_ok=True)
    target = modules / MODULE
    target_mod = modules / mod.name
    with tempfile.TemporaryDirectory(prefix='.bdfr_install_', dir=modules) as tmp:
        stage = Path(tmp)
        shutil.copytree(package, stage / MODULE)
        shutil.copy2(mod, stage / mod.name)
        # Keep previous files until both new items have been staged. On
        # failure, restore the old package and module descriptor.
        old = stage / 'previous'
        old.mkdir()
        moved = []
        try:
            for destination in (target, target_mod):
                if destination.exists():
                    backup = old / destination.name
                    destination.rename(backup)
                    moved.append((destination, backup))
            (stage / MODULE).rename(target)
            (stage / mod.name).rename(target_mod)
        except BaseException:
            if target.exists():
                shutil.rmtree(target)
            if target_mod.exists():
                target_mod.unlink()
            for destination, backup in reversed(moved):
                backup.rename(destination)
            raise
    message = ('BDFR AutoRig installed in:\n' + str(modules) +
               '\n\nRestart Maya, load bdfr_advanced_autorig.py in Plug-in Manager, '
               'then use the Rigging shelf button or BDFR AutoRig menu. If an older version is loaded, '
               'unload it before restarting.')
    if not cmds.about(batch=True):
        cmds.confirmDialog(title='BDFR AutoRig installed', message=message, button=['OK'])
    else:
        print(message)
    return target


def onMayaDroppedPythonFile(*_args):
    install()


if __name__ == '__main__':
    install()
