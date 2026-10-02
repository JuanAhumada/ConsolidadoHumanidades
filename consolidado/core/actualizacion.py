"""Actualización de los instalables (Windows / macOS / Linux). No aplica al código en desarrollo."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

from consolidado.paths import PROJECT_ROOT
from consolidado.version import APP_VERSION

_REPO_RAW = (
    "https://raw.githubusercontent.com/JuanAhumada/ConsolidadoHumanidades/Torre"
)
_REPO_ZIP = (
    "https://github.com/JuanAhumada/ConsolidadoHumanidades/raw/Torre/release"
)
_REPO_MEDIA = (
    "https://media.githubusercontent.com/media/JuanAhumada/ConsolidadoHumanidades/Torre/release"
)
_SKIP_DIRS = {"datos", "salida", ".venv", "venv", "__pycache__", ".git"}
_SKIP_FILES = {"config.json", "config_fabrica.json"}
_LANZADORES = (
    "Abrir.command",
    "Instalar.command",
    "Abrir.sh",
    "Instalar.sh",
    "LEEME.txt",
    "VERSION.txt",
)


def es_paquete_actualizable() -> bool:
    if getattr(sys, "frozen", False):
        return True
    marca = (os.environ.get("CONSOLIDADO_LOCAL") or "").strip().lower()
    return marca in {"1", "true", "yes", "si", "sí"}


def plataforma_paquete() -> str:
    if sys.platform.startswith("win"):
        return "Windows"
    if sys.platform == "darwin":
        return "macOS"
    return "Linux"


def clave_version(texto: str) -> tuple[int, ...]:
    nums = [int(p) for p in re.findall(r"\d+", str(texto or ""))]
    return tuple(nums) if nums else (0,)


def _ua() -> str:
    return f"BienestarEstudiantil/{APP_VERSION}"


def _http_get(url: str, *, timeout: int) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": _ua(),
            "Accept": "application/octet-stream",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _es_puntero_lfs(data: bytes) -> bool:
    cabeza = data[:240]
    return b"git-lfs.github.com" in cabeza or cabeza.startswith(b"version https://git-lfs")


def _descargar_zip(url: str, nombre: str) -> bytes:
    data = _http_get(url, timeout=600)
    if _es_puntero_lfs(data):
        data = _http_get(f"{_REPO_MEDIA}/{nombre}", timeout=600)
    if _es_puntero_lfs(data) or len(data) < 10_000:
        raise ValueError(
            "La descarga no es el instalable. Compruebe la conexión o baje el ZIP a mano."
        )
    return data


def _version_remota() -> str:
    raw = _http_get(f"{_REPO_RAW}/consolidado/version.py", timeout=20).decode(
        "utf-8", "replace"
    )
    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', raw)
    if not m:
        raise ValueError("No se pudo leer la versión publicada.")
    return m.group(1).strip()


def consultar_actualizacion() -> dict[str, Any]:
    plat = plataforma_paquete()
    zip_nombre = f"ConsolidadoHumanidades-{plat}.zip"
    base = {
        "paquete": es_paquete_actualizable(),
        "actual": APP_VERSION,
        "remota": None,
        "disponible": False,
        "plataforma": plat,
        "url": f"{_REPO_ZIP}/{zip_nombre}",
        "zip": zip_nombre,
    }
    if not base["paquete"]:
        return base
    remota = _version_remota()
    base["remota"] = remota
    base["disponible"] = clave_version(remota) > clave_version(APP_VERSION)
    return base


def _carpeta_trabajo() -> Path:
    ruta = PROJECT_ROOT / "datos" / "actualizacion"
    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


def _localizar_contenido(raiz: Path) -> Path:
    candidatos = [
        raiz / "ConsolidadoHumanidades" / "app",
        raiz / "app",
        raiz / "ConsolidadoHumanidades",
        raiz,
    ]
    hijos = [p for p in raiz.iterdir() if p.is_dir()]
    if len(hijos) == 1:
        candidatos = [
            hijos[0] / "app",
            hijos[0] / "ConsolidadoHumanidades",
            hijos[0],
        ] + candidatos
    for c in candidatos:
        if not c.is_dir():
            continue
        if (c / "main.py").is_file():
            return c
        if (c / "_internal").is_dir() and list(c.glob("ConsolidadoHumanidades.exe")):
            return c
    raise ValueError("El paquete descargado no tiene la estructura esperada.")


def _copiar_paquete(origen: Path, destino: Path) -> None:
    destino.mkdir(parents=True, exist_ok=True)
    for item in origen.iterdir():
        if item.name in _SKIP_DIRS or item.name in _SKIP_FILES:
            continue
        if item.suffix.lower() in {".db", ".db-journal"}:
            continue
        dest = destino / item.name
        if item.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(
                item,
                dest,
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
            )
        else:
            shutil.copy2(item, dest)
    _copiar_lanzadores(origen, destino)


def _copiar_lanzadores(origen_app: Path, destino_app: Path) -> None:
    padre_origen = origen_app.parent
    padre_dest = destino_app.parent
    if padre_origen == padre_dest:
        return
    if not any((padre_origen / n).exists() for n in _LANZADORES):
        return
    for nombre in _LANZADORES:
        src = padre_origen / nombre
        if src.is_file():
            shutil.copy2(src, padre_dest / nombre)
    bundle = padre_origen / "Consolidado Humanidades.app"
    if bundle.is_dir():
        dest_bundle = padre_dest / "Consolidado Humanidades.app"
        if dest_bundle.exists():
            shutil.rmtree(dest_bundle)
        shutil.copytree(bundle, dest_bundle)


def _script_reinicio_windows(origen: Path, destino: Path) -> Path:
    bat = _carpeta_trabajo() / "reiniciar.bat"
    exe = destino / "ConsolidadoHumanidades.exe"
    texto = f"""@echo off
