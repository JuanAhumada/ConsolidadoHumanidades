from __future__ import annotations

import re
from copy import deepcopy
from datetime import date
from pathlib import Path

from consolidado.paths import PROJECT_ROOT
from zipfile import BadZipFile

from openpyxl.styles import Font

from consolidado.config.settings import (
    ARCHIVOS_FUENTE_REQUERIDOS,
    COLUMNAS_ALERTAS,
    COLUMNAS_ALERTAS_PROPIAS,
    COLUMNAS_BECAS,
    COLUMNAS_DATOS,
    COLUMNAS_PRIORIZADO,
    COLUMNAS_PRIORIZADO_ENRIQUECIDO,
    cargar_config,
    construir_columnas_salida,
)
_REEMPLAZO_ACENTOS = str.maketrans(
    {
        "á": "a",
        "é": "e",
        "í": "i",
        "ó": "o",
        "ú": "u",
        "ü": "u",
        "Á": "a",
        "É": "e",
        "Í": "i",
        "Ó": "o",
        "Ú": "u",
        "Ü": "u",
    }
)

MAX_REINTENTOS_LECTURA = 3

PAUSA_ENTRE_REINTENTOS_SEG = 1.5

ANCHO_MAXIMO_COLUMNA_EXCEL = 255

ERRORES_LECTURA_REINTENTABLES = (
    PermissionError,
    FileNotFoundError,
    OSError,
    ValueError,
    BadZipFile,
)

COL_TELEFONO_CELULAR = "Teléfono celular"

COL_NOMBRE = "Nombre y apellidos"

COL_DATOS_CONTACTO = (
    COL_TELEFONO_CELULAR,
    "Correo institucional",
    "Correo personal",
)

_CARACTERES_TILDE = "áéíóúüÁÉÍÓÚÜñÑ"

COL_FECHA_NACIMIENTO = "Fecha de nacimiento"

COL_NUM_ALERTA_INICIAL = "Num Alerta inicial"
COL_TIPO_ALERTA_INICIAL = "Tipo Alerta inicial"
COL_NUM_ALERTA_FINAL = "Num Alerta final"
COL_TIPO_ALERTA_FINAL = "Tipo Alerta final"

# Compatibilidad con código legado
COL_NUM_ALERTAS = COL_NUM_ALERTA_INICIAL
COL_TIPOS_ALERTA = COL_TIPO_ALERTA_INICIAL

COL_AJUSTE_RAZONABLE = "Adaptacion"
COL_FECHA_AJUSTE = "Fecha adaptacion"
COL_ACTIVACION_RUTA = "Activacion de ruta"
COL_FECHA_ACTIVACION_RUTA = "Fecha activacion de ruta"

COL_TOTAL_BECA = "Total beca"
COL_FUNCIONARIO_BECA = "Funcionario que tiene a cargo la beca"
COL_TIPO_BECA = "Tipo de beca o crédito"

COL_REPITIENDO = "Repitiendo"

COL_PTJE_BECA = "Ptje Beca"
COL_PTJE_PRIORIZADO = "Ptje Priorizado"
COL_PTJE_REPITIENDO = "Ptje Repitiendo"
COL_PTJE_REINTEGRO = "Ptje Reintegro"
COL_PTJE_PROPIO = "Ptje Propio"
COL_PTJE_ACTIVACION = "Ptje Activacion"

COLUMNAS_PUNTAJE_COMPONENTES = (
    COL_PTJE_BECA,
    COL_PTJE_PRIORIZADO,
    COL_PTJE_REPITIENDO,
    COL_PTJE_REINTEGRO,
    COL_PTJE_PROPIO,
    COL_PTJE_ACTIVACION,
)

COL_ALERTA_PROPIA = "Alerta Propia"
COL_DETALLE_PROPIO = "Detalle Propio"

COL_PUNTAJE_PRIORIDAD = "Puntaje prioridad"
COL_NIVEL_PRIORIDAD = "Nivel prioridad"
COL_DETALLE_PRIORIDAD = "Detalle prioridad"

MOTIVO_PRIORIZADO_PROPIO = "Priorizado propio"
MOTIVO_PRIORIZADO_INTERNO = "PRIORIZADO INTERNO"

FILL_CALL_CENTER_EXCEL = "D9D9D9"

FILL_FILA_ACTIVACION_RUTA = "FFC7CE"

