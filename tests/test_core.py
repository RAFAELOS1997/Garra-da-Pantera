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
import garra_da_pantera as hs


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

    def test_semantic_evidence_audit_uses_face_labels_and_passes_consistent_selection(self):
        selected = np.array([1, 1, 1, 0, 0, 0, 0, 0], dtype=bool)
        positive = np.array([1, 1, 1, 0, 0, 0, 0, 0], dtype=bool)
        protected = np.array([0, 0, 0, 1, 1, 1, 0, 0], dtype=bool)
        result = hs.semantic_evidence_audit(selected, positive, protected)
        self.assertTrue(result["passed"])
        self.assertEqual(result["reason"], "passed")

    def test_semantic_evidence_audit_blocks_leaked_protected_faces(self):
        selected = np.array([1, 1, 1, 1, 0, 0, 0, 0], dtype=bool)
        positive = np.array([1, 1, 1, 0, 0, 0, 0, 0], dtype=bool)
        protected = np.array([0, 0, 0, 1, 1, 1, 0, 0], dtype=bool)
        result = hs.semantic_evidence_audit(selected, positive, protected)
        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "selection_conflicts_with_labels")

    def test_semantic_evidence_audit_rejects_image_space_face_count_mismatch(self):
        result = hs.semantic_evidence_audit(np.zeros(12), np.zeros(48), np.zeros(48))
        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "face_count_mismatch")

    def test_semantic_evidence_audit_requires_positive_and_protected_examples(self):
        result = hs.semantic_evidence_audit(np.ones(8), np.ones(8), np.zeros(8))
        self.assertFalse(result["passed"])
        self.assertEqual(result["reason"], "insufficient_labeled_faces")

    def test_local_reference_projection_produces_face_space_labels(self):
        app = object.__new__(hs.GarraDaPantera)
        app.reference_target_mask = np.array([[False, True], [False, False]])
        app.reference_protected_mask = np.array([[False, False], [True, False]])
        app.flip_reference = type("Value", (), {"get": lambda self: False})()
        app.projected = lambda: (np.array([[0., 0.], [1., 0.], [0., 1.], [1., 1.]]), np.zeros(4))
        app.visible_mask = lambda xy, depth: np.ones(4, dtype=bool)
        app.ai_positive = np.zeros(4, dtype=bool)
        app.ai_negative = np.zeros(4, dtype=bool)
        app.redraw = lambda: None
        app.status = type("Status", (), {"set": lambda self, value: None})()
        app.project_reference_labels()
        self.assertEqual(app.ai_positive.shape, (4,))
        self.assertEqual(app.ai_negative.shape, (4,))
        self.assertTrue(app.ai_positive[3])
        self.assertTrue(app.ai_negative[0])

    def test_voxel_repair_is_watertight(self):
        box = trimesh.creation.box(extents=[4, 5, 6])
        box.update_faces(np.arange(len(box.faces) - 2))
        fixed, metadata = hs.voxel_repair(box, target_resolution=60)
        self.assertTrue(hs.mesh_report(fixed)["watertight"])
        self.assertEqual(metadata["method"], "voxel_reconstruction")

    def test_voxel_repair_handles_degenerate_flat_mesh_without_crashing(self):
        # A single near-flat patch (no real volume) previously made marching
        # cubes raise "Surface level must be within volume data range",
        # which escaped export() uncaught and skipped writing the JSON
        # report that AGENTS.md requires even for a failed repair.
        flat = trimesh.Trimesh(vertices=[[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]],
                                faces=[[0, 1, 2], [0, 2, 3]], process=False)
        fixed, metadata = hs.voxel_repair(flat, target_resolution=60)
        self.assertEqual(metadata["method"], "voxel_reconstruction_failed")
        self.assertFalse(hs.report_is_valid(hs.mesh_report(fixed)))

    def test_seeded_graph_cut_respects_hard_labels(self):
        mesh = trimesh.creation.icosphere(subdivisions=1)
        app = object.__new__(hs.GarraDaPantera)
        app.mesh = mesh
        app.normals = mesh.face_normals
        app.ai_positive = np.zeros(len(mesh.faces), dtype=bool)
        app.ai_negative = np.zeros(len(mesh.faces), dtype=bool)
        app.curve_sensitivity = type("Value", (), {"get": lambda self: 18.0})()
        top = int(np.argmax(mesh.triangles_center[:, 2]))
        bottom = int(np.argmin(mesh.triangles_center[:, 2]))
        app.ai_positive[top] = True
        app.ai_negative[bottom] = True
        probability = (mesh.triangles_center[:, 2] - mesh.bounds[0, 2]) / mesh.extents[2]
        selected = app.graph_cut_selection(probability)
        self.assertTrue(selected[top])
        self.assertFalse(selected[bottom])

    def test_safe_slug_normalizes_arbitrary_target(self):
        self.assertEqual(hs.safe_slug("Braço / Espada Dourada"), "braco_espada_dourada")

    def test_pymeshfix_repair_closes_hole_or_no_ops_cleanly(self):
        box = trimesh.creation.box(extents=[4, 5, 6])
        box.update_faces(np.arange(len(box.faces) - 1))
        fixed, log = hs.pymeshfix_repair(box)
        self.assertTrue(log)
        report = hs.mesh_report(fixed)
        if "não está instalado" not in log[0] and "falhou" not in log[0]:
            self.assertTrue(report["watertight"])

    def test_resample_loop_covers_full_perimeter(self):
        angles = np.linspace(0, 2 * np.pi, 40, endpoint=False)
        circle = np.stack([np.cos(angles), np.sin(angles), np.zeros_like(angles)], axis=1) * 10.0
        points = hs._resample_loop(circle, spacing=5.0)
        self.assertGreaterEqual(len(points), 10)
        perimeter = 2 * np.pi * 10.0
        self.assertAlmostEqual(len(points), round(perimeter / 5.0), delta=2)

    def test_geodesic_click_segmentation_stops_at_sharp_fold(self):
        box = trimesh.creation.box(extents=[10, 10, 10])
        top_face = int(np.argmax(box.triangles_center[:, 2]))
        mask = hs.geodesic_click_segmentation(box, top_face, sensitivity_degrees=15.0)
        self.assertTrue(mask[top_face])
        top_faces = box.triangles_center[:, 2] > 4.9
        bottom_faces = box.triangles_center[:, 2] < -4.9
        self.assertTrue(mask[top_faces].all())
        self.assertFalse(mask[bottom_faces].any())

    def test_geodesic_click_segmentation_spreads_over_smooth_surface(self):
        sphere = trimesh.creation.icosphere(subdivisions=2)
        seed = int(np.argmax(sphere.triangles_center[:, 2]))
        mask = hs.geodesic_click_segmentation(sphere, seed, sensitivity_degrees=30.0)
        self.assertGreater(mask.sum(), len(sphere.faces) * 0.2)

    def test_generate_connectors_produces_valid_watertight_pair(self):
        left = trimesh.creation.box(extents=[10, 10, 10])
        left.apply_translation([-5, 0, 0])
        right = trimesh.creation.box(extents=[10, 10, 10])
        right.apply_translation([5, 0, 0])
        angle = np.linspace(0, 2 * np.pi, 24, endpoint=False)
        loop = np.stack([np.zeros_like(angle), 4 * np.cos(angle), 4 * np.sin(angle)], axis=1)
        target, remainder, log = hs.generate_connectors(
            left, right, [loop], peg_radius=1.0, peg_length=3.0, spacing=6.0, tolerance=0.15, embed=1.0)
        self.assertTrue(log)
        if "operação booleana indisponível" not in log[0] and "topologia inválida" not in log[0]:
            self.assertTrue(hs.report_is_valid(hs.mesh_report(target)))
            self.assertTrue(hs.report_is_valid(hs.mesh_report(remainder)))
            self.assertGreater(len(target.faces), len(left.faces))
            self.assertGreater(len(remainder.faces), len(right.faces))


if __name__ == "__main__":
    unittest.main()
