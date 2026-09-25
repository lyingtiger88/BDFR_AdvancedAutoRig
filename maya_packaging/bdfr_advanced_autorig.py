"""Maya plug-in entry point. The installed module supplies the actual rigging."""

import maya.api.OpenMaya as om
from maya import cmds

_COMMAND = 'bdfrAutoRig'
_MENU = 'BDFR_AutoRig_Menu'


class ShowAutoRig(om.MPxCommand):
    def doIt(self, args):
        from maya_autorig.ui import show
        show()


def _creator():
    return ShowAutoRig()


def initializePlugin(obj):
    plugin = om.MFnPlugin(obj, 'BDFR', '0.1.0', 'Any')
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
    if cmds.menu(_MENU, exists=True):
        cmds.deleteUI(_MENU)
    from maya_autorig.ui import close
    close()
    om.MFnPlugin(obj).deregisterCommand(_COMMAND)
