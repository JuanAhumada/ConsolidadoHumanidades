"""
SQLite del consolidado: versiones (snapshots) y estudiantes por categoría.

guardar_version nunca pisa un corte anterior. La ficha se arma desde fila_json
de las cuatro tablas (base, priorizado, rendimiento, alertas).
Periodo de la versión = periodo_desde_fecha (mes del corte).
Periodo del alumno = columna Periodo actual (COD_PERIODO).

Al cambiar tablas, incremente SCHEMA_VERSION y migre en inicializar_db.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

import polars as pl

from consolidado.config.settings import (
    COLUMNAS_ALERTAS,
    COLUMNAS_ALERTAS_PROPIAS,
    COLUMNAS_BECAS,
    COLUMNAS_DATOS,
    COLUMNAS_PRIORIDAD,
    COLUMNAS_PRIORIZADO,
    COLUMNAS_PRIORIZADO_ENRIQUECIDO,
    COLUMNAS_REPITIENDO,
)
from consolidado.core.normalizacion import normalizar_id
from consolidado.paths import PROJECT_ROOT

DB_FILENAME = "consolidado.db"
CARPETA_DATOS = "datos"
SCHEMA_VERSION = 9  # última: Periodo actual en estudiantes_base

# Columnas canónicas → campos indexables (identidad en `estudiantes_base`).
_CAMPOS_INDEXABLES: dict[str, str] = {
    "identificacion": "Identificación",
    "nombre": "Nombre y apellidos",
    "programa": "Programa",
    "periodo_ingreso": "Periodo ingreso",
    "periodo_actual": "Periodo actual",
    "fecha_nacimiento": "Fecha de nacimiento",
    "telefono": "Teléfono celular",
    "correo_institucional": "Correo institucional",
    "correo_personal": "Correo personal",
    "reintegros": "Reintegros",
    "lugar_nacimiento": "Lugar de nacimiento",
    "lugar_residencia": "Lugar de residencia",
    "nivel_prioridad": "Nivel prioridad",
    "puntaje_prioridad": "Puntaje prioridad",
    "detalle_prioridad": "Detalle prioridad",
    "priorizado": "Priorizado",
    "motivo_prio": "Motivo Prio.",
    "detalle_gprio": "Detalle GPrio.",
    "adaptacion": "Adaptacion",
    "fecha_adaptacion": "Fecha adaptacion",
    "activacion_ruta": "Activacion de ruta",
    "fecha_activacion_ruta": "Fecha activacion de ruta",
    "tipo_beca": "Tipo de beca o crédito",
    "total_beca": "Total beca",
    "funcionario_beca": "Funcionario que tiene a cargo la beca",
    "repitiendo": "Repitiendo",
    "alerta_propia": "Alerta Propia",
    "detalle_propio": "Detalle Propio",
    "num_alerta_inicial": "Num Alerta inicial",
    "tipo_alerta_inicial": "Tipo Alerta inicial",
    "num_alerta_final": "Num Alerta final",
    "tipo_alerta_final": "Tipo Alerta final",
}

_PTJE_PRIORIZADO = frozenset({"Ptje Priorizado", "Ptje Propio", "Ptje Activacion"})
_PTJE_RENDIMIENTO = frozenset({"Ptje Beca", "Ptje Repitiendo", "Ptje Reintegro"})

COLUMNAS_CAT_BASE = frozenset(COLUMNAS_DATOS + COLUMNAS_PRIORIDAD)
COLUMNAS_CAT_PRIORIZADO = (
    frozenset(COLUMNAS_PRIORIZADO + COLUMNAS_PRIORIZADO_ENRIQUECIDO) | _PTJE_PRIORIZADO
)
COLUMNAS_CAT_RENDIMIENTO = (
    frozenset(COLUMNAS_BECAS + COLUMNAS_REPITIENDO) | _PTJE_RENDIMIENTO
)
COLUMNAS_CAT_ALERTAS = frozenset(COLUMNAS_ALERTAS + COLUMNAS_ALERTAS_PROPIAS)
COLUMNAS_CATEGORIAS = (
    COLUMNAS_CAT_BASE
    | COLUMNAS_CAT_PRIORIZADO
    | COLUMNAS_CAT_RENDIMIENTO
    | COLUMNAS_CAT_ALERTAS
)


def ruta_base_datos(base: Path | None = None) -> Path:
    base = base or PROJECT_ROOT
    return base / CARPETA_DATOS / DB_FILENAME


def periodo_desde_fecha(fecha: date | datetime | None = None) -> str:
    """Enero–junio → YYYY-1; julio–diciembre → YYYY-2."""
    if fecha is None:
        fecha = date.today()
    if isinstance(fecha, datetime):
        fecha = fecha.date()
    semestre = 1 if fecha.month <= 6 else 2
    return f"{fecha.year}-{semestre}"


def nombre_excel_version(
    periodo: str,
    fecha_version: date,
    *,
    sufijo_hora: str | None = None,
) -> str:
    """Nombre del Excel: estudiantes_consolidado_2026-2_2026-07-30.xlsx"""
    base = f"estudiantes_consolidado_{periodo}_{fecha_version.isoformat()}"
    if sufijo_hora:
        base = f"{base}_{sufijo_hora}"
    return f"{base}.xlsx"


@contextmanager
def conexion(base: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = ruta_base_datos(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _columnas_tabla(conn: sqlite3.Connection, tabla: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({tabla})").fetchall()
    return {str(r["name"]) for r in rows}


def _schema_actual(conn: sqlite3.Connection) -> int:
    tablas = {
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "schema_meta" not in tablas:
        return 1 if "versiones" in tablas else 0
    row = conn.execute(
        "SELECT valor FROM schema_meta WHERE clave = 'version'"
    ).fetchone()
    if row is None:
        return 1
    try:
        return int(row["valor"])
    except (TypeError, ValueError):
        return 1


def _crear_tablas_v2(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            clave TEXT PRIMARY KEY,
            valor TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS versiones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            periodo TEXT NOT NULL,
            fecha_version TEXT NOT NULL,
            creado_en TEXT NOT NULL,
            num_estudiantes INTEGER NOT NULL DEFAULT 0,
            num_materias INTEGER,
            columnas_json TEXT NOT NULL,
            ruta_excel TEXT,
            notas TEXT
        );

        CREATE TABLE IF NOT EXISTS priorizados_propios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identificacion TEXT NOT NULL UNIQUE,
            nombre TEXT,
            motivo TEXT,
            detalle TEXT,
            activo INTEGER NOT NULL DEFAULT 1,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS alertas_propias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            identificacion TEXT NOT NULL UNIQUE,
            nombre TEXT,
            detalle TEXT NOT NULL,
            creado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS priorizados_contactados (
            identificacion TEXT PRIMARY KEY,
            contactado INTEGER NOT NULL DEFAULT 1,
            contactado_en TEXT NOT NULL,
            actualizado_en TEXT NOT NULL
        );
        """
    )


