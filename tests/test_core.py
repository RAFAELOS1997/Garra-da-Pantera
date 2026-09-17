import sys
import unittest
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
DEV_LIB = APP.parents[1] / "work" / "pythonlibs"
if DEV_LIB.exists():
    sys.path.insert(0, str(DEV_LIB))

import numpy as np
import trimesh

sys.path.insert(0, str(APP))
import hair_separator as hs


class CoreTests(unittest.TestCase):
    def test_cap_planar_patch(self):
        box = trimesh.creation.box()
        keep = box.triangles_center[:, 2] > 0.49
        patch = box.submesh([np.flatnonzero(keep)], append=True, repair=False)
        closed, warnings = hs.cap_mesh(patch)
        report = hs.mesh_report(closed)
        self.assertFalse(warnings)
        self.assertTrue(report["watertight"])
        self.assertEqual(report["boundary_edges"], 0)

    def test_validation_rejects_open_mesh(self):
        box = trimesh.creation.box()
        box.update_faces(np.arange(len(box.faces) - 1))
        self.assertFalse(hs.report_is_valid(hs.mesh_report(box)))

    def test_voxel_repair_is_watertight(self):
        box = trimesh.creation.box(extents=[4, 5, 6])
        box.update_faces(np.arange(len(box.faces) - 2))
        fixed, metadata = hs.voxel_repair(box, target_resolution=60)
        self.assertTrue(hs.mesh_report(fixed)["watertight"])
        self.assertEqual(metadata["method"], "voxel_reconstruction")

    def test_seeded_graph_cut_respects_hard_labels(self):
        mesh = trimesh.creation.icosphere(subdivisions=1)
        app = object.__new__(hs.HairSeparator)
        app.mesh = mesh
        app.normals = mesh.face_normals
        app.ai_positive = np.zeros(len(mesh.faces), dtype=bool)
        app.ai_negative = np.zeros(len(mesh.faces), dtype=bool)
        top = int(np.argmax(mesh.triangles_center[:, 2]))
        bottom = int(np.argmin(mesh.triangles_center[:, 2]))
        app.ai_positive[top] = True
        app.ai_negative[bottom] = True
        probability = (mesh.triangles_center[:, 2] - mesh.bounds[0, 2]) / mesh.extents[2]
        selected = app.graph_cut_selection(probability)
        self.assertTrue(selected[top])
        self.assertFalse(selected[bottom])


if __name__ == "__main__":
    unittest.main()
