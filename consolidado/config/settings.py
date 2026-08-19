"""
Carga y guardado de config.json.

COLUMNAS_* alimentan grupos_salida. ALIASES_DEFAULT mapea encabezados de Excel.
_fusionar_grupos_salida añade columnas nuevas del default al JSON existente
(por eso Periodo actual aparece sin reescribir a mano el archivo).
"""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from consolidado.paths import PROJECT_ROOT

CONFIG_FILENAME = "config.json"
CONFIG_FABRICA_FILENAME = "config_fabrica.json"
CARPETA_EXCELS_DEFAULT = "datos/entrada"

COLUMNAS_DATOS = [
    "Identificación",
    "Nombre y apellidos",
    "Activos",
    "Fecha de nacimiento",
    "Teléfono celular",
    "Programa",
    "Correo institucional",
    "Correo personal",
    "Periodo ingreso",
    "Periodo actual",
    "Reintegros",
    "Lugar de nacimiento",
    "Lugar de residencia",
]

COLUMNAS_PRIORIZADO = ["Priorizado", "Motivo Prio.", "Detalle GPrio."]

COLUMNAS_PRIORIZADO_ENRIQUECIDO = [
    "Adaptacion",
    "Fecha adaptacion",
    "Activacion de ruta",
    "Fecha activacion de ruta",
]

COLUMNAS_PUNTAJE_COMPONENTES = [
    "Ptje Beca",
    "Ptje Priorizado",
    "Ptje Repitiendo",
    "Ptje Reintegro",
    "Ptje Propio",
    "Ptje Activacion",
    "Ptje Ruta",
]

COLUMNAS_PRIORIDAD = [
    "Puntaje prioridad",
    "Nivel prioridad",
    "Detalle prioridad",
]

COLUMNAS_REPITIENDO = ["Repitiendo"]

COLUMNAS_BECAS = [
    "Tipo de beca o crédito",
    "Total beca",
    "Funcionario que tiene a cargo la beca",
]

COLUMNAS_ALERTAS = [
    "Num Alerta inicial",
    "Tipo Alerta inicial",
    "Num Alerta final",
    "Tipo Alerta final",
]

COLUMNAS_ALERTAS_PROPIAS = [
    "Alerta Propia",
    "Detalle Propio",
]

COLUMNAS_RUTA_GRADO = [
    "% créditos aprobados",
    "Estado opción de grado",
    "Opción de grado",
    "Estado de inglés",
    "Saber Pro",
]

ETIQUETAS_EXPORT_COLUMNAS: dict[str, str] = {
    "Ptje Beca": "Beca",
    "Ptje Priorizado": "Priorizado",
    "Ptje Repitiendo": "Repitiendo",
    "Ptje Reintegro": "Reintegro",
    "Ptje Propio": "Propio",
    "Ptje Activacion": "Activacion",
    "Ptje Ruta": "Ruta",
}

CATEGORIAS_FUENTE_DEFAULT: dict[str, str] = {
    "base": "Base",
    "priorizado": "Priorizado",
    "rendimiento": "Rendimiento",
    "alertas": "Alertas",
}

ORDEN_CATEGORIAS_FUENTE = ["base", "priorizado", "rendimiento", "alertas"]

ARCHIVOS_FUENTE_REQUERIDOS = {"bd1", "bd12", "bd2", "bd3"}

_COLUMNAS_ALERTAS_LEGACY = frozenset({"Num Alertas", "Tipos de Alerta"})

_MIGRACION_COLUMNAS_BECAS = {
    "Total": "Total beca",
    "Funcionario": "Funcionario que tiene a cargo la beca",
}

_MIGRACION_IDS_ARCHIVO: dict[str, str] = {
    "bd_alertas_com": "bd_alertas_com_1",
    "bd_alertas_psi": "bd_alertas_psi_1",
}

