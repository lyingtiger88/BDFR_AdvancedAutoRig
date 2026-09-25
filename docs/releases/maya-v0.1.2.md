# BDFR Advanced AutoRig for Maya v0.1.2 preview

Adds a one-click button with a turquoise rigged steering-wheel icon to Maya's **Rigging** shelf. Loading the plug-in adds the button and an icon to **BDFR AutoRig → Open Vehicle AutoRig**. Unloading removes the shelf button; reloading creates it once. Maya's batch mode does not create UI. The icon is included in the installable module ZIP at 64 and 128 pixel sizes.

To upgrade, unload `bdfr_advanced_autorig.py`, extract this ZIP in full, drag `install.py` into the Maya viewport, restart Maya and enable the plug-in in Plug-in Manager. Select your vehicle in Outliner and click the new button on the Rigging shelf. The matching Blender v0.6.0 ZIP is built and uploaded separately to the Blender release by the same workflow.

Automated package, initialization and shelf UI contract tests pass. Interactive UI loading in Maya 2027 remains to be verified in an actual installation.
