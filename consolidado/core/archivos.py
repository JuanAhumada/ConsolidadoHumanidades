from __future__ import annotations

from pathlib import Path

import polars as pl

from consolidado.config.settings import COLUMNAS_BECAS, COLUMNAS_PRIORIZADO
from consolidado.core.columnas import construir_mapa_columnas, renombrar_y_filtrar
from consolidado.core.constants import (
    COL_NOMBRE,
    _COLUMNAS_MOTIVO_PRIO_RUNTIME,
    aplicar_config,
)
from consolidado.core.excel_io import (
    _leer_hoja_excel,
    _nombres_hojas_excel,
    ejecutar_lectura_con_recuperacion,
)
from consolidado.core.fusion import (
    filtrar_filas_con_nombre,
    filtrar_filas_programas_permitidos,
)
from consolidado.core.normalizacion import (
    _es_nulo,
    _es_valor_true,
    _mapa_norm_a_real,
    _orden_fecha_por_tipo_libro,
    _str_celda,
    combinar_valores,
    normalizar_encabezado,
    normalizar_id,
    programa_es_permitido,
)
def _limpiar_becas_programa_no_permitido(df: pl.DataFrame) -> pl.DataFrame:
    """Quita datos de beca si el programa del estudiante no aplica."""
    if df.height == 0 or "Programa" not in df.columns:
        return df
    permitido = pl.col("Programa").map_elements(programa_es_permitido, return_dtype=pl.Boolean)
    exprs = []
    for col in df.columns:
        if col in COLUMNAS_BECAS:
            exprs.append(pl.when(permitido).then(pl.col(col)).otherwise(None).alias(col))
        else:
            exprs.append(pl.col(col))
    return df.select(exprs)

def _leer_hoja_datos(ruta: Path, *, tipo: str | None = None, hoja: str | None = None) -> pl.DataFrame:
    nombre_hoja = hoja or _elegir_hoja_datos(ruta, tipo=tipo)
    return _leer_hoja_excel(ruta, nombre_hoja)

def _nombre_hoja_horario(ruta: Path) -> str | None:
    suf = ruta.suffix.lower()
    if suf not in (".xlsx", ".xlsm"):
        return None
    nombres = _nombres_hojas_excel(ruta)
    for sn in nombres:
        if sn.strip().upper() == "HORARIO":
            return sn
    return _hoja_por_subcadena(nombres, "horario")

def _columna_horario(df: pl.DataFrame, nombre: str) -> str | None:
    nr = _mapa_norm_a_real(list(df.columns))
    return nr.get(normalizar_encabezado(nombre))

def _texto_horario(val) -> str:
    if _es_nulo(val):
        return ""
    if hasattr(val, "hour") and hasattr(val, "strftime") and not isinstance(val, type):
        if getattr(val, "hour", 0) or getattr(val, "minute", 0) or getattr(val, "second", 0):
            return val.strftime("%H:%M")
        return val.strftime("%Y-%m-%d")
    if hasattr(val, "hour") and hasattr(val, "minute"):
        return f"{val.hour:02d}:{val.minute:02d}"
    if isinstance(val, float) and 0 < val < 1:
        from datetime import datetime, timedelta

        return (datetime.min + timedelta(days=val)).strftime("%H:%M")
    if isinstance(val, float) and val == int(val):
        return str(int(val))
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return ""
    if " 00:00:00" in s:
        s = s.split()[0]
    return s

def _cod_pensum_es_numero(val) -> bool:
    if _es_nulo(val):
        return False
    if isinstance(val, bool):
        return False
    if isinstance(val, (int, float)):
        return True
    s = str(val).strip()
    if not s:
        return False
    if s.isdigit():
        return True
    try:
        float(s)
        return True
    except ValueError:
        return False

def _unir_partes(partes: list[str], separador: str = " - ") -> str:
    limpias = [p for p in partes if p]
    if not limpias:
        return ""
    if len(limpias) == 1:
        return limpias[0]
    return separador.join(limpias)

