# BDFR Advanced AutoRig for Maya v0.1.5 preview

Fixes **Build the rig in this window before exporting** after reopening the Maya tool. Opening the Rigging shelf button again preserves the current window and its built rig. Export can also recover a rig from the scene after the window was closed, the plug-in reloaded, or Maya restarted. New rigs save their axes and options on the root joint; rigs built with v0.1.4 can be recovered using their skinned meshes, skeleton and unmodified `BDFR_FRONT` indicator.

To export your already built car: unload the old plug-in, extract this ZIP, drag `install.py` into Maya, restart Maya and load `bdfr_advanced_autorig.py`. Open your rigged scene, select the `BDFR_Root` joint in Outliner, open BDFR AutoRig from the Rigging shelf, choose Unreal/Unity, frame range and an actual writable `.fbx` destination, then click Export. Do not run Analyze or Build again on the skinned model. If multiple rigs exist, select the correct root. If an older rig's FRONT arrow was removed or manually rotated, export direction cannot be recovered safely and the rig must be rebuilt from an unrigged copy.

The same publish workflow rebuilds and uploads the separate Blender v0.6.0 ZIP. Automated Maya package, scene and UI recovery tests pass; actual Maya 2027 and target engine import verification still need to be run on a real asset.
