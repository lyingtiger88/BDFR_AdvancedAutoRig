# BDFR Advanced AutoRig — Maya core prototype

This Maya 2024+ (Python 3.10+) module is distributed separately from the Blender add-on. The installable ZIP includes a `.mod` file, a Python plug-in entry point, and a small Maya window for analysis, rig building and FBX export. The Blender v0.6.0 ZIP does not install in Maya.

The core plans joints without importing Maya, then reads and modifies Maya scenes through `maya.cmds`. It supports car/SUV, truck/bus, motorcycle, bicycle and airplane models; Simple and Advanced rigs; a visible FRONT curve; named wheels and flight surfaces; landing struts; propellers; steering and a bone count target. Meshes receive one skinCluster each with **100% weight on one assigned joint**. The source meshes stay in their existing DAG hierarchy, which avoids doubled motion when the rig root moves.

## Install the Maya ZIP

1. Download **[BDFR_AdvancedAutoRig_Maya-0.1.5.zip](https://github.com/lyingtiger88/BDFR_AdvancedAutoRig/releases/download/maya-v0.1.5/BDFR_AdvancedAutoRig_Maya-0.1.5.zip)**. Extract the **entire** archive to a temporary folder.
2. Drag the extracted `install.py` onto a Maya viewport. The installer places `BDFR_AdvancedAutoRig.mod` and the module directory in Maya's user `modules` folder; it displays the actual location when done. If dragging is unavailable, see `README_MAYA.txt` inside the ZIP for a Script Editor command.
3. Restart Maya, open **Windows → Settings/Preferences → Plug-in Manager**, search for `bdfr_advanced_autorig.py`, and enable **Loaded**. Click the turquoise steering wheel icon on Maya's **Rigging** shelf or choose **BDFR AutoRig → Open Vehicle AutoRig** from the top menu. The interface offers vehicle/mode/front direction, independent Simple front/rear wheel counts, Advanced joint count, Analyze, Build and Unreal/Unity FBX export.

The ZIP is a Maya module, **not** a ZIP for Maya's Plug-in Manager: extract and run the included installer first. The plug-in only becomes discoverable in Plug-in Manager after the restart. `maya_autorig` can then be imported without editing `sys.path`. Select the actual model meshes or their group in the Outliner before Analyze. The strings `'/absolute/path/to/...'` in API examples elsewhere are placeholders and are not valid paths on your machine.

**Upgrading:** unload `bdfr_advanced_autorig.py`, run the installer from the v0.1.5 ZIP, restart Maya, then enable it in Plug-in Manager. v0.1.5 recovers a rig already in the scene for export when the tool window has been reopened. v0.1.4's multi-shell handling, Maya 2027 loading fixes, and Rigging shelf button remain. Automated tests cover plug-in registration, existing rig recovery, and the export button; interactive Maya 2027 validation is still pending.

**Export an already built rig:** Select its `BDFR_Root` joint in Outliner, click the Rigging shelf icon, choose Unreal or Unity and the frame range, then click **Export skinned game FBX**. A rig built before v0.1.5 can be recovered from its skinCluster influences and unmodified `BDFR_FRONT` arrow; you do not have to build it again. Newly built rigs save their original up/front axes and other options as metadata on the root joint so the settings survive a saved scene and Maya restart. If the older rig's FRONT arrow was removed or manually rotated, rebuild it from an unrigged model copy so its export direction is known. When there are multiple BDFR rigs in the scene, select the desired root before exporting.

`cmds.select('Vehicle')` in older examples uses **Vehicle as a placeholder**. If your scene has no object with that exact name, Maya raises `No object matches name: Vehicle`. Select your model group in the Outliner instead. To see its real name in Maya's Python Script Editor, run `cmds.ls(selection=True, long=True)` after selecting it. The window's **Analyze** button reads the current selection.

To open the window from Maya's Python Script Editor after loading the plug-in:

```python
from maya import cmds
cmds.bdfrAutoRig()
```

## Use the Python API directly

After installing, you can also call the underlying API from Maya's Python Script Editor. With the actual vehicle group selected, for example:

```python
from maya import cmds
from maya_autorig import (Options, analyze_selection, plan_rig, build_rig,
                          ExportOptions, export_game_fbx, drivecore_wheel_bones)

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

# After keyframing, choose a real output filename in the UI; alternatively:
# export_game_fbx(built, YOUR_EXISTING_DIRECTORY_AND_FBX_FILENAME,
#                 ExportOptions(engine='UNREAL', start=1, end=120, bake=True))
```

In a **Y-up Maya scene**, the default forward direction is **+Z**; in a **Z-up scene**, it is **+Y**. Set `forward_sign=-1` to reverse. If you omit `Options`, the adapter selects the forward axis based on the scene's up axis. To override detection, use selected meshes' **full DAG paths** as keys:

```python
analysis = analyze_selection(options, overrides={
    '|Vehicle|Aileron_L': {'kind': 'AILERON'},
    '|Vehicle|NoseWheel': {'kind': 'WHEEL', 'axle': 'FRONT', 'steer': 'YES'},
})
```

After building, animate the returned joints directly. `built.joints` maps logical names such as `Root`, `Body`, `Wheel.FL`, `Steer.FL`, `Suspension.FL.01` and `Aileron.010` to actual Maya DAG paths. Move `built.root` to translate the whole vehicle, rotate `Wheel.*` joints around their axle, rotate `Steer.*` around the scene up axis, and rotate `Propeller.*` around the forward axis. The window does not yet add animation sliders or an automated test animation.

## Simple-mode front and rear wheel counts

Set `front_wheels` and/or `rear_wheels` on `Options` when `mode='SIMPLE'`. Each is independently optional (`None` = infer from the visible wheel meshes), and accepts 0–32 physical wheels. For example, on a truck with two front and four rear wheels:

```python
options = Options(vehicle='TRUCK', mode='SIMPLE', front_wheels=2, rear_wheels=4,
                  up_axis=up, forward_axis='Z' if up == 'Y' else 'Y')
analysis = analyze_selection(options)
plan = plan_rig(analysis)
print(plan.wheel_counts)  # {'front': 2, 'rear': 4, 'other': 0}
built = build_rig(analysis)
```

You may specify only one number; the other is the number of remaining detected wheels. Wheels are divided by their position along the chosen forward axis; explicit per-mesh `axle='FRONT'` or `axle='REAR'` overrides take priority. Tires and rims at the same center count as **one wheel**, share one joint, and get one steering control if front. The requested counts must equal the detected physical wheels and agree with axle overrides; otherwise `plan_rig` or `build_rig` raises before changing the scene. Counts do not create geometry or joints for wheels absent from the model. Leave both unset to retain the original automatic axle classification. These two options are specific to Simple mode; Advanced keeps automatic axle classification and its independent bone count target.

## BDFR_DriveCore wheel bone names

The [BDFR_DriveCore sample car](https://github.com/lyingtiger88/BDFR_DriveCore/blob/main/Source/BDFR_DriveCore/Private/AdvancedVehiclePawn.cpp) uses four Chaos `WheelSetups` in FL, FR, RL, RR order. For **CAR** and **TRUCK** rigs, Maya creates these four wheel joint names exactly as configured in DriveCore:

| AutoRig logical key | Maya / FBX wheel joint | DriveCore wheel index |
| --- | --- | --- |
| `Wheel.FL` | `wheel_fl` | 0: front left |
| `Wheel.FR` | `wheel_fr` | 1: front right |
| `Wheel.RL` | `wheel_rl` | 2: rear left |
| `Wheel.RR` | `wheel_rr` | 3: rear right |

The actual joint is at the center of its detected wheel; concentric tire/rim meshes share it. Root, steering and suspension joints retain their `BDFR_` prefix, for example `BDFR_Steer_FL` and `BDFR_Suspension_FL_01`. Existing scripts can continue using `built.joints['Wheel.FL']`. For a four-wheel car, verify the detected axle/side and exact joint names before export:

```python
options = Options(vehicle='CAR', mode='SIMPLE', up_axis=up,
                  forward_axis='Z' if up == 'Y' else 'Y')
analysis = analyze_selection(options)
built = build_rig(analysis)
print(drivecore_wheel_bones(built))  # {'FL': '|...|wheel_fl', ...}
export_game_fbx(built, r'/absolute/path/to/drivecore_car.fbx',
                ExportOptions(engine='UNREAL', start=1, end=120))
```

`drivecore_wheel_bones` rejects missing/extra corner wheel joints and rigs made by the older naming scheme. For motorcycles, bicycles, airplanes and additional truck axles, the existing `BDFR_Wheel_*` names remain; configure the corresponding Chaos `WheelSetups` yourself. A six-wheel Simple rig uses `wheel_fl`, `wheel_fr`, `wheel_rl`, `wheel_rr` for its first front/rear pair, and additional distinct names such as `BDFR_Wheel_RL2` and `BDFR_Wheel_RR2`. The four-wheel DriveCore example cannot consume the extras without additional `WheelSetups`. DriveCore still needs a Skeletal Mesh, a suitable Physics Asset, and the wheel setup/animation setup in Unreal; name matching alone does not validate driving behavior. Before import, check the final FBX orientation (+X forward, +Z up), wheel centers and centimeter scale.

## Bake and export for game engines

Call `export_game_fbx(built, '/existing/directory/vehicle.fbx', ExportOptions(...))` after building and animating. Choose `engine='UNREAL'` for **+X forward / +Z up**, or `engine='UNITY'` for **+Z forward / +Y up**. The exporter uses the forward direction stored in `built.analysis.options` and rotates a temporary export parent to align the model. Maya FBX converts the up axis on export. Both Y-up and Z-up Maya scenes are supported, with any horizontal source forward direction in `Options`. `output.correction_degrees` reports the temporary rotation.

With `bake=True` (default), Maya samples the rig joints and the FBX exporter bakes the specified integer frame range and step. Set `start` and `end` together; leaving both unset uses the Maya playback range. With `bake=False`, the existing keyframes are exported without sampling; driven motion that needs baking may be lost. Set `overwrite=True` to replace an existing FBX file; by default this raises `FileExistsError`. The export includes the skeleton, separate bound mesh transforms and skins; the viewport FRONT curve is excluded.

Export runs in an Undo chunk, restores the Maya scene and FBX exporter preferences, and writes the FBX to a temporary file before installing the final file. Undo must be enabled. After reopening the window or loading a saved scene, select the root and call `recover_built_rig()` if scripting, then pass that result to `export_game_fbx`. FBX import and deformation still need a real Maya and target engine round-trip test.

## Model preparation and safety

- Use a separate mesh transform for each independently moving piece. A single `Body` mesh may contain multiple disconnected shells (panels, glass, interior pieces): all its vertices are rigidly weighted to the same body joint. A wheel mesh with disconnected tire/rim shells similarly follows one wheel joint. Analyze labels such meshes with their shell counts; check the assignment before Build. If a door, hood or wheel is contained in `Body`, separate it into its own mesh transform to animate it independently. The add-on does not split welded geometry or automatically infer which shell should be its own movable part.
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
