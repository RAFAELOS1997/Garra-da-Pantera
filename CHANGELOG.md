# Changelog

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