ALIASES_DEFAULT: dict[str, list[str]] = {
    "identificacion": [
        "documento",
        "num identificacion",
        "identificacion",
        "identificación",
        "identificacin",
        "id",
        "cedula",
        "cc",
        "numero documento",
        "documento identidad",
    ],
    "nombre_estudiante": [
        "nombres y apellidos",
        "nombres",
        "nombre de estudiante",
        "nombre estudiante",
        "nombre completo",
        "alumno",
        "apellidos y nombres",
    ],
    "fecha_nacimiento": [
        "fecha nacimiento",
        "fecha de nacimiento",
        "fec nacimiento",
    ],
    "telefono_celular": ["tel. celular", "celular"],
    "programa": ["programa", "nom unidad"],
    "correo_institucional": [
        "correo electronico institucional",
        "correo institucional",
        "email institucional",
        "correo u",
    ],
    "correo_personal": [
        "correo electronico personal",
        "correo personal",
        "email personal",
        "e mail personal",
        "e-mail personal",
    ],
    "periodo_ingreso": [
        "periodo de ingreso",
        "periodo ingreso",
        "cohorte de ingreso",
        "cohorte",
        "año ingreso",
        "ano ingreso",
    ],
    "periodo_actual": [
        "cod periodo",
        "codigo periodo",
        "cod_periodo",
        "ultimo periodo inscrito",
        "periodo ultima matricula",
        "cod pensum",
        "codigo pensum",
        "cod_pensum",
    ],
    "periodo_ultima_matricula": ["periodo ultima matricula"],
    "reintegros": ["reintegros"],
    "lugar_nacimiento": ["lugar de nacimiento", "lugar nacimiento"],
    "lugar_residencia": ["lugar de residencia", "lugar residencia"],
    "direccion_residencia": [
        "direccion de residencia",
        "direccion residencia",
        "dir residencia",
    ],
    "total_beca": [
        "total",
        "valor",
        "valor total",
        "monto total",
        "monto",
        "importe",
        "vr total",
        "vlr total",
        "valor beca",
        "vr beca",
        "total beca",
    ],
    "tipo_beca_credito": [
        "nom concepto",
        "tipo de beca o credito",
        "tipo de beca o crédito",
        "tipo beca credito",
        "tipo beca",
        "modalidad beca",
    ],
    "funcionario_beca": [
        "responsable",
        "funcionario",
        "funcionario que tiene a cargo la beca",
        "funcionario beca",
        "encargado beca",
    ],
}

PROGRAMAS_PERMITIDOS_DEFAULT = [
    "COMUNICACION SOCIAL Y MEDIOS DIGITALES",
    "PSICOLOGIA",
    "LICENCIATURA EN EDUCACION BASICA PRIMARIA",
]

PROGRAMAS_EXCLUIDOS_DEFAULT = [
    "PSICOLOGIA VILLAVICENCIO",
]

COLUMNAS_MOTIVO_PRIO_DEFAULT = [
    "DISCAPACIDAD",
    "MINORIA RACIAL",
    "LGTBI+",
    "VICTIMA DE CONFLICTO ARMADO",
    "ZONA DE DIFICIL ACCESO",
    "AJUSTES RAZONABLES",
    "N.A.",
]

COLORES_PRIORIDAD_DEFAULT = {
    "rojo": "E74C3C",
    "morado": "9B59B6",
    "naranja": "E67E22",
    "reintegro": "2980B9",
    "repitiendo": "5DADE2",
    "ruta": "1ABC9C",
    "amarillo": "F1C40F",
    "verde": "2ECC71",
    "gris": "BDC3C7",
}

# Compatibilidad con configuraciones guardadas con claves antiguas.
COLORES_PRIORIDAD_LEGACY = {
    "nivel_5": "rojo",
    "nivel_4": "naranja",
    "nivel_3": "reintegro",
    "nivel_2": "amarillo",
    "nivel_1": "verde",
    "alerta": "amarillo",
    "call_center": "gris",
    "azul": "reintegro",
}

