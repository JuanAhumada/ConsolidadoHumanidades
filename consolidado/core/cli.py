from __future__ import annotations

import argparse
import warnings
from pathlib import Path

from consolidado.paths import PROJECT_ROOT

from consolidado.core.constants import aplicar_config
from consolidado.core.excel_io import (
    elegir_cuatro_excels_en_explorador,
    listar_excels_en_carpeta,
)
from consolidado.core.pipeline import ejecutar_consolidado
from consolidado.storage.versiones import asegurar_semilla_si_vacia


def main() -> None:
    warnings.filterwarnings(
        "ignore",
        message="Workbook contains no default style",
        category=UserWarning,
        module="openpyxl.styles.stylesheet",
    )
    base = PROJECT_ROOT
    asegurar_semilla_si_vacia(base)

    parser = argparse.ArgumentParser(description="Fusiona Excel de estudiantes por identificación.")
    parser.add_argument(
        "--entrada",
        type=Path,
        default=None,
        help="Si se indica: leer todos los .xlsx/.xlsm de esa carpeta (sin diálogos). "
        "Si se omite: cuatro diálogos del explorador, cada uno titulado según el tipo de libro (BD 1, BD 1.2, BD 2, BD 3).",
    )
    parser.add_argument(
        "--salida",
        type=Path,
        default=None,
        help="Ruta del Excel de salida. Si se omite, se genera automáticamente "
        "como estudiantes_consolidado_{periodo}_{fecha}.xlsx en salida/.",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Abre la interfaz gráfica de configuración y consolidado.",
    )
    args = parser.parse_args()

    if args.gui:
        from consolidado.gui import main as gui_main

        gui_main()
        return

    aplicar_config()

    archivos: list[Path]

    if args.entrada is not None:
        entrada = args.entrada
        if not entrada.is_dir():
            raise SystemExit(f"No existe la carpeta de entrada: {entrada}")
        archivos = listar_excels_en_carpeta(entrada)
        if len(archivos) < 1:
            raise SystemExit(f"No hay archivos .xlsx ni .xlsm en {entrada}.")
        salida: Path | None = args.salida
    else:
        archivos_gui = elegir_cuatro_excels_en_explorador()
        if archivos_gui is None:
            raise SystemExit("Operación cancelada.")
        archivos = archivos_gui
        salida = args.salida

    consolidado, salida = ejecutar_consolidado(
        base=base,
        archivos=archivos,
        salida=salida,
        abrir=True,
    )
    print(f"Listo: {consolidado.height} estudiantes -> {salida}")
    print("  Guardado también en la base SQL (datos/consolidado.db)")
    print("  Hoja única con grupos: Datos, Priorizados, Becas, Materias (+ documentos extra)")
    print("  Abriendo el Excel generado...")
