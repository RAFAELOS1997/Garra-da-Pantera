# Changelog

## 2026-09-21 — Auditoria segura da seleção

- Corrigido o portão de auditoria semântica: a versão anterior comparava uma máscara 2D de imagem com uma seleção 3D por faces, causando incompatibilidade dimensional e uma métrica inválida.
- A exportação agora confere consistência da seleção com rótulos positivos e protegidos no espaço de faces, exige exemplos dos dois tipos, rejeita conflitos e grava métricas no relatório JSON.
- A interface deixa explícito que essa checagem é de consistência com evidências locais, não prova automática da semântica do objeto nem substitui a revisão visual em múltiplas vistas.
- Backup pré-alteração versionado em `backups/2026-09-21/garra_da_pantera.py`.
- Testes determinísticos cobrem seleção consistente, vazamento para faces protegidas, ausência de exemplos e mismatch entre máscaras de imagem e faces.
- Pesquisa primária consultada: documentação do Blender Bisect (corte planar e opções de preenchimento), CGAL Polygon Mesh Processing (reparo independente), OrcaSlicer Cutting Tool, MeshLib `MRContoursCut` (contorno auto-intersectante pode invalidar a área cortada) e release oficial MeshLib v3.1.3.429. Nenhum código incompatível foi copiado.

## 2.3.2 - 2026-09-18

- Pinned installation and fallback launch to Python 3.12 because PyMaxflow has no Python 3.14 wheel.
- Made setup fail immediately when venv creation, pip, dependency installation or final imports fail.
- Added a complete post-install import validation for the geometry and AI stack.

## 2.3.1 - 2026-09-18

- Fixed the Inno Setup script so the Windows installer compiles successfully.
- Updated release checkout steps to the Node 24 compatible action.

## 2.3.0 integration - 2026-09-18

- Integrated native curvature-aware 3D click segmentation, precision PyMeshFix repair and optional pin/socket connectors from the latest main branch.
- Fixed the updater's generated batch syntax, moved network checks out of import time and required SHA-256 verification before applying an update.
- Aligned the release manifest with the visible application version.

## 2.6.0 - 2026-09-18

- **Fixed a critical bug in the already-deployed auto-updater**: `atualizador.py` had a real `SyntaxError` (the update-apply `.bat` script was built from string literals containing raw, unescaped newlines instead of `\n` or triple quotes), so the entire auto-update feature has been silently failing on every launch since it was added — the only caller wraps the import in `except Exception`, which does catch `SyntaxError`, so users never saw a crash, only a swallowed `[Atualizador] Ignorado: ...` line.
- Hardened the auto-updater with SHA-256 verification: `release.yml` now generates and publishes a `.zip.sha256` checksum alongside each release ZIP, and `atualizador.py` downloads and verifies it before ever applying an update — a missing checksum asset, a mismatch, or any network/API failure cancels the update and leaves the program untouched, never applying an unverified download.
- Moved the update check out of module import time and into `main()` (i.e. only when the app is actually launched, not when `garra_da_pantera.py` is imported): importing it — as every unit test does — previously made a real network call to the GitHub API on every test run, which is both slow/flaky and against this project's "no downloads during tests" rule (AGENTS.md).
- Added deterministic tests in `tests/test_atualizador.py` against a local fake HTTP server standing in for the GitHub Releases API: version parsing/ordering, checksum accept/reject, missing-checksum-asset handling, unreachable-API never raising, and a regression test asserting the module's source is syntactically valid (guards directly against the bug above recurring).
- Decided against replacing this GitHub-Releases-based updater with a separate custom-domain manifest + frozen-`.exe`-swap design that was explored in this same session, since the former was already live in production with real release/installer infrastructure built around it; duplicating it would have left two competing auto-update systems in the same file.

## 2.5.1 - 2026-09-18

- Fixed a crash: `voxel_repair` raised an uncaught `ValueError` ("Surface level must be within volume data range") on a piece with no real volume (a near-flat patch, e.g. a single face selected with nothing behind it), which skipped export()'s JSON report entirely — a regression against the AGENTS.md rule that a failed repair must still produce a useful report and no final STL, never a raw crash. Found by running the full export pipeline end to end against a real Tk build (not the tkinter stub) via a local Python 3.12 venv with Xvfb, using a deliberately pathological (zero-thickness) selection.
- `voxel_repair` now catches this case (an all-empty or all-solid voxel grid has no zero-crossing for marching cubes to extract) and returns the untouched mesh with `method: "voxel_reconstruction_failed"`, so the normal validation path still runs and blocks the STL with a proper report instead of crashing.
- Added a regression test with a deliberately degenerate flat mesh.

