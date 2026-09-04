"""Arma empaque/paquete_inicial.zip a partir de ArchivosPrueba2026-1.zip."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from consolidado.config.settings import cargar_config  # noqa: E402
from consolidado.web.services import resolver_slot_por_nombre  # noqa: E402

ORIGEN = ROOT / "ArchivosPrueba2026-1.zip"
DESTINO = ROOT / "empaque" / "paquete_inicial.zip"


def main() -> int:
    if not ORIGEN.is_file():
        print(f"No está {ORIGEN.name}. Póngalo en la raíz del proyecto.")
        return 1
    cfg = cargar_config(ROOT)
    usados: set[str] = set()
    asignados: list[tuple[str, str, bytes]] = []
    sin_slot: list[str] = []
    with zipfile.ZipFile(ORIGEN) as zf:
        nombres = sorted(
            (i.filename for i in zf.infolist() if not i.is_dir()),
            key=lambda n: Path(n).name.casefold(),
        )
        for interno in nombres:
            nombre = Path(interno).name
            if Path(nombre).suffix.lower() not in {".xlsx", ".xlsm", ".xls"}:
                continue
            slot = resolver_slot_por_nombre(nombre, cfg, ya_usados=usados)
            if slot is None:
                sin_slot.append(nombre)
                continue
            sid = str(slot.get("id") or "")
            dest_name = str(slot.get("nombre_guardado") or f"{sid}.xlsx")
            asignados.append((dest_name, nombre, zf.read(interno)))
            usados.add(sid)

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(DESTINO, "w", compression=zipfile.ZIP_DEFLATED) as out:
        for dest_name, _origen, data in asignados:
            out.writestr(dest_name, data)
    print(f"Escrito {DESTINO} ({DESTINO.stat().st_size} bytes)")
    for dest_name, origen, _ in asignados:
        print(f"  {origen} -> {dest_name}")
    if sin_slot:
        print("Sin slot (omitidos):")
        for n in sin_slot:
            print(f"  {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
