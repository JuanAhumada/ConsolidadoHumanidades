"""Excel recortado: una versión del consolidado, columnas elegidas y filtro por carrera."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from io import BytesIO
from typing import Any

import polars as pl
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from consolidado.config.settings import construir_grupos_encabezado
from consolidado.core.charts import (
    COL_PROGRAMA_GRAFICA,
    _partir_categorias,
    filtrar_df_por_carreras,
    programas_disponibles,
)
from consolidado.core.constants import max_materias_en_dataframe

COLUMNAS_BASICAS = (
    "Identificación",
    "Nombre y apellidos",
    "Programa",
)

_RE_NOMBRE_ARCHIVO = re.compile(r"[^A-Za-z0-9._-]+")


def grupos_columnas_version(
    df: pl.DataFrame,
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    presentes = [str(c) for c in df.columns]
    vistos: set[str] = set()
    grupos: list[dict[str, Any]] = []
    num_mat = max(max_materias_en_dataframe(df), 1)
    for nombre, cols in construir_grupos_encabezado(cfg, num_mat):
        en_grupo = [c for c in cols if c in presentes and c not in vistos]
        if not en_grupo:
            continue
        grupos.append({"nombre": nombre, "columnas": en_grupo})
        vistos.update(en_grupo)
    resto = [c for c in presentes if c not in vistos]
    if resto:
        grupos.append({"nombre": "Otras", "columnas": resto})
    return grupos


def conteos_por_programa(df: pl.DataFrame) -> list[dict[str, Any]]:
    from collections import Counter

    if COL_PROGRAMA_GRAFICA not in df.columns:
        return []
    cont: Counter[str] = Counter()
    for val in df.get_column(COL_PROGRAMA_GRAFICA).to_list():
        if val is None:
            continue
        for parte in _partir_categorias(str(val)):
            if parte:
                cont[parte] += 1
    return [
        {"nombre": nombre, "n": cont[nombre]}
        for nombre in programas_disponibles(df)
    ]


def recortar_dataframe(
    df: pl.DataFrame,
    *,
    columnas: list[str],
    programas: list[str] | None,
) -> pl.DataFrame:
    cols = [str(c).strip() for c in columnas if str(c).strip()]
    if not cols:
        raise ValueError("Elija al menos una columna.")
    faltan = [c for c in cols if c not in df.columns]
    if faltan:
        raise ValueError(f"Esas columnas no están en esta versión: {', '.join(faltan[:8])}.")
    recorte = filtrar_df_por_carreras(df, programas)
    return recorte.select(cols)


def _valor_excel(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, bool):
        return "Sí" if val else "No"
    if isinstance(val, (int, float, datetime, date)):
        return val
    texto = str(val).strip()
    if not texto or texto.lower() in {"none", "null", "nan"}:
        return None
    return texto


def _slug_archivo(texto: str, *, max_len: int = 40) -> str:
    nfkd = unicodedata.normalize("NFKD", texto or "")
    ascii_txt = "".join(c for c in nfkd if not unicodedata.combining(c))
    limpio = _RE_NOMBRE_ARCHIVO.sub("_", ascii_txt).strip("._")
    return (limpio or "parcializado")[:max_len]


def nombre_excel_parcializado(
    *,
    periodo: str | None,
    fecha_version: str | None,
    programas: list[str] | None,
) -> str:
    partes = ["parcializado"]
    if periodo:
        partes.append(_slug_archivo(str(periodo), max_len=16))
    if fecha_version:
        partes.append(_slug_archivo(str(fecha_version), max_len=12))
    elegidas = [p for p in (programas or []) if str(p).strip()]
    if len(elegidas) == 1:
        partes.append(_slug_archivo(elegidas[0], max_len=24))
    elif len(elegidas) > 1:
        partes.append(f"{len(elegidas)}carreras")
    return "_".join(partes) + ".xlsx"


def excel_parcializado_bytes(
    df: pl.DataFrame,
    *,
    columnas: list[str],
    programas: list[str] | None,
    meta: dict[str, Any] | None = None,
) -> bytes:
    recorte = recortar_dataframe(df, columnas=columnas, programas=programas)
    wb = Workbook()
    ws = wb.active
    ws.title = "Parcializado"

    cabecera = Font(bold=True, color="FFFFFF")
    fondo = PatternFill("solid", fgColor="0C6B63")
    cols = list(recorte.columns)
    ws.append(cols)
    for cell in ws[1]:
        cell.font = cabecera
        cell.fill = fondo
        cell.alignment = Alignment(wrap_text=True, vertical="center")

    for fila in recorte.iter_rows(named=True):
        ws.append([_valor_excel(fila.get(c)) for c in cols])

    ultima = max(recorte.height + 1, 1)
    ult_col = get_column_letter(max(len(cols), 1))
    if recorte.height > 0 and cols:
        tabla = Table(displayName="Parcializado", ref=f"A1:{ult_col}{ultima}")
        tabla.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(tabla)
    else:
        ws.auto_filter.ref = f"A1:{ult_col}{ultima}"
    ws.freeze_panes = "A2"
    ws.row_dimensions[1].height = 22
    for i, nombre in enumerate(cols, start=1):
        ancho = min(max(len(nombre) + 2, 12), 42)
        ws.column_dimensions[get_column_letter(i)].width = ancho

    info = wb.create_sheet("Origen")
    info.append(["Campo", "Valor"])
    for cell in info[1]:
        cell.font = cabecera
        cell.fill = fondo
    meta = meta or {}
    elegidas = [p for p in (programas or []) if str(p).strip()]
    filas_origen = [
        ("Versión", meta.get("id")),
        ("Periodo", meta.get("periodo")),
        ("Fecha del corte", meta.get("fecha_version")),
        ("Carreras", ", ".join(elegidas) if elegidas else "Todas"),
        ("Columnas", recorte.width),
        ("Filas", recorte.height),
    ]
    for campo, valor in filas_origen:
        info.append([campo, valor if valor is not None else "—"])
    info.column_dimensions["A"].width = 22
    info.column_dimensions["B"].width = 48

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
