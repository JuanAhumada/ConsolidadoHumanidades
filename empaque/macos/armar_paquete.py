"""Arma los ZIP de Mac y Linux (instalador local, no binario nativo).

Se puede ejecutar en Windows. PyInstaller no cruza de Win32 a Darwin ni a Linux.
"""

from __future__ import annotations

import re
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consolidado.version import APP_VERSION  # noqa: E402

MACOS_DIR = Path(__file__).resolve().parent
LINUX_DIR = ROOT / "empaque" / "linux"
DESTINO = ROOT / "release" / "ConsolidadoHumanidades-macOS.zip"
DESTINO_LINUX = ROOT / "release" / "ConsolidadoHumanidades-Linux.zip"
CARPETA_ZIP = "ConsolidadoHumanidades"

ARCHIVOS_RAIZ = (
    "main.py",
    "requirements.txt",
    "config.json",
    "config_fabrica.json",
)
DIR_SKIP = {
    ".git",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".cursor",
    "dist",
    "build",
    ".eggs",
}
SUFIJOS_SKIP = {".pyc", ".pyo", ".db", ".db-journal", ".log"}
EJECUTABLES = {".command", ".sh"}


def _mtime_tuple(ruta: Path) -> tuple[int, int, int, int, int, int]:
    st = ruta.stat().st_mtime
    return time.localtime(st)[:6]


def _zip_info(arcname: str, ruta: Path | None = None, *, executable: bool = False) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(arcname.replace("\\", "/"))
    info.date_time = _mtime_tuple(ruta) if ruta and ruta.exists() else time.localtime()[:6]
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    modo = 0o755 if executable else 0o644
    info.external_attr = modo << 16
    return info


def _es_ejecutable(ruta: Path) -> bool:
    if ruta.suffix.lower() in EJECUTABLES:
        return True
    return ruta.name == "ConsolidadoHumanidades" and "MacOS" in ruta.parts


def _bytes_texto(ruta: Path) -> bytes:
    data = ruta.read_bytes()
    if _es_ejecutable(ruta) or ruta.suffix.lower() in {".plist", ".txt", ".sh", ".command"}:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return data


def _escribir(zf: zipfile.ZipFile, ruta: Path, arcname: str) -> None:
    data = _bytes_texto(ruta)
    zf.writestr(_zip_info(arcname, ruta, executable=_es_ejecutable(ruta)), data)


def _copiar_arbol(zf: zipfile.ZipFile, origen: Path, prefijo: str) -> None:
    for item in origen.rglob("*"):
        if not item.is_file():
            continue
        if any(parte in DIR_SKIP for parte in item.parts):
            continue
        if item.suffix.lower() in SUFIJOS_SKIP:
            continue
        rel = item.relative_to(origen).as_posix()
        _escribir(zf, item, f"{prefijo}/{rel}")


def _info_plist(version: str) -> bytes:
    plantilla = (MACOS_DIR / "Consolidado Humanidades.app" / "Contents" / "Info.plist").read_text(
        encoding="utf-8"
    )
    plantilla = re.sub(
        r"(<key>CFBundleVersion</key>\s*<string>)[^<]+(</string>)",
        rf"\g<1>{version}\2",
        plantilla,
    )
    plantilla = re.sub(
        r"(<key>CFBundleShortVersionString</key>\s*<string>)[^<]+(</string>)",
        rf"\g<1>{version}\2",
        plantilla,
    )
    return plantilla.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _archivos_iniciales() -> Path | None:
    for candidato in (
        ROOT / "empaque" / "paquete_inicial.zip",
        ROOT / "ArchivosPrueba2026-1.zip",
    ):
        if candidato.is_file():
            return candidato
    return None


def _empaquetar_app(zf: zipfile.ZipFile, carpeta: str) -> int:
    for nombre in ARCHIVOS_RAIZ:
        src = ROOT / nombre
        if not src.is_file():
            print(f"Falta {nombre}")
            return 1
        _escribir(zf, src, f"{carpeta}/app/{nombre}")

    _copiar_arbol(zf, ROOT / "consolidado", f"{carpeta}/app/consolidado")

    for gitkeep in (
        ROOT / "datos" / "entrada" / ".gitkeep",
        ROOT / "salida" / ".gitkeep",
    ):
        if gitkeep.is_file():
            rel = gitkeep.relative_to(ROOT).as_posix()
            _escribir(zf, gitkeep, f"{carpeta}/app/{rel}")

    iniciales = _archivos_iniciales()
    if iniciales is not None:
        _escribir(zf, iniciales, f"{carpeta}/Archivos iniciales.zip")

    version_txt = f"{APP_VERSION}\n".encode("utf-8")
    zf.writestr(_zip_info(f"{carpeta}/VERSION.txt", executable=False), version_txt)
    return 0


def _armar_macos() -> int:
    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    if DESTINO.is_file():
        DESTINO.unlink()

    with zipfile.ZipFile(DESTINO, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        _escribir(zf, MACOS_DIR / "LEEME.txt", f"{CARPETA_ZIP}/LEEME.txt")
        _escribir(zf, MACOS_DIR / "Instalar.command", f"{CARPETA_ZIP}/Instalar.command")
        _escribir(zf, MACOS_DIR / "Abrir.command", f"{CARPETA_ZIP}/Abrir.command")

        launcher = (
            MACOS_DIR
            / "Consolidado Humanidades.app"
            / "Contents"
            / "MacOS"
            / "ConsolidadoHumanidades"
        )
        _escribir(
            zf,
            launcher,
            f"{CARPETA_ZIP}/Consolidado Humanidades.app/Contents/MacOS/ConsolidadoHumanidades",
        )
        plist_arc = f"{CARPETA_ZIP}/Consolidado Humanidades.app/Contents/Info.plist"
        zf.writestr(_zip_info(plist_arc, executable=False), _info_plist(APP_VERSION))

        favicon = ROOT / "consolidado" / "web" / "static" / "favicon.png"
        if favicon.is_file():
            _escribir(
                zf,
                favicon,
                f"{CARPETA_ZIP}/Consolidado Humanidades.app/Contents/Resources/favicon.png",
            )

        if _empaquetar_app(zf, CARPETA_ZIP) != 0:
            return 1

    print(f"Escrito {DESTINO} ({DESTINO.stat().st_size} bytes)")
    return 0


def _armar_linux() -> int:
    if not (LINUX_DIR / "Instalar.sh").is_file():
        print(f"Falta {LINUX_DIR / 'Instalar.sh'}")
        return 1
    DESTINO_LINUX.parent.mkdir(parents=True, exist_ok=True)
    if DESTINO_LINUX.is_file():
        DESTINO_LINUX.unlink()

    with zipfile.ZipFile(DESTINO_LINUX, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        _escribir(zf, LINUX_DIR / "LEEME.txt", f"{CARPETA_ZIP}/LEEME.txt")
        _escribir(zf, LINUX_DIR / "Instalar.sh", f"{CARPETA_ZIP}/Instalar.sh")
        _escribir(zf, LINUX_DIR / "Abrir.sh", f"{CARPETA_ZIP}/Abrir.sh")
        if _empaquetar_app(zf, CARPETA_ZIP) != 0:
            return 1

    print(f"Escrito {DESTINO_LINUX} ({DESTINO_LINUX.stat().st_size} bytes)")
    return 0


def main() -> int:
    codigo = _armar_macos()
    if codigo != 0:
        return codigo
    codigo = _armar_linux()
    if codigo != 0:
        return codigo
    print(f"Versión {APP_VERSION}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
