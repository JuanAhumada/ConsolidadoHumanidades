"""
Raíz del proyecto.

En desarrollo: carpeta del repo (config.json). En .exe: carpeta del ejecutable,
para que datos/ y config viajen junto al binario.
"""

from __future__ import annotations

import sys
from pathlib import Path


def _meipass() -> Path | None:
    raw = getattr(sys, "_MEIPASS", None)
    return Path(raw) if raw else None


def resolver_project_root() -> Path:
    """
    En desarrollo: carpeta del repo (donde está config.json).
    En .exe: carpeta donde está el ejecutable (datos y config junto al .exe).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resolver_bundle_dir() -> Path:
    """Recursos empaquetados (plantillas, estáticos). En .exe es _MEIPASS."""
    if getattr(sys, "frozen", False):
        return _meipass() or Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = resolver_project_root()
BUNDLE_DIR = resolver_bundle_dir()
