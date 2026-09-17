"""Agregación para Chart.js. Si la columna es Programa, usa colores de colores_programa."""

from __future__ import annotations

import re
from collections import Counter
from io import BytesIO
from typing import Any

from consolidado.core.colores_programa import colores_para_etiquetas
from consolidado.core.constants import es_columna_materia_horario
from consolidado.core.normalizacion import clave_orden_etiqueta

import polars as pl
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

TIPOS_GRAFICA = (
    "line",
    "bar",
    "pie",
    "scatter",
)

_TIPO_POWERBI = {
    "scatter": "Gráfico de dispersión",
    "bar": "Columnas agrupadas",
    "pie": "Gráfico circular",
    "line": "Gráfico de líneas",
}

_ALIAS_TIPO = {
    "bar_horizontal": "bar",
    "barras": "bar",
    "doughnut": "pie",
    "dona": "pie",
    "pastel": "pie",
    "torta": "pie",
    "linea": "line",
    "línea": "line",
    "puntos": "line",
    "punto": "line",
    "dispersion": "scatter",
    "dispersión": "scatter",
}

PALETA_GRAFICA = (
    "#A3161A",
    "#C9A227",
    "#FCD116",
    "#078930",
    "#595959",
    "#A5A5A5",
    "#8B1216",
    "#E0B52C",
    "#0AA33A",
    "#3D080A",
    "#CCCCCC",
    "#6B0E12",
    "#D4B01C",
    "#045A1E",
    "#7A1014",
    "#C41C21",
    "#B08918",
    "#0C6B28",
    "#F6E4E5",
    "#2A0506",
    "#A3861C",
    "#4A0A0C",
    "#E8B4B6",
    "#D4F0DE",
    "#8A8A8A",
)


def paleta_categorias(n: int) -> list[str]:
    if n <= 0:
        return []
    base = list(PALETA_GRAFICA)
    if n <= len(base):
        return base[:n]
    out = list(base)
    while len(out) < n:
        out.append(base[len(out) % len(base)])
    return out[:n]


COLUMNAS_GRAFICA_PUNTAJE = frozenset(
    {
        "Puntaje prioridad",
        "Nivel prioridad",
        "Detalle prioridad",
        "Ptje Beca",
        "Ptje Priorizado",
        "Ptje Repitiendo",
        "Ptje Reintegro",
        "Ptje Propio",
        "Ptje Activacion",
        "Ptje Ruta",
    }
)

_RE_COL_PUNTAJE = re.compile(r"^(ptje|puntaje|nivel prioridad)\b", re.IGNORECASE)

COLUMNAS_GRAFICA_UNICAS = frozenset(
    {
        "Identificación",
        "Nombre y apellidos",
        "Teléfono celular",
        "Correo institucional",
        "Correo personal",
        "Fecha de nacimiento",
        "Lugar de nacimiento",
        "Lugar de residencia",
        "Dirección residencia",
        "Detalle GPrio.",
        "Detalle Propio",
        "Fecha adaptacion",
        "Fecha activacion de ruta",
    }
)

_CLAVES_UNICAS = (
    "identificación",
    "identificacion",
    "cédula",
    "cedula",
    "nombre y apellido",
    "nombres y apellido",
    "nombre completo",
    "nombre del estudiante",
    "nombre estudiante",
    "teléfono",
    "telefono",
    "celular",
    "correo",
    "e-mail",
    "email",
    "fecha",
    "lugar de nacimiento",
    "lugar de residencia",
    "dirección",
    "direccion",
    "detalle",
    "_id_key",
)
_RE_MATERIA_AMPLIA = re.compile(r"^(materia|horario|profesor)s?\b", re.I)


def _parece_informacion_unica(nombre: str) -> bool:
    n = str(nombre or "").strip().casefold()
    if n in {"nombre", "nombres", "apellido", "apellidos"}:
        return True
    return any(clave in n for clave in _CLAVES_UNICAS)


def es_columna_materia_grafica(col: str) -> bool:
    nombre = str(col or "").strip()
    return bool(es_columna_materia_horario(nombre) or _RE_MATERIA_AMPLIA.match(nombre))


