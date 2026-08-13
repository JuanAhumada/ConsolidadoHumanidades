"""Agregación de datos para gráficas (Chart.js en el frontend)."""

from __future__ import annotations

from collections import Counter
from typing import Any

import polars as pl

TIPOS_GRAFICA = (
    "bar",
    "bar_horizontal",
    "pie",
    "doughnut",
    "line",
)


def columnas_graficables(df: pl.DataFrame) -> list[str]:
    return list(df.columns)


def preparar_datos_grafica(
    df: pl.DataFrame,
    *,
    columna: str,
    tipo: str = "bar",
    top: int = 25,
) -> dict[str, Any]:
    """
    Devuelve labels/valores listos para Chart.js.
    """
    tipo = (tipo or "bar").strip().lower()
    if tipo not in TIPOS_GRAFICA:
        raise ValueError(f"Tipo no soportado: {tipo}. Use: {', '.join(TIPOS_GRAFICA)}")
    if columna not in df.columns:
        raise ValueError(f"Columna «{columna}» no encontrada.")

    valores: list[str] = []
    for v in df.get_column(columna).to_list():
        if v is None:
            continue
        texto = str(v).strip()
        if not texto or texto.lower() in {"none", "null", "nan"}:
            continue
        valores.append(texto)

    if not valores:
        raise ValueError(f"La columna «{columna}» no tiene datos para graficar.")

    cont = Counter(valores)
    mas = cont.most_common(max(1, min(top, 50)))
    labels = [k for k, _ in mas]
    data = [n for _, n in mas]

    chart_type = {
        "bar": "bar",
        "bar_horizontal": "bar",
        "pie": "pie",
        "doughnut": "doughnut",
        "line": "line",
    }[tipo]

    return {
        "columna": columna,
        "tipo": tipo,
        "chart_type": chart_type,
        "horizontal": tipo == "bar_horizontal",
        "labels": labels,
        "values": data,
        "total_filas": len(valores),
        "categorias": len(labels),
    }