ARCHIVOS_FUENTE_DEFAULT = [
    {
        "id": "bd1",
        "categoria": "base",
        "titulo": "Matriculados activos",
        "tipo": "bd1",
        "nombre_guardado": "bd1.xlsx",
    },
    {
        "id": "bd12",
        "categoria": "base",
        "titulo": "Matriculados activos (entrenamiento)",
        "tipo": "bd12",
        "nombre_guardado": "bd12.xlsx",
    },
    {
        "id": "bd2",
        "categoria": "priorizado",
        "titulo": "Grupos priorizados",
        "tipo": "bd2",
        "nombre_guardado": "bd2.xlsx",
    },
    {
        "id": "bd_prio_psi",
        "categoria": "priorizado",
        "titulo": "Priorizado Psicología enriquecido",
        "tipo": "bd_prio_psi",
        "nombre_guardado": "bd_prio_psi.xlsx",
        "hoja": "PRIORIZADOS GENERAL",
    },
    {
        "id": "bd_prio_lic",
        "categoria": "priorizado",
        "titulo": "Priorizados Lic. Comun. y Entrenamiento",
        "tipo": "bd_prio_lic",
        "nombre_guardado": "bd_prio_lic.xlsx",
        "hoja": "GRUPOS_PRIORIZADOS",
    },
    {
        "id": "bd3",
        "categoria": "rendimiento",
        "titulo": "Becados y con crédito",
        "tipo": "bd3",
        "nombre_guardado": "bd3.xlsx",
        "hoja": "BECAS Y CRÉDITOS",
    },
    {
        "id": "bd_rep",
        "categoria": "rendimiento",
        "titulo": "Asignaturas repetidas",
        "tipo": "bd_rep",
        "nombre_guardado": "bd_rep.xlsx",
        "hoja": "Hoja1",
    },
    {
        "id": "bd_permanencia",
        "categoria": "rendimiento",
        "titulo": "Permanencia y ruta de grado",
        "tipo": "bd_permanencia",
        "nombre_guardado": "bd_permanencia.xlsx",
        "requerido": False,
    },
    {
        "id": "bd_alertas_com_1",
        "categoria": "alertas",
        "titulo": "Alertas Comunicación — inicial",
        "tipo": "bd_alertas_com",
        "fase": "inicial",
        "nombre_guardado": "bd_alertas_com_1.xlsx",
    },
    {
        "id": "bd_alertas_com_2",
        "categoria": "alertas",
        "titulo": "Alertas Comunicación — final",
        "tipo": "bd_alertas_com",
        "fase": "final",
        "requerido": False,
        "nombre_guardado": "bd_alertas_com_2.xlsx",
    },
    {
        "id": "bd_alertas_psi_1",
        "categoria": "alertas",
        "titulo": "Alertas Psicología — inicial",
        "tipo": "bd_alertas_psi",
        "fase": "inicial",
        "nombre_guardado": "bd_alertas_psi_1.xlsx",
    },
    {
        "id": "bd_alertas_psi_2",
        "categoria": "alertas",
        "titulo": "Alertas Psicología — final",
        "tipo": "bd_alertas_psi",
        "fase": "final",
        "requerido": False,
        "nombre_guardado": "bd_alertas_psi_2.xlsx",
    },
]


def config_default(base: Path | None = None) -> dict[str, Any]:
    base = base or PROJECT_ROOT
    return {
        "carpeta_excels": CARPETA_EXCELS_DEFAULT,
        "archivos_fuente": deepcopy(ARCHIVOS_FUENTE_DEFAULT),
        "documentos_adicionales": [],
        "aliases": deepcopy(ALIASES_DEFAULT),
        "programas_permitidos": list(PROGRAMAS_PERMITIDOS_DEFAULT),
        "programas_excluidos": list(PROGRAMAS_EXCLUIDOS_DEFAULT),
        "columnas_motivo_priorizado": list(COLUMNAS_MOTIVO_PRIO_DEFAULT),
        "colores_prioridad": deepcopy(COLORES_PRIORIDAD_DEFAULT),
        "categorias_fuente": deepcopy(CATEGORIAS_FUENTE_DEFAULT),
        "grupos_salida": [
            {"nombre": "Datos", "columnas": list(COLUMNAS_DATOS)},
            {
                "nombre": "Puntaje",
                "columnas": list(COLUMNAS_PUNTAJE_COMPONENTES) + list(COLUMNAS_PRIORIDAD),
            },
            {
                "nombre": "Priorizados",
                "columnas": list(COLUMNAS_PRIORIZADO) + list(COLUMNAS_PRIORIZADO_ENRIQUECIDO),
            },
            {"nombre": "Becas", "columnas": list(COLUMNAS_BECAS)},
            {"nombre": "Ruta de grado", "columnas": list(COLUMNAS_RUTA_GRADO)},
            {
                "nombre": "Alertas",
                "columnas": list(COLUMNAS_ALERTAS) + list(COLUMNAS_ALERTAS_PROPIAS),
            },
        ],
        "grupo_materias": "Materias",
        "interfaz": {"modo_apariencia": "system"},
        "salida": {
            "hoja": "Listado",
            "ruta": "salida/estudiantes_consolidado.xlsx",
        },
    }


def slot_es_requerido(slot: dict) -> bool:
    """Indica si un archivo fuente debe estar cargado para generar el consolidado."""
    if slot.get("requerido") is False:
        return False
    if slot.get("fase") == "final" and slot.get("tipo") in ("bd_alertas_com", "bd_alertas_psi"):
        return False
    return slot.get("id") in ARCHIVOS_FUENTE_REQUERIDOS


def ruta_config(base: Path | None = None) -> Path:
    base = base or PROJECT_ROOT
    return base / CONFIG_FILENAME


def ruta_config_fabrica(base: Path | None = None) -> Path:
    base = base or PROJECT_ROOT
    return base / CONFIG_FABRICA_FILENAME


