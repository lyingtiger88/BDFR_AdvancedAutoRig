## BDFR Advanced AutoRig v0.1.0 (preview)

First installable preview of the Blender vehicle auto-rig add-on. Download the attached **BDFR_AdvancedAutoRig-0.1.0.zip** asset and install it from Blender's **Edit → Preferences → Add-ons → Install from Disk**. The automatic GitHub source archives are not the installable add-on.

### Included

- Initial rig generation for cars/SUVs, trucks/buses, motorcycles and bicycles.
- Heuristic wheel detection from names, dimensions and location; disconnected mesh-island scanning; editable part assignments.
- Rigid component weights, steering pivots and keyframeable steering/wheel-roll controls.
- English and Persian documentation.

### Preview limitations

This build has passed Python syntax and geometry-detection smoke tests but has **not yet been tested inside Blender**. Use a copy of your `.blend` file. Wheels fused into one contiguous body mesh must be separated first. Suspension, vehicle physics, Ackermann steering, path animation and export baking are not included.
