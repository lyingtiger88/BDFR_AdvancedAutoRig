BDFR Advanced AutoRig for Maya v0.1.1 (Maya 2024+, Python 3.10+)

INSTALL (Windows, macOS or Linux)
1. Extract this ZIP to any temporary folder. Do not install the Blender ZIP.
2. With Maya running, drag the extracted install.py onto a Maya viewport.
3. Restart Maya. In Windows > Settings/Preferences > Plug-in Manager, find
   bdfr_advanced_autorig.py and turn Loaded on (Auto load is optional).
4. Select a model's mesh group in the Outliner, then use the BDFR AutoRig menu
   > Open Vehicle AutoRig. You can also run in Maya's Python Script Editor:
       from maya import cmds
       cmds.loadPlugin('bdfr_advanced_autorig.py', quiet=True)
       cmds.bdfrAutoRig()

If drag-and-drop does not work, run this in Maya's *Python* Script Editor,
replacing the filename with the actual location of extracted install.py:
    import runpy
    runpy.run_path(r'C:\path\where\you\extracted\install.py')['install']()

The installer copies the module into Maya's own user application directory.
After restarting Maya, 'import maya_autorig' works without sys.path edits.
When updating v0.1.0, unload the previous plug-in first, run the new installer,
restart Maya, then load it again in Plug-in Manager. This release fixes the
MObject type error during plug-in initialization.
The input model must have separate mesh objects for movable parts. Save the
scene, select its group, Analyze, review the detected parts, then Build Rig.
Simple mode has independent front/rear wheel counts (Auto by default).
Advanced mode uses a target bone count. The export tool supports Unreal
(+X forward, +Z up) and Unity (+Z forward, +Y up).

The FBX export path must be a real writable location selected in the UI.
The earlier README's '/absolute/path/to/...' strings were examples only.
Core and FBX integration have not yet been verified in an installed Maya.
Blender v0.6.0 is a separate release and is not contained in this ZIP.
