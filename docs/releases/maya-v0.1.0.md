# BDFR Advanced AutoRig for Maya v0.1.0 preview

First installable Maya module package. Unzip it, drag `install.py` into a Maya viewport, restart Maya and load `bdfr_advanced_autorig.py` in Plug-in Manager. Choose **BDFR AutoRig → Open Vehicle AutoRig**. Maya 2024+ is targeted.

The included window exposes automatic part analysis, Simple and Advanced rig building, separate Simple front/rear wheel counts, and baked FBX output for Unreal and Unity. The source meshes get rigid skin weights. Four car wheel joints match `wheel_fl`, `wheel_fr`, `wheel_rl`, `wheel_rr` in BDFR_DriveCore.

The previous `No module named 'maya_autorig'` error came from an example path rather than an installed module. This package uses Maya's `.mod` discovery; no manual `sys.path` line is required after installation.

The separate Blender add-on remains at v0.6.0. The Maya module has passed Python package and adapter tests; interactive Maya and game-engine import validation are pending.