def columna_excluida_grafica(col: str) -> bool:
    nombre = str(col or "").strip()
    if not nombre:
        return True
    if nombre.startswith("_"):
        return True
    if es_columna_materia_grafica(nombre):
        return True
    if nombre in COLUMNAS_GRAFICA_UNICAS or nombre in COLUMNAS_GRAFICA_PUNTAJE:
        return True
    if _RE_COL_PUNTAJE.match(nombre):
        return True
    return _parece_informacion_unica(nombre)


def columnas_graficables(
    df: pl.DataFrame | None,
    permitidas: list[str] | None = None,
) -> list[str]:
    if df is None:
        return []
    cols = [str(c) for c in df.columns]
    if permitidas is not None:
        ok = {str(c).strip() for c in permitidas if str(c).strip()}
        cols = [c for c in cols if c in ok]
    return [c for c in cols if not columna_excluida_grafica(c)]


def agrupar_columnas_grafica(
    columnas: list[str],
    grupos: list[tuple[str, list[str]]] | None = None,
) -> list[dict[str, Any]]:
    """Repartir columnas graficables en los grupos de encabezado del consolidado."""
    habilitadas = [str(c) for c in columnas if str(c).strip()]
    if not habilitadas:
        return []
    disponibles = set(habilitadas)
    vistos: set[str] = set()
    out: list[dict[str, Any]] = []
    for nombre, cols_grupo in grupos or []:
        miembros = [
            c for c in cols_grupo
            if c in disponibles and c not in vistos
        ]
        if not miembros:
            continue
        vistos.update(miembros)
        out.append({"nombre": str(nombre or "Grupo").strip() or "Grupo", "columnas": miembros})
    resto = [c for c in habilitadas if c not in vistos]
    if resto:
        out.append({"nombre": "Otros", "columnas": resto})
    return out


_RE_PARTIR_ITEMS = re.compile(r"\s*\|\s*|,\s+")


def partir_items(texto: str) -> list[str]:
    """Parte becas (`|`) y motivos (`, `) en un ítem por valor."""
    s = str(texto or "").strip()
    if not s or s.lower() in {"none", "null", "nan", "nat", "—", "-"}:
        return []
    return [p.strip() for p in _RE_PARTIR_ITEMS.split(s.replace("||", "|")) if p.strip()]


def _partir_categorias(texto: str) -> list[str]:
    """Si el valor trae varios ítems unidos con «|», cada uno cuenta aparte."""
    partes = partir_items(texto)
    return partes or ([str(texto).strip()] if str(texto).strip() else [])


