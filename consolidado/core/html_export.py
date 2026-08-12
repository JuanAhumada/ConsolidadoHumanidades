"""Exportación HTML del consolidado (vista web)."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

import polars as pl

from consolidado.config.settings import (
    construir_columnas_salida,
    construir_grupos_encabezado,
    etiqueta_export_columna,
)
from consolidado.core.constants import max_materias_en_dataframe
from consolidado.core.prioridad import color_excel_fila


def _css_hex(color: str | None) -> str:
    if not color:
        return ""
    c = color.strip().lstrip("#")
    if len(c) == 6:
        return f"#{c}"
    return ""


def guardar_html_consolidado(
    df: pl.DataFrame,
    destino: Path,
    *,
    cfg: dict | None = None,
    num_materias: int | None = None,
    titulo: str | None = None,
    limite_filas: int | None = None,
) -> Path:
    """
    Genera una página HTML con tabla del consolidado (grupos + colores de prioridad).
    """
    cfg = cfg or {}
    n_mat = num_materias or max_materias_en_dataframe(df) or 1
    columnas = [c for c in construir_columnas_salida(cfg, n_mat) if c in df.columns]
    if not columnas:
        columnas = list(df.columns)
    grupos = construir_grupos_encabezado(cfg, n_mat)
    grupos_filtrados: list[tuple[str, list[str]]] = []
    for nombre, cols in grupos:
        presentes = [c for c in cols if c in columnas]
        if presentes:
            grupos_filtrados.append((nombre, presentes))

    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    titulo = titulo or "Consolidado de estudiantes"
    generado = datetime.now().strftime("%d/%m/%Y %H:%M")

    filas_df = df.select(columnas) if columnas else df
    total = filas_df.height
    if limite_filas is not None:
        filas_df = filas_df.head(limite_filas)

    # Encabezado de grupos
    th_grupos = []
    th_cols = []
    for nombre, cols in grupos_filtrados:
        th_grupos.append(
            f'<th colspan="{len(cols)}" class="grupo">{html.escape(nombre)}</th>'
        )
        for c in cols:
            th_cols.append(f"<th>{html.escape(etiqueta_export_columna(c))}</th>")

    body_rows = []
    for row in filas_df.iter_rows(named=True):
        color = _css_hex(color_excel_fila(row))
        style = f' style="background:{color}"' if color else ""
        celdas = []
        for c in columnas:
            val = row.get(c)
            texto = "" if val is None else str(val)
            celdas.append(f"<td>{html.escape(texto)}</td>")
        body_rows.append(f"<tr{style}>{''.join(celdas)}</tr>")

    aviso_limite = ""
    if limite_filas is not None and total > limite_filas:
        aviso_limite = (
            f"<p class='meta'>Mostrando {limite_filas} de {total} filas.</p>"
        )

    contenido = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{html.escape(titulo)}</title>
  <style>
    :root {{
      --bg: #f1f5f9;
      --card: #ffffff;
      --text: #0f172a;
      --muted: #64748b;
      --accent: #0f766e;
      --border: #e2e8f0;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Calibri, "Segoe UI", sans-serif;
      background: linear-gradient(180deg, #ecfeff 0%, var(--bg) 28%);
      color: var(--text);
    }}
    header {{
      padding: 28px 32px 12px;
      max-width: 100%;
    }}
    h1 {{
      margin: 0 0 6px;
      font-size: 1.75rem;
      letter-spacing: -0.02em;
    }}
    .meta {{ color: var(--muted); margin: 4px 0 12px; }}
    .wrap {{
      margin: 0 16px 32px;
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      overflow: auto;
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06);
    }}
    table {{
      border-collapse: collapse;
      width: max-content;
      min-width: 100%;
      font-size: 13px;
    }}
    th, td {{
      border: 1px solid var(--border);
      padding: 8px 10px;
      white-space: nowrap;
      text-align: left;
    }}
    th.grupo {{
      background: var(--accent);
      color: #fff;
      text-align: center;
      font-size: 14px;
      position: sticky;
      top: 0;
      z-index: 2;
    }}
    thead tr:nth-child(2) th {{
      background: #ccfbf1;
      color: #134e4a;
      position: sticky;
      top: 34px;
      z-index: 1;
    }}
    tbody tr:hover td {{ filter: brightness(0.97); }}
    .badge {{
      display: inline-block;
      background: #ccfbf1;
      color: #0f766e;
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 600;
    }}
  </style>
</head>
<body>
  <header>
    <h1>{html.escape(titulo)}</h1>
    <p class="meta">Generado {html.escape(generado)} · <span class="badge">{total} estudiantes</span></p>
    {aviso_limite}
  </header>
  <div class="wrap">
    <table>
      <thead>
        <tr>{''.join(th_grupos)}</tr>
        <tr>{''.join(th_cols)}</tr>
      </thead>
      <tbody>
        {''.join(body_rows)}
      </tbody>
    </table>
  </div>
</body>
</html>
"""
    destino.write_text(contenido, encoding="utf-8")
    return destino.resolve()


def ruta_html_desde_excel(ruta_excel: Path) -> Path:
    return Path(ruta_excel).with_suffix(".html")
