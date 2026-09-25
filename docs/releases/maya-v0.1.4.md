# BDFR Advanced AutoRig for Maya v0.1.4 preview

The Maya Analyze button now accepts multi-shell polygon meshes. An imported `Body` made of disconnected panels or interior pieces can be analyzed and rigidly skinned as one part; a tire and rim in one mesh also follow their single wheel joint. Analyze shows a shell count next to these meshes and a note that each mesh follows one joint. Before Build, the adapter checks that the shell count has not changed.

All disconnected shells in one mesh get the same rigid weight. To open a door or hood independently, its geometry must be a separate mesh transform. The add-on does not automatically classify and split shells hidden inside `Body`, and it cannot separate welded geometry.

Upgrade by unloading the old plug-in in Plug-in Manager, extracting this ZIP, dragging its `install.py` into a Maya viewport, restarting Maya and enabling `bdfr_advanced_autorig.py`. Select your vehicle meshes or their parent group in Outliner, click the Rigging shelf icon, Analyze, review part types and wheel positions, then Build.

The same publish workflow also rebuilds and uploads the separate Blender v0.6.0 ZIP. Automated Maya package and scene adapter tests pass; an interactive Maya 2027 test on your scene remains necessary.
