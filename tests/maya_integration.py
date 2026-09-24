"""Run inside mayapy or Maya's Python Script Editor to verify actual skin deformation.

    mayapy tests/maya_integration.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    import maya.standalone
    maya.standalone.initialize(name='python')
except (ImportError, RuntimeError):
    # The Script Editor already has Maya initialized; do not initialize twice.
    pass

from maya import cmds
from maya_autorig import Options, analyze_selection, build_rig


def pos(mesh):
    return tuple(cmds.pointPosition(mesh + '.vtx[0]', world=True))


def delta(a, b):
    return sum((x-y)**2 for x, y in zip(a, b)) ** .5


cmds.file(new=True, force=True)
cmds.upAxis(axis='y')
group = cmds.group(empty=True, name='Vehicle')


def cube(name, location, dimensions):
    node = cmds.polyCube(name=name, width=dimensions[0], height=dimensions[1],
                         depth=dimensions[2], constructionHistory=False)[0]
    cmds.xform(node, worldSpace=True, translation=location)
    cmds.parent(node, group)
    return cmds.ls(node, long=True)[0]


body = cube('Chassis', (0, 1, 0), (1.8, .7, 3.2))
wheels = [cube('Wheel_%s_%s' % (x, z), (x*.9, .42, z*1.1),
               (.22, .82, .82)) for x in (-1, 1) for z in (-1, 1)]
cmds.select(group, replace=True)
analysis = analyze_selection(Options(up_axis='Y', forward_axis='Z', vehicle='CAR'))
assert len(analysis.parts) == 5
before = [pos(node) for node in [body, *wheels]]
built = build_rig(analysis)
assert len(built.skin_clusters) == 5
assert all(delta(pos(node), original) < 1e-4 for node, original in zip([body, *wheels], before))
cmds.xform(built.root, worldSpace=True, translation=(2, 0, 0))
assert all(delta(pos(node), (original[0]+2, original[1], original[2])) < 1e-4
           for node, original in zip([body, *wheels], before))
first_wheel = cmds.skinCluster(built.skin_clusters[wheels[0]], query=True, influence=True)[0]
initial = pos(wheels[0])
cmds.setAttr(first_wheel + '.rotateX', 30)
assert delta(initial, pos(wheels[0])) > .03
print('PASS: Maya Y-up: rigid bind, no snapping, whole-rig movement and wheel pose')
