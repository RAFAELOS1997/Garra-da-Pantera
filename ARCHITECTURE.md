# Architecture

The pipeline combines independent evidence instead of treating one algorithm as authoritative:

1. **Input and preflight** — load, merge coincident vertices, preserve scale and report existing defects. Dense meshes receive a reversible working-copy simplification.
2. **Image understanding** — SegFormer human parsing identifies hair, face, limbs and clothing in a reference image. The image stays local.
3. **Camera projection** — semantic pixels are projected onto the currently selected orthographic mesh view. These labels become training examples, not final faces.
4. **Interactive teaching** — lasso annotations add positive hair and negative anatomy/clothing examples in multiple views.
5. **Geometric learning** — an Extra Trees ensemble learns normalized position, face normal, radial distance and local dihedral curvature.
6. **Curved boundary optimization** — seeded graph cut combines learned probabilities with pairwise adjacency costs. Cutting across smooth faces is expensive; natural folds are cheaper.
7. **Manual refinement** — confidence threshold, add/remove, grow/shrink, fragment cleanup and undo remain available.
8. **Split and repair** — selected/unselected faces are separated. Conservative cleanup runs first. Volumetric reconstruction is a recorded last resort.
9. **Validation gate** — both outputs must be watertight and free of boundary, non-manifold and degenerate geometry before final STL export.

The current photo-to-mesh registration normalizes the image and mesh bounding boxes. It is useful for frontal reference images but does not yet solve perspective or articulated registration. Landmark-assisted camera fitting is the next major milestone.
