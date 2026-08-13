"""Base de datos SQLite del consolidado (versiones, estudiantes y marcaciones)."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

import polars as pl

from consolidado.paths import PROJECT_ROOT

DB_FILENAME = "consolidado.db"
CARPETA_DATOS = "datos"
SCHEMA_VERSION = 4

# Columnas canónicas del consolidado → campos indexables en `estudiantes`.
_CAMPOS_INDEXABLES: dict[str, str] = {
    "identificacion": "Identificación",
    "nombre": "Nombre y apellidos",
    "programa": "Programa",
    "periodo_ingreso": "Periodo ingreso",
    "priorizado": "Priorizado",
    "motivo_prio": "Motivo Prio.",
    "alerta_propia": "Alerta Propia",
    "detalle_propio": "Detalle Propio",
    "nivel_prioridad": "Nivel prioridad",
    "puntaje_prioridad": "Puntaje prioridad",
    "tipo_beca": "Tipo de beca o crédito",
}


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

        CREATE TABLE IF NOT EXISTS estudiantes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version_id INTEGER NOT NULL
                REFERENCES versiones(id) ON DELETE CASCADE,
            identificacion TEXT,
            nombre TEXT,
            programa TEXT,
            periodo_ingreso TEXT,
            priorizado TEXT,
            motivo_prio TEXT,
            alerta_propia TEXT,
            detalle_propio TEXT,
            nivel_prioridad TEXT,
            puntaje_prioridad REAL,
            tipo_beca TEXT,
            fila_json TEXT NOT NULL
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


def _crear_indices_v2(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_estudiantes_version
            ON estudiantes(version_id);
        CREATE INDEX IF NOT EXISTS idx_estudiantes_identificacion
            ON estudiantes(identificacion);
        CREATE INDEX IF NOT EXISTS idx_estudiantes_programa
            ON estudiantes(programa);
        CREATE INDEX IF NOT EXISTS idx_estudiantes_nivel
            ON estudiantes(nivel_prioridad);
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


def inicializar_db(base: Path | None = None) -> Path:
    """Crea o migra el schema. Devuelve la ruta del archivo .db."""
    base = base or PROJECT_ROOT
    with conexion(base) as conn:
        version = _schema_actual(conn)
        if version < 1:
            _crear_tablas_v2(conn)
            _crear_indices_v2(conn)
            _marcar_schema_version(conn)
            _migrar_json_marcaciones(conn, base)
        elif version < SCHEMA_VERSION:
            _crear_tablas_v2(conn)
            _migrar_estudiantes_v1_a_v2(conn)
            _migrar_priorizados_activo(conn)
            _crear_indices_v2(conn)
            _migrar_json_marcaciones(conn, base)
            _marcar_schema_version(conn)
        else:
            # Asegura tablas/índices por si el archivo se creó a medias.
            _crear_tablas_v2(conn)
            _migrar_priorizados_activo(conn)
            _crear_indices_v2(conn)
            _migrar_json_marcaciones(conn, base)
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
        registros = []
        for f in filas:
            campos = _extraer_campos_indexables(f)
            registros.append(
                (
                    version_id,
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
                    json.dumps(f, ensure_ascii=False),
                )
            )
        conn.executemany(
            """
            INSERT INTO estudiantes (
                version_id, identificacion, nombre, programa, periodo_ingreso,
                priorizado, motivo_prio, alerta_propia, detalle_propio,
                nivel_prioridad, puntaje_prioridad, tipo_beca, fila_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            registros,
        )

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


def cargar_dataframe_version(
    version_id: int,
    base: Path | None = None,
) -> pl.DataFrame:
    meta = obtener_version(version_id, base)
    if meta is None:
        raise ValueError(f"No existe la versión id={version_id}")
    with conexion(base) as conn:
        rows = conn.execute(
            "SELECT fila_json FROM estudiantes WHERE version_id = ? ORDER BY id",
            (version_id,),
        ).fetchall()
    filas = [json.loads(r["fila_json"]) for r in rows]
    return filas_a_dataframe(filas, meta["columnas"])


def buscar_estudiantes_version(
    version_id: int,
    termino: str,
    *,
    base: Path | None = None,
    limite: int = 50,
) -> list[dict[str, Any]]:
    """Búsqueda por cédula/nombre sobre columnas indexadas de una versión."""
    inicializar_db(base)
    q = f"%{termino.strip()}%"
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT id, identificacion, nombre, programa, nivel_prioridad,
                   puntaje_prioridad, priorizado, alerta_propia
            FROM estudiantes
            WHERE version_id = ?
              AND (
                identificacion LIKE ? COLLATE NOCASE
                OR nombre LIKE ? COLLATE NOCASE
              )
            ORDER BY nombre
            LIMIT ?
            """,
            (version_id, q, q, limite),
        ).fetchall()
    return [dict(r) for r in rows]


def contar_versiones(base: Path | None = None) -> int:
    inicializar_db(base)
    with conexion(base) as conn:
        row = conn.execute("SELECT COUNT(*) AS n FROM versiones").fetchone()
    return int(row["n"]) if row else 0


def ultima_version(base: Path | None = None) -> dict[str, Any] | None:
    versiones = listar_versiones(base)
    return versiones[0] if versiones else None