def asegurar_config_fabrica(base: Path | None = None) -> Path:
    """
    Guarda una copia de la configuración base (valores de fábrica) si aún no existe.
    No sobrescribe una fábrica ya guardada.
    """
    base = base or PROJECT_ROOT
    path = ruta_config_fabrica(base)
    if not path.is_file():
        fabrica = config_default(base)
        with path.open("w", encoding="utf-8") as f:
            json.dump(fabrica, f, ensure_ascii=False, indent=2)
    return path


def cargar_config_fabrica(base: Path | None = None) -> dict[str, Any]:
    base = base or PROJECT_ROOT
    asegurar_config_fabrica(base)
    path = ruta_config_fabrica(base)
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return _fusionar_con_default(data, config_default(base))


def restaurar_config_fabrica(
    cfg_actual: dict[str, Any] | None = None,
    base: Path | None = None,
    *,
    preservar_interfaz: bool = True,
    preservar_salida: bool = True,
) -> dict[str, Any]:
    """
    Restablece config.json a los valores de fábrica.
    Conserva por defecto modo de apariencia y carpeta de salida.
    """
    base = base or PROJECT_ROOT
    fabrica = cargar_config_fabrica(base)
    actual = cfg_actual or {}
    if preservar_interfaz and isinstance(actual.get("interfaz"), dict):
        fabrica["interfaz"] = deepcopy(actual["interfaz"])
    if preservar_salida and isinstance(actual.get("salida"), dict):
        fabrica["salida"] = deepcopy(actual["salida"])
    guardar_config(fabrica, base)
    return fabrica


def cargar_config(base: Path | None = None) -> dict[str, Any]:
    base = base or PROJECT_ROOT
    asegurar_config_fabrica(base)
    path = ruta_config(base)
    if not path.is_file():
        cfg = config_default(base)
        guardar_config(cfg, base)
        return cfg
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return _fusionar_con_default(data, config_default(base))


