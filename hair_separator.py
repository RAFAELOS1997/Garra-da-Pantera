from __future__ import annotations

import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
WORKSPACE_LIB = APP_DIR.parents[1] / "work" / "pythonlibs"
for candidate in (APP_DIR / "vendor", WORKSPACE_LIB):
    if candidate.exists():
        sys.path.insert(0, str(candidate))

import numpy as np
import trimesh
import fast_simplification
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.path import Path as MplPath
from matplotlib.widgets import LassoSelector
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.ndimage import maximum_filter, binary_closing, binary_fill_holes
from sklearn.ensemble import ExtraTreesClassifier


VIEWS = {
    "Frente": (0, 2, 1, 1.0),
    "Costas": (0, 2, 1, -1.0),
    "Direita": (1, 2, 0, 1.0),
    "Esquerda": (1, 2, 0, -1.0),
    "Topo": (0, 1, 2, 1.0),
}


def mesh_report(mesh: trimesh.Trimesh) -> dict:
    mesh.remove_unreferenced_vertices()
    counts = np.bincount(mesh.edges_unique_inverse, minlength=len(mesh.edges_unique))
    tri = mesh.triangles
    cross = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    diag = max(float(np.linalg.norm(mesh.extents)), 1e-12)
    degenerate = int(np.count_nonzero(np.linalg.norm(cross, axis=1) <= diag * diag * 1e-12))
    adj = mesh.face_adjacency
    if len(mesh.faces):
        graph = coo_matrix((np.ones(len(adj) * 2),
                            (np.r_[adj[:, 0], adj[:, 1]], np.r_[adj[:, 1], adj[:, 0]])),
                           shape=(len(mesh.faces), len(mesh.faces)))
        components, labels = connected_components(graph, directed=False)
        sizes = np.bincount(labels)
    else:
        components, sizes = 0, np.array([], dtype=int)
    return {
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "winding_consistent": bool(mesh.is_winding_consistent),
        "boundary_edges": int(np.count_nonzero(counts == 1)),
        "nonmanifold_edges": int(np.count_nonzero(counts > 2)),
        "degenerate_faces": degenerate,
        "components": int(components),
        "largest_components": sorted(map(int, sizes), reverse=True)[:8],
        "bounds": mesh.bounds.tolist(),
    }


def boundary_loops(mesh: trimesh.Trimesh) -> list[list[int]]:
    counts = np.bincount(mesh.edges_unique_inverse, minlength=len(mesh.edges_unique))
    edges = mesh.edges_unique[counts == 1]
    neighbors: dict[int, list[int]] = {}
    for a, b in edges:
        neighbors.setdefault(int(a), []).append(int(b))
        neighbors.setdefault(int(b), []).append(int(a))
    if any(len(v) != 2 for v in neighbors.values()):
        return []
    unused = {tuple(sorted(map(int, e))) for e in edges}
    loops = []
    while unused:
        edge = next(iter(unused))
        start, current = edge
        previous = start
        loop = [start, current]
        unused.discard(edge)
        for _ in range(len(edges) + 1):
            candidates = [n for n in neighbors[current] if n != previous]
            if not candidates:
                break
            nxt = candidates[0]
            unused.discard(tuple(sorted((current, nxt))))
            if nxt == start:
                loops.append(loop)
                break
            loop.append(nxt)
            previous, current = current, nxt
    return loops


def cap_mesh(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, list[str]]:
    import mapbox_earcut

    result = mesh.copy()
    warnings = []
    loops = boundary_loops(result)
    if not loops and not result.is_watertight:
        return result, ["A borda não forma ciclos simples; fechamento automático cancelado."]
    added = []
    for loop in loops:
        if len(loop) < 3:
            continue
        pts = result.vertices[np.asarray(loop)]
        center = pts.mean(axis=0)
        _, singular, vh = np.linalg.svd(pts - center, full_matrices=False)
        projected = (pts - center) @ vh[:2].T
        scale = max(np.linalg.norm(np.ptp(projected, axis=0)), 1e-12)
        planarity = float(singular[-1] / scale) if len(singular) == 3 else 0.0
        if planarity > 0.08:
            warnings.append(f"Contorno com {len(loop)} vértices é muito não-planar ({planarity:.3f}).")
            continue
        try:
            idx = mapbox_earcut.triangulate_float64(
                np.asarray(projected, dtype=np.float64),
                np.asarray([len(loop)], dtype=np.uint32),
            ).reshape(-1, 3)
        except Exception as exc:
            warnings.append(f"Falha ao triangular contorno de {len(loop)} vértices: {exc}")
            continue
        added.extend(np.asarray(loop, dtype=np.int64)[idx].tolist())
    if added:
        result.faces = np.vstack([result.faces, np.asarray(added, dtype=np.int64)])
        result.update_faces(result.unique_faces())
        result.remove_unreferenced_vertices()
        trimesh.repair.fix_normals(result, multibody=True)
    return result, warnings


