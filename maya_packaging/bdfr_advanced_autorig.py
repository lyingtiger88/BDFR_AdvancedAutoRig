"""Maya plug-in entry point. The installed module supplies the actual rigging."""

from pathlib import Path
import maya.OpenMayaMPx as ommpx
from maya import cmds

_COMMAND = 'bdfrAutoRig'
_MENU = 'BDFR_AutoRig_Menu'
_SHELF = 'Rigging'
_SHELF_BUTTON = 'BDFR_AutoRig_ShelfButton'
_MODULE = 'BDFR_AdvancedAutoRig'


def _icon_path():
    # Maya may execute plug-ins without setting __file__. Resolve the module
    # through Maya instead, after the plug-in has been registered.
    try:
        module_path = cmds.moduleInfo(moduleName=_MODULE, path=True)
    except (RuntimeError, ValueError):
        return None
    if isinstance(module_path, (list, tuple)):
        module_path = module_path[0] if module_path else None
    icon = Path(module_path) / 'icons' / 'BDFR_AutoRig_64.png' if module_path else None
    return str(icon) if icon and icon.is_file() else None


def _add_shelf_button():
    if not cmds.shelfLayout(_SHELF, exists=True):
        return
    if cmds.shelfButton(_SHELF_BUTTON, exists=True):
        cmds.deleteUI(_SHELF_BUTTON, control=True)
    button = dict(parent=_SHELF, label='BDFR AutoRig',
                  annotation='Open BDFR Advanced AutoRig',
                  sourceType='python', command='from maya import cmds; cmds.bdfrAutoRig()')
    icon = _icon_path()
    if icon:
        button['image1'] = icon
    cmds.shelfButton(_SHELF_BUTTON, **button)


class ShowAutoRig(ommpx.MPxCommand):
    def doIt(self, args):
        from maya_autorig.ui import show
        show()


def _creator():
    return ommpx.asMPxPtr(ShowAutoRig())


def initializePlugin(obj):
    plugin = ommpx.MFnPlugin(obj, 'BDFR', '0.1.3', 'Any')
    plugin.registerCommand(_COMMAND, _creator)
    if not cmds.about(batch=True):
        try:
            if cmds.menu(_MENU, exists=True):
                cmds.deleteUI(_MENU)
            cmds.menu(_MENU, label='BDFR AutoRig', parent='MayaWindow', tearOff=False)
            item = dict(label='Open Vehicle AutoRig', parent=_MENU,
                        command=lambda *_: cmds.bdfrAutoRig())
            icon = _icon_path()
            if icon:
                item['image'] = icon
            cmds.menuItem(**item)
            _add_shelf_button()
        except BaseException:
            if cmds.shelfButton(_SHELF_BUTTON, exists=True):
                cmds.deleteUI(_SHELF_BUTTON, control=True)
            if cmds.menu(_MENU, exists=True):
                cmds.deleteUI(_MENU)
            plugin.deregisterCommand(_COMMAND)
            raise


def uninitializePlugin(obj):
    if not cmds.about(batch=True):
        if cmds.shelfButton(_SHELF_BUTTON, exists=True):
            cmds.deleteUI(_SHELF_BUTTON, control=True)
        if cmds.menu(_MENU, exists=True):
            cmds.deleteUI(_MENU)
        from maya_autorig.ui import close
        close()
    ommpx.MFnPlugin(obj).deregisterCommand(_COMMAND)
