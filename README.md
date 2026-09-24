# BDFR Advanced AutoRig

![Vehicle rig overview](assets/hero.webp)

**Automatic first-pass vehicle rigging for Blender 4.2+.** Select a vehicle, inspect detected parts, and build an armature with rigid weights and simple animation controls.

> **Status:** v0.2.0 preview. Detection uses object names, disconnected mesh islands, dimensions and position. It is heuristic geometry analysis, not machine-learning segmentation. Blender runtime validation on representative production files is still pending.

[راهنمای فارسی](docs/README.fa.md) · [Installable add-on ZIP](https://github.com/lyingtiger88/BDFR_AdvancedAutoRig/releases/download/v0.2.0/BDFR_AdvancedAutoRig-0.2.0.zip)

## What it does

- Supports **car/SUV, truck/bus, motorcycle and bicycle** layouts; set the model's front axis to `±X` or `±Y` (`Z` up).
- Finds wheels from component names or shape and location, scans disconnected mesh islands, and merges concentric tire/rim/hub components into one wheel control.
- Lets you review each detected component and correct its type. Separate mesh objects can also be explicitly marked as body, wheel, door, hood, trunk or ignored.
- **Simple** creates `Root`, `Body`, wheels and steering controls. Doors and hatches stay rigid with the body. **Advanced** adds one or more poseable suspension bones per wheel, plus optional door, hood and trunk hinges. Each component receives a rigid vertex group and an Armature modifier; source mesh geometry is not split.
- In Advanced mode, **Bone Count** sets a target total of 2–128 bones. The panel shows the minimum and actual count after analysis. Required controls are never discarded; extra bones extend the wheel suspension chains. The value is saved into each newly built rig.
- Parents the selected vehicle hierarchy to the armature object while preserving world transforms, so moving `Vehicle_Rig` in Object Mode carries the meshes. Also exposes animatable **Steering (degrees)** and **Wheel roll (degrees)** properties.

## Install

Download [the add-on ZIP](https://github.com/lyingtiger88/BDFR_AdvancedAutoRig/releases/download/v0.2.0/BDFR_AdvancedAutoRig-0.2.0.zip). In Blender, open **Edit → Preferences → Add-ons → Install from Disk**, select the ZIP, and enable **BDFR Advanced AutoRig**. Open the 3D View sidebar with `N` and find the **Vehicle Rig** tab. Install the add-on ZIP, not GitHub's *Download ZIP* archive of the whole repository.

## Quick start

1. Save a backup of your `.blend` file. Select all vehicle meshes or select a parent object containing them.
2. Choose the vehicle type, front direction and **Simple** or **Advanced**. Click **1. Analyze Vehicle**. In Advanced mode, set **Bone Count** and check the displayed minimum/actual total.
3. Review the detected parts. Change the type beside any component that was misidentified. To override a separate object's classification, select it, use **Mark Selected Objects**, then analyze again.
4. Re-select the original vehicle meshes if necessary, then click **2. Build Rig**.
5. Select `Vehicle_Rig`. Moving it in Object Mode moves the whole vehicle. In Pose Mode, use `Root` for whole-vehicle motion and `Body` for body movement. Use the sidebar properties **Steering (degrees)** and **Wheel roll (degrees)** for animation; right-click a value and choose **Insert Keyframe**. Advanced rigs expose **Front suspension** and **Rear suspension** travel (scene units); the first bone in each wheel's suspension chain has a driver, while additional chain bones can be posed individually. These are animation controls, not simulated springs.

## Fix a rig built with v0.1.0

Install v0.2.0, select the existing `Vehicle_Rig` object, and click **Repair Existing Rig Binding** in the Vehicle Rig sidebar. The repair attaches meshes already using this rig as their Armature modifier target, without rebuilding weights. Reset any rig movement that previously left the meshes behind **before** running repair; the repair preserves their current world positions. The existing vehicle hierarchy is preserved when its mesh descendants all use this rig. To switch an existing rig to Advanced, build a new rig from an unrigged model; repair does not add new bones.

## Model preparation and limitations

- The model must have `Z` as its vertical axis. Parts can be separate objects or disconnected islands within a mesh. **Wheels welded into a single contiguous body mesh cannot be separated reliably by this version**; separate their geometry first.
- Named doors, hood and trunk can get bones, but their hinge locations are estimates. Correct them in Armature Edit Mode if needed.
- Very large meshes above the configured per-mesh scan limit are treated as one component and flagged. A source mesh with an existing Armature modifier or linked library data is rejected.
- Advanced suspension is manually animated wheel travel, **not** spring physics, wheel-ground contact or collision detection. This release also does not implement Ackermann steering, vehicle physics, path driving, export baking or production-ready auto-animation. Front steering shares one angle, wheel roll shares one rotation, and suspension travel is shared per front/rear axle group.
- A Blender 4.5 integration test checks both rig modes, object-mode rig translation, suspension motion, bone counts, pose deformation, imported hierarchy preservation and repair of an older rig. Test with a copy of a production vehicle before relying on it.

## Development

```bash
python -m py_compile vehicle_auto_rig/__init__.py
python tests/test_detection.py
```

The ZIP in `dist/` contains only the `vehicle_auto_rig` add-on package. The README banner is project artwork, not a screenshot of Blender or a guarantee of the precise rig generated by the add-on.
