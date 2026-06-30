"""Rutas base del proyecto (directorio que contiene config.json)."""

from __future__ import annotations

import sys
from pathlib import Path


def resolver_project_root() -> Path:
    """
    En desarrollo: carpeta del repo (donde está config.json).
    En .exe: carpeta donde está el ejecutable (datos y config junto al .exe).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


PROJECT_ROOT = resolver_project_root()