FILL_FILA_ALERTA = "FFEB9C"

FONT_MATERIA_REPETIDA = Font(bold=True, underline="single")

_MESES_ES = (
    "enero",
    "febrero",
    "marzo",
    "abril",
    "mayo",
    "junio",
    "julio",
    "agosto",
    "septiembre",
    "octubre",
    "noviembre",
    "diciembre",
)

_TIPOS_FUENTE_AUXILIARES = {
    "bd_rep",
    "bd_alertas_com",
    "bd_alertas_psi",
    "bd_prio_psi",
    "bd_prio_lic",
}

COLUMNAS_EXCLUIDAS_LISTADO = frozenset(
    COLUMNAS_ALERTAS + COLUMNAS_ALERTAS_PROPIAS + COLUMNAS_PRIORIZADO_ENRIQUECIDO
)

FORMATO_FECHA_DMY = "dmy"

FORMATO_FECHA_MDY = "mdy"

_EXCEL_EPOCH = date(1899, 12, 30)

HOJA_LISTADO = "Listado"

SALIDA_COLUMNAS_LISTADO = [
    *COLUMNAS_DATOS,
    *COLUMNAS_PRIORIZADO,
    *COLUMNAS_BECAS,
]

_APP_CONFIG: dict | None = None

_ALIASES_RUNTIME: dict[str, list[str]] = {}

_PROGRAMAS_PERMITIDOS_RUNTIME: set[str] = set()

_PROGRAMAS_EXCLUIDOS_RUNTIME: set[str] = set()

_COLUMNAS_MOTIVO_PRIO_RUNTIME: list[str] = []

_RE_COL_MATERIA = re.compile(r"^(Materia|Horario|Profesor) (\d+)$")

TITULOS_EXCEL_FUENTE = [
    "Archivo 1 — Matriculados activos",
    "Archivo 2 — Matriculados activos (entrenamiento)",
    "Archivo 3 — Grupos priorizados",
    "Archivo 4 — Becados y con crédito",
]

def columnas_materia_horario(num_materias: int) -> list[str]:
    cols: list[str] = []
    for i in range(1, max(num_materias, 1) + 1):
        cols.extend([f"Materia {i}", f"Horario {i}", f"Profesor {i}"])
    return cols

def aplicar_config(cfg: dict | None = None, base: Path | None = None) -> dict:
    """Carga aliases y reglas desde config.json al runtime del módulo."""
    global _APP_CONFIG
    base = base or PROJECT_ROOT
    _APP_CONFIG = cfg if cfg is not None else cargar_config(base)
    # Mutar en sitio: otros módulos importan estas referencias con `from ... import`.
    _ALIASES_RUNTIME.clear()
    _ALIASES_RUNTIME.update(deepcopy(_APP_CONFIG.get("aliases", {})))
    from consolidado.core.normalizacion import normalizar_encabezado

    _PROGRAMAS_PERMITIDOS_RUNTIME.clear()
    _PROGRAMAS_PERMITIDOS_RUNTIME.update(
        normalizar_encabezado(p) for p in _APP_CONFIG.get("programas_permitidos", [])
    )
    _PROGRAMAS_EXCLUIDOS_RUNTIME.clear()
    _PROGRAMAS_EXCLUIDOS_RUNTIME.update(
        normalizar_encabezado(p) for p in _APP_CONFIG.get("programas_excluidos", [])
    )
    _COLUMNAS_MOTIVO_PRIO_RUNTIME.clear()
    _COLUMNAS_MOTIVO_PRIO_RUNTIME.extend(
        normalizar_encabezado(c)
        for c in _APP_CONFIG.get("columnas_motivo_priorizado", [])
    )
    from consolidado.core.prioridad import aplicar_colores_prioridad

    aplicar_colores_prioridad(_APP_CONFIG)
    return _APP_CONFIG

def _cfg() -> dict:
    if _APP_CONFIG is None:
        return aplicar_config()
    return _APP_CONFIG

def es_columna_materia_horario(col: str) -> bool:
    return _RE_COL_MATERIA.match(str(col)) is not None

def max_materias_en_dataframe(df: pl.DataFrame) -> int:
    max_n = 0
    for col in df.columns:
        m = _RE_COL_MATERIA.match(str(col))
        if m:
            max_n = max(max_n, int(m.group(2)))
    return max_n

