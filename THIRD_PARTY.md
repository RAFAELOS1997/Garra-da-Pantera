# Third-party components and models

Garra da Pantera depends on the Python packages listed in `requirements.txt`. Their licenses remain with their respective authors.

Image analysis downloads the Hugging Face models `mattmdjaga/segformer_b2_clothes` and, for arbitrary text targets, `CIDAS/clipseg-rd64-refined` at runtime. Review their model cards and licenses before redistribution or commercial deployment. Model weights are never committed.

Research references include Nativos3D Mesh Cut's publicly delivered interface and browser bundle, CGAL, libigl, MeshLab/VCGlib, MeshLib, PyMeshFix, SegFormer, CLIPSeg and Self-Correction for Human Parsing. No implementation code from those projects or services is copied into this repository. Implementations here were written independently from documented algorithms and observable interfaces.
