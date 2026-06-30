from __future__ import annotations

import re
from datetime import date, datetime, timedelta

import polars as pl

from consolidado.core.constants import (
    FORMATO_FECHA_DMY,
    FORMATO_FECHA_MDY,
    _CARACTERES_TILDE,
    _EXCEL_EPOCH,
    _MESES_ES,
    _PROGRAMAS_EXCLUIDOS_RUNTIME,
    _PROGRAMAS_PERMITIDOS_RUNTIME,
    _REEMPLAZO_ACENTOS,
    aplicar_config,
)
def _es_nulo(val) -> bool:
    if val is None:
        return True
    if isinstance(val, float):
        return val != val
    return False

def _anio_completo(anio: int) -> int:
    if anio < 100:
        return 2000 + anio if anio < 50 else 1900 + anio
    return anio

def _fecha_a_texto_salida(d: date) -> str:
    """Formato MMMM-DD-YYYY (mes en español, p. ej. Mayo-20-2003)."""
    mes = _MESES_ES[d.month - 1].capitalize()
    return f"{mes}-{d.day:02d}-{d.year:04d}"

def _fecha_a_texto_dmy(d: date) -> str:
    return _fecha_a_texto_salida(d)

def _es_serial_excel_fecha(val) -> bool:
    if isinstance(val, bool):
        return False
    if isinstance(val, (int, float)) and not _es_nulo(val):
        n = float(val)
        return 1000 < n < 120000
    return False

def _serial_excel_a_fecha(serial: float) -> date | None:
    try:
        return _EXCEL_EPOCH + timedelta(days=int(serial))
    except (OverflowError, ValueError):
        return None

def _parsear_fecha_texto(texto: str, orden: str) -> date | None:
    s = texto.strip()
    if not s or s.lower() in ("nan", "nat", "none"):
        return None
    if " " in s:
        s = s.split()[0]
    if "T" in s and len(s) > 10:
        s = s.split("T")[0]

    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if iso:
        try:
            return date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        except ValueError:
            pass

    for sep in ("/", "-", "."):
        if sep not in s:
            continue
        partes = re.split(r"[/\-.]", s)
        if len(partes) != 3:
            continue
        try:
            p0, p1, p2 = (int(x) for x in partes)
        except ValueError:
            continue
        anio = _anio_completo(p2)
        if orden == FORMATO_FECHA_DMY:
            dia, mes = p0, p1
        else:
            mes, dia = p0, p1
        try:
            return date(anio, mes, dia)
        except ValueError:
            continue
    return None

def formatear_fecha_nacimiento(val, orden_origen: str = FORMATO_FECHA_DMY) -> str | None:
    """Normaliza a texto MMMM-DD-YYYY (mes en español)."""
    if _es_nulo(val):
        return None
    if isinstance(val, datetime):
        return _fecha_a_texto_dmy(val.date())
    if isinstance(val, date):
        return _fecha_a_texto_dmy(val)
    if hasattr(val, "date") and callable(getattr(val, "date", None)):
        try:
            return _fecha_a_texto_dmy(val.date())
        except (TypeError, ValueError):
            pass
    if _es_serial_excel_fecha(val):
        d = _serial_excel_a_fecha(float(val))
        if d:
            return _fecha_a_texto_dmy(d)
    texto = str(val).strip()
    if not texto or texto.lower() in ("nan", "nat"):
        return None
    d = _parsear_fecha_texto(texto, orden_origen)
    if d:
        return _fecha_a_texto_dmy(d)
    otro = FORMATO_FECHA_MDY if orden_origen == FORMATO_FECHA_DMY else FORMATO_FECHA_DMY
    d = _parsear_fecha_texto(texto, otro)
    if d:
        return _fecha_a_texto_dmy(d)
    return texto

def _orden_fecha_por_tipo_libro(tipo: str) -> str:
    return FORMATO_FECHA_MDY if tipo == "bd12" else FORMATO_FECHA_DMY

def normalizar_encabezado(col: str) -> str:
    if col is None or _es_nulo(col):
        return ""
    s = str(col).strip().lower().translate(_REEMPLAZO_ACENTOS)
    s = s.replace("_", " ")
    s = re.sub(r"\s+", " ", s)
    return s

def programa_esta_excluido(val) -> bool:
    if _es_nulo(val):
        return False
    if not _PROGRAMAS_EXCLUIDOS_RUNTIME:
        aplicar_config()
    norm = normalizar_encabezado(str(val))
    if norm in _PROGRAMAS_EXCLUIDOS_RUNTIME:
        return True
    for excl in _PROGRAMAS_EXCLUIDOS_RUNTIME:
        if excl and excl in norm:
            return True
    return False