def report_is_valid(report: dict) -> bool:
    return (report["watertight"] and report["winding_consistent"]
            and report["boundary_edges"] == 0
            and report["nonmanifold_edges"] == 0
            and report["degenerate_faces"] == 0)


def conservative_repair(mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, list[str]]:
    result = mesh.copy()
    log = []
    before = len(result.faces)
    result.update_faces(result.unique_faces())
    result.update_faces(result.nondegenerate_faces())
    result.remove_unreferenced_vertices()
    result.merge_vertices()
    if len(result.faces) != before:
        log.append(f"Limpeza: {before - len(result.faces):,} faces duplicadas ou degeneradas removidas.")
    try:
        trimesh.repair.fix_winding(result)
        trimesh.repair.fix_normals(result, multibody=True)
        trimesh.repair.fill_holes(result)
        log.append("Normais, orientação e pequenos buracos foram reparados.")
    except Exception as exc:
        log.append(f"Reparo conservador parcial: {exc}")
    capped, warnings = cap_mesh(result)
    log.extend(warnings)
    return capped, log


def voxel_repair(mesh: trimesh.Trimesh, target_resolution=340) -> tuple[trimesh.Trimesh, dict]:
    """Last-resort local reconstruction. It is watertight but can soften detail."""
    longest = float(max(mesh.extents))
    pitch = max(longest / float(target_resolution), 0.06)
    voxel = mesh.voxelized(pitch)
    matrix = binary_closing(voxel.matrix, iterations=1)
    matrix = binary_fill_holes(matrix)
    grid = trimesh.voxel.VoxelGrid(matrix, transform=voxel.transform)
    rebuilt = grid.marching_cubes
    rebuilt.apply_transform(grid.transform)
    rebuilt.update_faces(rebuilt.nondegenerate_faces())
    rebuilt.update_faces(rebuilt.unique_faces())
    rebuilt.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(rebuilt, multibody=True)
    return rebuilt, {
        "method": "voxel_reconstruction",
        "pitch_mm": float(pitch),
        "maximum_surface_shift_estimate_mm": float(pitch * 1.75),
        "warning": "Reconstrução volumétrica aplicada; detalhes menores que aproximadamente dois voxels podem ser suavizados."
    }


