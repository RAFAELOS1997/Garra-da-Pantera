from __future__ import annotations

# Verificacao automatica de atualizacoes
try:
    from atualizador import verificar_atualizacao
    verificar_atualizacao(silencioso=True)
except Exception as _upd_err:
    print(f"[Atualizador] Ignorado: {_upd_err}")

import json
import re
import sys
import traceback
import unicodedata
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
from matplotlib.collections import LineCollection
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


def safe_slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "alvo"


class GarraDaPantera:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("Garra da Pantera 2.3 — corte semântico inteligente para impressão 3D")
        root.geometry("1480x900")
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
        self.curve_sensitivity = tk.DoubleVar(value=18.0)
        self.confidence_text = tk.StringVar(value="64%")
        self.angle_text = tk.StringVar(value="18°")
        self.ai_positive = None
        self.ai_negative = None
        self.ai_confidence = None
        self.feature_cache = None
        self.view_cache = {}
        self.reference_image = None
        self.reference_target_mask = None
        self.reference_protected_mask = None
        self.target_prompt = tk.StringVar(value="cabelo")
        self.flip_reference = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Abra um STL para começar.")
        self.mesh_stats = tk.StringVar(value="NENHUM MODELO")
        self.selection_stats = tk.StringVar(value="SELEÇÃO  0%")
        self.tool_text = tk.StringVar(value="FERRAMENTA  SELECIONAR")
        self.show_cut_line = tk.BooleanVar(value=True)
        self.path = None
        self._build()
        self.mode.trace_add("write", self._update_tool_badge)
        self._bind_shortcuts()

    def _configure_style(self):
        self.root.configure(bg="#0b0e14")
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure(".", background="#121722", foreground="#e8ecf3", fieldbackground="#1a2130",
                        bordercolor="#2a3447", lightcolor="#2a3447", darkcolor="#080a0f",
                        font=("Segoe UI", 10))
        style.configure("TFrame", background="#121722")
        style.configure("Card.TFrame", background="#151b27")
        style.configure("TLabel", background="#121722", foreground="#d5dbe6")
        style.configure("Muted.TLabel", foreground="#8994a7", font=("Segoe UI", 9))
        style.configure("Section.TLabel", foreground="#f2f5fa", font=("Segoe UI Semibold", 10))
        style.configure("Badge.TLabel", background="#202838", foreground="#9aa8bd", padding=(8, 4))
        style.configure("Status.TLabel", background="#0d1119", foreground="#aeb8c8", padding=(12, 8))
        style.configure("TButton", background="#202838", foreground="#e8ecf3", padding=(10, 7), borderwidth=0)
        style.map("TButton", background=[("active", "#2b374c"), ("pressed", "#111722")])
        style.configure("Accent.TButton", background="#ed168c", foreground="white",
                        font=("Segoe UI Semibold", 10), padding=(14, 9))
        style.map("Accent.TButton", background=[("active", "#ff329f"), ("pressed", "#c80b70")])
        style.configure("Secondary.TButton", background="#253047", foreground="#dbe4f2")
        style.configure("TRadiobutton", background="#151b27", foreground="#ced5e0", padding=3)
        style.configure("TCheckbutton", background="#151b27", foreground="#ced5e0", padding=3)
        style.map("TRadiobutton", background=[("active", "#151b27")])
        style.map("TCheckbutton", background=[("active", "#151b27")])
        style.configure("TEntry", fieldbackground="#0e131d", foreground="#f4f6fa", padding=8, borderwidth=1)
        style.configure("TCombobox", fieldbackground="#0e131d", background="#202838", foreground="#f4f6fa", padding=6)
        style.configure("Horizontal.TScale", background="#151b27", troughcolor="#2a3447")
        style.configure("Horizontal.TProgressbar", troughcolor="#111722", background="#ed168c", thickness=3)
        style.configure("TPanedwindow", background="#0b0e14")

    def _card(self, parent, title, description=None):
        card = ttk.Frame(parent, style="Card.TFrame", padding=14)
        ttk.Label(card, text=title.upper(), style="Section.TLabel").pack(anchor="w")
        if description:
            ttk.Label(card, text=description, style="Muted.TLabel", wraplength=300).pack(anchor="w", pady=(2, 10))
        return card

    def _bind_shortcuts(self):
        self.root.bind("<Control-o>", lambda _e: self.open_mesh())
        self.root.bind("<Control-s>", lambda _e: self.save_project())
        self.root.bind("<Control-e>", lambda _e: self.export())
        self.root.bind("<Control-z>", lambda _e: self.undo())
        self.root.bind("<Escape>", lambda _e: self.clear())
        for key, view_name in zip(("1", "2", "3", "4", "5"), VIEWS):
            self.root.bind(key, lambda _e, name=view_name: (self.view.set(name), self.redraw()))

    def _update_tool_badge(self, *_args):
        names = {"Adicionar": "SELECIONAR", "Remover": "APAGAR",
                 "Ensinar alvo": "ENSINAR ALVO", "Proteger": "PROTEGER"}
        self.tool_text.set(f"FERRAMENTA  {names.get(self.mode.get(), self.mode.get()).upper()}")

    def _build(self):
        self._configure_style()
        header = tk.Frame(self.root, bg="#0d1119", height=76, padx=18, pady=12)
        header.pack(fill=tk.X)
        brand = tk.Frame(header, bg="#0d1119")
        brand.pack(side=tk.LEFT)
        tk.Label(brand, text="GARRA DA PANTERA", bg="#0d1119", fg="#ffffff",
                 font=("Segoe UI Semibold", 18)).pack(anchor="w")
        tk.Label(brand, text="CORTE SEMÂNTICO 3D  •  LOCAL  •  V2.3", bg="#0d1119", fg="#ed168c",
                 font=("Segoe UI Semibold", 9)).pack(anchor="w")
        actions = ttk.Frame(header)
        actions.pack(side=tk.RIGHT, pady=3)
        ttk.Button(actions, text="?  Como usar", command=self.show_help).pack(side=tk.RIGHT, padx=(6, 0))
        ttk.Button(actions, text="Salvar projeto", command=self.save_project).pack(side=tk.RIGHT, padx=3)
        ttk.Button(actions, text="Carregar projeto", command=self.load_project).pack(side=tk.RIGHT, padx=3)

        steps = tk.Frame(self.root, bg="#111722", padx=18, pady=8)
        steps.pack(fill=tk.X)
        for number, label in (("1", "ABRIR MODELO"), ("2", "DEFINIR ALVO"), ("3", "REFINAR CORTE"), ("4", "VALIDAR E EXPORTAR")):
            item = tk.Frame(steps, bg="#111722")
            item.pack(side=tk.LEFT, padx=(0, 28))
            tk.Label(item, text=number, bg="#ed168c", fg="white", width=2,
                     font=("Segoe UI Semibold", 9)).pack(side=tk.LEFT)
            tk.Label(item, text=label, bg="#111722", fg="#9eabba",
                     font=("Segoe UI Semibold", 9), padx=7).pack(side=tk.LEFT)

        body = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        sidebar_shell = ttk.Frame(body, style="Card.TFrame", width=365)
        sidebar_shell.pack_propagate(False)
        body.add(sidebar_shell, weight=0)
        side_canvas = tk.Canvas(sidebar_shell, bg="#121722", highlightthickness=0, width=345)
        side_scroll = ttk.Scrollbar(sidebar_shell, orient=tk.VERTICAL, command=side_canvas.yview)
        side_canvas.configure(yscrollcommand=side_scroll.set)
        side_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        side_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sidebar = ttk.Frame(side_canvas, style="Card.TFrame")
        sidebar_window = side_canvas.create_window((0, 0), window=sidebar, anchor="nw")
        sidebar.bind("<Configure>", lambda _e: side_canvas.configure(scrollregion=side_canvas.bbox("all")))
        side_canvas.bind("<Configure>", lambda e: side_canvas.itemconfigure(sidebar_window, width=e.width))
        side_canvas.bind("<MouseWheel>", lambda e: side_canvas.yview_scroll(int(-e.delta / 120), "units"))
        viewer = ttk.Frame(body, style="Card.TFrame")
        body.add(viewer, weight=1)

        file_card = self._card(sidebar, "Modelo", "Abra a malha e escolha a vista correspondente à imagem.")
        file_card.pack(fill=tk.X, padx=7, pady=(7, 4))
        file_row = ttk.Frame(file_card, style="Card.TFrame")
        file_row.pack(fill=tk.X)
        ttk.Button(file_row, text="＋ Abrir malha", command=self.open_mesh, style="Accent.TButton").pack(side=tk.LEFT)
        ttk.Button(file_row, text="Diagnóstico", command=self.preflight).pack(side=tk.LEFT, padx=6)
        view_row = ttk.Frame(file_card, style="Card.TFrame")
        view_row.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(view_row, text="Vista", style="Muted.TLabel").pack(side=tk.LEFT)
        view_box = ttk.Combobox(view_row, textvariable=self.view, values=list(VIEWS), width=13, state="readonly")
        view_box.pack(side=tk.RIGHT)
        view_box.bind("<<ComboboxSelected>>", lambda _e: self.redraw())

        target_card = self._card(sidebar, "Alvo inteligente", "Descreva qualquer elemento visível na imagem.")
        target_card.pack(fill=tk.X, padx=7, pady=4)
        ttk.Entry(target_card, textvariable=self.target_prompt, font=("Segoe UI Semibold", 12)).pack(fill=tk.X)
        image_row = ttk.Frame(target_card, style="Card.TFrame")
        image_row.pack(fill=tk.X, pady=(9, 3))
        ttk.Button(image_row, text="Analisar imagem", command=self.analyze_reference_image,
                   style="Secondary.TButton").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(image_row, text="Reconhecer no 3D", command=self.predict_ai,
                   style="Accent.TButton").pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6, 0))
        ttk.Checkbutton(target_card, text="Espelhar imagem", variable=self.flip_reference).pack(anchor="w")

        teach_card = self._card(sidebar, "Pincel semântico", "Desenhe laços no visor. Verde ensina; rosa protege.")
        teach_card.pack(fill=tk.X, padx=7, pady=4)
        modes = ttk.Frame(teach_card, style="Card.TFrame")
        modes.pack(fill=tk.X)
        for text_label, value in (("＋ Selecionar", "Adicionar"), ("− Apagar", "Remover"),
                                  ("● É o alvo", "Ensinar alvo"), ("◆ Proteger", "Proteger")):
            ttk.Radiobutton(modes, text=text_label, variable=self.mode, value=value).pack(anchor="w")
        ttk.Checkbutton(teach_card, text="Somente superfície visível", variable=self.visible_only).pack(anchor="w", pady=(5, 0))

        refine_card = self._card(sidebar, "Contorno e refino")
        refine_card.pack(fill=tk.X, padx=7, pady=4)
        ttk.Checkbutton(refine_card, text="Contorno curvo inteligente", variable=self.curved_graph_cut).pack(anchor="w")
        angle_row = ttk.Frame(refine_card, style="Card.TFrame")
        angle_row.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(angle_row, text="Sensibilidade angular", style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Label(angle_row, textvariable=self.angle_text, style="Badge.TLabel").pack(side=tk.RIGHT)
        ttk.Scale(refine_card, from_=4, to=60, variable=self.curve_sensitivity,
                  command=lambda v: self.angle_text.set(f"{float(v):.0f}°")).pack(fill=tk.X)
        conf_row = ttk.Frame(refine_card, style="Card.TFrame")
        conf_row.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(conf_row, text="Confiança da seleção", style="Muted.TLabel").pack(side=tk.LEFT)
        ttk.Label(conf_row, textvariable=self.confidence_text, style="Badge.TLabel").pack(side=tk.RIGHT)
        ttk.Scale(refine_card, from_=0.50, to=0.92, variable=self.ai_threshold,
                  command=self._on_confidence).pack(fill=tk.X)
        edit_row = ttk.Frame(refine_card, style="Card.TFrame")
        edit_row.pack(fill=tk.X, pady=(8, 0))
        for label, command in (("Expandir", self.grow_selection), ("Retrair", self.shrink_selection),
                               ("Fragmentos", self.remove_fragments)):
            ttk.Button(edit_row, text=label, command=command).pack(side=tk.LEFT, padx=(0, 4))
        history_row = ttk.Frame(refine_card, style="Card.TFrame")
        history_row.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(history_row, text="↶ Desfazer", command=self.undo).pack(side=tk.LEFT)
        ttk.Button(history_row, text="Limpar seleção", command=self.clear).pack(side=tk.LEFT, padx=5)

        export_card = self._card(sidebar, "Saída segura")
        export_card.pack(fill=tk.X, padx=7, pady=4)
        ttk.Checkbutton(export_card, text="Autocorrigir malhas inválidas", variable=self.auto_repair).pack(anchor="w")
        ttk.Button(export_card, text="CORTAR, CORRIGIR E VALIDAR", command=self.export,
                   style="Accent.TButton").pack(fill=tk.X, pady=(8, 0))
        ttk.Label(sidebar, text="ATALHOS  Ctrl+O abrir  •  Ctrl+S salvar  •  Ctrl+E exportar\n"
                                "1–5 vistas  •  Ctrl+Z desfazer  •  Esc limpar",
                  style="Muted.TLabel", justify=tk.CENTER).pack(fill=tk.X, padx=12, pady=(6, 14))

        viewer_head = ttk.Frame(viewer, style="Card.TFrame", padding=(12, 9))
        viewer_head.pack(fill=tk.X)
        ttk.Label(viewer_head, text="VISUALIZAÇÃO DA MALHA", style="Section.TLabel").pack(side=tk.LEFT)
        ttk.Label(viewer_head, textvariable=self.mesh_stats, style="Badge.TLabel").pack(side=tk.LEFT, padx=(14, 4))
        ttk.Label(viewer_head, textvariable=self.selection_stats, style="Badge.TLabel").pack(side=tk.LEFT, padx=4)
        ttk.Label(viewer_head, textvariable=self.tool_text, style="Badge.TLabel").pack(side=tk.LEFT, padx=4)
        for color, label in (("#ff7a16", "Seleção"), ("#28d17c", "Alvo"), ("#e83f8c", "Protegido")):
            tk.Label(viewer_head, text=f" ● {label}", bg="#151b27", fg=color,
                     font=("Segoe UI Semibold", 9)).pack(side=tk.RIGHT, padx=6)

        viewport_tools = ttk.Frame(viewer, style="Card.TFrame", padding=(10, 5))
        viewport_tools.pack(fill=tk.X)
        ttk.Label(viewport_tools, text="VISTAS", style="Muted.TLabel").pack(side=tk.LEFT, padx=(2, 7))
        for label, view_name in (("F", "Frente"), ("C", "Costas"), ("D", "Direita"),
                                 ("E", "Esquerda"), ("T", "Topo")):
            ttk.Button(viewport_tools, text=label, width=3,
                       command=lambda name=view_name: self.set_view(name)).pack(side=tk.LEFT, padx=2)
        ttk.Separator(viewport_tools, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=9)
        ttk.Button(viewport_tools, text="Enquadrar tudo", command=self.redraw).pack(side=tk.LEFT, padx=2)
        ttk.Button(viewport_tools, text="Focar seleção", command=self.focus_selection).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(viewport_tools, text="Linha de corte", variable=self.show_cut_line,
                        command=self.redraw).pack(side=tk.RIGHT, padx=4)

        self.progress = ttk.Progressbar(viewer, mode="indeterminate")
        self.progress.pack(fill=tk.X)
        self.fig = Figure(figsize=(10, 7), dpi=100, facecolor="#0d1119")
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=viewer)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self.canvas.get_tk_widget().configure(bg="#0d1119", highlightthickness=0)
        self.lasso = LassoSelector(self.ax, onselect=self.on_lasso, button=1)
        self.canvas.mpl_connect("scroll_event", self._zoom_view)
        ttk.Label(self.root, textvariable=self.status, style="Status.TLabel").pack(fill=tk.X)

    def _on_confidence(self, value):
        self.confidence_text.set(f"{float(value) * 100:.0f}%")
        self.apply_ai_threshold()

    def _zoom_view(self, event):
        if event.xdata is None or event.ydata is None:
            return
        factor = 0.82 if event.button == "up" else 1.22
        x0, x1 = self.ax.get_xlim()
        y0, y1 = self.ax.get_ylim()
        self.ax.set_xlim(event.xdata + (x0 - event.xdata) * factor,
                         event.xdata + (x1 - event.xdata) * factor)
        self.ax.set_ylim(event.ydata + (y0 - event.ydata) * factor,
                         event.ydata + (y1 - event.ydata) * factor)
        self.canvas.draw_idle()

    def set_view(self, name):
        self.view.set(name)
        self.redraw()

    def focus_selection(self):
        if self.mesh is None or not self.selection.any():
            return
        xy, _depth = self.projected()
        points = xy[self.selection]
        low, high = points.min(axis=0), points.max(axis=0)
        span = np.maximum(high - low, np.linalg.norm(self.mesh.extents) * 0.02)
        margin = span * 0.12
        self.ax.set_xlim(low[0] - margin[0], high[0] + margin[0])
        self.ax.set_ylim(low[1] - margin[1], high[1] + margin[1])
        self.canvas.draw_idle()

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
        self.ax.set_facecolor("#0d1119")
        self.ax.set_aspect("equal", adjustable="box")
        self.ax.axis("off")
        if self.mesh is None:
            self.ax.text(0.5, 0.57, "⬡", transform=self.ax.transAxes, ha="center", va="center",
                         fontsize=70, color="#263044")
            self.ax.text(0.5, 0.43, "ABRA UMA MALHA PARA COMEÇAR", transform=self.ax.transAxes,
                         ha="center", va="center", fontsize=14, fontweight="bold", color="#dbe2ed")
            self.ax.text(0.5, 0.36, "STL  •  OBJ  •  PLY\nUse Ctrl+O ou o botão Abrir malha",
                         transform=self.ax.transAxes, ha="center", va="center", fontsize=10,
                         color="#7f8ba0", linespacing=1.8)
            self.canvas.draw_idle()
            return
        xy, depth = self.projected()
        visible = self.visible_mask(xy, depth)
        ids = np.flatnonzero(visible)
        if len(ids) > 120000:
            ids = ids[np.linspace(0, len(ids) - 1, 120000).astype(int)]
        sampled_depth = depth[ids]
        depth_range = max(float(np.ptp(sampled_depth)), 1e-9)
        depth_light = (sampled_depth - sampled_depth.min()) / depth_range
        view_depth_axis = VIEWS[self.view.get()][2]
        light = np.clip(0.38 + 0.36 * depth_light + 0.26 * np.abs(self.normals[ids, view_depth_axis]), 0, 1)
        colors = np.array(["#%02x%02x%02x" % (int(75 + 100*v), int(84 + 105*v), int(100 + 115*v))
                           for v in light], dtype=object)
        if self.ai_confidence is not None:
            confidence = self.ai_confidence[ids]
            colors = np.array(["#%02x%02x%02x" % (int(45 + 210*p), int(80 + 90*(1-p)), int(210 - 150*p))
                               for p in confidence], dtype=object)
        colors[self.selection[ids]] = "#ff7a16"
        colors[self.ai_positive[ids]] = "#28d17c"
        colors[self.ai_negative[ids]] = "#e83f8c"
        point_size = 1.2 if len(ids) < 70000 else 0.72
        self.ax.scatter(xy[ids, 0], xy[ids, 1], s=point_size, c=colors, linewidths=0, rasterized=True)
        cut_length = 0.0
        if self.selection.any() and not self.selection.all():
            adj = self.mesh.face_adjacency
            crossing = self.selection[adj[:, 0]] ^ self.selection[adj[:, 1]]
            all_edge_ids = self.mesh.face_adjacency_edges[crossing]
            if len(all_edge_ids):
                cut_length = float(np.linalg.norm(
                    self.mesh.vertices[all_edge_ids[:, 0]] - self.mesh.vertices[all_edge_ids[:, 1]], axis=1
                ).sum())
            edge_ids = all_edge_ids
            if len(edge_ids) > 25000:
                edge_ids = edge_ids[np.linspace(0, len(edge_ids) - 1, 25000).astype(int)]
            if self.show_cut_line.get() and len(edge_ids):
                axis_a, axis_b, _axis_depth, sign = VIEWS[self.view.get()]
                vertices = self.mesh.vertices[edge_ids][:, :, [axis_a, axis_b]].copy()
                if sign < 0:
                    vertices[:, :, 0] *= -1
                seam = LineCollection(vertices, colors="#ffb11b", linewidths=1.15,
                                      alpha=0.92, zorder=6, rasterized=True)
                self.ax.add_collection(seam)
        self.ax.set_title(f"{self.view.get().upper()}   •   DESENHE UM LAÇO PARA SELECIONAR",
                          color="#aeb8c8", fontsize=10, fontweight="bold", pad=14)
        self.canvas.draw_idle()
        pos = int(self.ai_positive.sum())
        neg = int(self.ai_negative.sum())
        selected = int(self.selection.sum())
        percent = selected / max(len(self.mesh.faces), 1) * 100
        self.mesh_stats.set(f"{len(self.mesh.faces):,} FACES")
        cut_info = f"  •  CORTE {cut_length:.1f}" if cut_length else ""
        self.selection_stats.set(f"SELEÇÃO  {percent:.1f}%{cut_info}")
        self.status.set(f"{self.path.name}  •  seleção {selected:,} faces  •  exemplos {pos:,} alvo / {neg:,} protegidos  •  roda do mouse: zoom")

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
        elif mode == "Ensinar alvo":
            self.ai_positive |= inside
            self.ai_negative &= ~inside
        elif mode == "Proteger":
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
                                   "Marque pelo menos algumas regiões verdes como alvo e regiões rosas como partes protegidas em duas ou mais vistas.")
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
        """Graph cut guiado por sementes, dobra, concavidade e comprimento da aresta."""
        import maxflow
        p = np.clip(np.asarray(probability, dtype=np.float64), 1e-5, 1 - 1e-5)
        n = len(p)
        adj = self.mesh.face_adjacency
        graph = maxflow.Graph[float](n, len(adj) * 2)
        graph.add_nodes(n)
        target_cost = -np.log(p)
        protected_cost = -np.log(1.0 - p)
        target_cost[self.ai_positive] = 0.0
        protected_cost[self.ai_positive] = 80.0
        target_cost[self.ai_negative] = 80.0
        protected_cost[self.ai_negative] = 0.0
        for i in range(n):
            graph.add_tedge(i, float(protected_cost[i]), float(target_cost[i]))
        dots = np.clip(np.einsum('ij,ij->i', self.normals[adj[:, 0]], self.normals[adj[:, 1]]), -1, 1)
        angle = np.arccos(dots)
        sensitivity = np.deg2rad(max(float(self.curve_sensitivity.get()), 1.0))
        edge_vertices = self.mesh.face_adjacency_edges
        edge_length = np.linalg.norm(self.mesh.vertices[edge_vertices[:, 0]] - self.mesh.vertices[edge_vertices[:, 1]], axis=1)
        edge_length /= max(float(np.median(edge_length)), 1e-9)
        convex = np.asarray(self.mesh.face_adjacency_convex, dtype=bool)
        # Dobras fortes e côncavas são costuras naturais. A normalização pelo
        # comprimento reduz atalhos serrilhados por muitas arestas curtas.
        fold_cost = np.exp(-np.square(angle / sensitivity))
        concavity_factor = np.where(convex, 1.0, 0.55)
        pairwise = 0.02 + 2.4 * fold_cost * concavity_factor * np.clip(edge_length, 0.35, 3.0)
        for (a, b), weight in zip(adj, pairwise):
            graph.add_edge(int(a), int(b), float(weight), float(weight))
        graph.maxflow()
        selected = np.fromiter((graph.get_segment(i) == 0 for i in range(n)), dtype=bool, count=n)
        selected[self.ai_positive] = True
        selected[self.ai_negative] = False
        self.last_boundary_metrics = self.boundary_metrics(selected)
        return selected

    def boundary_metrics(self, mask):
        adj = self.mesh.face_adjacency
        crossing = mask[adj[:, 0]] ^ mask[adj[:, 1]]
        edges = self.mesh.face_adjacency_edges[crossing]
        if not len(edges):
            return {"arestas": 0, "comprimento": 0.0, "angulo_medio_graus": 0.0}
        lengths = np.linalg.norm(self.mesh.vertices[edges[:, 0]] - self.mesh.vertices[edges[:, 1]], axis=1)
        dots = np.clip(np.einsum('ij,ij->i', self.normals[adj[crossing, 0]], self.normals[adj[crossing, 1]]), -1, 1)
        return {"arestas": int(len(edges)), "comprimento": float(lengths.sum()),
                "angulo_medio_graus": float(np.degrees(np.arccos(dots)).mean())}

    def analyze_reference_image(self):
        if self.mesh is None:
            messagebox.showinfo("Abra o modelo", "Abra o STL antes de analisar a imagem de referência.")
            return
        p = filedialog.askopenfilename(title="Imagem de referência",
                                       filetypes=[("Imagens", "*.png *.jpg *.jpeg *.webp")])
        if not p:
            return
        self.progress.start(12)
        prompt = self.target_prompt.get().strip()
        if not prompt:
            messagebox.showwarning("Informe o alvo", "Escreva o que deseja separar, por exemplo: espada, capa, cabelo ou base.")
            return
        self.status.set(f"Visão local: procurando '{prompt}' na imagem...")
        self.root.update_idletasks()
        try:
            import torch
            image = Image.open(p).convert("RGB")
            target, protected, engine = self.segment_image(image, prompt, torch)
            self.reference_image = image
            self.reference_target_mask = target
            self.reference_protected_mask = protected
            self.project_reference_labels()
            self.show_reference_preview(engine)
        except Exception:
            messagebox.showerror("Falha ao analisar imagem", traceback.format_exc())
        finally:
            self.progress.stop()

    def segment_image(self, image, prompt, torch):
        """Use precise human parsing when possible, otherwise open-vocabulary CLIPSeg."""
        from transformers import (AutoImageProcessor, AutoModelForSemanticSegmentation,
                                  CLIPSegProcessor, CLIPSegForImageSegmentation)
        normalized = unicodedata.normalize("NFKD", prompt.lower()).encode("ascii", "ignore").decode("ascii")
        aliases = {
            "cabelo": ["hair"], "hair": ["hair"], "chapeu": ["hat"], "hat": ["hat"],
            "oculos": ["sunglasses"], "rosto": ["face"], "face": ["face"],
            "blusa": ["upper-clothes"], "camisa": ["upper-clothes"], "saia": ["skirt"],
            "calca": ["pants"], "vestido": ["dress"], "cinto": ["belt"],
            "sapato": ["left-shoe", "right-shoe"], "sapatos": ["left-shoe", "right-shoe"],
            "perna": ["left-leg", "right-leg"], "pernas": ["left-leg", "right-leg"],
            "braco": ["left-arm", "right-arm"], "bracos": ["left-arm", "right-arm"],
            "bolsa": ["bag"], "cachecol": ["scarf"],
        }
        if normalized in aliases:
            model_id = "mattmdjaga/segformer_b2_clothes"
            processor = AutoImageProcessor.from_pretrained(model_id)
            model = AutoModelForSemanticSegmentation.from_pretrained(model_id).eval()
            with torch.inference_mode():
                logits = model(**processor(images=image, return_tensors="pt")).logits
                logits = torch.nn.functional.interpolate(logits, size=(image.height, image.width),
                                                          mode="bilinear", align_corners=False)
            labels = logits.argmax(dim=1)[0].cpu().numpy()
            id2label = {int(k): str(v).lower() for k, v in model.config.id2label.items()}
            ids = [k for k, v in id2label.items() if v in aliases[normalized]]
            target = np.isin(labels, ids)
            protected = (labels != 0) & ~target
            return target, protected, "análise anatômica especializada"

        vision_terms = {
            "espada": "sword", "capa": "cape", "base": "pedestal base", "escudo": "shield",
            "arma": "weapon", "coroa": "crown", "asa": "wing", "asas": "wings",
            "cauda": "tail", "mao": "hand", "maos": "hands", "cabeca": "head",
            "colar": "necklace", "armadura": "armor", "capacete": "helmet", "lanca": "spear",
            "arco": "bow", "flecha": "arrow", "mochila": "backpack", "acessorio": "accessory",
        }
        vision_prompt = vision_terms.get(normalized, prompt)
        model_id = "CIDAS/clipseg-rd64-refined"
        processor = CLIPSegProcessor.from_pretrained(model_id)
        model = CLIPSegForImageSegmentation.from_pretrained(model_id).eval()
        inputs = processor(text=[vision_prompt], images=[image], padding=True, return_tensors="pt")
        with torch.inference_mode():
            logits = model(**inputs).logits
            if logits.ndim == 2:
                logits = logits[None, None]
            elif logits.ndim == 3:
                logits = logits[:, None]
            probability = torch.sigmoid(torch.nn.functional.interpolate(
                logits, size=(image.height, image.width), mode="bilinear", align_corners=False
            ))[0, 0].cpu().numpy()
        target = probability >= 0.42
        target = binary_fill_holes(binary_closing(target, iterations=2))
        protected = probability <= 0.10
        return target, protected, "segmentação aberta por texto (CLIPSeg)"

    def project_reference_labels(self):
        target_mask = self.reference_target_mask
        if target_mask is None:
            return
        xy, depth = self.projected()
        visible = self.visible_mask(xy, depth)
        mins, maxs = xy.min(axis=0), xy.max(axis=0)
        norm = (xy - mins) / np.maximum(maxs - mins, 1e-9)
        px = np.clip((norm[:, 0] * (target_mask.shape[1] - 1)).astype(int), 0, target_mask.shape[1] - 1)
        if self.flip_reference.get():
            px = target_mask.shape[1] - 1 - px
        py = np.clip(((1.0 - norm[:, 1]) * (target_mask.shape[0] - 1)).astype(int), 0, target_mask.shape[0] - 1)
        target = visible & target_mask[py, px]
        protected = visible & self.reference_protected_mask[py, px]
        self.ai_positive |= target
        self.ai_negative |= protected
        self.ai_positive &= ~self.ai_negative
        self.redraw()
        self.status.set(f"Imagem analisada: {target.sum():,} faces ensinadas como alvo e {protected.sum():,} protegidas.")

    def show_reference_preview(self, engine):
        image = np.asarray(self.reference_image).copy()
        overlay = image.astype(np.float32)
        overlay[self.reference_protected_mask] = overlay[self.reference_protected_mask] * 0.68 + np.array([232, 63, 140]) * 0.32
        overlay[self.reference_target_mask] = overlay[self.reference_target_mask] * 0.30 + np.array([40, 220, 120]) * 0.70
        preview = Image.fromarray(np.uint8(np.clip(overlay, 0, 255)))
        preview.thumbnail((680, 680))
        win = tk.Toplevel(self.root)
        win.title(f"Garra da Pantera — verde = {self.target_prompt.get().strip()}")
        photo = ImageTk.PhotoImage(preview)
        label = ttk.Label(win, image=photo)
        label.image = photo
        label.pack(padx=8, pady=8)
        ttk.Label(win, text=f"{engine}. Verde = alvo; rosa = proteção. A máscara foi projetada na vista 3D atual.").pack(padx=8, pady=(0, 8))

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
        p = filedialog.asksaveasfilename(defaultextension=".pantera.npz", filetypes=[("Projeto Garra da Pantera", "*.npz")])
        if not p:
            return
        np.savez_compressed(p, source=str(self.path), faces=len(self.mesh.faces), selection=self.selection,
                            positive=self.ai_positive, negative=self.ai_negative,
                            confidence=self.ai_confidence if self.ai_confidence is not None else np.array([]),
                            target_prompt=np.asarray(self.target_prompt.get()))
        self.status.set(f"Projeto salvo em {p}")

    def load_project(self):
        if self.mesh is None:
            messagebox.showinfo("Abra o modelo", "Abra primeiro o mesmo STL usado no projeto.")
            return
        p = filedialog.askopenfilename(filetypes=[("Projeto Garra da Pantera", "*.npz"), ("Projetos antigos", "*.hairproj.npz")])
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
        if 'target_prompt' in data:
            self.target_prompt.set(str(data['target_prompt']))
        self.redraw()

    def show_help(self):
        messagebox.showinfo(
            "Fluxo recomendado",
            "1. Abra a malha e clique em Diagnóstico inicial.\n"
            "2. Escreva o alvo: espada, capa, cabelo, braço, base ou qualquer elemento visível.\n"
            "3. Escolha a vista correspondente e use Analisar imagem. A visão roda localmente.\n"
            "4. Em duas ou mais vistas, ensine exceções com É o alvo e Proteger.\n"
            "5. Clique Reconhecer no 3D. Verde e rosa são exemplos; laranja é a seleção.\n"
            "6. Ajuste Confiança, corrija com Selecionar/Apagar e use Expandir/Retrair.\n"
            "7. Limpe fragmentos, salve o projeto e só então separe e valide.\n\n"
            "Para classes humanas, o programa usa análise anatômica especializada; para qualquer outro texto, usa segmentação aberta.\n"
            "A imagem, o modelo e o treinamento permanecem neste computador."
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
            messagebox.showwarning("Seleção incompleta", "Selecione o alvo e preserve ao menos uma parte restante antes de exportar.")
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
            target_mesh = self.mesh.submesh([np.flatnonzero(self.selection)], append=True, repair=False)
            remainder_mesh = self.mesh.submesh([np.flatnonzero(~self.selection)], append=True, repair=False)
            out = Path(folder) / f"GarraDaPantera_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            out.mkdir(parents=False, exist_ok=False)
            raw_reports = {"alvo": mesh_report(target_mesh.copy()), "restante": mesh_report(remainder_mesh.copy())}
            target_mesh, target_log = conservative_repair(target_mesh)
            remainder_mesh, remainder_log = conservative_repair(remainder_mesh)
            repair_log.extend(["Alvo: " + x for x in target_log])
            repair_log.extend(["Restante: " + x for x in remainder_log])
            target_report = mesh_report(target_mesh)
            remainder_report = mesh_report(remainder_mesh)
            reconstruction = {}
            if self.auto_repair.get() and not report_is_valid(target_report):
                self.status.set("Autocorreção: reconstruindo o volume do alvo...")
                self.root.update_idletasks()
                target_mesh.export(out / "diagnostico_alvo_antes_reconstrucao.stl")
                target_mesh, reconstruction["alvo"] = voxel_repair(target_mesh, self.repair_resolution.get())
                target_report = mesh_report(target_mesh)
            if self.auto_repair.get() and not report_is_valid(remainder_report):
                self.status.set("Autocorreção: reconstruindo o volume restante...")
                self.root.update_idletasks()
                remainder_mesh.export(out / "diagnostico_restante_antes_reconstrucao.stl")
                remainder_mesh, reconstruction["restante"] = voxel_repair(remainder_mesh, self.repair_resolution.get())
                remainder_report = mesh_report(remainder_mesh)
            reports = {"aplicativo": "Garra da Pantera", "alvo_solicitado": self.target_prompt.get(),
                       "entrada_separada": raw_reports, "alvo": target_report, "restante": remainder_report,
                       "metricas_contorno": self.boundary_metrics(self.selection),
                       "sensibilidade_angular_graus": float(self.curve_sensitivity.get()),
                       "repair_log": repair_log, "reconstruction": reconstruction}
            report_path = out / "validacao_separacao.json"
            report_path.write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
            valid = report_is_valid(target_report) and report_is_valid(remainder_report)
            if not valid:
                self.status.set(f"Exportação bloqueada: veja {report_path.name}")
                messagebox.showerror("Malha ainda inválida",
                                     "O programa bloqueou os STL porque uma ou ambas as peças falharam na validação.\n\n"
                                     f"Relatório: {report_path}")
                return
            target_path = out / f"alvo_{safe_slug(self.target_prompt.get())}.stl"
            remainder_path = out / "restante.stl"
            target_mesh.export(target_path)
            remainder_mesh.export(remainder_path)
            serialized = {
                "alvo": mesh_report(trimesh.load_mesh(target_path, process=True)),
                "restante": mesh_report(trimesh.load_mesh(remainder_path, process=True)),
            }
            reports["validacao_apos_gravar_stl"] = serialized
            report_path.write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
            if not (report_is_valid(serialized["alvo"]) and report_is_valid(serialized["restante"])):
                target_path.unlink(missing_ok=True)
                remainder_path.unlink(missing_ok=True)
                self.status.set("A serialização STL alterou a topologia; arquivos finais removidos.")
                messagebox.showerror("Falha após gravar STL",
                                     f"A segunda validação falhou. Os STL finais foram removidos.\nRelatório: {report_path}")
                return
            self.status.set(f"Concluído: {target_path.name} e restante.stl passaram na validação.")
            messagebox.showinfo("Pronto para revisão no fatiador",
                                "As duas peças foram exportadas e passaram nas verificações topológicas.")
        except Exception:
            messagebox.showerror("Erro na separação", traceback.format_exc())


def main():
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    GarraDaPantera(root)
    root.mainloop()


if __name__ == "__main__":
    main()