def programa_es_permitido(val) -> bool:
    if _es_nulo(val):
        return False
    if programa_esta_excluido(val):
        return False
    if not _PROGRAMAS_PERMITIDOS_RUNTIME:
        aplicar_config()
    return normalizar_encabezado(str(val)) in _PROGRAMAS_PERMITIDOS_RUNTIME

def _es_valor_true(val) -> bool:
    if _es_nulo(val):
        return False
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val == 1
    return str(val).strip().lower() in ("true", "verdadero", "si", "sí", "1")

def normalizar_id(val) -> str:
    if _es_nulo(val):
        return ""
    # Enteros de Excel sin decimales molestos
    if isinstance(val, float) and val == int(val):
        val = int(val)
    s = str(val).strip()
    s = re.sub(r"\s+", "", s)
    return s

def _mapa_norm_a_real(columns: list[str]) -> dict[str, str]:
    return {normalizar_encabezado(c): c for c in columns}

def _str_celda(v) -> str:
    if _es_nulo(v):
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s

def _nombre_valido(val) -> bool:
    if _es_nulo(val):
        return False
    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "nat", "-", "—"):
        return False
    return True

def _clave_nombre_unico(val) -> str:
    """Clave para comparar nombres (sin acentos, minúsculas, espacios normalizados)."""
    if not _nombre_valido(val):
        return ""
    s = str(val).strip().lower().translate(_REEMPLAZO_ACENTOS)
    return re.sub(r"\s+", " ", s)

def _telefono_presente(val) -> bool:
    return bool(normalizar_telefono_celda(val))

def _es_valor_vacio(val) -> bool:
    if _es_nulo(val):
        return True
    return str(val).strip() == ""

def _cuenta_tildes(texto: str) -> int:
    return sum(1 for c in texto if c in _CARACTERES_TILDE)

def _preferir_nombre_con_tildes(nuevo: str, actual: str) -> bool:
    t_n = _cuenta_tildes(nuevo)
    t_a = _cuenta_tildes(actual)
    if t_n != t_a:
        return t_n > t_a
    return len(nuevo) > len(actual)

def combinar_valores(valores: list, separador: str = " | ") -> str:
    vals: list[str] = []
    for v in valores:
        if _es_nulo(v):
            continue
        s = str(v).strip()
        if s and s not in vals:
            vals.append(s)
    if not vals:
        return ""
    if len(vals) == 1:
        return vals[0]
    return separador.join(vals)

def _digitos_a_entero_str(digits: str) -> str | None:
    if not digits:
        return None
    try:
        return str(int(digits))
    except ValueError:
        return digits

def normalizar_telefono_celda(val) -> str | None:
    """Uno o varios teléfonos como enteros; varios separados por coma."""
    if _es_nulo(val):
        return None
    texto = str(val).strip()
    if not texto or texto.lower() == "nan":
        return None
    partes = re.split(r"[/|,]+|\s*\|\s*", texto)
    vistos: list[str] = []
    for parte in partes:
        p = parte.strip()
        if not p:
            continue
        if isinstance(p, float) and p == int(p):
            p = str(int(p))
        digits = re.sub(r"\D", "", p)
        entero = _digitos_a_entero_str(digits)
        if entero and entero not in vistos:
            vistos.append(entero)
    if not vistos:
        return None
    return ", ".join(vistos)

def _combinar_telefonos(valores: list) -> str:
    todos: list[str] = []
    for v in valores:
        norm = normalizar_telefono_celda(v)
        if not norm:
            continue
        for n in norm.split(", "):
            if n and n not in todos:
                todos.append(n)
    return ", ".join(todos)

def _entero_o_texto(val) -> str | None:
    if _es_nulo(val):
        return None
    if isinstance(val, float) and val == int(val):
        return str(int(val))
    if isinstance(val, int):
        return str(val)
    s = str(val).strip()
    if not s:
        return None
    digits = re.sub(r"\D", "", s)
    if digits and digits == re.sub(r"\s+", "", s):
        return digits
    return s

def _primero_no_vacio(valores: list):
    for v in valores:
        if _es_nulo(v):
            continue
        t = str(v).strip()
        if t:
            return v
    return None

def _es_funcionario_call_center(val) -> bool:
    if _es_nulo(val):
        return False
    return "call center" in str(val).strip().lower()

