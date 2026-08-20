# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

SPECDIR = Path(SPECPATH)

datas = [
    (str(SPECDIR / "consolidado" / "web" / "templates"), "consolidado/web/templates"),
    (str(SPECDIR / "consolidado" / "web" / "static"), "consolidado/web/static"),
]
binaries = []
hiddenimports = collect_submodules("consolidado")
hiddenimports += [
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "multipart",
    "itsdangerous",
    "fastexcel",
    "polars",
    "openpyxl",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
]

for pkg in ("customtkinter", "polars", "fastexcel", "uvicorn", "fastapi", "starlette", "jinja2"):
    collected = collect_all(pkg)
    datas += collected[0]
    binaries += collected[1]
    hiddenimports += collected[2]

a = Analysis(
    ["main.py"],
    pathex=[str(SPECDIR)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter.test", "matplotlib", "numpy.tests"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ConsolidadoHumanidades",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ConsolidadoHumanidades",
)
