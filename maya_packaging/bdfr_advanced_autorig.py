"""Maya plug-in entry point. The installed module supplies the actual rigging."""

from pathlib import Path
import maya.OpenMayaMPx as ommpx
from maya import cmds

_COMMAND = 'bdfrAutoRig'
_MENU = 'BDFR_AutoRig_Menu'
_SHELF = 'Rigging'
_SHELF_BUTTON = 'BDFR_AutoRig_ShelfButton'
_ICON_FILE = Path(__file__).resolve().parents[1] / 'icons' / 'BDFR_AutoRig_64.png'
if not _ICON_FILE.is_file():  # Running directly from the source tree.
    _ICON_FILE = Path(__file__).resolve().parent / 'icons' / 'BDFR_AutoRig_64.png'
_ICON = str(_ICON_FILE)


def _add_shelf_button():
    if not cmds.shelfLayout(_SHELF, exists=True):
        return
    if cmds.shelfButton(_SHELF_BUTTON, exists=True):
        cmds.deleteUI(_SHELF_BUTTON, control=True)
    cmds.shelfButton(_SHELF_BUTTON, parent=_SHELF, image1=_ICON,
                     label='BDFR AutoRig', annotation='Open BDFR Advanced AutoRig',
                     sourceType='python', command='from maya import cmds; cmds.bdfrAutoRig()')


class ShowAutoRig(ommpx.MPxCommand):
    def doIt(self, args):
        from maya_autorig.ui import show
        show()


def _creator():
    return ommpx.asMPxPtr(ShowAutoRig())


def initializePlugin(obj):
    plugin = ommpx.MFnPlugin(obj, 'BDFR', '0.1.2', 'Any')
    plugin.registerCommand(_COMMAND, _creator)
    if not cmds.about(batch=True):
        try:
            if cmds.menu(_MENU, exists=True):
                cmds.deleteUI(_MENU)
            cmds.menu(_MENU, label='BDFR AutoRig', parent='MayaWindow', tearOff=False)
            cmds.menuItem(label='Open Vehicle AutoRig', parent=_MENU,
                          image=_ICON, command=lambda *_: cmds.bdfrAutoRig())
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
