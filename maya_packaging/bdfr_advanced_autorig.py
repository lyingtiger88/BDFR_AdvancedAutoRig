"""Maya plug-in entry point. The installed module supplies the actual rigging."""

import maya.OpenMayaMPx as ommpx
from maya import cmds

_COMMAND = 'bdfrAutoRig'
_MENU = 'BDFR_AutoRig_Menu'


class ShowAutoRig(ommpx.MPxCommand):
    def doIt(self, args):
        from maya_autorig.ui import show
        show()


def _creator():
    return ommpx.asMPxPtr(ShowAutoRig())


def initializePlugin(obj):
    plugin = ommpx.MFnPlugin(obj, 'BDFR', '0.1.1', 'Any')
    plugin.registerCommand(_COMMAND, _creator)
    if not cmds.about(batch=True):
        try:
            if cmds.menu(_MENU, exists=True):
                cmds.deleteUI(_MENU)
            cmds.menu(_MENU, label='BDFR AutoRig', parent='MayaWindow', tearOff=False)
            cmds.menuItem(label='Open Vehicle AutoRig', parent=_MENU,
                          command=lambda *_: cmds.bdfrAutoRig())
        except BaseException:
            plugin.deregisterCommand(_COMMAND)
            raise


def uninitializePlugin(obj):
    if not cmds.about(batch=True):
        if cmds.menu(_MENU, exists=True):
            cmds.deleteUI(_MENU)
        from maya_autorig.ui import close
        close()
    ommpx.MFnPlugin(obj).deregisterCommand(_COMMAND)
