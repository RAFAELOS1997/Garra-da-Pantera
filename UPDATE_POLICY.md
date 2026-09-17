# Update policy

Daily research may inspect official documentation, primary papers and official repositories. An automatic update is accepted only when it:

- has a concrete benefit for curved semantic cutting, repair, validation or usability;
- does not transmit user data;
- introduces no paid API dependency;
- includes deterministic tests;
- preserves the previous version in a local backup;
- passes syntax, unit and GUI smoke tests;
- records source, behavior, limitations and migration notes in `CHANGELOG.md`.

Research targets include Nativos3D, PrusaSlicer, OrcaSlicer, Blender, MeshLab/VCGlib, CGAL, libigl, MeshLib, PyMeshFix, open-vocabulary vision models and recent papers about semantic mesh segmentation and geodesic contours. Updates must improve generic target separation rather than optimizing for a single anatomy class.
