# HairSeparator AI

Local desktop tool for separating hair and other semantic regions from dense character meshes, creating two independently printable solids and refusing invalid STL exports.

The project combines a reference-image human parser, interactive teaching labels, learned geometric classification, curvature-weighted graph cut, manual refinement and a multi-stage repair/validation pipeline. Images and meshes remain on the computer.

## Current capabilities

- STL/OBJ/PLY loading with automatic working-copy simplification above one million faces.
- Front, back, left, right and top orthographic editing views.
- Continuous visible-surface lasso selection with add/remove and undo.
- Positive “hair” and negative “anatomy/clothing” teaching labels.
- Local human parsing from a reference image using SegFormer.
- Extra Trees geometric classifier using face position, normals, radial position and dihedral curvature.
- Seeded graph cut that prefers curved seams along natural folds.
- Confidence adjustment, grow, shrink and fragment cleanup.
- Save/load project masks without embedding the source mesh.
- Conservative topology repair followed by a recorded voxel fallback when required.
- Strict topology gate before final STL export.

## Install on Windows

Open PowerShell in the project directory and run:

```powershell
.\setup.ps1
```

Then double-click `abrir_programa.bat`.

The human-parsing weights are downloaded from `mattmdjaga/segformer_b2_clothes` the first time **Analyze image** is used. The reference image itself is processed locally and is not uploaded.

## Recommended workflow

1. Open the mesh and run **Initial diagnostics**.
2. Select the view matching the reference image and run **Analyze image**.
3. Inspect the green hair labels and pink protected anatomy/clothing labels.
4. Add examples manually in at least two views.
5. Run **Recognize hair** with **Curved contour** enabled.
6. Adjust confidence, correct the selection, grow/shrink and clean fragments.
7. Save the project before cutting.
8. Run **Separate, close and validate**.

Orange faces are the proposed cut selection. Green faces are positive teaching examples. Pink faces are protected negative examples. When image inference has run, unselected faces also show a blue-to-red confidence heat map.

## Export and automatic correction

The repair cascade removes duplicate and degenerate faces, merges coincident vertices, fixes orientation and normals, fills small holes and triangulates safe boundary cycles. If validation still fails and **Auto-correct cut** is enabled, a local voxel reconstruction produces a closed fallback and records its pitch and estimated surface displacement.

The final `cabelo.stl` and `corpo.stl` are written only if both meshes are watertight, consistently oriented and have zero open, non-manifold and degenerate elements. Diagnostic pre-reconstruction meshes and `validacao_separacao.json` explain any lossy fallback or blocked export.

## Known limitations

- Reference-image projection currently uses normalized orthographic alignment. Perspective and pose differences require manual correction.
- Voxel reconstruction can soften details smaller than roughly two voxels.
- Topological validity does not guarantee sufficient wall thickness, good support placement or a useful physical joint.
- SegFormer human parsing is evidence for the 3D learner; it is not treated as an infallible final selection.

## Contributing

Humans and coding agents should read [AGENTS.md](AGENTS.md), [ARCHITECTURE.md](ARCHITECTURE.md), [UPDATE_POLICY.md](UPDATE_POLICY.md) and [PESQUISA_E_DECISOES.md](PESQUISA_E_DECISOES.md) before changing the pipeline.

Run checks with:

```powershell
.\.venv\Scripts\python.exe -m py_compile hair_separator.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

User models, images, weights, reports and project masks are intentionally excluded by `.gitignore`.