def _crear_tablas_categorias(conn: sqlite3.Connection) -> None:
    """Estudiantes separados por categoría fuente; se busca por identificación."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS estudiantes_base (
            identificacion TEXT NOT NULL,
            version_id INTEGER NOT NULL
                REFERENCES versiones(id) ON DELETE CASCADE,
            nombre TEXT,
            programa TEXT,
            periodo_ingreso TEXT,
            periodo_actual TEXT,
            fecha_nacimiento TEXT,
            telefono TEXT,
            correo_institucional TEXT,
            correo_personal TEXT,
            reintegros TEXT,
            lugar_nacimiento TEXT,
            lugar_residencia TEXT,
            nivel_prioridad TEXT,
            puntaje_prioridad REAL,
            detalle_prioridad TEXT,
            fila_json TEXT NOT NULL,
            PRIMARY KEY (identificacion, version_id)
        );

        CREATE TABLE IF NOT EXISTS estudiantes_priorizado (
            identificacion TEXT NOT NULL,
            version_id INTEGER NOT NULL
                REFERENCES versiones(id) ON DELETE CASCADE,
            priorizado TEXT,
            motivo_prio TEXT,
            detalle_gprio TEXT,
            adaptacion TEXT,
            fecha_adaptacion TEXT,
            activacion_ruta TEXT,
            fecha_activacion_ruta TEXT,
            fila_json TEXT NOT NULL,
            PRIMARY KEY (identificacion, version_id)
        );

        CREATE TABLE IF NOT EXISTS estudiantes_rendimiento (
            identificacion TEXT NOT NULL,
            version_id INTEGER NOT NULL
                REFERENCES versiones(id) ON DELETE CASCADE,
            tipo_beca TEXT,
            total_beca TEXT,
            funcionario_beca TEXT,
            repitiendo TEXT,
            fila_json TEXT NOT NULL,
            PRIMARY KEY (identificacion, version_id)
        );

        CREATE TABLE IF NOT EXISTS estudiantes_alertas (
            identificacion TEXT NOT NULL,
            version_id INTEGER NOT NULL
                REFERENCES versiones(id) ON DELETE CASCADE,
            num_alerta_inicial TEXT,
            tipo_alerta_inicial TEXT,
            num_alerta_final TEXT,
            tipo_alerta_final TEXT,
            alerta_propia TEXT,
            detalle_propio TEXT,
            fila_json TEXT NOT NULL,
            PRIMARY KEY (identificacion, version_id)
        );
        """
    )


