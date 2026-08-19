"""
Usuarios de la web.

Roles: admin y consulta. Si la tabla está vacía se crea admin/admin.
Las claves van con PBKDF2; no las guarde en texto plano.
"""

from __future__ import annotations

import binascii
import hashlib
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any

from consolidado.paths import PROJECT_ROOT
from consolidado.storage.db import conexion, inicializar_db

ROLES = ("admin", "consulta")
USUARIO_ADMIN_INICIAL = "admin"
CLAVE_ADMIN_INICIAL = "admin"
_ITERACIONES = 200_000


def hash_clave(clave: str) -> str:
    sal = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal.encode("utf-8"), _ITERACIONES)
    return f"pbkdf2${sal}${binascii.hexlify(dk).decode('ascii')}"


def verificar_clave(clave: str, almacenado: str) -> bool:
    try:
        esquema, sal, esperado = str(almacenado).split("$", 2)
    except ValueError:
        return False
    if esquema != "pbkdf2":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), sal.encode("utf-8"), _ITERACIONES)
    return secrets.compare_digest(binascii.hexlify(dk).decode("ascii"), esperado)


def _fila(row: Any) -> dict[str, Any]:
    return {
        "id": int(row["id"]),
        "usuario": row["usuario"],
        "nombre": row["nombre"] or row["usuario"],
        "rol": row["rol"],
        "activo": bool(row["activo"]),
        "creado_en": row["creado_en"],
        "es_admin": row["rol"] == "admin",
    }


def listar_usuarios(base: Path | None = None) -> list[dict[str, Any]]:
    inicializar_db(base)
    with conexion(base) as conn:
        rows = conn.execute(
            """
            SELECT id, usuario, nombre, rol, activo, creado_en
            FROM usuarios
            ORDER BY rol DESC, usuario COLLATE NOCASE
            """
        ).fetchall()
    return [_fila(r) for r in rows]


def obtener_usuario(user_id: int, base: Path | None = None) -> dict[str, Any] | None:
    inicializar_db(base)
    with conexion(base) as conn:
        row = conn.execute(
            """
            SELECT id, usuario, nombre, rol, activo, creado_en
            FROM usuarios
            WHERE id = ?
            """,
            (int(user_id),),
        ).fetchone()
    return _fila(row) if row else None


def autenticar(usuario: str, clave: str, base: Path | None = None) -> dict[str, Any] | None:
    inicializar_db(base)
    nombre = str(usuario or "").strip()
    if not nombre or not clave:
        return None
    with conexion(base) as conn:
        row = conn.execute(
            """
            SELECT id, usuario, nombre, rol, activo, creado_en, clave_hash
            FROM usuarios
            WHERE usuario = ? COLLATE NOCASE
            """,
            (nombre,),
        ).fetchone()
    if row is None or not row["activo"]:
        return None
    if not verificar_clave(clave, row["clave_hash"]):
        return None
    return _fila(row)


def crear_usuario(
    usuario: str,
    clave: str,
    *,
    nombre: str = "",
    rol: str = "consulta",
    base: Path | None = None,
) -> dict[str, Any]:
    inicializar_db(base)
    usuario = str(usuario or "").strip()
    nombre = str(nombre or "").strip() or usuario
    rol = "admin" if str(rol).strip().lower() == "admin" else "consulta"
    if not usuario:
        raise ValueError("Indique un nombre de usuario.")
    if " " in usuario:
        raise ValueError("El usuario no puede tener espacios.")
    if len(usuario) < 3:
        raise ValueError("El usuario debe tener al menos 3 caracteres.")
    if len(clave) < 4:
        raise ValueError("La contraseña debe tener al menos 4 caracteres.")
    ahora = datetime.now().isoformat(timespec="seconds")
    with conexion(base) as conn:
        existe = conn.execute(
            "SELECT id FROM usuarios WHERE usuario = ? COLLATE NOCASE",
            (usuario,),
        ).fetchone()
        if existe:
            raise ValueError(f"Ya existe el usuario «{usuario}».")
        cur = conn.execute(
            """
            INSERT INTO usuarios (usuario, nombre, clave_hash, rol, activo, creado_en)
            VALUES (?, ?, ?, ?, 1, ?)
            """,
            (usuario, nombre, hash_clave(clave), rol, ahora),
        )
        nuevo_id = int(cur.lastrowid)
    return obtener_usuario(nuevo_id, base) or {
        "id": nuevo_id,
        "usuario": usuario,
        "nombre": nombre,
        "rol": rol,
        "activo": True,
        "es_admin": rol == "admin",
    }


def cambiar_clave(user_id: int, clave: str, base: Path | None = None) -> None:
    if len(clave) < 4:
        raise ValueError("La contraseña debe tener al menos 4 caracteres.")
    inicializar_db(base)
    with conexion(base) as conn:
        n = conn.execute(
            "UPDATE usuarios SET clave_hash = ? WHERE id = ?",
            (hash_clave(clave), int(user_id)),
        ).rowcount
    if not n:
        raise ValueError("No se encontró el usuario.")


def set_usuario_activo(user_id: int, activo: bool, base: Path | None = None) -> None:
    inicializar_db(base)
    with conexion(base) as conn:
        row = conn.execute(
            "SELECT id, rol, activo FROM usuarios WHERE id = ?",
            (int(user_id),),
        ).fetchone()
        if row is None:
            raise ValueError("No se encontró el usuario.")
        if row["rol"] == "admin" and not activo:
            vivos = conn.execute(
                "SELECT COUNT(*) FROM usuarios WHERE rol = 'admin' AND activo = 1 AND id != ?",
                (int(user_id),),
            ).fetchone()[0]
            if int(vivos) < 1:
                raise ValueError("No se puede desactivar al único administrador.")
        conn.execute(
            "UPDATE usuarios SET activo = ? WHERE id = ?",
            (1 if activo else 0, int(user_id)),
        )


def contar_admins_activos(base: Path | None = None) -> int:
    inicializar_db(base)
    with conexion(base) as conn:
        n = conn.execute(
            "SELECT COUNT(*) FROM usuarios WHERE rol = 'admin' AND activo = 1"
        ).fetchone()[0]
    return int(n)


def asegurar_admin_inicial(base: Path | None = None) -> bool:
    """Crea admin/admin si no hay usuarios. Devuelve True si lo acaba de crear."""
    inicializar_db(base)
    with conexion(base) as conn:
        n = conn.execute("SELECT COUNT(*) FROM usuarios").fetchone()[0]
        if int(n) > 0:
            return False
    crear_usuario(
        USUARIO_ADMIN_INICIAL,
        CLAVE_ADMIN_INICIAL,
        nombre="Administrador",
        rol="admin",
        base=base,
    )
    return True


def secreto_sesion(base: Path | None = None) -> str:
    inicializar_db(base)
    with conexion(base) as conn:
        row = conn.execute(
            "SELECT valor FROM schema_meta WHERE clave = 'session_secret'"
        ).fetchone()
        if row and row["valor"]:
            return str(row["valor"])
        valor = secrets.token_hex(32)
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (clave, valor) VALUES ('session_secret', ?)",
            (valor,),
        )
        return valor