def _formatear_aparicion_horario(row: dict, c: dict[str, str | None]) -> tuple[str, str, str]:
    """Devuelve (materia, horario, profesor) para una fila de la hoja HORARIO."""
    pensum = row[c["cod_pensum"]] if c.get("cod_pensum") else None
    if _cod_pensum_es_numero(pensum):
        materia = _unir_partes(
            [
                _texto_horario(row[c["nom_subgrupo"]]) if c.get("nom_subgrupo") else "",
                _texto_horario(row[c["num_grupo"]]) if c.get("num_grupo") else "",
            ]
        )
        dia_hora = _unir_partes(
            [
                " ".join(
                    p
                    for p in (
                        _texto_horario(row[c["num_dia"]]) if c.get("num_dia") else "",
                        _texto_horario(row[c["dia"]]) if c.get("dia") else "",
                    )
                    if p
                ),
                _texto_horario(row[c["hor_inicio"]]) if c.get("hor_inicio") else "",
            ],
        )
        profesor = _unir_partes(
            [
                _texto_horario(row[c["num_identificacion_docente"]])
                if c.get("num_identificacion_docente")
                else "",
                _texto_horario(row[c["docente"]]) if c.get("docente") else "",
            ],
            separador=": ",
        )
    else:
        materia = _unir_partes(
            [
                _texto_horario(row[c["num_grupo"]]) if c.get("num_grupo") else "",
                _texto_horario(row[c["nom_materia"]]) if c.get("nom_materia") else "",
            ]
        )
        dia_hora = _unir_partes(
            [
                " ".join(
                    p
                    for p in (
                        _texto_horario(row[c["dia"]]) if c.get("dia") else "",
                        _texto_horario(row[c["hor_inicio"]]) if c.get("hor_inicio") else "",
                    )
                    if p
                ),
                _texto_horario(row[c["hor_fin"]]) if c.get("hor_fin") else "",
            ],
        )
        profesor = _unir_partes(
            [
                _texto_horario(row[c["docente"]]) if c.get("docente") else "",
                _texto_horario(row[c["dir_email"]]) if c.get("dir_email") else "",
            ],
            separador=": ",
        )
    return materia, dia_hora, profesor

def _mapear_columnas_horario(df: pl.DataFrame) -> dict[str, str | None]:
    return {
        "num_identificacion": _columna_horario(df, "NUM_IDENTIFICACION"),
        "genero": _columna_horario(df, "GENERO"),
        "cod_pensum": _columna_horario(df, "COD_PENSUM"),
        "nom_subgrupo": _columna_horario(df, "NOM_SUBGRUPO"),
        "num_grupo": _columna_horario(df, "NUM_GRUPO"),
        "nom_materia": _columna_horario(df, "NOM_MATERIA"),
        "num_dia": _columna_horario(df, "NUM_DIA"),
        "dia": _columna_horario(df, "DIA"),
        "hor_inicio": _columna_horario(df, "HOR_INICIO"),
        "hor_fin": _columna_horario(df, "HOR_FIN"),
        "num_identificacion_docente": _columna_horario(df, "NUM_IDENTIFICACION_DOCENTE"),
        "docente": _columna_horario(df, "DOCENTE"),
        "dir_email": _columna_horario(df, "DIR_EMAIL"),
    }

def resumir_hoja_horario(df_horario: pl.DataFrame) -> pl.DataFrame:
    """Por NUM_IDENTIFICACION: Materia/Horario/Profesor 1..n (una materia por fila de clase)."""
    c = _mapear_columnas_horario(df_horario)
    if not c.get("num_identificacion"):
        raise ValueError(
            "La hoja HORARIO no tiene columna NUM_IDENTIFICACION. "
            f"Columnas: {list(df_horario.columns)}"
        )

    por_id: dict[str, list[dict]] = {}
    for row in df_horario.iter_rows(named=True):
        id_key = normalizar_id(row[c["num_identificacion"]])
        if not id_key:
            continue
        materia, horario, profesor = _formatear_aparicion_horario(row, c)
        if id_key not in por_id:
            por_id[id_key] = []
        por_id[id_key].append(
            {
                "materia": materia,
                "horario": horario,
                "profesor": profesor,
            }
        )

    if not por_id:
        return pl.DataFrame()

    filas: list[dict] = []
    for id_key in sorted(por_id.keys()):
        items = por_id[id_key]
        fila: dict = {
            "_id_key": id_key,
            "Identificación": id_key,
        }
        for i, it in enumerate(items, start=1):
            if it["materia"]:
                fila[f"Materia {i}"] = it["materia"]
            if it["horario"]:
                fila[f"Horario {i}"] = it["horario"]
            if it["profesor"]:
                fila[f"Profesor {i}"] = it["profesor"]
        filas.append(fila)
    return pl.DataFrame(filas)

def _motivos_fila_priorizado(row: dict, cols_motivo: list[tuple[str, str]]) -> str:
    motivos: list[str] = []
    for titulo, col in cols_motivo:
        if _es_valor_true(row[col]):
            if titulo not in motivos:
                motivos.append(titulo)
    return ", ".join(motivos)

def _detalle_fila_priorizado(row: dict, col_tipo: str | None, col_detalle: str | None) -> str:
    partes: list[str] = []
    if col_tipo:
        tipo = _str_celda(row[col_tipo])
        if tipo and tipo not in ("-", "—"):
            partes.append(tipo)
    if col_detalle:
        det = _str_celda(row[col_detalle])
        if det:
            partes.append(det)
    return " | ".join(partes)