## 2.5.0 - 2026-09-18

- Added native 3D point-prompt segmentation (`geodesic_click_segmentation`): click near a part directly on the rendered mesh and the program selects the natural region via a curvature-aware geodesic Dijkstra search (reusing the same crease-cost model as `graph_cut_selection`), placing the boundary at a quantile-binned elbow in the resulting distance ordering. This needs no reference photo, no camera/projection alignment, and no trained classifier — it directly addresses the documented perspective/pose limitation of the photo-projection workflow.
- Documented this explicitly as a heuristic geometric method (not a learned model), per the AGENTS.md rule against labeling heuristics as AI: it complements, never replaces, the Extra Trees + graph cut pipeline.
- Added a new "IA 3D nativa (clique)" teaching mode in the sidebar and help text.
- Added deterministic tests: a cube (must stop at sharp 90° folds, no leak to the opposite face) and a sphere (must spread broadly across a smooth surface).

## 2.4.0 - 2026-09-18

- Studied current tooling: Point-SAM/SAM 3D (promptable 3D segmentation), PartField/PartSAM (learned part segmentation), the Chopper paper (Luo/Baran/Rusinkiewicz/Matusik, SIGGRAPH Asia 2012) on printable partitioning with interface connectors, pychop3d, and PyMeshFix (Attene's MeshFix) for watertight repair.
- Added `pymeshfix_repair` as an intermediate repair stage between the conservative repair and the voxel reconstruction fallback: it closes holes and removes self-intersections while leaving already-correct surface untouched, so fewer exports fall back to lossy volumetric reconstruction. Silently skipped if `pymeshfix` is not installed.
- Added optional pin/socket connector generation (`generate_connectors`) along the cut interface, inspired by Chopper's assemblability-oriented connectors: cylindrical pegs are boolean-unioned onto the target piece and matching sockets are boolean-subtracted from the remainder piece, with configurable spacing and radial tolerance, so the two exported STLs can be located and re-assembled by hand instead of only touching along a bare cut line.
- Connectors and the PyMeshFix stage never bypass topology validation: both fall back to the untouched, already-valid meshes and log why if the result would not pass `report_is_valid`.
- Added UI controls for connector spacing, peg radius and tolerance, and a toggle to disable connector generation.
- Added `pymeshfix` and `manifold3d` to `requirements-core.txt`.
- Added deterministic tests for `pymeshfix_repair`, `_resample_loop` and `generate_connectors` on synthetic geometry.

## 2.3.0 - 2026-09-17

- Added a high-contrast projected seam showing the actual selected/unselected mesh boundary.
- Added live cut-length feedback and a persistent active-tool indicator.
- Added one-click orthographic view buttons, full framing and selection focus.
- Verified boundary rendering and focus behavior on a synthetic sphere.

## 2.2.0 - 2026-09-17

- Added a scrollable control rail that remains usable on smaller screens.
- Added an instructional empty state, keyboard shortcuts and mouse-wheel zoom.
- Added live face-count and selection-percentage badges.
- Added depth- and normal-aware mesh shading for clearer shape perception.

## 2.0.0 - 2026-09-17

- Redesigned the desktop UI as Garra da Pantera 2.1 with a dark visual system, branded header, four-step workflow, grouped control cards, persistent color legend and live confidence/angle badges.
- Renamed the product to Garra da Pantera.
- Replaced the hair-specific workflow with arbitrary text-guided target separation.
- Added CLIPSeg open-vocabulary image segmentation while retaining specialized human parsing.
- Generalized labels, projects, help, validation reports and export names.
- Improved curved graph cut with adjustable angular sensitivity, concavity and edge-length costs.
- Studied the public Nativos3D Mesh Cut workflow: SmartCut regional mode, piece/curve modes, angle sensitivity, BVH acceleration and boundary statistics.
- Kept a `hair_separator.py` compatibility entry point for existing integrations.

## 1.0.0 - 2026-09-17

- Added local semantic image parsing for hair, face, limbs and clothing.
- Added interactive positive/negative teaching labels.
- Added learned geometric face classification using position, normals and curvature.
- Added curvature-weighted seeded graph cut for continuous curved boundaries.
- Added selection grow, shrink, fragment cleanup, undo and project persistence.
- Added conservative repair and validated voxel reconstruction fallback.
- Added automatic working-copy simplification above one million faces.
- Added topology reports and strict export blocking.
- Added daily research/update policy and contributor instructions for AI agents.