def _fusionar_archivos_fuente(
    val: list[dict[str, Any]],
    default: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    por_id = {s.get("id"): deepcopy(s) for s in val if s.get("id")}
    for old_id, new_id in _MIGRACION_IDS_ARCHIVO.items():
        if old_id in por_id and new_id not in por_id:
            migrado = deepcopy(por_id[old_id])
            migrado["id"] = new_id
            por_id[new_id] = migrado
    merged: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for slot in default:
        sid = slot.get("id")
        if not sid:
            continue
        if sid in por_id:
            actual = deepcopy(por_id[sid])
            for clave in ("categoria", "fase", "tipo", "hoja", "requerido"):
                if clave not in actual and clave in slot:
                    actual[clave] = slot[clave]
            merged.append(actual)
        else:
            merged.append(deepcopy(slot))
        vistos.add(sid)
    for slot in val:
        sid = slot.get("id")
        if sid and sid not in vistos and sid not in _MIGRACION_IDS_ARCHIVO:
            merged.append(deepcopy(slot))
    return merged


def _fusionar_grupos_salida(
    val: list[dict[str, Any]],
    default: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    por_nombre = {g.get("nombre"): deepcopy(g) for g in val if g.get("nombre")}
    merged: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for grupo in default:
        nombre = grupo.get("nombre")
        if not nombre:
            continue
        if nombre in por_nombre:
            existente = por_nombre[nombre]
            if nombre in ("Alertas", "Priorizados", "Prioridad", "Puntaje", "Becas", "Ruta de grado"):
                existente["columnas"] = list(grupo.get("columnas", []))
            else:
                cols = [c for c in existente.get("columnas", []) if c not in _COLUMNAS_ALERTAS_LEGACY]
                for col in grupo.get("columnas", []):
                    if col not in cols:
                        cols.append(col)
                existente["columnas"] = cols
            merged.append(existente)
        else:
            merged.append(deepcopy(grupo))
        vistos.add(nombre)
    for grupo in val:
        nombre = grupo.get("nombre")
        if nombre and nombre not in vistos:
            merged.append(deepcopy(grupo))
    return merged


def _fusionar_con_default(data: dict[str, Any], default: dict[str, Any]) -> dict[str, Any]:
    out = deepcopy(default)
    for key, val in data.items():
        if key == "aliases" and isinstance(val, dict):
            merged = deepcopy(out["aliases"])
            merged.update(val)
            out["aliases"] = merged
        elif key == "archivos_fuente" and isinstance(val, list):
            out["archivos_fuente"] = _fusionar_archivos_fuente(val, default.get("archivos_fuente", []))
        elif key == "grupos_salida" and isinstance(val, list):
            out["grupos_salida"] = _fusionar_grupos_salida(val, default.get("grupos_salida", []))
        elif isinstance(val, dict) and isinstance(out.get(key), dict):
            inner = deepcopy(out[key])
            inner.update(val)
            out[key] = inner
        else:
            out[key] = val
    return out


def guardar_config(cfg: dict[str, Any], base: Path | None = None) -> Path:
    base = base or PROJECT_ROOT
    path = ruta_config(base)
    with path.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return path


def carpeta_excels(cfg: dict[str, Any], base: Path | None = None) -> Path:
    base = base or PROJECT_ROOT
    rel = cfg.get("carpeta_excels", CARPETA_EXCELS_DEFAULT)
    return (base / rel).resolve()


def guardar_excel_fuente(
    origen: Path,
    slot: dict[str, Any],
    cfg: dict[str, Any],
    base: Path | None = None,
) -> Path:
    """Copia un Excel al almacén local y devuelve la ruta guardada."""
    dest_dir = carpeta_excels(cfg, base)
    dest_dir.mkdir(parents=True, exist_ok=True)
    nombre = slot.get("nombre_guardado") or f"{slot.get('id', 'archivo')}{origen.suffix.lower()}"
    destino = dest_dir / nombre
    shutil.copy2(origen, destino)
    return destino


def rutas_archivos_cargados(cfg: dict[str, Any], base: Path | None = None) -> list[Path]:
    base = base or PROJECT_ROOT
    carpeta = carpeta_excels(cfg, base)
    rutas: list[Path] = []
    for slot in cfg.get("archivos_fuente", []):
        p = carpeta / slot.get("nombre_guardado", "")
        if p.is_file():
            rutas.append(p)
    for doc in cfg.get("documentos_adicionales", []):
        p = carpeta / doc.get("nombre_guardado", "")
        if p.is_file():
            rutas.append(p)
    return rutas


def columnas_grupos_fijos(cfg: dict[str, Any]) -> list[tuple[str, list[str]]]:
    grupos: list[tuple[str, list[str]]] = []
    for g in cfg.get("grupos_salida", []):
        grupos.append((g["nombre"], list(g["columnas"])))
    for doc in cfg.get("documentos_adicionales", []):
        cols = [c["salida"] for c in doc.get("columnas", []) if c.get("salida")]
        if cols:
            grupos.append((doc.get("grupo_encabezado", doc.get("titulo", "Extra")), cols))
    return grupos


def construir_columnas_salida(cfg: dict[str, Any], num_materias: int = 1) -> list[str]:
    cols: list[str] = []
    for _, columnas in columnas_grupos_fijos(cfg):
        for c in columnas:
            if c not in cols:
                cols.append(c)
    for c in COLUMNAS_REPITIENDO:
        if c not in cols:
            cols.append(c)
    for i in range(1, max(num_materias, 1) + 1):
        for c in (f"Materia {i}", f"Horario {i}", f"Profesor {i}"):
            if c not in cols:
                cols.append(c)
    return cols


def construir_grupos_encabezado(cfg: dict[str, Any], num_materias: int) -> list[tuple[str, list[str]]]:
    grupos = columnas_grupos_fijos(cfg)
    materias: list[str] = []
    for c in COLUMNAS_REPITIENDO:
        if c not in materias:
            materias.append(c)
    for i in range(1, max(num_materias, 1) + 1):
        materias.extend([f"Materia {i}", f"Horario {i}", f"Profesor {i}"])
    if materias:
        grupos.append((cfg.get("grupo_materias", "Materias"), materias))
    return grupos


# Etiquetas legibles para el editor visual de aliases
ALIAS_ETIQUETAS: dict[str, str] = {
    "identificacion": "Identificación",
    "nombre_estudiante": "Nombre y apellidos",
    "fecha_nacimiento": "Fecha de nacimiento",
    "telefono_celular": "Teléfono celular",
    "programa": "Programa",
    "correo_institucional": "Correo institucional",
    "correo_personal": "Correo personal",
    "periodo_ingreso": "Periodo ingreso",
    "periodo_actual": "Periodo actual",
    "periodo_ultima_matricula": "Periodo última matrícula",
    "reintegros": "Reintegros",
    "lugar_nacimiento": "Lugar de nacimiento",
    "lugar_residencia": "Lugar de residencia",
    "direccion_residencia": "Dirección residencia",
    "total_beca": "Total beca",
    "tipo_beca_credito": "Tipo de beca o crédito",
    "funcionario_beca": "Funcionario beca",
}


def etiqueta_export_columna(nombre_columna: str) -> str:
    return ETIQUETAS_EXPORT_COLUMNAS.get(nombre_columna, nombre_columna)


def etiqueta_alias(canon: str) -> str:
    return ALIAS_ETIQUETAS.get(canon, canon.replace("_", " ").title())

