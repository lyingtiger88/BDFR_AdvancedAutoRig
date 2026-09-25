"""Small Maya window for the installable Maya module; no Maya import at module load."""

from .core import Options, plan_rig
from .export import ExportOptions, export_game_fbx
from .scene import analyze_selection, build_rig


_WINDOW = 'BDFR_AdvancedAutoRig_Window'
_active = None


class _RigWindow:
    def __init__(self, cmds):
        self.cmds = cmds
        self.analysis = None
        self.built = None

    def _menu(self, label, items, callback=None):
        flags = {'label': label}
        if callback is not None:
            flags['changeCommand'] = callback
        control = self.cmds.optionMenu(**flags)
        for item in items:
            self.cmds.menuItem(label=item)
        return control

    def create(self):
        c = self.cmds
        if c.window(_WINDOW, exists=True):
            c.deleteUI(_WINDOW)
        c.window(_WINDOW, title='BDFR Advanced AutoRig | Maya', sizeable=True,
                 widthHeight=(400, 650))
        c.columnLayout(adjustableColumn=True, rowSpacing=6)
        c.text(label='Select the vehicle meshes or their parent group in the Outliner.',
               align='left')
        self.vehicle = self._menu('Vehicle', ('CAR', 'TRUCK', 'MOTORCYCLE',
                                             'BICYCLE', 'AIRPLANE'))
        self.mode = self._menu('Rig mode', ('SIMPLE', 'ADVANCED'))
        up = c.upAxis(query=True, axis=True).upper()
        horizontal = 'Z' if up == 'Y' else 'Y'
        self.forward = self._menu('Front direction', ('+' + horizontal, '-' + horizontal,
                                                       '+X', '-X'))
        c.separator(style='in')
        c.text(label='Simple | Physical wheel counts (Auto uses detection)', align='left')
        self.auto_front = c.checkBox(label='Auto front wheels', value=True)
        self.front = c.intField(value=2, minValue=0, maxValue=32)
        self.auto_rear = c.checkBox(label='Auto rear wheels', value=True)
        self.rear = c.intField(value=2, minValue=0, maxValue=32)
        c.separator(style='in')
        c.text(label='Advanced | Target joint count', align='left')
        self.bones = c.intField(value=16, minValue=2, maxValue=128)
        c.separator(style='in')
        c.button(label='1. Analyze selected vehicle', command=self.analyze)
        self.parts = c.textScrollList(height=105, allowMultiSelection=False)
        c.button(label='2. Build rig and skin meshes', command=self.build)
        c.separator(style='in')
        self.engine = self._menu('Game engine', ('UNREAL', 'UNITY'))
        self.bake = c.checkBox(label='Bake animation for export', value=True)
        self.start = c.intField(value=int(c.playbackOptions(query=True, minTime=True)))
        self.end = c.intField(value=int(c.playbackOptions(query=True, maxTime=True)))
        self.overwrite = c.checkBox(label='Overwrite existing FBX', value=False)
        c.button(label='3. Export skinned game FBX', command=self.export)
        self.status = c.text(label='Ready to analyze.', align='left')
        c.optionMenu(self.mode, edit=True, changeCommand=self._refresh)
        c.checkBox(self.auto_front, edit=True, changeCommand=self._refresh)
        c.checkBox(self.auto_rear, edit=True, changeCommand=self._refresh)
        self._refresh()
        c.showWindow(_WINDOW)

    def _refresh(self, *_):
        c = self.cmds
        simple = c.optionMenu(self.mode, query=True, value=True) == 'SIMPLE'
        c.checkBox(self.auto_front, edit=True, enable=simple)
        c.checkBox(self.auto_rear, edit=True, enable=simple)
        c.intField(self.front, edit=True,
                   enable=simple and not c.checkBox(self.auto_front, query=True, value=True))
        c.intField(self.rear, edit=True,
                   enable=simple and not c.checkBox(self.auto_rear, query=True, value=True))
        c.intField(self.bones, edit=True, enable=not simple)

    def _options(self):
        c = self.cmds
        direction = c.optionMenu(self.forward, query=True, value=True)
        simple = c.optionMenu(self.mode, query=True, value=True) == 'SIMPLE'
        return Options(vehicle=c.optionMenu(self.vehicle, query=True, value=True),
                       mode='SIMPLE' if simple else 'ADVANCED',
                       up_axis=c.upAxis(query=True, axis=True).upper(),
                       forward_axis=direction[1:],
                       forward_sign=1 if direction[0] == '+' else -1,
                       bone_count=c.intField(self.bones, query=True, value=True),
                       front_wheels=(None if not simple or c.checkBox(
                           self.auto_front, query=True, value=True) else c.intField(
                               self.front, query=True, value=True)),
                       rear_wheels=(None if not simple or c.checkBox(
                           self.auto_rear, query=True, value=True) else c.intField(
                               self.rear, query=True, value=True)))

    def _error(self, exc):
        self.cmds.text(self.status, edit=True, label=str(exc))
        self.cmds.warning('BDFR AutoRig: ' + str(exc))

    def analyze(self, *_):
        try:
            opts = self._options()
            candidate = analyze_selection(opts, cmds=self.cmds)
            plan = plan_rig(candidate)
            self.analysis = candidate
            self.built = None
            self.cmds.textScrollList(self.parts, edit=True, removeAll=True)
            for part in candidate.parts:
                self.cmds.textScrollList(self.parts, edit=True,
                                         append=part.kind + '  |  ' + part.node)
            self.cmds.text(self.status, edit=True,
                           label='Detected wheels: %s | joints: %s' % (
                               plan.wheel_counts, len(plan.joints)))
        except (ValueError, RuntimeError) as exc:
            self.analysis = None
            self._error(exc)

    def build(self, *_):
        try:
            if self.analysis is None or self.analysis.options != self._options():
                raise ValueError('Analyze the selected model with these settings first')
            self.built = build_rig(self.analysis, cmds=self.cmds)
            self.cmds.text(self.status, edit=True,
                           label='Rig built. Bound %d separate meshes.' % len(
                               self.built.skin_clusters))
        except (ValueError, RuntimeError) as exc:
            self._error(exc)

    def export(self, *_):
        try:
            if self.built is None:
                raise ValueError('Build the rig in this window before exporting')
            filename = self.cmds.fileDialog2(fileMode=0, fileFilter='FBX (*.fbx)',
                                              dialogStyle=2, caption='Export game FBX')
            if not filename:
                return
            c = self.cmds
            opts = ExportOptions(engine=c.optionMenu(self.engine, query=True, value=True),
                                 start=c.intField(self.start, query=True, value=True),
                                 end=c.intField(self.end, query=True, value=True),
                                 bake=c.checkBox(self.bake, query=True, value=True),
                                 overwrite=c.checkBox(self.overwrite, query=True, value=True))
            result = export_game_fbx(self.built, filename[0], opts, cmds=c)
            c.text(self.status, edit=True, label='Exported: ' + result.path)
        except (ValueError, RuntimeError, OSError) as exc:
            self._error(exc)


def show():
    global _active
    from maya import cmds
    _active = _RigWindow(cmds)
    _active.create()


def close():
    global _active
    from maya import cmds
    if cmds.window(_WINDOW, exists=True):
        cmds.deleteUI(_WINDOW)
    _active = None
