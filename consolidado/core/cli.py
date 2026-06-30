from __future__ import annotations

import argparse
import warnings
from pathlib import Path

from consolidado.paths import PROJECT_ROOT

import polars as pl

from consolidado.core.alertas import _aplicar_alertas, _cargar_alertas_cfg
from consolidado.core.archivos import (
    _limpiar_becas_programa_no_permitido,
    _tipo_libro_desde_nombre,
    preparar_archivo,
    procesar_tabla_priorizados_con_recuperacion,
)
from consolidado.core.columnas import alinear_dataframe_salida
from consolidado.core.constants import (
    COLUMNAS_EXCLUIDAS_LISTADO,
    TITULOS_EXCEL_FUENTE,
    _TIPOS_FUENTE_AUXILIARES,
    _cfg,
    aplicar_config,
    columnas_materia_horario,
    es_columna_materia_horario,
    max_materias_en_dataframe,
)
from consolidado.config.settings import construir_columnas_salida
from consolidado.core.documentos import _unir_documentos_adicionales
from consolidado.core.excel_io import (
    abrir_archivo_en_sistema,
    elegir_cuatro_excels_en_explorador,
    listar_excels_en_carpeta,
    resolver_ruta_salida_consolidado,
)
from consolidado.core.export import guardar_excel_consolidado
from consolidado.core.fusion import fusionar_por_id
from consolidado.core.prioridad import aplicar_prioridad
from consolidado.core.priorizados import aplicar_priorizados_propios
from consolidado.core.repetidas import _cargar_materias_repetidas_cfg
from consolidado.core.normalizacion import normalizar_id
from consolidado.storage.priorizados import cargar_priorizados_propios
def main() -> None:
    warnings.filterwarnings(
        "ignore",
        message="Workbook contains no default style",
        category=UserWarning,
        module="openpyxl.styles.stylesheet",
    )
    base = PROJECT_ROOT
    salida_default = base / "salida" / "estudiantes_consolidado.xlsx"

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
        help="Ruta del Excel de salida. Si se omite, se preguntará si desea "
        "sobreescribir salida/estudiantes_consolidado.xlsx (o la última ruta guardada).",
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
        salida: Path = args.salida if args.salida is not None else salida_default
    else:
        archivos_gui = elegir_cuatro_excels_en_explorador()
        if archivos_gui is None:
            raise SystemExit("Operación cancelada.")
        archivos = archivos_gui
        salida = args.salida if args.salida is not None else salida_default

    partes: list[pl.DataFrame] = []
    tipos_partes: list[str] = []
    horarios_partes: list[pl.DataFrame] = []
    priorizados: pl.DataFrame | None = None
    max_materias = 1
    cfg = _cfg()
    for indice, p in enumerate(archivos):
        slot = (
            cfg["archivos_fuente"][indice]
            if indice < len(cfg.get("archivos_fuente", []))
            else None
        )
        etiqueta = slot["titulo"] if slot else (
            TITULOS_EXCEL_FUENTE[indice]
            if indice < len(TITULOS_EXCEL_FUENTE)
            else p.name
        )
        tipo = slot["tipo"] if slot else _tipo_libro_desde_nombre(p)
        hoja = slot.get("hoja") if slot else None
        if tipo in _TIPOS_FUENTE_AUXILIARES:
            continue
        if tipo == "bd2":
            priorizados, _ = procesar_tabla_priorizados_con_recuperacion(
                p, etiqueta, tipo=tipo, hoja=hoja
            )
            continue
        df_listado, df_horarios, _ = preparar_archivo(
            p, etiqueta, tipo=tipo, hoja=hoja
        )
        max_materias = max(max_materias, max_materias_en_dataframe(df_horarios))
        partes.append(df_listado)
        tipos_partes.append(tipo)
        if df_horarios.height > 0:
            horarios_partes.append(df_horarios)

    materias_repetidas = _cargar_materias_repetidas_cfg(_cfg(), base)
    alertas = _cargar_alertas_cfg(_cfg(), base)

    columnas_listado = [
        c
        for c in construir_columnas_salida(_cfg(), max_materias)
        if not es_columna_materia_horario(c) and c not in COLUMNAS_EXCLUIDAS_LISTADO
    ]
    columnas_materias = columnas_materia_horario(max_materias)
    partes = [alinear_dataframe_salida(df, columnas_listado) for df in partes]

    consolidado = fusionar_por_id(
        partes,
        horarios_partes,
        priorizados=priorizados,
        columnas_listado=columnas_listado,
        columnas_materias=columnas_materias,
        tipos_partes=tipos_partes,
    )
    consolidado = _unir_documentos_adicionales(consolidado, _cfg(), base)
    consolidado = _limpiar_becas_programa_no_permitido(consolidado)
    consolidado = _aplicar_alertas(consolidado, alertas)

    propios = cargar_priorizados_propios(base)
    consolidado = aplicar_priorizados_propios(consolidado, propios)
    ids_propios = {
        normalizar_id(p.get("identificacion", ""))
        for p in propios
        if normalizar_id(p.get("identificacion", ""))
    }
    consolidado = aplicar_prioridad(consolidado, ids_propios)

    if args.salida is None:
        destino_resuelta = resolver_ruta_salida_consolidado(_cfg(), base)
        if destino_resuelta is None:
            raise SystemExit("Operación cancelada.")
        salida = destino_resuelta
    else:
        salida = args.salida

    salida.parent.mkdir(parents=True, exist_ok=True)
    salida = guardar_excel_consolidado(
        consolidado,
        salida,
        cfg=_cfg(),
        num_materias=max_materias,
        materias_repetidas=materias_repetidas,
    )
    print(f"Listo: {consolidado.height} estudiantes -> {salida}")
    print(f"  Hoja única con grupos: Datos, Priorizados, Becas, Materias (+ documentos extra)")
    abrir_archivo_en_sistema(salida)
    print("  Abriendo el Excel generado...")