def procesar_tabla_priorizados(
    ruta: Path,
    *,
    tipo: str | None = None,
    hoja: str | None = None,
) -> pl.DataFrame:
    """
    BD Grupos priorizados: solo programas permitidos.
    No crea filas nuevas; devuelve datos para enriquecer identificaciones existentes.
    """
    df = _leer_hoja_datos(ruta, tipo=tipo or "bd2", hoja=hoja)
    df = filtrar_filas_programas_permitidos(df)
    if df.height == 0:
        return pl.DataFrame(schema={"_id_key": pl.Utf8, **{c: pl.Utf8 for c in COLUMNAS_PRIORIZADO}})

    m = construir_mapa_columnas(list(df.columns))
    if "identificacion" not in m:
        raise ValueError(
            "Grupos priorizados: falta columna de identificación. "
            f"Columnas: {list(df.columns)}"
        )

    nr = _mapa_norm_a_real(list(df.columns))
    cols_motivo: list[tuple[str, str]] = []
    if not _COLUMNAS_MOTIVO_PRIO_RUNTIME:
        aplicar_config()
    for norm in _COLUMNAS_MOTIVO_PRIO_RUNTIME:
        if norm in nr:
            cols_motivo.append((nr[norm], nr[norm]))

    col_tipo = nr.get(normalizar_encabezado("TIPO DE DISCAPACIDAD"))
    col_detalle = nr.get(normalizar_encabezado("DETALLE GRUPO PRIORIZADO"))

    registros: list[dict] = []
    for row in df.iter_rows(named=True):
        id_key = normalizar_id(row[m["identificacion"]])
        if not id_key:
            continue
        registros.append(
            {
                "_id_key": id_key,
                "Priorizado": True,
                "Motivo Prio.": _motivos_fila_priorizado(row, cols_motivo) or None,
                "Detalle GPrio.": _detalle_fila_priorizado(row, col_tipo, col_detalle) or None,
            }
        )

    if not registros:
        return pl.DataFrame(schema={"_id_key": pl.Utf8, **{c: pl.Utf8 for c in COLUMNAS_PRIORIZADO}})

    tmp = pl.DataFrame(registros)
    filas: list[dict] = []
    for key in tmp["_id_key"].unique().sort().to_list():
        grp = tmp.filter(pl.col("_id_key") == key)
        fila: dict = {"_id_key": key, "Priorizado": True}
        fila["Motivo Prio."] = combinar_valores(grp["Motivo Prio."].to_list(), separador=", ") or None
        fila["Detalle GPrio."] = combinar_valores(grp["Detalle GPrio."].to_list(), separador=", ") or None
        filas.append(fila)
    return pl.DataFrame(filas)

def _preparar_archivo_interno(
    ruta: Path,
    *,
    tipo: str | None = None,
    hoja: str | None = None,
) -> tuple[pl.DataFrame, pl.DataFrame]:
    tipo = tipo or _tipo_libro_desde_nombre(ruta)
    raw = _leer_hoja_datos(ruta, tipo=tipo, hoja=hoja)
    if tipo in ("bd2", "bd3"):
        raw = filtrar_filas_programas_permitidos(raw)
        if raw.height == 0:
            return pl.DataFrame(), pl.DataFrame()
    df_listado = renombrar_y_filtrar(
        raw, formato_fecha_nacimiento=_orden_fecha_por_tipo_libro(tipo)
    )
    df_listado = filtrar_filas_con_nombre(df_listado)
    df_horarios = pl.DataFrame()
    if tipo == "bd1":
        hoja_hor = _nombre_hoja_horario(ruta)
        if hoja_hor:
            df_horarios = resumir_hoja_horario(_leer_hoja_excel(ruta, hoja_hor))
    return df_listado, df_horarios

def preparar_archivo(
    ruta: Path,
    etiqueta: str = "",
    *,
    tipo: str | None = None,
    hoja: str | None = None,
    permitir_seleccionar_otro: bool = True,
) -> tuple[pl.DataFrame, pl.DataFrame, Path]:
    etiqueta = etiqueta or ruta.name

    def _cargar(path: Path) -> tuple[pl.DataFrame, pl.DataFrame]:
        return _preparar_archivo_interno(path, tipo=tipo, hoja=hoja)

    resultado, ruta_ok = ejecutar_lectura_con_recuperacion(
        ruta,
        etiqueta,
        _cargar,
        permitir_seleccionar_otro=permitir_seleccionar_otro,
    )
    listado, horarios = resultado
    return listado, horarios, ruta_ok

