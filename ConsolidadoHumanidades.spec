# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = [
    'consolidado',
    'consolidado.gui',
    'consolidado.gui.app',
    'consolidado.gui.dialogs',
    'consolidado.gui.dialogs.configuracion',
    'consolidado.gui.dialogs.documento',
    'consolidado.gui.dialogs.info_prioridad',
    'consolidado.gui.dialogs.priorizado',
    'consolidado.gui.dialogs.vista_previa',
    'consolidado.core.cli',
    'consolidado.core.pipeline',
    'consolidado.core.prioridad',
    'fastexcel',
    'polars',
    'openpyxl',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
]
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ConsolidadoHumanidades',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
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
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ConsolidadoHumanidades',
)