def _crear_indices_v2(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_versiones_periodo
            ON versiones(periodo);
        CREATE INDEX IF NOT EXISTS idx_versiones_fecha
            ON versiones(fecha_version);
        CREATE INDEX IF NOT EXISTS idx_priorizados_identificacion
            ON priorizados_propios(identificacion);
        CREATE INDEX IF NOT EXISTS idx_alertas_identificacion
            ON alertas_propias(identificacion);
        CREATE INDEX IF NOT EXISTS idx_contactados_flag
            ON priorizados_contactados(contactado);
        CREATE INDEX IF NOT EXISTS idx_priorizados_activo
            ON priorizados_propios(activo);
        """
    )


def _crear_indices_categorias(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_est_base_id
            ON estudiantes_base(identificacion);
        CREATE INDEX IF NOT EXISTS idx_est_base_version
            ON estudiantes_base(version_id);
        CREATE INDEX IF NOT EXISTS idx_est_base_nombre
            ON estudiantes_base(nombre);
        CREATE INDEX IF NOT EXISTS idx_est_base_programa
            ON estudiantes_base(programa);
        CREATE INDEX IF NOT EXISTS idx_est_base_nivel
            ON estudiantes_base(nivel_prioridad);
        CREATE INDEX IF NOT EXISTS idx_est_prio_id
            ON estudiantes_priorizado(identificacion);
        CREATE INDEX IF NOT EXISTS idx_est_prio_version
            ON estudiantes_priorizado(version_id);
        CREATE INDEX IF NOT EXISTS idx_est_rend_id
            ON estudiantes_rendimiento(identificacion);
        CREATE INDEX IF NOT EXISTS idx_est_rend_version
            ON estudiantes_rendimiento(version_id);
        CREATE INDEX IF NOT EXISTS idx_est_alertas_id
            ON estudiantes_alertas(identificacion);
        CREATE INDEX IF NOT EXISTS idx_est_alertas_version
            ON estudiantes_alertas(version_id);
        """
    )


def _crear_tablas_alertas_descartadas(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS alertas_descartadas (
            identificacion TEXT NOT NULL,
            fase TEXT NOT NULL,
            tipo TEXT NOT NULL,
            creado_en TEXT NOT NULL,
            PRIMARY KEY (identificacion, fase, tipo)
        );
        CREATE INDEX IF NOT EXISTS idx_alertas_desc_id
            ON alertas_descartadas(identificacion);
        """
    )


def _crear_tablas_usuarios(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT NOT NULL UNIQUE COLLATE NOCASE,
            nombre TEXT,
            clave_hash TEXT NOT NULL,
            rol TEXT NOT NULL DEFAULT 'consulta',
            activo INTEGER NOT NULL DEFAULT 1,
            creado_en TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_usuarios_usuario
            ON usuarios(usuario);
        """
    )


