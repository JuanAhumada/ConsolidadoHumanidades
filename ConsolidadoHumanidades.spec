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
    "tkinter",
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

def _escribir_icono() -> str | None:
    png = SPECDIR / "consolidado" / "web" / "static" / "favicon.png"
    ico = SPECDIR / "empaque" / "icono.ico"
    if not png.is_file():
        return str(ico) if ico.is_file() else None
    from PIL import Image
    imagen = Image.open(png).convert("RGBA")
    ico.parent.mkdir(parents=True, exist_ok=True)
    imagen.save(
        ico,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)],
    )
    return str(ico)


ICONO = _escribir_icono()

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
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=ICONO,
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
