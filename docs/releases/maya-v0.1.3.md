# BDFR Advanced AutoRig for Maya v0.1.3 preview

Fixes the `NameError: __file__ is not defined` raised by Maya 2027 while loading v0.1.2. The plug-in now resolves its Rigging shelf icon through Maya's installed module path at UI creation time, so the plug-in can initialize even when Maya executes its Python source without `__file__`. The menu remains available if the icon is missing. An automated test executes the packaged plug-in without `__file__`, checks icon resolution, opens the shelf button, and verifies unload cleanup.

To upgrade, unload `bdfr_advanced_autorig.py` in Plug-in Manager, extract the full ZIP, drag `install.py` into a Maya viewport, restart Maya, and load the plug-in. Select your actual vehicle group in Outliner; click the Rigging shelf icon and then Analyze. `cmds.select('Vehicle')` is a placeholder in old sample code and fails unless an object has exactly that name. You can run `cmds.ls(selection=True, long=True)` in the Python Script Editor to find your selected group's real name.

The publish workflow also rebuilds the Blender v0.6.0 ZIP and uploads it to its separate release. Automated tests pass; an interactive Maya 2027 run still needs validation.