setlocal
timeout /t 4 /nobreak >nul
robocopy "{origen}" "{destino}" /E /XD datos salida .venv venv __pycache__ /XF config.json config_fabrica.json /NFL /NDL /NJH /NJS /nc /ns /np
if exist "{exe}" start "" "{exe}"
endlocal
"""
    bat.write_text(texto, encoding="utf-8")
    return bat


def _reinstalar_deps() -> None:
    venv_py = PROJECT_ROOT / ".venv" / "bin" / "python"
    req = PROJECT_ROOT / "requirements.txt"
    if not venv_py.is_file() or not req.is_file():
        return
    filtrado = PROJECT_ROOT / ".requirements-update.txt"
    lineas = [
        ln
        for ln in req.read_text(encoding="utf-8").splitlines()
        if "pyinstaller" not in ln.lower()
    ]
    filtrado.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    try:
        subprocess.run(
            [str(venv_py), "-m", "pip", "install", "-r", str(filtrado)],
            check=False,
            timeout=600,
        )
    finally:
        try:
            filtrado.unlink()
        except OSError:
            pass


def _programar_reinicio_unix() -> None:
    raiz = PROJECT_ROOT.parent if PROJECT_ROOT.name == "app" else PROJECT_ROOT
    if sys.platform == "darwin":
        abrir = raiz / "Abrir.command"
        bundle = raiz / "Consolidado Humanidades.app"
        if abrir.is_file():
            lanzar = f'exec /bin/bash "{abrir}"'
        elif bundle.is_dir():
            lanzar = f'open "{bundle}"'
        else:
            return
    else:
        abrir = raiz / "Abrir.sh"
        if not abrir.is_file():
            return
        lanzar = f'exec /bin/bash "{abrir}"'
    script = _carpeta_trabajo() / "reiniciar.sh"
    script.write_text(
        f"""#!/bin/bash
sleep 3
cd "{raiz}"
{lanzar}
""",
        encoding="utf-8",
    )
    subprocess.Popen(
        ["/bin/bash", str(script)],
        cwd=str(raiz),
        start_new_session=True,
    )


def aplicar_actualizacion() -> dict[str, Any]:
    if not es_paquete_actualizable():
        raise ValueError(
            "La búsqueda de actualizaciones solo está en los instalables de Windows, Mac y Linux."
        )
    info = consultar_actualizacion()
    if not info.get("disponible"):
        return {
            "ok": True,
            "reinicia": False,
            "mensaje": f"Ya está en la última versión ({APP_VERSION}).",
            **info,
        }

    trabajo = _carpeta_trabajo()
    zip_path = trabajo / info["zip"]
    zip_path.write_bytes(_descargar_zip(info["url"], info["zip"]))

    staging = trabajo / "staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(staging)
    origen = _localizar_contenido(staging)

    if sys.platform.startswith("win") and getattr(sys, "frozen", False):
        bat = _script_reinicio_windows(origen, PROJECT_ROOT)
        flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
            subprocess, "DETACHED_PROCESS", 0
        )
        subprocess.Popen(
            ["cmd", "/c", str(bat)],
            cwd=str(trabajo),
            creationflags=flags,
            close_fds=True,
        )
        return {
            "ok": True,
            "reinicia": True,
            "mensaje": f"Se descargó {info['remota']}. La aplicación se cerrará y volverá a abrir.",
            **info,
        }

    _copiar_paquete(origen, PROJECT_ROOT)
    _reinstalar_deps()
    _programar_reinicio_unix()
    return {
        "ok": True,
        "reinicia": True,
        "mensaje": f"Se instaló {info['remota']}. La aplicación se reiniciará.",
        **info,
    }