def _crear_tablas_modificaciones(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS modificaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            creado_en TEXT NOT NULL,
            usuario TEXT,
            accion TEXT NOT NULL,
            entidad TEXT,
            identificacion TEXT,
            resumen TEXT NOT NULL,
            detalle_json TEXT,
            version_antes INTEGER,
            version_despues INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_modificaciones_fecha
            ON modificaciones(creado_en);
        CREATE INDEX IF NOT EXISTS idx_modificaciones_accion
            ON modificaciones(accion);
        """
    )


def _marcar_schema_version(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (clave, valor) VALUES ('version', ?)",
        (str(SCHEMA_VERSION),),
    )


def _migrar_priorizados_activo(conn: sqlite3.Connection) -> None:
    cols = _columnas_tabla(conn, "priorizados_propios")
    if cols and "activo" not in cols:
        conn.execute(
            "ALTER TABLE priorizados_propios ADD COLUMN activo INTEGER NOT NULL DEFAULT 1"
        )


def _crear_schema_v2(conn: sqlite3.Connection) -> None:
    _crear_tablas_v2(conn)
    _crear_indices_v2(conn)
    _marcar_schema_version(conn)


def _migrar_estudiantes_v1_a_v2(conn: sqlite3.Connection) -> None:
    cols = _columnas_tabla(conn, "estudiantes")
    if not cols or "fila_json" not in cols:
        return
    nuevas = [
        ("programa", "TEXT"),
        ("periodo_ingreso", "TEXT"),
        ("priorizado", "TEXT"),
        ("motivo_prio", "TEXT"),
        ("alerta_propia", "TEXT"),
        ("detalle_propio", "TEXT"),
        ("nivel_prioridad", "TEXT"),
        ("puntaje_prioridad", "REAL"),
        ("tipo_beca", "TEXT"),
    ]
    for nombre, tipo in nuevas:
        if nombre not in cols:
            conn.execute(f"ALTER TABLE estudiantes ADD COLUMN {nombre} {tipo}")

    rows = conn.execute(
        "SELECT id, fila_json FROM estudiantes WHERE fila_json IS NOT NULL"
    ).fetchall()
    for row in rows:
        try:
            fila = json.loads(row["fila_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        campos = _extraer_campos_indexables(fila)
        conn.execute(
            """
            UPDATE estudiantes SET
                identificacion = COALESCE(?, identificacion),
                nombre = COALESCE(?, nombre),
                programa = ?,
                periodo_ingreso = ?,
                priorizado = ?,
                motivo_prio = ?,
                alerta_propia = ?,
                detalle_propio = ?,
                nivel_prioridad = ?,
                puntaje_prioridad = ?,
                tipo_beca = ?
            WHERE id = ?
            """,
            (
                campos["identificacion"],
                campos["nombre"],
                campos["programa"],
                campos["periodo_ingreso"],
                campos["priorizado"],
                campos["motivo_prio"],
                campos["alerta_propia"],
                campos["detalle_propio"],
                campos["nivel_prioridad"],
                campos["puntaje_prioridad"],
                campos["tipo_beca"],
                row["id"],
            ),
        )


def _migrar_json_marcaciones(conn: sqlite3.Connection, base: Path) -> None:
    """Importa priorizados/alertas desde JSON legacy si las tablas están vacías."""
    ahora = datetime.now().isoformat(timespec="seconds")
    n_prio = conn.execute("SELECT COUNT(*) AS n FROM priorizados_propios").fetchone()["n"]
    if int(n_prio) == 0:
        path = base / CARPETA_DATOS / "priorizados_propios.json"
        if path.is_file():
            try:
                with path.open(encoding="utf-8") as f:
                    data = json.load(f)
                items = data if isinstance(data, list) else list(
                    data.get("priorizados_propios", [])
                )
            except (OSError, json.JSONDecodeError):
                items = []
            for item in items:
                ident = str(item.get("identificacion", "")).strip()
                if not ident:
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO priorizados_propios (
                        identificacion, nombre, motivo, detalle, activo,
                        creado_en, actualizado_en
                    ) VALUES (?, ?, ?, ?, 1, ?, ?)
                    """,
                    (
                        ident,
                        str(item.get("nombre") or "") or None,
                        str(item.get("motivo") or "") or None,
                        str(item.get("detalle") or "") or None,
                        ahora,
                        ahora,
                    ),
                )

    n_alertas = conn.execute("SELECT COUNT(*) AS n FROM alertas_propias").fetchone()["n"]
    if int(n_alertas) == 0:
        path = base / CARPETA_DATOS / "alertas_propias.json"
        if path.is_file():
            try:
                with path.open(encoding="utf-8") as f:
                    data = json.load(f)
                items = data if isinstance(data, list) else list(
                    data.get("alertas_propias", [])
                )
            except (OSError, json.JSONDecodeError):
                items = []
            for item in items:
                ident = str(item.get("identificacion", "")).strip()
                detalle = str(item.get("detalle") or "").strip()
                if not ident or not detalle:
                    continue
                conn.execute(
                    """
                    INSERT OR REPLACE INTO alertas_propias (
                        identificacion, nombre, detalle,
                        creado_en, actualizado_en
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        ident,
                        str(item.get("nombre") or "") or None,
                        detalle,
                        ahora,
                        ahora,
                    ),
                )


def _tablas(conn: sqlite3.Connection) -> set[str]:
    return {
        str(r["name"])
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _subfila(fila: dict[str, Any], columnas: frozenset[str]) -> dict[str, Any]:
    return {k: fila[k] for k in fila if k in columnas}


def _fila_tiene_datos(sub: dict[str, Any], *, ignorar: set[str] | None = None) -> bool:
    ignorar = ignorar or {"Identificación", "Nombre y apellidos"}
    for clave, val in sub.items():
        if clave in ignorar or str(clave).startswith("Ptje "):
            continue
        if val is None or val is False:
            continue
        if isinstance(val, (int, float)) and val == 0:
            continue
        if isinstance(val, str) and val.strip().lower() in {"", "false", "0", "no", "none", "-"}:
            continue
        return True
    return False


def _insertar_estudiante_categorias(
    conn: sqlite3.Connection,
    version_id: int,
    fila: dict[str, Any],
) -> None:
    campos = _extraer_campos_indexables(fila)
    ident = normalizar_id(campos.get("identificacion"))
    if not ident:
        return

    extras = {k: v for k, v in fila.items() if k not in COLUMNAS_CATEGORIAS}
    base_json = {**_subfila(fila, COLUMNAS_CAT_BASE), **extras}
    prio_json = _subfila(fila, COLUMNAS_CAT_PRIORIZADO)
    rend_json = _subfila(fila, COLUMNAS_CAT_RENDIMIENTO)
    alertas_json = _subfila(fila, COLUMNAS_CAT_ALERTAS)

    conn.execute(
        """
        INSERT OR REPLACE INTO estudiantes_base (
            identificacion, version_id, nombre, programa, periodo_ingreso,
            periodo_actual, fecha_nacimiento, telefono, correo_institucional,
            correo_personal, reintegros, lugar_nacimiento, lugar_residencia,
            nivel_prioridad, puntaje_prioridad, detalle_prioridad, fila_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ident,
            version_id,
            campos.get("nombre"),
            campos.get("programa"),
            campos.get("periodo_ingreso"),
            campos.get("periodo_actual"),
            campos.get("fecha_nacimiento"),
            campos.get("telefono"),
            campos.get("correo_institucional"),
            campos.get("correo_personal"),
            campos.get("reintegros"),
            campos.get("lugar_nacimiento"),
            campos.get("lugar_residencia"),
            campos.get("nivel_prioridad"),
            campos.get("puntaje_prioridad"),
            campos.get("detalle_prioridad"),
            json.dumps(base_json, ensure_ascii=False),
        ),
    )
    if _fila_tiene_datos(prio_json):
        conn.execute(
            """
            INSERT OR REPLACE INTO estudiantes_priorizado (
                identificacion, version_id, priorizado, motivo_prio, detalle_gprio,
                adaptacion, fecha_adaptacion, activacion_ruta, fecha_activacion_ruta,
                fila_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ident,
                version_id,
                campos.get("priorizado"),
                campos.get("motivo_prio"),
                campos.get("detalle_gprio"),
                campos.get("adaptacion"),
                campos.get("fecha_adaptacion"),
                campos.get("activacion_ruta"),
                campos.get("fecha_activacion_ruta"),
                json.dumps(prio_json, ensure_ascii=False),
            ),
        )
    if _fila_tiene_datos(rend_json):
        conn.execute(
            """
            INSERT OR REPLACE INTO estudiantes_rendimiento (
                identificacion, version_id, tipo_beca, total_beca,
                funcionario_beca, repitiendo, fila_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ident,
                version_id,
                campos.get("tipo_beca"),
                campos.get("total_beca"),
                campos.get("funcionario_beca"),
                campos.get("repitiendo"),
                json.dumps(rend_json, ensure_ascii=False),
            ),
        )
    if _fila_tiene_datos(alertas_json):
        conn.execute(
            """
            INSERT OR REPLACE INTO estudiantes_alertas (
                identificacion, version_id, num_alerta_inicial, tipo_alerta_inicial,
                num_alerta_final, tipo_alerta_final, alerta_propia, detalle_propio,
                fila_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ident,
                version_id,
                campos.get("num_alerta_inicial"),
                campos.get("tipo_alerta_inicial"),
                campos.get("num_alerta_final"),
                campos.get("tipo_alerta_final"),
                campos.get("alerta_propia"),
                campos.get("detalle_propio"),
                json.dumps(alertas_json, ensure_ascii=False),
            ),
        )


def _migrar_estudiantes_a_categorias(conn: sqlite3.Connection) -> None:
    tablas = _tablas(conn)
    if "estudiantes_base" not in tablas:
        return
    n_base = conn.execute("SELECT COUNT(*) AS n FROM estudiantes_base").fetchone()["n"]
    if int(n_base) > 0:
        if "estudiantes" in tablas and "fila_json" in _columnas_tabla(conn, "estudiantes"):
            conn.execute("DROP TABLE IF EXISTS estudiantes")
        return
    if "estudiantes" not in tablas:
        return
    cols = _columnas_tabla(conn, "estudiantes")
    if "fila_json" not in cols:
        return
    rows = conn.execute(
        "SELECT version_id, fila_json FROM estudiantes WHERE fila_json IS NOT NULL"
    ).fetchall()
    for row in rows:
        try:
            fila = json.loads(row["fila_json"])
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(fila, dict):
            continue
        _insertar_estudiante_categorias(conn, int(row["version_id"]), fila)
    conn.execute("DROP TABLE IF EXISTS estudiantes")


def _asegurar_periodo_actual(conn: sqlite3.Connection) -> None:
    cols = _columnas_tabla(conn, "estudiantes_base")
    if cols and "periodo_actual" not in cols:
        conn.execute("ALTER TABLE estudiantes_base ADD COLUMN periodo_actual TEXT")


def inicializar_db(base: Path | None = None) -> Path:
    """Crea o migra el schema. Devuelve la ruta del archivo .db."""
    base = base or PROJECT_ROOT
    with conexion(base) as conn:
        version = _schema_actual(conn)
        if version < 1:
            _crear_tablas_v2(conn)
            _crear_indices_v2(conn)
            _migrar_json_marcaciones(conn, base)
        elif version < 4:
            _crear_tablas_v2(conn)
            _migrar_estudiantes_v1_a_v2(conn)
            _migrar_priorizados_activo(conn)
            _crear_indices_v2(conn)
            _migrar_json_marcaciones(conn, base)
        else:
            _crear_tablas_v2(conn)
            _migrar_priorizados_activo(conn)
            _crear_indices_v2(conn)
            _migrar_json_marcaciones(conn, base)
        _crear_tablas_categorias(conn)
        if version < 5:
            _migrar_estudiantes_a_categorias(conn)
        _crear_indices_categorias(conn)
        _crear_tablas_alertas_descartadas(conn)
        _crear_tablas_usuarios(conn)
        _crear_tablas_modificaciones(conn)
        _asegurar_periodo_actual(conn)
        _marcar_schema_version(conn)
    return ruta_base_datos(base)


def _serializar_valor(val: Any) -> Any:
    if val is None:
        return None
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float, str)):
        return val
    try:
        if hasattr(val, "item"):
            return _serializar_valor(val.item())
    except Exception:
        pass
    return str(val)


def _texto_o_none(val: Any) -> str | None:
    if val is None:
        return None
    texto = str(val).strip()
    return texto or None


def _float_o_none(val: Any) -> float | None:
    if val is None or val == "":
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _extraer_campos_indexables(fila: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for campo, col in _CAMPOS_INDEXABLES.items():
        raw = fila.get(col)
        if campo == "puntaje_prioridad":
            out[campo] = _float_o_none(raw)
        else:
            out[campo] = _texto_o_none(raw)
    return out


def dataframe_a_filas(df: pl.DataFrame) -> list[dict[str, Any]]:
    filas: list[dict[str, Any]] = []
    for row in df.iter_rows(named=True):
        filas.append({k: _serializar_valor(v) for k, v in row.items()})
    return filas


def filas_a_dataframe(filas: list[dict[str, Any]], columnas: list[str]) -> pl.DataFrame:
    if not filas:
        return pl.DataFrame({c: [] for c in columnas})
    normalizadas = [{c: fila.get(c) for c in columnas} for fila in filas]
    return pl.from_dicts(normalizadas, infer_schema_length=None)


def guardar_version(
    df: pl.DataFrame,
    *,
    base: Path | None = None,
    fecha_version: date | None = None,
    periodo: str | None = None,
    num_materias: int | None = None,
    ruta_excel: str | Path | None = None,
    notas: str | None = None,
) -> dict[str, Any]:
    """
    Guarda un consolidado como nueva versión (nunca sobrescribe versiones previas).
    """
    base = base or PROJECT_ROOT
    inicializar_db(base)
    fecha_version = fecha_version or date.today()
    periodo = periodo or periodo_desde_fecha(fecha_version)
    creado_en = datetime.now().isoformat(timespec="seconds")
    columnas = list(df.columns)
    filas = dataframe_a_filas(df)
    ruta_rel = None
    if ruta_excel is not None:
        ruta = Path(ruta_excel)
        try:
            ruta_rel = ruta.resolve().relative_to(Path(base).resolve()).as_posix()
        except ValueError:
            ruta_rel = str(ruta)

    with conexion(base) as conn:
        cur = conn.execute(
            """
            INSERT INTO versiones (
                periodo, fecha_version, creado_en, num_estudiantes,
                num_materias, columnas_json, ruta_excel, notas
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                periodo,
                fecha_version.isoformat(),
                creado_en,
                len(filas),
                num_materias,
                json.dumps(columnas, ensure_ascii=False),
                ruta_rel,
                notas,
            ),
        )
        version_id = int(cur.lastrowid)
        for f in filas:
            _insertar_estudiante_categorias(conn, version_id, f)

    return {
        "id": version_id,
        "periodo": periodo,
        "fecha_version": fecha_version.isoformat(),
        "creado_en": creado_en,
        "num_estudiantes": len(filas),
        "num_materias": num_materias,
        "ruta_excel": ruta_rel,
        "notas": notas,
    }


