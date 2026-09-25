# BDFR Advanced AutoRig — Maya core prototype

This is the **script-only Maya implementation** in the same repository as the Blender add-on. It targets Maya 2024+ (Python 3.10+), and has no Maya shelf button or GUI yet. The Blender release ZIP contains only the Blender package and is not a Maya installer.

The core plans joints without importing Maya, then reads and modifies Maya scenes through `maya.cmds`. It supports car/SUV, truck/bus, motorcycle, bicycle and airplane models; Simple and Advanced rigs; a visible FRONT curve; named wheels and flight surfaces; landing struts; propellers; steering and a bone count target. Meshes receive one skinCluster each with **100% weight on one assigned joint**. The source meshes stay in their existing DAG hierarchy, which avoids doubled motion when the rig root moves.

## Run in Maya

Place this repository somewhere Maya's Python process can read, then run in the Python Script Editor:

```python
import sys
sys.path.insert(0, r'/absolute/path/to/BDFR_AdvancedAutoRig')
from maya import cmds
from maya_autorig import (Options, analyze_selection, plan_rig, build_rig,
                          ExportOptions, export_game_fbx)

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

# After keyframing the joints, export an engine-ready skinned FBX:
output = export_game_fbx(built, r'/absolute/path/to/vehicle.fbx',
                         ExportOptions(engine='UNREAL', start=1, end=120,
                                       step=1, bake=True))
print(output.path, output.up_axis, output.forward_axis)
```

In a **Y-up Maya scene**, the default forward direction is **+Z**; in a **Z-up scene**, it is **+Y**. Set `forward_sign=-1` to reverse. If you omit `Options`, the adapter selects the forward axis based on the scene's up axis. To override detection, use selected meshes' **full DAG paths** as keys:

```python
analysis = analyze_selection(options, overrides={
    '|Vehicle|Aileron_L': {'kind': 'AILERON'},
    '|Vehicle|NoseWheel': {'kind': 'WHEEL', 'axle': 'FRONT', 'steer': 'YES'},
})
```

After building, animate the returned joints directly. `built.joints` maps logical names such as `Root`, `Body`, `Wheel.FL`, `Steer.FL`, `Suspension.FL.01` and `Aileron.010` to actual Maya DAG paths. Move `built.root` to translate the whole vehicle, rotate `Wheel.*` joints around their axle, rotate `Steer.*` around the scene up axis, and rotate `Propeller.*` around the forward axis. The Maya core does not yet add animation sliders or an automated test animation.

## Bake and export for game engines

Call `export_game_fbx(built, '/existing/directory/vehicle.fbx', ExportOptions(...))` after building and animating. Choose `engine='UNREAL'` for **+X forward / +Z up**, or `engine='UNITY'` for **+Z forward / +Y up**. The exporter uses the forward direction stored in `built.analysis.options` and rotates a temporary export parent to align the model. Maya FBX converts the up axis on export. Both Y-up and Z-up Maya scenes are supported, with any horizontal source forward direction in `Options`. `output.correction_degrees` reports the temporary rotation.

With `bake=True` (default), Maya samples the rig joints and the FBX exporter bakes the specified integer frame range and step. Set `start` and `end` together; leaving both unset uses the Maya playback range. With `bake=False`, the existing keyframes are exported without sampling; driven motion that needs baking may be lost. Set `overwrite=True` to replace an existing FBX file; by default this raises `FileExistsError`. The export includes the skeleton, separate bound mesh transforms and skins; the viewport FRONT curve is excluded.

Export runs in an Undo chunk, restores the Maya scene and FBX exporter preferences, and writes the FBX to a temporary file before installing the final file. Undo must be enabled. Keep the returned `built` object from `build_rig`; rigs built with earlier versions do not carry the direction metadata and should be rebuilt. This API is script-only; FBX import and deformation still need a real Maya and target engine round-trip test.

## Model preparation and safety

- Use a separate mesh transform for each independently moving piece. Each mesh may contain only **one connected shell**; the core rejects multiple shells rather than assigning them all the same rigid weight. It cannot separate parts welded into a contiguous mesh.
- Give parts informative names (`Wheel_FL`, `NoseWheel`, `MainGear_L`, `Propeller_1`, `Aileron_L`, `Elevator`, `Rudder`, `Flap_L`) or supply explicit overrides. Review the analysis before building. Gear struts, hinges and wheel geometry need a real model check; positions and wheel grouping are estimated from bounds.
- Build refuses referenced or locked meshes, instanced shapes, meshes with existing skinClusters, changed meshes after analysis, scenes whose up axis changed, and sessions without Maya Undo. A failed build closes its Undo chunk and calls Undo to restore the scene. Keep a saved copy of your scene when testing production assets.
- This core handles rigid per-object weights. It does not yet support multiple moving parts within a single mesh, animated previews, complex multilink landing gear, or flight and suspension physics.

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