def procesar_tabla_priorizados_con_recuperacion(
    ruta: Path,
    etiqueta: str = "",
    *,
    tipo: str | None = None,
    hoja: str | None = None,
    permitir_seleccionar_otro: bool = True,
) -> tuple[pl.DataFrame, Path]:
    etiqueta = etiqueta or ruta.name

    def _cargar(path: Path) -> pl.DataFrame:
        return procesar_tabla_priorizados(path, tipo=tipo, hoja=hoja)

    return ejecutar_lectura_con_recuperacion(
        ruta,
        etiqueta,
        _cargar,
        permitir_seleccionar_otro=permitir_seleccionar_otro,
    )

def _es_hoja_auxiliar(nombre: str) -> bool:
    u = nombre.strip().upper()
    return u == "SQL" or "PIVOT" in u

def _tipo_libro_desde_nombre(ruta: Path) -> str:
    n = ruta.name.lower()
    if n.startswith("bd3.") or n == "bd3.xlsx":
        return "bd3"
    if n.startswith("bd2.") or n == "bd2.xlsx":
        return "bd2"
    if n.startswith("bd12.") or n == "bd12.xlsx":
        return "bd12"
    if n.startswith("bd1.") or n == "bd1.xlsx":
        return "bd1"
    if "1.2" in n or "entrenamiento" in n:
        return "bd12"
    if n.startswith("bd 2") or "bd 2." in n or "grupos priorizados" in n:
        return "bd2"
    if "bd 3" in n or "becados" in n or ("credito" in n and "beca" in n):
        return "bd3"
    if n.startswith("bd_rep") or "asignaturas repetidas" in n or "repetidas" in n:
        return "bd_rep"
    if "alertas" in n and "psicolog" in n:
        return "bd_alertas_psi"
    if "alertas" in n and ("comunicacion" in n or "entrenamiento" in n):
        return "bd_alertas_com"
    if "alertas" in n:
        return "bd_alertas_com"
    if "priorizado" in n and "psicolog" in n:
        return "bd_prio_psi"
    if "priorizados licen" in n or ("priorizado" in n and "licen" in n):
        return "bd_prio_lic"
    return "bd1"

def _hoja_por_subcadena(nombres: list[str], parcial: str) -> str | None:
    p = parcial.lower()
    for sn in nombres:
        if p in sn.lower():
            return sn
    return None

def _elegir_hoja_datos(ruta: Path, *, tipo: str | None = None) -> str:
    nombres = _nombres_hojas_excel(ruta)
    tipo = tipo or _tipo_libro_desde_nombre(ruta)
    candidata: str | None = None

    if tipo == "bd1":
        candidata = next((sn for sn in nombres if sn.strip().upper() == "BASE"), None) or _hoja_por_subcadena(
            nombres, "base"
        )
    elif tipo == "bd12":
        candidata = _hoja_por_subcadena(nombres, "exportar")
    elif tipo == "bd2":
        candidata = next(
            (sn for sn in nombres if sn.upper().replace(" ", "_") == "GRUPOS_PRIORIZADOS"),
            None,
        ) or _hoja_por_subcadena(nombres, "grupos_priorizado")
    elif tipo == "bd3":
        candidata = next(
            (sn for sn in nombres if sn.strip().upper() == "ESTUDIANTES"),
            None,
        ) or next(
            (
                sn
                for sn in nombres
                if "becas" in sn.lower() and "credito" in sn.lower().replace("é", "e")
            ),
            None,
        ) or _hoja_por_subcadena(nombres, "estudiantes")
    elif tipo == "bd_rep":
        candidata = _hoja_por_subcadena(nombres, "hoja") or (nombres[0] if nombres else None)
    elif tipo in ("bd_alertas_com", "bd_alertas_psi"):
        candidata = _hoja_por_subcadena(nombres, "sheet") or (nombres[0] if nombres else None)
    elif tipo == "bd_prio_psi":
        candidata = next(
            (sn for sn in nombres if sn.strip().upper() == "PRIORIZADOS GENERAL"),
            None,
        ) or _hoja_por_subcadena(nombres, "priorizados general")
    elif tipo == "bd_prio_lic":
        candidata = next(
            (sn for sn in nombres if sn.upper().replace(" ", "_") == "GRUPOS_PRIORIZADOS"),
            None,
        ) or _hoja_por_subcadena(nombres, "grupos_priorizado")

    if candidata:
        return candidata
    return _primera_hoja_con_tabla(ruta, nombres)

def _primera_hoja_con_tabla(ruta: Path, nombres: list[str]) -> str:
    for sn in nombres:
        if _es_hoja_auxiliar(sn):
            continue
        df = _leer_hoja_excel(ruta, sn).head(5)
        if df.width < 2:
            continue
        if "identificacion" in construir_mapa_columnas(list(df.columns)):
            return sn
    for sn in nombres:
        if not _es_hoja_auxiliar(sn):
            return sn
    return nombres[0]

