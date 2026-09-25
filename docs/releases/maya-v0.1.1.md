# BDFR Advanced AutoRig for Maya v0.1.1 preview

Fixes the `TypeError: argument 1 must be OpenMaya.MObject, not MObject` seen when Maya 2027 tried to load the v0.1.0 plug-in. The command class, plug-in registration and command creator now use the same Maya Python API; an automated test reproduces the initialization type mismatch and checks registration and deregistration.

To upgrade: unload `bdfr_advanced_autorig.py` in Plug-in Manager, extract this ZIP in full, drag `install.py` into a Maya viewport, restart Maya, and enable the plug-in again. The installer replaces the existing module. Choose **BDFR AutoRig → Open Vehicle AutoRig**.

Maya 2024+ is targeted. Automated package, core and adapter tests pass. Loading and deformation in an actual Maya 2027 session still need validation.
