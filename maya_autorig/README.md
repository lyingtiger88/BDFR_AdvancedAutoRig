# BDFR Advanced AutoRig — Maya core prototype

This is the **script-only Maya implementation** in the same repository as the Blender add-on. It targets Maya 2024+ (Python 3.10+), and has no Maya shelf button or GUI yet. The Blender release ZIP contains only the Blender package and is not a Maya installer.

The core plans joints without importing Maya, then reads and modifies Maya scenes through `maya.cmds`. It supports car/SUV, truck/bus, motorcycle, bicycle and airplane models; Simple and Advanced rigs; a visible FRONT curve; named wheels and flight surfaces; landing struts; propellers; steering and a bone count target. Meshes receive one skinCluster each with **100% weight on one assigned joint**. The source meshes stay in their existing DAG hierarchy, which avoids doubled motion when the rig root moves.

## Run in Maya

Place this repository somewhere Maya's Python process can read, then run in the Python Script Editor:

```python
import sys
sys.path.insert(0, r'/absolute/path/to/BDFR_AdvancedAutoRig')
from maya import cmds
from maya_autorig import Options, analyze_selection, plan_rig, build_rig

cmds.select('Vehicle', replace=True)  # or select separate mesh transforms
up = cmds.upAxis(query=True, axis=True).upper()
options = Options(vehicle='AIRPLANE', mode='ADVANCED', bone_count=24,
                  up_axis=up, forward_axis='Z' if up == 'Y' else 'Y')
analysis = analyze_selection(options)
for part in analysis.parts:
    print(part.node, part.kind)
plan = plan_rig(analysis)
print('Minimum / planned joints:', plan.minimum_bones, len(plan.joints))
# Inspect the assignments before running this scene-changing command:
built = build_rig(analysis)
print('Rig:', built.root, 'Skins:', built.skin_clusters)
```

In a **Y-up Maya scene**, the default forward direction is **+Z**; in a **Z-up scene**, it is **+Y**. Set `forward_sign=-1` to reverse. If you omit `Options`, the adapter selects the forward axis based on the scene's up axis. To override detection, use selected meshes' **full DAG paths** as keys:

```python
analysis = analyze_selection(options, overrides={
    '|Vehicle|Aileron_L': {'kind': 'AILERON'},
    '|Vehicle|NoseWheel': {'kind': 'WHEEL', 'axle': 'FRONT', 'steer': 'YES'},
})
```

After building, animate the returned joints directly. `built.joints` maps logical names such as `Root`, `Body`, `Wheel.FL`, `Steer.FL`, `Suspension.FL.01` and `Aileron.010` to actual Maya DAG paths. Move `built.root` to translate the whole vehicle, rotate `Wheel.*` joints around their axle, rotate `Steer.*` around the scene up axis, and rotate `Propeller.*` around the forward axis. The Maya core does not yet add animation sliders or an automated test animation.

## Model preparation and safety

- Use a separate mesh transform for each independently moving piece. Each mesh may contain only **one connected shell**; the core rejects multiple shells rather than assigning them all the same rigid weight. It cannot separate parts welded into a contiguous mesh.
- Give parts informative names (`Wheel_FL`, `NoseWheel`, `MainGear_L`, `Propeller_1`, `Aileron_L`, `Elevator`, `Rudder`, `Flap_L`) or supply explicit overrides. Review the analysis before building. Gear struts, hinges and wheel geometry need a real model check; positions and wheel grouping are estimated from bounds.
- Build refuses referenced or locked meshes, instanced shapes, meshes with existing skinClusters, changed meshes after analysis, scenes whose up axis changed, and sessions without Maya Undo. A failed build closes its Undo chunk and calls Undo to restore the scene. Keep a saved copy of your scene when testing production assets.
- This initial core handles rigid per-object weights. It does not yet support multiple moving parts within a single mesh, animated previews, export baking, complex multilink landing gear, or flight and suspension physics.

## Tests

Pure Python unit tests and a fake `maya.cmds` contract run without Maya:

```bash
python -m unittest discover -s tests -p 'test_maya_*.py'
```

The actual Maya deformation test must run **inside a Maya installation**:

```bash
mayapy tests/maya_integration.py
```

The repository's CI runs the unit and contract tests. Actual Maya runtime verification remains pending until the integration script is run using `mayapy`.