def tabla_items_en_columnas(
    df: pl.DataFrame,
    *,
    columna: str,
    prefijo: str,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Una fila por estudiante; cada ítem en «Beca 1», «Beca 2»… (o Motivo)."""
    if columna not in df.columns:
        return [], []
    grupos: list[tuple[dict[str, Any], list[str]]] = []
    n = 0
    for row in df.iter_rows(named=True):
        partes = partir_items(str(row.get(columna) or ""))
        if not partes:
            continue
        n = max(n, len(partes))
        grupos.append((row, partes))
    if not n:
        return [], []
    cols = ["Documento", "Nombre", "Carrera"] + [f"{prefijo} {i}" for i in range(1, n + 1)]
    filas: list[dict[str, Any]] = []
    for row, partes in grupos:
        rec: dict[str, Any] = {
            "Documento": row.get("Identificación"),
            "Nombre": row.get("Nombre y apellidos"),
            "Carrera": row.get("Programa"),
        }
        for i in range(1, n + 1):
            rec[f"{prefijo} {i}"] = partes[i - 1] if i <= len(partes) else None
        filas.append(rec)
    return cols, filas


def filas_items_separados(
    df: pl.DataFrame,
    *,
    columna: str,
    campo: str,
) -> list[dict[str, Any]]:
    """Una fila por cédula e ítem (beca o motivo), con columnas fijas."""
    if columna not in df.columns:
        return []
    out: list[dict[str, Any]] = []
    for row in df.iter_rows(named=True):
        partes = partir_items(str(row.get(columna) or ""))
        if not partes:
            continue
        for item in partes:
            out.append(
                {
                    "Identificación": row.get("Identificación"),
                    "Nombre y apellidos": row.get("Nombre y apellidos"),
                    "Programa": row.get("Programa"),
                    campo: item,
                }
            )
    return out


COL_PROGRAMA_GRAFICA = "Programa"


def programas_disponibles(df: pl.DataFrame | None) -> list[str]:
    if df is None or COL_PROGRAMA_GRAFICA not in df.columns:
        return []
    vistos: list[str] = []
    for val in df.get_column(COL_PROGRAMA_GRAFICA).to_list():
        if val is None:
            continue
        for parte in _partir_categorias(str(val)):
            if parte and parte not in vistos:
                vistos.append(parte)
    return sorted(vistos, key=lambda s: s.casefold())


def filtrar_df_por_carreras(df: pl.DataFrame, carreras: list[str] | None) -> pl.DataFrame:
    claves = [str(c).strip() for c in (carreras or []) if str(c).strip()]
    if not claves or COL_PROGRAMA_GRAFICA not in df.columns:
        return df
    claves_cf = {c.casefold() for c in claves}

    def _coincide(val: Any) -> bool:
        if val is None:
            return False
        return any(p.casefold() in claves_cf for p in _partir_categorias(str(val)))

    return df.filter(
        pl.col(COL_PROGRAMA_GRAFICA).map_elements(_coincide, return_dtype=pl.Boolean)
    )


def filtrar_df_por_carrera(df: pl.DataFrame, carrera: str | None) -> pl.DataFrame:
    clave = (carrera or "").strip()
    if not clave:
        return df
    return filtrar_df_por_carreras(df, [clave])


def preparar_datos_grafica(
    df: pl.DataFrame,
    *,
    columna: str,
    tipo: str = "line",
    top: int = 25,
    programa: str | None = None,
) -> dict[str, Any]:
    """
    Devuelve labels/valores listos para Chart.js.
    """
    tipo = _ALIAS_TIPO.get((tipo or "line").strip().lower(), (tipo or "line").strip().lower())
    if tipo not in TIPOS_GRAFICA:
        raise ValueError(f"Tipo no soportado: {tipo}. Use: {', '.join(TIPOS_GRAFICA)}")
    carrera = (programa or "").strip()
    if carrera:
        df = filtrar_df_por_carrera(df, carrera)
        if df.height == 0:
            raise ValueError(f"No hay estudiantes de la carrera «{carrera}».")
    if columna not in df.columns:
        raise ValueError(f"Columna «{columna}» no encontrada.")

    valores: list[str] = []
    for v in df.get_column(columna).to_list():
        if v is None:
            continue
        texto = str(v).strip()
        if not texto or texto.lower() in {"none", "null", "nan"}:
            continue
        valores.extend(_partir_categorias(texto))

    if not valores:
        raise ValueError(f"La columna «{columna}» no tiene datos para graficar.")

    cont = Counter(valores)
    items = [(k, n) for k, n in cont.items() if n > 0]
    tope = max(1, min(top, 50))
    if len(items) > tope:
        items = sorted(items, key=lambda par: (-par[1], clave_orden_etiqueta(par[0])))[:tope]
    items.sort(key=lambda par: clave_orden_etiqueta(par[0]))
    labels = [k for k, _ in items]
    data = [n for _, n in items]
    es_programa = columna.strip().casefold() in {"programa"}
    max_valor = max(data) if data else 0

    return {
        "columna": columna,
        "tipo": tipo,
        "chart_type": tipo,
        "horizontal": False,
        "labels": labels,
        "values": data,
        "max_valor": max_valor,
        "colores": colores_para_etiquetas(labels) if es_programa else paleta_categorias(len(labels)),
        "total_filas": len(valores),
        "categorias": len(labels),
        "programa": carrera,
    }


def _nombre_hoja_excel(indice: int, columna: str, usados: set[str]) -> str:
    base = re.sub(r"[\\/*?:\[\]]+", "", f"G{indice}_{columna}".strip()) or f"Grafica{indice}"
    base = base[:31]
    nombre = base
    n = 2
    while nombre.lower() in usados:
        suf = f"_{n}"
        nombre = f"{base[: 31 - len(suf)]}{suf}"
        n += 1
    usados.add(nombre.lower())
    return nombre


def excel_powerbi_desde_graficas(series: list[dict[str, Any]]) -> bytes:
    """
    Excel tabular listo para Power BI: una hoja-tabla por gráfica
    (categoría + conteo) y una hoja de índice con el visual sugerido.
    """
    if not series:
        raise ValueError("No hay gráficas para exportar.")

    wb = Workbook()
    indice = wb.active
    indice.title = "Indice"
    cabecera = Font(bold=True, color="FFFFFF")
    fondo = PatternFill("solid", fgColor="0C6B63")
    indice.append(["Hoja", "Columna", "Visual sugerido en Power BI", "Categorias", "Valores"])
    for cell in indice[1]:
        cell.font = cabecera
        cell.fill = fondo

    usados: set[str] = {"indice"}
    for i, item in enumerate(series, start=1):
        columna = str(item.get("columna") or f"Grafica {i}")
        tipo = str(item.get("tipo") or "line")
        labels = list(item.get("labels") or [])
        values = list(item.get("values") or [])
        hoja_nombre = _nombre_hoja_excel(i, columna, usados)
        ws = wb.create_sheet(hoja_nombre)
        ws.append([columna, "Conteo"])
        for lab, val in zip(labels, values):
            ws.append([lab, val])
        ultima = max(len(labels) + 1, 2)
        for cell in ws[1]:
            cell.font = cabecera
            cell.fill = fondo
        for row in ws.iter_rows(min_row=2, max_row=ultima, min_col=2, max_col=2):
            for cell in row:
                cell.number_format = "#,##0"
        tabla = Table(displayName=f"Grafica{i}", ref=f"A1:B{ultima}")
        tabla.tableStyleInfo = TableStyleInfo(
            name="TableStyleMedium2",
            showFirstColumn=False,
            showLastColumn=False,
            showRowStripes=True,
            showColumnStripes=False,
        )
        ws.add_table(tabla)
        ws.column_dimensions["A"].width = max(18, min(42, max((len(str(x)) for x in [columna, *labels]), default=12) + 2))
        ws.column_dimensions["B"].width = 14
        ws.auto_filter.ref = f"A1:B{ultima}"
        ws.freeze_panes = "A2"
        indice.append(
            [
                hoja_nombre,
                columna,
                _TIPO_POWERBI.get(tipo, "Columnas agrupadas"),
                len(labels),
                int(sum(float(v) for v in values if v is not None)),
            ]
        )

    uso = wb.create_sheet("Como_importar", 1)
    uso["A1"] = "Cómo llevar estas gráficas a Power BI"
    uso["A1"].font = Font(bold=True, size=14, color="0C6B63")
    lineas = [
        "",
        "Opción A — Pegar (una gráfica):",
        "1. En la web pulse «Copiar datos».",
        "2. En Power BI Desktop: Inicio → Introducir datos.",
        "3. Clic en la primera celda y Ctrl+V. Cargue.",
        "4. Inserte el visual indicado en la hoja Índice.",
        "",
        "Opción B — Excel (varias gráficas):",
        "1. Power BI Desktop: Inicio → Obtener datos → Excel.",
        "2. Elija este archivo. Verá una tabla por gráfica (Grafica1, Grafica2…).",
        "3. Seleccione las tablas y pulse Cargar.",
        "4. Arrastre la columna de categoría y Conteo al visual.",
        "",
        "Las imágenes PNG sirven para Insertar → Imagen, pero no son visuales interactivos.",
    ]
    for i, texto in enumerate(lineas, start=2):
        uso[f"A{i}"] = texto
        uso[f"A{i}"].alignment = Alignment(wrap_text=True)
    uso.column_dimensions["A"].width = 88
    for col in indice.columns:
        letra = get_column_letter(col[0].column)
        indice.column_dimensions[letra].width = 28
    indice.freeze_panes = "A2"

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
