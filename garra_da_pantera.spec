# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build spec for a standalone GarraDaPantera.exe that needs no
Python installed on the user's machine.

Built with `pyinstaller garra_da_pantera.spec --noconfirm` from a venv that
has requirements-build.txt installed. Produces a one-folder (--onedir style)
build under dist/GarraDaPantera/, chosen over --onefile because this app
bundles torch/transformers: a one-file build would have to self-extract
several GB into a temp folder on every launch, which is far slower to start
than opening a folder directly.

`--collect-all` is used liberally for the packages most known to trip up
PyInstaller's static import analysis (dynamic/plugin-style imports, or
required non-Python data files): torch, torchvision, transformers, sklearn,
skimage, trimesh, matplotlib, scipy. Model weights themselves are NOT
bundled — they still download on first use exactly as documented in
README.md, so the app also works offline once cached.
"""

from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas = []
binaries = []
hiddenimports = [
    # Small compiled extensions imported lazily inside the app (per
    # AGENTS.md's "keep heavy imports lazy") that PyInstaller's static
    # analysis still needs to be told about explicitly, since they are
    # imported deep inside function bodies or by a dependency's own
    # runtime-selected optional backend rather than at module top level.
    "mapbox_earcut",
    "fast_simplification",
    "maxflow",
    "pymeshfix",
    "manifold3d",
]

for package in (
    "torch",
    "torchvision",
    "transformers",
    "sklearn",
    "skimage",
    "trimesh",
    "matplotlib",
    "scipy",
):
    pkg_datas, pkg_binaries, pkg_hiddenimports = collect_all(package)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hiddenimports

a = Analysis(
    ["garra_da_pantera.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="GarraDaPantera",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="GarraDaPantera",
)
