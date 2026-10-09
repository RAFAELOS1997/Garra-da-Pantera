# Instructions for AI development agents

## Mission

Build a local-first, visual and reliable tool that separates any user-described visible region from dense meshes and produces independently printable solids. The application must prefer refusing an unsafe export over silently producing a broken STL.

## Read first

Before changing code, read `README.md`, `ARCHITECTURE.md`, `PESQUISA_E_DECISOES.md`, `UPDATE_POLICY.md`, `THIRD_PARTY.md` and `CHANGELOG.md`.

## Non-negotiable rules

1. Never commit user meshes, reference images, generated projects, reports, model weights, credentials or absolute user paths.
2. Never overwrite an input mesh. Every mutation works on an in-memory copy and every export uses a new path.
3. Image analysis is local. Do not upload images or meshes to an API.
4. Never bypass topology validation. A printable export requires: watertight, consistent winding, zero boundary edges, zero non-manifold edges and zero degenerate faces.
5. Lossy reconstruction must be recorded with voxel pitch and an estimated surface-shift bound.
6. Do not label a heuristic as AI. Document whether a result came from image parsing, learned geometric classification, graph cut, morphology or reconstruction.
7. Preserve undo state for every selection-changing operation.
8. Keep heavy imports lazy so the basic editor starts without loading PyTorch.
9. Any new algorithm needs a deterministic test on synthetic geometry and a regression test for its failure mode.
10. Respect upstream licenses. Study GPL code and papers, but do not copy incompatible implementation code into this MIT project.
11. The self-update check (`atualizador.py`) is the one intentional exception to rule 3's "no network" spirit — it only fetches a GitHub Releases manifest and a SHA-256-verified ZIP, never mesh/image/project data. Never weaken its checksum verification, never apply an update while unsaved work could be lost, and never make any other feature phone home.
12. A new lazily-imported package (rule 8) also needs an entry in `garra_da_pantera.spec`'s `hiddenimports` (or a `collect_all(...)` call for one with data files/dynamic plugins) — PyInstaller's static analysis does see imports inside function bodies, but not imports a dependency itself performs conditionally at runtime (e.g. `trimesh.boolean`'s optional `manifold3d` backend).

## Architecture boundaries

- `garra_da_pantera.py`: current desktop application and geometry pipeline. `hair_separator.py` is only a compatibility shim.
- Image parsing: specialized human parsing plus open-vocabulary text segmentation. It supplies evidence, never the final 3D selection.
- Geometric learner: learns from positive and negative face labels using position, normals, radial location and curvature.
- Curved graph cut: combines unary semantic confidence with adjacency costs; cuts should prefer high dihedral-angle boundaries.
- Repair cascade: sanitize → orient → fill small holes → triangulate safe boundary loops → validated volumetric reconstruction only as fallback.
- Validation: independent of the repair method and always run after export serialization in future versions.

## Development commands

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m py_compile garra_da_pantera.py hair_separator.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Definition of done

- Syntax and unit tests pass.
- The GUI can be constructed and destroyed without entering the main loop.
- No model or image is downloaded during tests.
- The change is documented in `CHANGELOG.md` with sources and limitations.
- A failed repair produces a useful JSON report and no final STL.
- A successful repair is reloaded from the serialized STL and validated again.

## High-value roadmap

1. Move algorithms into `hairseparator/core` and add typed dataclasses for reports.
2. Add a GPU-backed interactive 3D viewport with face picking and overlay layers.
3. Replace normalized photo projection with landmark-assisted camera registration.
4. Add multi-view consensus and confidence calibration.
5. Add curvature-aware shortest closed curves and editable anchor points.
6. Build complementary male/female interfaces and optional keyed connectors with explicit tolerance.
7. Add self-intersection tests and thickness analysis before declaring print-ready.