class HairSeparator:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("HairSeparator AI 1.0 — preparação visual para impressão 3D")
        root.geometry("1220x820")
        self.mesh = None
        self.centroids = None
        self.normals = None
        self.selection = None
        self.history = []
        self.view = tk.StringVar(value="Frente")
        self.mode = tk.StringVar(value="Adicionar")
        self.visible_only = tk.BooleanVar(value=True)
        self.ai_threshold = tk.DoubleVar(value=0.64)
        self.auto_repair = tk.BooleanVar(value=True)
        self.repair_resolution = tk.IntVar(value=340)
        self.curved_graph_cut = tk.BooleanVar(value=True)
        self.ai_positive = None
        self.ai_negative = None
        self.ai_confidence = None
        self.feature_cache = None
        self.view_cache = {}
        self.reference_image = None
        self.reference_labels = None
        self.reference_id2label = None
        self.flip_reference = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Abra um STL para começar.")
        self.path = None
        self._build()

    def _build(self):
        bar = ttk.Frame(self.root, padding=8)
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="Abrir STL", command=self.open_mesh).pack(side=tk.LEFT)
        ttk.Label(bar, text="Vista:").pack(side=tk.LEFT, padx=(16, 4))
        view_box = ttk.Combobox(bar, textvariable=self.view, values=list(VIEWS), width=11, state="readonly")
        view_box.pack(side=tk.LEFT)
        view_box.bind("<<ComboboxSelected>>", lambda _e: self.redraw())
        ttk.Radiobutton(bar, text="Selecionar", variable=self.mode, value="Adicionar").pack(side=tk.LEFT, padx=(16, 2))
        ttk.Radiobutton(bar, text="Apagar", variable=self.mode, value="Remover").pack(side=tk.LEFT)
        ttk.Checkbutton(bar, text="Somente superfície visível", variable=self.visible_only).pack(side=tk.LEFT, padx=14)
        ttk.Button(bar, text="Desfazer", command=self.undo).pack(side=tk.LEFT)
        ttk.Button(bar, text="Limpar", command=self.clear).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Diagnóstico inicial", command=self.preflight).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="Separar, fechar e validar", command=self.export).pack(side=tk.RIGHT)

        ai = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        ai.pack(fill=tk.X)
        ttk.Label(ai, text="ENSINAR IA:").pack(side=tk.LEFT)
        ttk.Radiobutton(ai, text="É cabelo", variable=self.mode, value="Ensinar cabelo").pack(side=tk.LEFT, padx=4)
        ttk.Radiobutton(ai, text="Não é cabelo", variable=self.mode, value="Ensinar corpo").pack(side=tk.LEFT)
        ttk.Button(ai, text="Reconhecer cabelo", command=self.predict_ai).pack(side=tk.LEFT, padx=(10, 4))
        ttk.Button(ai, text="Analisar imagem", command=self.analyze_reference_image).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(ai, text="Espelhar foto", variable=self.flip_reference).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(ai, text="Contorno curvo", variable=self.curved_graph_cut).pack(side=tk.LEFT, padx=2)
        ttk.Label(ai, text="Confiança:").pack(side=tk.LEFT, padx=(8, 2))
        ttk.Scale(ai, from_=0.50, to=0.92, variable=self.ai_threshold, length=120,
                  command=lambda _v: self.apply_ai_threshold()).pack(side=tk.LEFT)
        ttk.Button(ai, text="Expandir", command=self.grow_selection).pack(side=tk.LEFT, padx=(12, 2))
        ttk.Button(ai, text="Retrair", command=self.shrink_selection).pack(side=tk.LEFT)
        ttk.Button(ai, text="Limpar fragmentos", command=self.remove_fragments).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(ai, text="Autocorrigir corte", variable=self.auto_repair).pack(side=tk.LEFT, padx=(8, 2))
        ttk.Button(ai, text="Salvar projeto", command=self.save_project).pack(side=tk.RIGHT)
        ttk.Button(ai, text="Carregar projeto", command=self.load_project).pack(side=tk.RIGHT, padx=2)
        ttk.Button(ai, text="Como usar", command=self.show_help).pack(side=tk.RIGHT, padx=8)

        self.progress = ttk.Progressbar(self.root, mode="indeterminate")
        self.progress.pack(fill=tk.X, padx=8)

        self.fig = Figure(figsize=(10, 7), dpi=100, facecolor="#111318")
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.root)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.lasso = LassoSelector(self.ax, onselect=self.on_lasso, button=1)
        ttk.Label(self.root, textvariable=self.status, padding=8).pack(fill=tk.X)

    def open_mesh(self):
        p = filedialog.askopenfilename(title="Abrir modelo", filetypes=[("STL", "*.stl"), ("Malhas", "*.stl *.obj *.ply")])
        if not p:
            return
        try:
            self.status.set("Carregando e unindo vértices coincidentes...")
            self.root.update_idletasks()
            loaded = trimesh.load_mesh(p, process=True)
            if isinstance(loaded, trimesh.Scene):
                loaded = trimesh.util.concatenate(tuple(loaded.geometry.values()))
            original_faces = len(loaded.faces)
            if original_faces > 1_000_000:
                self.status.set(f"Criando cópia de trabalho com 900.000 faces (original: {original_faces:,})...")
                self.root.update_idletasks()
                v, f = fast_simplification.simplify(
                    np.asarray(loaded.vertices), np.asarray(loaded.faces),
                    target_count=900_000, agg=5
                )
                loaded = trimesh.Trimesh(vertices=v, faces=f, process=True)
            self.mesh = loaded
            self.path = Path(p)
            self.centroids = self.mesh.triangles_center
            self.normals = self.mesh.face_normals
            self.selection = np.zeros(len(self.mesh.faces), dtype=bool)
            self.ai_positive = np.zeros(len(self.mesh.faces), dtype=bool)
            self.ai_negative = np.zeros(len(self.mesh.faces), dtype=bool)
            self.ai_confidence = None
            self.feature_cache = None
            self.view_cache.clear()
            self.history.clear()
            self.redraw()
            if original_faces > 1_000_000:
                messagebox.showinfo(
                    "Cópia de trabalho criada",
                    f"O original tem {original_faces:,} faces. A edição usará uma cópia em memória com "
                    f"{len(self.mesh.faces):,} faces, preservando tamanho e arquivo original."
                )
        except Exception:
            messagebox.showerror("Erro ao abrir", traceback.format_exc())

    def projected(self):
        key = self.view.get()
        cached = self.view_cache.get(key)
        if cached is not None:
            return cached
        a, b, depth, sign = VIEWS[self.view.get()]
        xy = self.centroids[:, [a, b]].copy()
        if sign < 0:
            xy[:, 0] *= -1
        d = self.centroids[:, depth] * sign
        self.view_cache[key] = (xy, d)
        return xy, d

    def visible_mask(self, xy, depth, grid=320):
        """Approximate the continuous front surface with a tolerant depth buffer.

        Keeping only the single nearest triangle in each pixel creates a dotted
        mask on dense scans.  A 3x3 maximum filter plus a physical depth band
        keeps neighboring triangles on the same visible surface.
        """
        mins, maxs = xy.min(axis=0), xy.max(axis=0)
        span = np.maximum(maxs - mins, 1e-9)
        ij = np.clip(((xy - mins) / span * (grid - 1)).astype(np.int32), 0, grid - 1)
        cell = ij[:, 0] + grid * ij[:, 1]
        zbuffer = np.full(grid * grid, -np.inf, dtype=np.float64)
        np.maximum.at(zbuffer, cell, depth)
        zbuffer = maximum_filter(zbuffer.reshape(grid, grid), size=3, mode="nearest").ravel()
        tolerance = max(float(np.linalg.norm(self.mesh.extents)) * 0.01, 0.20)
        return depth >= zbuffer[cell] - tolerance

    def component_summary(self, mask):
        ids = np.flatnonzero(mask)
        if not len(ids):
            return 0, []
        local = np.full(len(mask), -1, dtype=np.int64)
        local[ids] = np.arange(len(ids))
        adj = self.mesh.face_adjacency
        keep = mask[adj[:, 0]] & mask[adj[:, 1]]
        edges = local[adj[keep]]
        graph = coo_matrix((np.ones(len(edges) * 2),
                            (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])),
                           shape=(len(ids), len(ids)))
        count, labels = connected_components(graph, directed=False)
        sizes = sorted(map(int, np.bincount(labels)), reverse=True)
        return int(count), sizes

    def redraw(self):
        self.ax.clear()
        self.ax.set_facecolor("#111318")
        self.ax.set_aspect("equal", adjustable="box")
        self.ax.axis("off")
        if self.mesh is None:
            self.canvas.draw_idle()
            return
        xy, depth = self.projected()
        visible = self.visible_mask(xy, depth)
        ids = np.flatnonzero(visible)
        if len(ids) > 120000:
            ids = ids[np.linspace(0, len(ids) - 1, 120000).astype(int)]
        colors = np.full(len(ids), "#c9ced6", dtype=object)
        if self.ai_confidence is not None:
            confidence = self.ai_confidence[ids]
            colors = np.array(["#%02x%02x%02x" % (int(45 + 210*p), int(80 + 90*(1-p)), int(210 - 150*p))
                               for p in confidence], dtype=object)
        colors[self.selection[ids]] = "#ff7a16"
        colors[self.ai_positive[ids]] = "#28d17c"
        colors[self.ai_negative[ids]] = "#e83f8c"
        self.ax.scatter(xy[ids, 0], xy[ids, 1], s=0.6, c=colors, linewidths=0)
        self.ax.set_title(f"{self.view.get()} — desenhe um laço com o mouse", color="white")
        self.canvas.draw_idle()
        pos = int(self.ai_positive.sum())
        neg = int(self.ai_negative.sum())
        self.status.set(f"{self.path.name} — {len(self.mesh.faces):,} faces — seleção: {self.selection.sum():,} — exemplos IA: {pos:,} cabelo / {neg:,} corpo")

    def on_lasso(self, vertices):
        if self.mesh is None or len(vertices) < 3:
            return
        xy, depth = self.projected()
        inside = MplPath(vertices).contains_points(xy)
        if self.visible_only.get():
            inside &= self.visible_mask(xy, depth)
        self.history.append(self.selection.copy())
        if len(self.history) > 12:
            self.history.pop(0)
        mode = self.mode.get()
        if mode == "Adicionar":
            self.selection |= inside
        elif mode == "Remover":
            self.selection &= ~inside
        elif mode == "Ensinar cabelo":
            self.ai_positive |= inside
            self.ai_negative &= ~inside
        elif mode == "Ensinar corpo":
            self.ai_negative |= inside
            self.ai_positive &= ~inside
        self.redraw()

    def adjacency_step(self, mask, grow=True):
        adj = self.mesh.face_adjacency
        result = mask.copy()
        if grow:
            hit = mask[adj[:, 0]] | mask[adj[:, 1]]
            result[adj[hit].ravel()] = True
        else:
            border = mask[adj[:, 0]] ^ mask[adj[:, 1]]
            selected_border = adj[border][mask[adj[border]]]
            result[selected_border] = False
        return result

    def grow_selection(self):
        if self.selection is None:
            return
        self.history.append(self.selection.copy())
        self.selection = self.adjacency_step(self.selection, True)
        self.redraw()

    def shrink_selection(self):
        if self.selection is None:
            return
        self.history.append(self.selection.copy())
        self.selection = self.adjacency_step(self.selection, False)
        self.redraw()

    def selection_components(self, mask):
        ids = np.flatnonzero(mask)
        if not len(ids):
            return ids, np.array([], dtype=int), np.array([], dtype=int)
        local = np.full(len(mask), -1, dtype=np.int64)
        local[ids] = np.arange(len(ids))
        adj = self.mesh.face_adjacency
        keep = mask[adj[:, 0]] & mask[adj[:, 1]]
        edges = local[adj[keep]]
        graph = coo_matrix((np.ones(len(edges) * 2),
                            (np.r_[edges[:, 0], edges[:, 1]], np.r_[edges[:, 1], edges[:, 0]])),
                           shape=(len(ids), len(ids)))
        _, labels = connected_components(graph, directed=False)
        return ids, labels, np.bincount(labels)

    def remove_fragments(self):
        if self.selection is None or not self.selection.any():
            return
        ids, labels, sizes = self.selection_components(self.selection)
        minimum = max(20, int(self.selection.sum() * 0.00005))
        keep = sizes[labels] >= minimum
        cleaned = np.zeros_like(self.selection)
        cleaned[ids[keep]] = True
        removed = int(self.selection.sum() - cleaned.sum())
        self.history.append(self.selection.copy())
        self.selection = cleaned
        self.redraw()
        self.status.set(f"Limpeza concluída: {removed:,} faces em fragmentos menores que {minimum} foram removidas.")

    def compute_features(self):
        if self.feature_cache is not None:
            return self.feature_cache
        c = self.centroids
        center = c.mean(axis=0)
        scale = np.maximum(np.ptp(c, axis=0), 1e-9)
        pos = (c - center) / scale
        radial = np.linalg.norm(pos[:, :2], axis=1, keepdims=True)
        curvature_sum = np.zeros(len(c), dtype=np.float32)
        curvature_n = np.zeros(len(c), dtype=np.float32)
        adj = self.mesh.face_adjacency
        dots = np.clip(np.einsum('ij,ij->i', self.normals[adj[:, 0]], self.normals[adj[:, 1]]), -1, 1)
        angles = np.arccos(dots).astype(np.float32)
        np.add.at(curvature_sum, adj[:, 0], angles)
        np.add.at(curvature_sum, adj[:, 1], angles)
        np.add.at(curvature_n, adj[:, 0], 1)
        np.add.at(curvature_n, adj[:, 1], 1)
        curvature = (curvature_sum / np.maximum(curvature_n, 1))[:, None]
        self.feature_cache = np.column_stack([pos, self.normals, radial, curvature]).astype(np.float32)
        return self.feature_cache

    def predict_ai(self):
        if self.mesh is None:
            return
        positive = np.flatnonzero(self.ai_positive)
        negative = np.flatnonzero(self.ai_negative)
        if len(positive) < 30 or len(negative) < 30:
            messagebox.showwarning("Faltam exemplos",
                                   "Marque pelo menos algumas regiões verdes como cabelo e regiões rosas como corpo/rosto/roupa em duas ou mais vistas.")
            return
        self.progress.start(12)
        self.status.set("IA local: extraindo forma, normais e curvatura...")
        self.root.update_idletasks()
        try:
            features = self.compute_features()
            rng = np.random.default_rng(42)
            limit = 70_000
            if len(positive) > limit:
                positive = rng.choice(positive, limit, replace=False)
            if len(negative) > limit:
                negative = rng.choice(negative, limit, replace=False)
            train = np.r_[positive, negative]
            target = np.r_[np.ones(len(positive), dtype=np.uint8), np.zeros(len(negative), dtype=np.uint8)]
            model = ExtraTreesClassifier(n_estimators=96, max_depth=22, min_samples_leaf=3,
                                         class_weight="balanced", n_jobs=-1, random_state=42)
            self.status.set(f"IA local: aprendendo com {len(train):,} faces marcadas...")
            self.root.update_idletasks()
            model.fit(features[train], target)
            confidence = np.empty(len(features), dtype=np.float32)
            for start in range(0, len(features), 200_000):
                confidence[start:start+200_000] = model.predict_proba(features[start:start+200_000])[:, 1]
                self.root.update_idletasks()
            adj = self.mesh.face_adjacency
            for _ in range(2):
                total = np.zeros(len(confidence), dtype=np.float32)
                count = np.zeros(len(confidence), dtype=np.float32)
                np.add.at(total, adj[:, 0], confidence[adj[:, 1]])
                np.add.at(total, adj[:, 1], confidence[adj[:, 0]])
                np.add.at(count, adj[:, 0], 1)
                np.add.at(count, adj[:, 1], 1)
                confidence = 0.78 * confidence + 0.22 * total / np.maximum(count, 1)
            confidence[self.ai_positive] = 1.0
            confidence[self.ai_negative] = 0.0
            self.ai_confidence = confidence
            if self.curved_graph_cut.get():
                self.status.set("Contorno curvo: buscando a fronteira de menor custo sobre a malha...")
                self.root.update_idletasks()
                try:
                    previous = self.selection.copy()
                    self.selection = self.graph_cut_selection(confidence)
                    self.history.append(previous)
                    self.redraw()
                except Exception as exc:
                    self.status.set(f"Graph cut indisponível ({exc}); usando limiar de confiança.")
                    self.apply_ai_threshold(force=True)
            else:
                self.apply_ai_threshold(force=True)
        except Exception:
            messagebox.showerror("Falha no reconhecimento", traceback.format_exc())
        finally:
            self.progress.stop()

    def graph_cut_selection(self, probability):
        """Seeded graph cut. Sharp/concave face boundaries are cheaper seams."""
        import maxflow
        p = np.clip(np.asarray(probability, dtype=np.float64), 1e-5, 1 - 1e-5)
        n = len(p)
        adj = self.mesh.face_adjacency
        graph = maxflow.Graph[float](n, len(adj) * 2)
        graph.add_nodes(n)
        hair_cost = -np.log(p)
        body_cost = -np.log(1.0 - p)
        hair_cost[self.ai_positive] = 0.0
        body_cost[self.ai_positive] = 80.0
        hair_cost[self.ai_negative] = 80.0
        body_cost[self.ai_negative] = 0.0
        for i in range(n):
            graph.add_tedge(i, float(body_cost[i]), float(hair_cost[i]))
        dots = np.clip(np.einsum('ij,ij->i', self.normals[adj[:, 0]], self.normals[adj[:, 1]]), -1, 1)
        angle = np.arccos(dots)
        # Smooth areas are expensive to cut; sharp folds are natural boundaries.
        pairwise = 0.025 + 2.2 * np.exp(-np.square(angle / 0.48))
        for (a, b), weight in zip(adj, pairwise):
            graph.add_edge(int(a), int(b), float(weight), float(weight))
        graph.maxflow()
        selected = np.fromiter((graph.get_segment(i) == 0 for i in range(n)), dtype=bool, count=n)
        selected[self.ai_positive] = True
        selected[self.ai_negative] = False
        return selected

    def analyze_reference_image(self):
        if self.mesh is None:
            messagebox.showinfo("Abra o modelo", "Abra o STL antes de analisar a imagem de referência.")
            return
        p = filedialog.askopenfilename(title="Imagem de referência",
                                       filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp")])
        if not p:
            return
        self.progress.start(12)
        self.status.set("Visão local: carregando modelo de segmentação humana...")
        self.root.update_idletasks()
        try:
            import torch
            from transformers import AutoImageProcessor, AutoModelForSemanticSegmentation
            model_id = "mattmdjaga/segformer_b2_clothes"
            image = Image.open(p).convert("RGB")
            processor = AutoImageProcessor.from_pretrained(model_id)
            model = AutoModelForSemanticSegmentation.from_pretrained(model_id)
            model.eval()
            inputs = processor(images=image, return_tensors="pt")
            with torch.inference_mode():
                logits = model(**inputs).logits
                logits = torch.nn.functional.interpolate(logits, size=(image.height, image.width),
                                                          mode="bilinear", align_corners=False)
            labels = logits.argmax(dim=1)[0].cpu().numpy().astype(np.int16)
            id2label = {int(k): str(v).lower() for k, v in model.config.id2label.items()}
            hair_ids = [k for k, v in id2label.items() if "hair" in v]
            if not hair_ids:
                raise RuntimeError("O modelo de visão não forneceu a classe cabelo.")
            self.reference_image = image
            self.reference_labels = labels
            self.reference_id2label = id2label
            self.project_reference_labels()
            self.show_reference_preview()
        except Exception:
            messagebox.showerror("Falha ao analisar imagem", traceback.format_exc())
        finally:
            self.progress.stop()

    def project_reference_labels(self):
        labels = self.reference_labels
        if labels is None:
            return
        xy, depth = self.projected()
        visible = self.visible_mask(xy, depth)
        mins, maxs = xy.min(axis=0), xy.max(axis=0)
        norm = (xy - mins) / np.maximum(maxs - mins, 1e-9)
        px = np.clip((norm[:, 0] * (labels.shape[1] - 1)).astype(int), 0, labels.shape[1] - 1)
        if self.flip_reference.get():
            px = labels.shape[1] - 1 - px
        py = np.clip(((1.0 - norm[:, 1]) * (labels.shape[0] - 1)).astype(int), 0, labels.shape[0] - 1)
        sampled = labels[py, px]
        hair_ids = {k for k, v in self.reference_id2label.items() if "hair" in v}
        protected_words = ("face", "arm", "dress", "skirt", "pants", "upper", "shoe", "leg", "belt")
        protected_ids = {k for k, v in self.reference_id2label.items() if any(w in v for w in protected_words)}
        hair = visible & np.isin(sampled, list(hair_ids))
        protected = visible & np.isin(sampled, list(protected_ids))
        self.ai_positive |= hair
        self.ai_negative |= protected
        self.ai_positive &= ~self.ai_negative
        self.redraw()
        self.status.set(f"Imagem analisada: {hair.sum():,} faces ensinadas como cabelo e {protected.sum():,} como anatomia/roupa.")

    def show_reference_preview(self):
        image = np.asarray(self.reference_image).copy()
        hair_ids = [k for k, v in self.reference_id2label.items() if "hair" in v]
        mask = np.isin(self.reference_labels, hair_ids)
        overlay = image.astype(np.float32)
        overlay[mask] = overlay[mask] * 0.35 + np.array([40, 220, 120]) * 0.65
        preview = Image.fromarray(np.uint8(np.clip(overlay, 0, 255)))
        preview.thumbnail((680, 680))
        win = tk.Toplevel(self.root)
        win.title("Análise da imagem — verde = cabelo reconhecido")
        photo = ImageTk.PhotoImage(preview)
        label = ttk.Label(win, image=photo)
        label.image = photo
        label.pack(padx=8, pady=8)
        ttk.Label(win, text="A máscara foi projetada na vista 3D atual como exemplos para a IA geométrica.").pack(padx=8, pady=(0, 8))

    def apply_ai_threshold(self, force=False):
        if self.ai_confidence is None:
            return
        if force:
            self.history.append(self.selection.copy())
        self.selection = self.ai_confidence >= float(self.ai_threshold.get())
        self.selection[self.ai_positive] = True
        self.selection[self.ai_negative] = False
        self.redraw()

    def save_project(self):
        if self.mesh is None:
            return
        p = filedialog.asksaveasfilename(defaultextension=".hairproj.npz", filetypes=[("Projeto HairSeparator", "*.npz")])
        if not p:
            return
        np.savez_compressed(p, source=str(self.path), faces=len(self.mesh.faces), selection=self.selection,
                            positive=self.ai_positive, negative=self.ai_negative,
                            confidence=self.ai_confidence if self.ai_confidence is not None else np.array([]))
        self.status.set(f"Projeto salvo em {p}")

    def load_project(self):
        if self.mesh is None:
            messagebox.showinfo("Abra o modelo", "Abra primeiro o mesmo STL usado no projeto.")
            return
        p = filedialog.askopenfilename(filetypes=[("Projeto HairSeparator", "*.npz")])
        if not p:
            return
        data = np.load(p, allow_pickle=False)
        if int(data['faces']) != len(self.mesh.faces):
            messagebox.showerror("Modelo incompatível", "O projeto pertence a uma malha com outra quantidade de faces.")
            return
        self.selection = data['selection'].astype(bool)
        self.ai_positive = data['positive'].astype(bool)
        self.ai_negative = data['negative'].astype(bool)
        self.ai_confidence = data['confidence'].astype(np.float32) if len(data['confidence']) else None
        self.redraw()

    def show_help(self):
        messagebox.showinfo(
            "Fluxo recomendado",
            "1. Abra o STL e clique em Diagnóstico inicial.\n"
            "2. Em duas ou mais vistas, use É cabelo para marcar mechas evidentes.\n"
            "3. Opcional: escolha a vista correspondente e use Analisar imagem. A segmentação é local.\n"
            "4. Use Não é cabelo no rosto, braços, vestido e base.\n"
            "5. Clique Reconhecer cabelo. Verde e rosa são exemplos; laranja é a seleção.\n"
            "6. Ajuste Confiança, corrija com Selecionar/Apagar e use Expandir/Retrair.\n"
            "7. Limpe fragmentos, salve o projeto e só então separe e valide.\n\n"
            "O modelo e o treinamento permanecem neste computador."
        )

    def undo(self):
        if self.history:
            self.selection = self.history.pop()
            self.redraw()

    def clear(self):
        if self.selection is not None:
            self.history.append(self.selection.copy())
            self.selection[:] = False
            self.redraw()

    def preflight(self):
        if self.mesh is None:
            return
        report = mesh_report(self.mesh.copy())
        messagebox.showinfo(
            "Diagnóstico inicial",
            f"Faces: {report['faces']:,}\n"
            f"Fechada: {'sim' if report['watertight'] else 'não'}\n"
            f"Arestas abertas: {report['boundary_edges']:,}\n"
            f"Arestas não-manifold: {report['nonmanifold_edges']:,}\n"
            f"Faces degeneradas: {report['degenerate_faces']:,}\n"
            f"Componentes: {report['components']:,}"
        )

    def export(self):
        if self.mesh is None or not self.selection.any() or self.selection.all():
            messagebox.showwarning("Seleção incompleta", "Selecione parte do modelo como cabelo antes de exportar.")
            return
        folder = filedialog.askdirectory(title="Pasta de saída")
        if not folder:
            return
        try:
            self.status.set("Separando, fechando e validando...")
            self.root.update_idletasks()
            repair_log = []
            ids, labels, sizes = self.selection_components(self.selection)
            patch_count = len(sizes)
            if patch_count > 80:
                order = np.argsort(sizes)[::-1]
                cumulative = np.cumsum(sizes[order])
                wanted = order[cumulative <= max(int(sizes.sum() * 0.997), int(sizes[order[0]]))]
                wanted = order[:max(1, min(40, len(wanted) + 1))]
                cleaned = np.zeros_like(self.selection)
                cleaned[ids[np.isin(labels, wanted)]] = True
                removed = int(self.selection.sum() - cleaned.sum())
                self.selection = cleaned
                repair_log.append(f"Máscara: {removed:,} faces distribuídas em fragmentos residuais foram removidas automaticamente.")
                self.redraw()
            hair = self.mesh.submesh([np.flatnonzero(self.selection)], append=True, repair=False)
            body = self.mesh.submesh([np.flatnonzero(~self.selection)], append=True, repair=False)
            out = Path(folder) / f"HairSeparator_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            out.mkdir(parents=False, exist_ok=False)
            raw_reports = {"cabelo": mesh_report(hair.copy()), "corpo": mesh_report(body.copy())}
            hair, hair_log = conservative_repair(hair)
            body, body_log = conservative_repair(body)
            repair_log.extend(["Cabelo: " + x for x in hair_log])
            repair_log.extend(["Corpo: " + x for x in body_log])
            hair_report = mesh_report(hair)
            body_report = mesh_report(body)
            reconstruction = {}
            if self.auto_repair.get() and not report_is_valid(hair_report):
                self.status.set("Autocorreção: reconstruindo volume do cabelo...")
                self.root.update_idletasks()
                hair.export(out / "diagnostico_cabelo_antes_reconstrucao.stl")
                hair, reconstruction["cabelo"] = voxel_repair(hair, self.repair_resolution.get())
                hair_report = mesh_report(hair)
            if self.auto_repair.get() and not report_is_valid(body_report):
                self.status.set("Autocorreção: reconstruindo volume do corpo...")
                self.root.update_idletasks()
                body.export(out / "diagnostico_corpo_antes_reconstrucao.stl")
                body, reconstruction["corpo"] = voxel_repair(body, self.repair_resolution.get())
                body_report = mesh_report(body)
            reports = {"entrada_separada": raw_reports, "cabelo": hair_report, "corpo": body_report,
                       "repair_log": repair_log, "reconstruction": reconstruction}
            report_path = out / "validacao_separacao.json"
            report_path.write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
            valid = report_is_valid(hair_report) and report_is_valid(body_report)
            if not valid:
                self.status.set(f"Exportação bloqueada: veja {report_path.name}")
                messagebox.showerror("Malha ainda inválida",
                                     "O programa bloqueou os STL porque uma ou ambas as peças falharam na validação.\n\n"
                                     f"Relatório: {report_path}")
                return
            hair_path = out / "cabelo.stl"
            body_path = out / "corpo.stl"
            hair.export(hair_path)
            body.export(body_path)
            serialized = {
                "cabelo": mesh_report(trimesh.load_mesh(hair_path, process=True)),
                "corpo": mesh_report(trimesh.load_mesh(body_path, process=True)),
            }
            reports["validacao_apos_gravar_stl"] = serialized
            report_path.write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
            if not (report_is_valid(serialized["cabelo"]) and report_is_valid(serialized["corpo"])):
                hair_path.unlink(missing_ok=True)
                body_path.unlink(missing_ok=True)
                self.status.set("A serialização STL alterou a topologia; arquivos finais removidos.")
                messagebox.showerror("Falha após gravar STL",
                                     f"A segunda validação falhou. Os STL finais foram removidos.\nRelatório: {report_path}")
                return
            self.status.set("Concluído: cabelo.stl e corpo.stl passaram na validação.")
            messagebox.showinfo("Pronto para revisão no fatiador",
                                "As duas peças foram exportadas e passaram nas verificações topológicas.")
        except Exception:
            messagebox.showerror("Erro na separação", traceback.format_exc())


def main():
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    HairSeparator(root)
    root.mainloop()


if __name__ == "__main__":
    main()