def listar_versiones(
    base: Path | None = None,
    *,
    periodo: str | None = None,
) -> list[dict[str, Any]]:
    inicializar_db(base)
    with conexion(base) as conn:
        if periodo:
            rows = conn.execute(
                """
                SELECT id, periodo, fecha_version, creado_en, num_estudiantes,
                       num_materias, ruta_excel, notas
                FROM versiones
                WHERE periodo = ?
                ORDER BY fecha_version DESC, id DESC
                """,
                (periodo,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT id, periodo, fecha_version, creado_en, num_estudiantes,
                       num_materias, ruta_excel, notas
                FROM versiones
                ORDER BY fecha_version DESC, id DESC
                """
            ).fetchall()
    return [dict(r) for r in rows]


def obtener_version(version_id: int, base: Path | None = None) -> dict[str, Any] | None:
    inicializar_db(base)
    with conexion(base) as conn:
        row = conn.execute(
            """
            SELECT id, periodo, fecha_version, creado_en, num_estudiantes,
                   num_materias, columnas_json, ruta_excel, notas
            FROM versiones WHERE id = ?
            """,
            (version_id,),
        ).fetchone()
    if row is None:
        return None
    data = dict(row)
    data["columnas"] = json.loads(data.pop("columnas_json"))
    return data


def _parse_json_fila(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _fusionar_filas_categoria(
    base_json: Any,
    prio_json: Any = None,
    rend_json: Any = None,
    alertas_json: Any = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for raw in (base_json, prio_json, rend_json, alertas_json):
        out.update(_parse_json_fila(raw))
    return out


def cargar_dataframe_version(
    version_id: int,
    base: Path | None = None,
) -> pl.DataFrame:
    meta = obtener_version(version_id, base)
    if meta is None:
        raise ValueError(f"No existe la versión id={version_id}")
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT b.fila_json AS base_json,
                   p.fila_json AS prio_json,
                   r.fila_json AS rend_json,
                   a.fila_json AS alertas_json
            FROM estudiantes_base b
            LEFT JOIN estudiantes_priorizado p
              ON p.identificacion = b.identificacion AND p.version_id = b.version_id
            LEFT JOIN estudiantes_rendimiento r
              ON r.identificacion = b.identificacion AND r.version_id = b.version_id
            LEFT JOIN estudiantes_alertas a
              ON a.identificacion = b.identificacion AND a.version_id = b.version_id
            WHERE b.version_id = ?
            ORDER BY b.nombre COLLATE NOCASE, b.identificacion
            """,
            (version_id,),
        ).fetchall()
    filas = [
        _fusionar_filas_categoria(
            r["base_json"], r["prio_json"], r["rend_json"], r["alertas_json"]
        )
        for r in rows
    ]
    return filas_a_dataframe(filas, meta["columnas"])


def obtener_fila_estudiante(
    identificacion: str,
    *,
    version_id: int | None = None,
    base: Path | None = None,
) -> dict[str, Any] | None:
    """Busca un estudiante por identificación (versión más reciente si no se indica)."""
    inicializar_db(base)
    ident = normalizar_id(identificacion)
    if not ident:
        return None
    if version_id is None:
        ult = ultima_version(base)
        if ult is None:
            return None
        version_id = int(ult["id"])
    with conexion(base) as conn:
        row = conn.execute(
            """
            SELECT b.identificacion, b.nombre, b.programa, b.version_id,
                   b.nivel_prioridad, b.puntaje_prioridad,
                   b.fila_json AS base_json,
                   p.fila_json AS prio_json,
                   r.fila_json AS rend_json,
                   a.fila_json AS alertas_json
            FROM estudiantes_base b
            LEFT JOIN estudiantes_priorizado p
              ON p.identificacion = b.identificacion AND p.version_id = b.version_id
            LEFT JOIN estudiantes_rendimiento r
              ON r.identificacion = b.identificacion AND r.version_id = b.version_id
            LEFT JOIN estudiantes_alertas a
              ON a.identificacion = b.identificacion AND a.version_id = b.version_id
            WHERE b.version_id = ?
              AND b.identificacion = ?
            """,
            (version_id, ident),
        ).fetchone()
        if row is None:
            row = conn.execute(
                """
                SELECT b.identificacion, b.nombre, b.programa, b.version_id,
                       b.nivel_prioridad, b.puntaje_prioridad,
                       b.fila_json AS base_json,
                       p.fila_json AS prio_json,
                       r.fila_json AS rend_json,
                       a.fila_json AS alertas_json
                FROM estudiantes_base b
                LEFT JOIN estudiantes_priorizado p
                  ON p.identificacion = b.identificacion AND p.version_id = b.version_id
                LEFT JOIN estudiantes_rendimiento r
                  ON r.identificacion = b.identificacion AND r.version_id = b.version_id
                LEFT JOIN estudiantes_alertas a
                  ON a.identificacion = b.identificacion AND a.version_id = b.version_id
                WHERE b.identificacion = ?
                ORDER BY b.version_id DESC
                LIMIT 1
                """,
                (ident,),
            ).fetchone()
    if row is None:
        return None
    fila = _fusionar_filas_categoria(
        row["base_json"], row["prio_json"], row["rend_json"], row["alertas_json"]
    )
    fila["_version_id"] = row["version_id"]
    return fila


def buscar_estudiantes(
    termino: str,
    *,
    version_id: int | None = None,
    base: Path | None = None,
    limite: int = 50,
) -> list[dict[str, Any]]:
    """Búsqueda por cédula/nombre. Si no hay version_id, usa la más reciente."""
    inicializar_db(base)
    q = termino.strip()
    if not q:
        return []
    if version_id is None:
        ult = ultima_version(base)
        if ult is None:
            return []
        version_id = int(ult["id"])
    like = f"%{q}%"
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT b.identificacion, b.nombre, b.programa, b.nivel_prioridad,
                   b.puntaje_prioridad, p.priorizado, a.alerta_propia
            FROM estudiantes_base b
            LEFT JOIN estudiantes_priorizado p
              ON p.identificacion = b.identificacion AND p.version_id = b.version_id
            LEFT JOIN estudiantes_alertas a
              ON a.identificacion = b.identificacion AND a.version_id = b.version_id
            WHERE b.version_id = ?
              AND (
                b.identificacion LIKE ? COLLATE NOCASE
                OR b.nombre LIKE ? COLLATE NOCASE
              )
            ORDER BY b.nombre COLLATE NOCASE, b.identificacion
            LIMIT ?
            """,
            (version_id, like, like, limite),
        ).fetchall()
    return [dict(r) for r in rows]


def buscar_estudiantes_version(
    version_id: int,
    termino: str,
    *,
    base: Path | None = None,
    limite: int = 50,
) -> list[dict[str, Any]]:
    """Búsqueda por cédula/nombre sobre una versión concreta."""
    return buscar_estudiantes(
        termino, version_id=version_id, base=base, limite=limite
    )


def contar_versiones(base: Path | None = None) -> int:
    inicializar_db(base)
    with conexion(base) as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM versiones").fetchone()
    return int(row["n"]) if row else 0


def contar_estudiantes_distintos(base: Path | None = None) -> int:
    """Personas distintas (por identificación) en cualquier versión del consolidado."""
    inicializar_db(base)
    with conexion(base) as conn:
        row = conn.execute(
            """
            SELECT COUNT(DISTINCT identificacion) AS n
            FROM estudiantes_base
            WHERE identificacion IS NOT NULL
              AND TRIM(identificacion) != ''
            """
        ).fetchone()
    return int(row["n"]) if row else 0


def ultima_version(base: Path | None = None) -> dict[str, Any] | None:
    versiones = listar_versiones(base)
    return versiones[0] if versiones else None


def ultima_version_por_id(base: Path | None = None) -> dict[str, Any] | None:
    """Última versión insertada (por id), no la de fecha más reciente."""
    inicializar_db(base)
    with conexion(base) as conn:
        row = conn.execute(
            """
            SELECT id, periodo, fecha_version, creado_en, num_estudiantes,
                   num_materias, ruta_excel, notas
            FROM versiones
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
    return dict(row) if row else None
