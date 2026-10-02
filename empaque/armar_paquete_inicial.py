"""Arma empaque/paquete_inicial.zip con las fuentes que siguen en config.

El archivo 1 (bd1.xlsx) es la base nueva de matriculados y repitentes.
No entran alertas ni asignaturas repetidas, que ya no son fuentes.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consolidado.config.settings import ARCHIVOS_FUENTE_RETIRADOS, cargar_config  # noqa: E402

ENTRADA = ROOT / "datos" / "entrada"
DESTINO = ROOT / "empaque" / "paquete_inicial.zip"
NUEVA_BD1 = (
    ENTRADA / "sol_20260929_matriculados_y_repitentes_2.xlsx",
    Path(r"c:\Users\USER\Downloads\SOL 20260929 - MATRICULADOS Y REPITENTES-2.xlsx"),
)


def _origen_bd1() -> Path:
    for candidato in NUEVA_BD1:
        if candidato.is_file():
            return candidato
    actual = ENTRADA / "bd1.xlsx"
    if actual.is_file():
        return actual
    raise FileNotFoundError("No está la base nueva de matriculados para el archivo 1.")


def main() -> int:
    cfg = cargar_config(ROOT)
    origen_bd1 = _origen_bd1()
    asignados: list[tuple[str, Path]] = []
    faltan: list[str] = []

    for slot in cfg.get("archivos_fuente", []):
        sid = str(slot.get("id") or "")
        if not sid or sid in ARCHIVOS_FUENTE_RETIRADOS:
            continue
        dest_name = str(slot.get("nombre_guardado") or f"{sid}.xlsx")
        if sid == "bd1":
            asignados.append((dest_name, origen_bd1))
            continue
        ruta = ENTRADA / dest_name
        if ruta.is_file():
            asignados.append((dest_name, ruta))
        else:
            faltan.append(dest_name)

    if not asignados:
        print(f"No hay Excel en {ENTRADA}.")
        return 1

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(DESTINO, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for dest_name, ruta in asignados:
            out.write(ruta, arcname=dest_name)

    print(f"Escrito {DESTINO} ({DESTINO.stat().st_size} bytes)")
    for dest_name, ruta in asignados:
        print(f"  {ruta.name} -> {dest_name}")
    if faltan:
        print("No estaban en datos/entrada:")
        for nombre in faltan:
            print(f"  {nombre}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
