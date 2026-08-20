"""
Rutas FastAPI, sesión y control de acceso.

Consultor: hasta /versiones (GET). Admin: Data, Historial, Config, Usuarios,
Datos antiguos y POST de generar/importar.
Las plantillas reciben es_admin y el usuario de sesión vía _render.
"""

from __future__ import annotations

import sys
import tempfile
import webbrowser
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote

import uvicorn
from fastapi import Body, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from consolidado.config.settings import (
    cargar_config,
    guardar_config,
    restaurar_config_fabrica,
)
from consolidado.core.charts import (
    TIPOS_GRAFICA,
    columnas_graficables,
    excel_powerbi_desde_graficas,
    preparar_datos_grafica,
)
from consolidado.core.constants import aplicar_config
from consolidado.core.colores_programa import color_programa, estilo_color
from consolidado.core.ficha_estudiante import obtener_ficha_estudiante
from consolidado.core.priorizados import (
    buscar_estudiantes_en_fuentes,
)
from consolidado.core.seguimiento import CATEGORIAS_SEGUIMIENTO, listar_seguimiento
from consolidado.paths import BUNDLE_DIR, PROJECT_ROOT
from consolidado.storage.alertas_fuente import (
    descartar_alerta_fuente,
)
from consolidado.storage.alertas_propias import (
    agregar_alerta_propia,
    cargar_alertas_propias,
    quitar_alerta_propia,
)
from consolidado.storage.contactados import marcar_contactado
from consolidado.storage.db import (
    buscar_estudiantes,
    listar_versiones,
    ultima_version,
)
from consolidado.storage.modificaciones import (
    comparar_versiones,
    listar_modificaciones,
    registrar_modificacion,
    reset_usuario_log,
    set_usuario_log,
)
from consolidado.storage.periodos import sincronizar_periodo_actual_ultima_version
from consolidado.storage.priorizados import agregar_priorizado_propio, set_priorizado_activo
from consolidado.storage.usuarios import (
    asegurar_admin_inicial,
    autenticar,
    cambiar_clave,
    crear_usuario,
    listar_usuarios,
    obtener_usuario,
    secreto_sesion,
    set_usuario_activo,
)
from consolidado.storage.versiones import asegurar_semilla_si_vacia
from consolidado.web import services
from consolidado.web.manual_usuario import MANUAL_USUARIO

def _web_dir() -> Path:
    if getattr(sys, "frozen", False):
        bundled = BUNDLE_DIR / "consolidado" / "web"
        if (bundled / "templates").is_dir():
            return bundled
    return Path(__file__).resolve().parent


WEB_DIR = _web_dir()
TEMPLATES = Jinja2Templates(directory=str(WEB_DIR / "templates"))

app = FastAPI(title="Consolidado de Humanidades")
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

_RUTAS_PUBLICAS = {"/login", "/logout"}
# Rutas solo para rol admin. Consulta: hasta Versiones (GET), más Metas y Colores.
_PREFIJOS_ADMIN = (
    "/config",
    "/usuarios",
    "/archivos",
    "/upload",
    "/datos-antiguos",
    "/modificaciones",
    "/generar",
)
_RUTAS_ADMIN_EXTRA = {"/versiones/importar", "/versiones/generar"}


def _es_publico(path: str) -> bool:
    return path.startswith("/static") or path in _RUTAS_PUBLICAS


def _es_admin_ruta(path: str) -> bool:
    if path in _RUTAS_ADMIN_EXTRA:
        return True
    return any(path == p or path.startswith(p + "/") for p in _PREFIJOS_ADMIN)


def _usuario_sesion(request: Request) -> dict[str, Any] | None:
    uid = request.session.get("user_id")
    if not uid:
        return None
    usuario = obtener_usuario(int(uid), PROJECT_ROOT)
    if not usuario or not usuario.get("activo"):
        request.session.clear()
        return None
    return usuario


@app.middleware("http")
async def _auth_middleware(request: Request, call_next):
    path = request.url.path
    if _es_publico(path):
        return await call_next(request)
    usuario = _usuario_sesion(request)
    if usuario is None:
        if path.startswith("/api/"):
            return JSONResponse({"detail": "Inicie sesión."}, status_code=401)
        siguiente = quote(path)
        return RedirectResponse(f"/login?next={siguiente}", status_code=303)
    request.state.usuario = usuario
    token = set_usuario_log(usuario.get("usuario") or usuario.get("nombre"))
    try:
        if _es_admin_ruta(path) and not usuario.get("es_admin"):
            return RedirectResponse(
                "/?err=" + quote("Solo el administrador puede entrar ahí."),
                status_code=303,
            )
        return await call_next(request)
    finally:
        reset_usuario_log(token)


app.add_middleware(
    SessionMiddleware,
    secret_key=secreto_sesion(PROJECT_ROOT),
    session_cookie="humanidades_sesion",
    max_age=60 * 60 * 12,
    same_site="lax",
)


def _ctx(request: Request, **extra: Any) -> dict[str, Any]:
    cfg = services.cfg_actual()
    estado = services.estado_archivos(cfg)
    usuario = extra.pop("usuario", None)
    if usuario is None and not extra.pop("sin_sesion", False):
        usuario = _usuario_sesion(request)
    data = {
        "cfg": cfg,
        "estado": estado,
        "nav": extra.pop("nav", "archivos"),
        "flash": request.query_params.get("msg"),
        "error": request.query_params.get("err") or extra.pop("error", None),
        "hoy": date.today().isoformat(),
        "usuario": usuario,
        "es_admin": bool(usuario and usuario.get("es_admin")),
        "categorias_seg": [
            {"id": c["id"], "titulo": c["titulo"]} for c in CATEGORIAS_SEGUIMIENTO
        ],
        "cat": "",
        "vista": "pendientes",
        "manual_usuario": MANUAL_USUARIO,
    }
    data.update(extra)
    data["ayuda_clave"] = data.get("ayuda_clave") or data.get("nav") or "inicio"
    return data


def _render(request: Request, template: str, **extra: Any) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request, template, _ctx(request, **extra))


def _redir(path: str, *, msg: str | None = None, err: str | None = None) -> RedirectResponse:
    params: list[str] = []
    if msg:
        params.append(f"msg={quote(msg)}")
    if err:
        params.append(f"err={quote(err)}")
    if not params:
        return RedirectResponse(path, status_code=303)
    sep = "&" if "?" in path else "?"
    return RedirectResponse(f"{path}{sep}{'&'.join(params)}", status_code=303)


def _pintar_programas(filas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for f in filas:
        color = color_programa(f.get("programa"))
        f["color"] = color
        f["estilo"] = estilo_color(color)
    return filas


@app.on_event("startup")
def _startup() -> None:
    # Semilla SQL, Periodo actual desde BD1/BD12 (solo última versión) y admin inicial.
    asegurar_semilla_si_vacia(PROJECT_ROOT)
    try:
        sincronizar_periodo_actual_ultima_version(PROJECT_ROOT)
    except Exception as exc:
        if getattr(sys, "frozen", False):
            import logging

            logging.getLogger("consolidado").warning("No se pudo actualizar Periodo actual: %s", exc)
        else:
            print(f"No se pudo actualizar Periodo actual: {exc}")
    if asegurar_admin_inicial(PROJECT_ROOT) and not getattr(sys, "frozen", False):
        print("Usuario inicial creado: admin / admin. Cámbielo en Usuarios.")


@app.get("/login", response_class=HTMLResponse)
async def pagina_login(request: Request) -> HTMLResponse:
    if _usuario_sesion(request):
        return RedirectResponse("/", status_code=303)
    return TEMPLATES.TemplateResponse(
        request,
        "login.html",
        {
            "error": request.query_params.get("err"),
            "flash": request.query_params.get("msg"),
            "siguiente": request.query_params.get("next") or "/",
            "manual_usuario": MANUAL_USUARIO,
            "ayuda_clave": "login",
        },
    )


@app.post("/login")
async def iniciar_sesion(
    request: Request,
    usuario: str = Form(...),
    clave: str = Form(...),
    siguiente: str = Form("/"),
) -> RedirectResponse:
    cuenta = autenticar(usuario, clave, PROJECT_ROOT)
    if cuenta is None:
        return _redir("/login", err="Usuario o contraseña incorrectos.")
    request.session["user_id"] = cuenta["id"]
    destino = siguiente if siguiente.startswith("/") and not siguiente.startswith("//") else "/"
    return RedirectResponse(destino, status_code=303)


@app.get("/logout")
@app.post("/logout")
async def cerrar_sesion(request: Request) -> RedirectResponse:
    request.session.clear()
    return _redir("/login", msg="Sesión cerrada.")


@app.get("/", response_class=HTMLResponse)
async def inicio(request: Request) -> HTMLResponse:
    return _render(request, "inicio.html", nav="inicio")


@app.get("/metas", response_class=HTMLResponse)
async def pagina_metas(request: Request) -> HTMLResponse:
    return _render(request, "metas.html", nav="metas", metas=services.metas_ruta_grado())


@app.get("/colores", response_class=HTMLResponse)
async def pagina_colores(request: Request) -> HTMLResponse:
    return _render(request, "colores.html", nav="colores", leyenda=services.leyenda_colores())


@app.get("/archivos", response_class=HTMLResponse)
async def pagina_archivos(request: Request) -> HTMLResponse:
    return _render(request, "archivos.html", nav="archivos")


@app.post("/upload/{slot_id}")
async def upload_slot(slot_id: str, archivo: UploadFile = File(...)) -> RedirectResponse:
    try:
        contenido = await archivo.read()
        if not contenido:
            raise ValueError("Archivo vacío.")
        services.subir_slot(slot_id, archivo.filename or "archivo.xlsx", contenido)
    except Exception as exc:
        return _redir("/archivos", err=str(exc))
    return _redir("/archivos", msg="Archivo actualizado")


@app.post("/generar")
async def generar_consolidado(
    fecha_version: str = Form(""),
    notas: str = Form(""),
) -> RedirectResponse:
    try:
        fecha = services.parse_fecha(fecha_version)
        info = services.generar(fecha_version=fecha, notas=notas or None, abrir=True)
        n = info["estudiantes"]
        return _redir(
            "/versiones",
            msg=f"Versión {fecha.isoformat()} guardada: {n} estudiantes. Se abrió el Excel.",
        )
    except Exception as exc:
        return _redir("/", err=str(exc))


@app.get("/consolidado", response_class=HTMLResponse)
async def vista_consolidado() -> RedirectResponse:
    return RedirectResponse("/graficas", status_code=303)


@app.get("/estudiante", response_class=HTMLResponse)
async def pagina_estudiante(request: Request, q: str = "") -> HTMLResponse:
    cfg = services.cfg_actual()
    resultados = []
    ficha = None
    if q.strip():
        resultados = buscar_estudiantes(q.strip(), base=PROJECT_ROOT, limite=40)
        if not resultados:
            resultados = buscar_estudiantes_en_fuentes(cfg, PROJECT_ROOT, q.strip(), limite=40)
        _pintar_programas(resultados)
        if len(resultados) == 1:
            ficha = obtener_ficha_estudiante(cfg, PROJECT_ROOT, resultados[0]["identificacion"])
        elif q.strip().isdigit() or len(q.strip()) >= 5:
            ficha = obtener_ficha_estudiante(cfg, PROJECT_ROOT, q.strip())
    return _render(
        request,
        "estudiante.html",
        nav="estudiante",
        q=q,
        resultados=resultados,
        ficha=ficha,
    )


@app.get("/estudiante/{identificacion}", response_class=HTMLResponse)
async def ficha_estudiante(request: Request, identificacion: str) -> HTMLResponse:
    cfg = services.cfg_actual()
    ficha = obtener_ficha_estudiante(cfg, PROJECT_ROOT, identificacion)
    if ficha is None:
        return _render(
            request,
            "estudiante.html",
            nav="estudiante",
            q=identificacion,
            resultados=[],
            ficha=None,
            error="No se encontró el estudiante en el consolidado actual.",
        )
    return _render(
        request,
        "estudiante.html",
        nav="estudiante",
        q=identificacion,
        resultados=[],
        ficha=ficha,
    )


@app.get("/seguimiento", response_class=HTMLResponse)
async def pagina_seguimiento(
    request: Request,
    cat: str = "general",
    vista: str = "pendientes",
) -> HTMLResponse:
    data = listar_seguimiento(cat_id=cat, vista=vista, base=PROJECT_ROOT)
    return _render(
        request,
        "seguimiento.html",
        nav="seguimiento",
        cat=data["categoria"]["id"],
        categorias=data["categorias"],
        categoria=data["categoria"],
        filas=data["filas"],
        total=data["total"],
        visibles=data["visibles"],
        vista=data["vista"],
        meta=data["meta"],
        alertas_propias=cargar_alertas_propias(PROJECT_ROOT) if data["categoria"]["id"] == "alertas" else [],
    )


@app.get("/priorizados", response_class=HTMLResponse)
async def pagina_priorizados(vista: str = "primer_plano") -> RedirectResponse:
    destino = "pendientes" if vista == "primer_plano" else "todos"
    return RedirectResponse(f"/seguimiento?cat=priorizado&vista={destino}", status_code=303)


@app.get("/alertas", response_class=HTMLResponse)
async def pagina_alertas() -> RedirectResponse:
    return RedirectResponse("/seguimiento?cat=alertas", status_code=303)


@app.post("/seguimiento/marcar")
async def marcar_seguimiento(
    identificacion: str = Form(...),
    contactado: str = Form("1"),
    cat: str = Form("general"),
    vista: str = Form("pendientes"),
) -> RedirectResponse:
    marcar_contactado(
        identificacion,
        contactado=contactado in {"1", "true", "on"},
        base=PROJECT_ROOT,
    )
    estado = "contactado" if contactado in {"1", "true", "on"} else "pendiente"
    registrar_modificacion(
        accion="contactado",
        resumen=f"Marcó {identificacion} como {estado}",
        entidad="estudiante",
        identificacion=identificacion,
    )
    return RedirectResponse(
        f"/seguimiento?cat={quote(cat)}&vista={quote(vista)}",
        status_code=303,
    )


@app.post("/priorizados/contactado")
async def toggle_contactado(
    identificacion: str = Form(...),
    contactado: str = Form("1"),
    vista: str = Form("primer_plano"),
) -> RedirectResponse:
    marcar_contactado(identificacion, contactado=contactado in {"1", "true", "on"}, base=PROJECT_ROOT)
    estado = "contactado" if contactado in {"1", "true", "on"} else "no contactado"
    registrar_modificacion(
        accion="contactado",
        resumen=f"Marcó {identificacion} como {estado}",
        entidad="estudiante",
        identificacion=identificacion,
    )
    return RedirectResponse(
        f"/seguimiento?cat=priorizado&vista={'todos' if vista == 'completo' else 'pendientes'}",
        status_code=303,
    )


@app.post("/priorizados/activo")
async def toggle_activo(
    identificacion: str = Form(...),
    activo: str = Form("1"),
    vista: str = Form("completo"),
) -> RedirectResponse:
    activo_ok = activo in {"1", "true", "on"}
    set_priorizado_activo(identificacion, activo=activo_ok, base=PROJECT_ROOT)
    registrar_modificacion(
        accion="priorizado_activo",
        resumen=f"{'Activó' if activo_ok else 'Desactivó'} priorizado {identificacion}",
        entidad="estudiante",
        identificacion=identificacion,
    )
    return RedirectResponse("/seguimiento?cat=priorizado&vista=todos&msg=Estado+actualizado", status_code=303)


@app.post("/priorizados/anadir")
async def anadir_propio(
    identificacion: str = Form(...),
    nombre: str = Form(""),
    motivo: str = Form("Priorizado propio"),
    detalle: str = Form(""),
) -> RedirectResponse:
    agregar_priorizado_propio(
        {
            "identificacion": identificacion,
            "nombre": nombre,
            "motivo": motivo or "Priorizado propio",
            "detalle": detalle,
        },
        PROJECT_ROOT,
    )
    registrar_modificacion(
        accion="priorizado_propio",
        resumen=f"Añadió priorizado propio {identificacion}",
        entidad="estudiante",
        identificacion=identificacion,
        detalle={"motivo": motivo, "nombre": nombre},
    )
    return RedirectResponse("/seguimiento?cat=priorizado&vista=todos&msg=Priorizado+guardado", status_code=303)


@app.post("/alertas/fuente/quitar")
async def quitar_alerta_fuente(
    identificacion: str = Form(...),
    fase: str = Form(...),
    tipo: str = Form(...),
    volver: str = Form(""),
) -> RedirectResponse:
    raw = volver.strip()
    if raw.startswith("/estudiante"):
        destino = raw
    elif raw.startswith("/seguimiento"):
        destino = raw
    else:
        destino = "/seguimiento?cat=alertas"
    try:
        descartar_alerta_fuente(identificacion, fase, tipo, PROJECT_ROOT)
    except ValueError as exc:
        return _redir(destino, err=str(exc))
    registrar_modificacion(
        accion="descartar_alerta",
        resumen=f"Descartó alerta {fase}: {tipo} · {identificacion}",
        entidad="alerta",
        identificacion=identificacion,
        detalle={"fase": fase, "tipo": tipo},
    )
    return _redir(destino, msg="Alerta descartada. No volverá a aparecer al generar.")


@app.post("/alertas/anadir")
async def anadir_alerta(
    identificacion: str = Form(...),
    nombre: str = Form(""),
    detalle: str = Form(...),
) -> RedirectResponse:
    agregar_alerta_propia(
        {"identificacion": identificacion, "nombre": nombre, "detalle": detalle},
        PROJECT_ROOT,
    )
    registrar_modificacion(
        accion="alerta_propia",
        resumen=f"Añadió alerta propia a {identificacion}",
        entidad="alerta",
        identificacion=identificacion,
    )
    return RedirectResponse("/seguimiento?cat=alertas&msg=Alerta+guardada", status_code=303)


@app.post("/alertas/quitar")
async def quitar_alerta(identificacion: str = Form(...)) -> RedirectResponse:
    quitar_alerta_propia(identificacion, PROJECT_ROOT)
    registrar_modificacion(
        accion="quitar_alerta_propia",
        resumen=f"Quitó alerta propia de {identificacion}",
        entidad="alerta",
        identificacion=identificacion,
    )
    return RedirectResponse("/seguimiento?cat=alertas&msg=Alerta+eliminada", status_code=303)


@app.get("/config", response_class=HTMLResponse)
async def pagina_config(request: Request) -> HTMLResponse:
    cfg = services.cfg_actual()
    return _render(
        request,
        "config.html",
        nav="config",
        aliases=cfg.get("aliases", {}),
        programas=cfg.get("programas_permitidos", []),
        excluidos=cfg.get("programas_excluidos", []),
        motivos=cfg.get("columnas_motivo_priorizado", []),
        documentos=cfg.get("documentos_adicionales", []),
    )


@app.post("/config/guardar")
async def guardar_config_web(
    programas: str = Form(""),
    excluidos: str = Form(""),
    motivos: str = Form(""),
) -> RedirectResponse:
    cfg = cargar_config(PROJECT_ROOT)

    def _lineas(texto: str) -> list[str]:
        return [ln.strip() for ln in texto.splitlines() if ln.strip()]

    cfg["programas_permitidos"] = _lineas(programas)
    cfg["programas_excluidos"] = _lineas(excluidos)
    cfg["columnas_motivo_priorizado"] = _lineas(motivos)
    guardar_config(cfg, PROJECT_ROOT)
    aplicar_config(cfg, PROJECT_ROOT)
    registrar_modificacion(
        accion="config",
        resumen="Guardó la configuración (programas, exclusiones y motivos)",
        entidad="config",
    )
    return RedirectResponse("/config?msg=Configuración+guardada", status_code=303)


@app.post("/config/fabrica")
async def config_fabrica() -> RedirectResponse:
    cfg = cargar_config(PROJECT_ROOT)
    restaurar_config_fabrica(cfg, PROJECT_ROOT)
    registrar_modificacion(
        accion="config",
        resumen="Restauró valores de fábrica de la configuración",
        entidad="config",
    )
    return RedirectResponse("/config?msg=Valores+de+fábrica+restaurados", status_code=303)


@app.get("/usuarios", response_class=HTMLResponse)
async def pagina_usuarios(request: Request) -> HTMLResponse:
    return _render(
        request,
        "usuarios.html",
        nav="usuarios",
        usuarios=listar_usuarios(PROJECT_ROOT),
    )


@app.post("/usuarios/crear")
async def usuarios_crear(
    usuario: str = Form(...),
    nombre: str = Form(""),
    clave: str = Form(...),
    rol: str = Form("consulta"),
) -> RedirectResponse:
    try:
        crear_usuario(usuario, clave, nombre=nombre, rol=rol, base=PROJECT_ROOT)
    except ValueError as exc:
        return _redir("/usuarios", err=str(exc))
    registrar_modificacion(
        accion="usuario",
        resumen=f"Creó usuario «{usuario}» ({rol})",
        entidad="usuario",
        identificacion=usuario,
    )
    return _redir("/usuarios", msg=f"Usuario «{usuario}» creado.")


@app.post("/usuarios/clave")
async def usuarios_clave(
    user_id: int = Form(...),
    clave: str = Form(...),
) -> RedirectResponse:
    try:
        cambiar_clave(user_id, clave, PROJECT_ROOT)
    except ValueError as exc:
        return _redir("/usuarios", err=str(exc))
    registrar_modificacion(
        accion="usuario",
        resumen=f"Actualizó la contraseña del usuario id={user_id}",
        entidad="usuario",
        identificacion=str(user_id),
    )
    return _redir("/usuarios", msg="Contraseña actualizada.")


@app.post("/usuarios/activo")
async def usuarios_activo(
    request: Request,
    user_id: int = Form(...),
    activo: str = Form("1"),
) -> RedirectResponse:
    actual = _usuario_sesion(request)
    if actual and int(actual["id"]) == int(user_id) and activo not in {"1", "true", "on"}:
        return _redir("/usuarios", err="No puede desactivar su propia cuenta.")
    try:
        set_usuario_activo(user_id, activo in {"1", "true", "on"}, PROJECT_ROOT)
    except ValueError as exc:
        return _redir("/usuarios", err=str(exc))
    estado = "activó" if activo in {"1", "true", "on"} else "desactivó"
    registrar_modificacion(
        accion="usuario",
        resumen=f"{estado.capitalize()} usuario id={user_id}",
        entidad="usuario",
        identificacion=str(user_id),
    )
    return _redir("/usuarios", msg="Usuario actualizado.")


@app.get("/versiones", response_class=HTMLResponse)
async def pagina_versiones(request: Request) -> HTMLResponse:
    return _render(
        request,
        "versiones.html",
        nav="versiones",
        versiones=listar_versiones(PROJECT_ROOT),
    )


@app.get("/versiones/ultima/excel")
async def descargar_ultimo_excel() -> FileResponse:
    ult = ultima_version(PROJECT_ROOT)
    if not ult:
        raise HTTPException(404, "Aún no hay un Excel generado.")
    try:
        ruta = services.excel_de_version(int(ult["id"]))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(
        path=str(ruta.resolve()),
        filename=ruta.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/versiones/{version_id}/excel")
async def descargar_excel_version(version_id: int) -> FileResponse:
    try:
        ruta = services.excel_de_version(version_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(
        path=str(ruta.resolve()),
        filename=ruta.name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.get("/modificaciones", response_class=HTMLResponse)
async def pagina_modificaciones(
    request: Request,
    de: int | None = None,
    a: int | None = None,
) -> HTMLResponse:
    versiones = listar_versiones(PROJECT_ROOT)
    de_id, a_id = de, a
    if de_id is None and a_id is None and len(versiones) >= 2:
        por_id = sorted(versiones, key=lambda v: int(v["id"]))
        de_id = int(por_id[-2]["id"])
        a_id = int(por_id[-1]["id"])
    comparacion = None
    cmp_error = None
    if de_id is not None and a_id is not None:
        try:
            comparacion = comparar_versiones(int(de_id), int(a_id), base=PROJECT_ROOT)
        except ValueError as exc:
            cmp_error = str(exc)
    return _render(
        request,
        "modificaciones.html",
        nav="modificaciones",
        modificaciones=listar_modificaciones(PROJECT_ROOT),
        versiones=versiones,
        comparacion=comparacion,
        de_id=de_id,
        a_id=a_id,
        cmp_error=cmp_error,
    )


@app.get("/datos-antiguos", response_class=HTMLResponse)
async def pagina_datos_antiguos(request: Request) -> HTMLResponse:
    return _render(request, "datos_antiguos.html", nav="datos-antiguos")


async def _importar_excel_request(
    archivo: UploadFile,
    fecha_version: str,
    notas: str,
    destino: str,
) -> RedirectResponse:
    tmp_path: Path | None = None
    try:
        fecha = services.parse_fecha(fecha_version)
        contenido = await archivo.read()
        if not contenido:
            raise ValueError("Archivo vacío.")
        suffix = Path(archivo.filename or "consolidado.xlsx").suffix.lower() or ".xlsx"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(contenido)
            tmp_path = Path(tmp.name)
        info = services.importar_version(tmp_path, fecha, notas or None)
        n = info["estudiantes"]
        return _redir(
            destino,
            msg=f"Excel importado como versión {fecha.isoformat()}: {n} estudiantes.",
        )
    except Exception as exc:
        return _redir(destino, err=str(exc))
    finally:
        if tmp_path is not None and tmp_path.is_file():
            try:
                tmp_path.unlink()
            except OSError:
                pass


@app.post("/datos-antiguos/importar")
async def importar_datos_antiguos(
    archivo: UploadFile = File(...),
    fecha_version: str = Form(...),
    notas: str = Form(""),
) -> RedirectResponse:
    return await _importar_excel_request(archivo, fecha_version, notas, "/datos-antiguos")


@app.post("/versiones/importar")
async def importar_version_excel_legacy(
    archivo: UploadFile = File(...),
    fecha_version: str = Form(...),
    notas: str = Form(""),
) -> RedirectResponse:
    return await _importar_excel_request(archivo, fecha_version, notas, "/datos-antiguos")


@app.post("/datos-antiguos/generar")
async def generar_datos_antiguos(request: Request) -> RedirectResponse:
    try:
        form = await request.form()
        fecha = services.parse_fecha(str(form.get("fecha_version") or ""))
        notas = str(form.get("notas") or "")
        archivos: dict[str, tuple[str, bytes]] = {}
        for key, value in form.multi_items():
            if not str(key).startswith("archivo_"):
                continue
            slot_id = str(key)[len("archivo_") :]
            if not slot_id or not hasattr(value, "read"):
                continue
            contenido = await value.read()
            if not contenido:
                continue
            nombre = getattr(value, "filename", None) or "archivo.xlsx"
            archivos[slot_id] = (str(nombre), contenido)
        info = services.generar_version_historica(archivos, fecha, notas or None)
        n = info["estudiantes"]
        return _redir(
            "/datos-antiguos",
            msg=(
                f"Versión histórica {fecha.isoformat()} creada: {n} estudiantes. "
                "Los archivos actuales no se modificaron."
            ),
        )
    except Exception as exc:
        return _redir("/datos-antiguos", err=str(exc))


@app.post("/versiones/generar")
async def generar_version_fechada_legacy() -> RedirectResponse:
    return _redir(
        "/datos-antiguos",
        err="Las versiones antiguas se montan en Datos antiguos, sin tocar los archivos actuales.",
    )


@app.get("/graficas", response_class=HTMLResponse)
async def pagina_graficas(request: Request) -> HTMLResponse:
    df, meta = services.df_ultima_version()
    columnas = columnas_graficables(df) if df is not None else []
    return _render(
        request,
        "graficas.html",
        nav="graficas",
        columnas=columnas,
        tipos=TIPOS_GRAFICA,
        meta=meta,
    )


@app.get("/api/grafica")
async def api_grafica(columna: str, tipo: str = "bar", top: int = 25) -> JSONResponse:
    df, _ = services.df_ultima_version()
    if df is None or df.height == 0:
        raise HTTPException(400, "No hay datos del consolidado. Genere uno primero.")
    try:
        data = preparar_datos_grafica(df, columna=columna, tipo=tipo, top=top)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse(data)


@app.post("/api/grafica/powerbi")
async def api_grafica_powerbi(payload: dict[str, Any] = Body(...)) -> Response:
    df, _ = services.df_ultima_version()
    if df is None or df.height == 0:
        raise HTTPException(400, "No hay datos del consolidado. Genere uno primero.")
    items = payload.get("graficas") if isinstance(payload, dict) else None
    if not items:
        raise HTTPException(400, "Indique al menos una gráfica lista.")
    series: list[dict[str, Any]] = []
    try:
        for item in items:
            columna = str(item.get("columna") or "")
            tipo = str(item.get("tipo") or "bar")
            top = int(item.get("top") or 20)
            data = preparar_datos_grafica(df, columna=columna, tipo=tipo, top=top)
            series.append(data)
        contenido = excel_powerbi_desde_graficas(series)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="graficas_powerbi.xlsx"'
        },
    )


@app.get("/api/buscar")
async def api_buscar(q: str = "") -> JSONResponse:
    resultados = buscar_estudiantes(q, base=PROJECT_ROOT, limite=30)
    if not resultados:
        cfg = services.cfg_actual()
        resultados = buscar_estudiantes_en_fuentes(cfg, PROJECT_ROOT, q, limite=30)
    _pintar_programas(resultados)
    return JSONResponse(resultados)


def main(host: str = "127.0.0.1", port: int = 8765, *, open_browser: bool = True) -> None:
    if getattr(sys, "frozen", False):
        _run_empaquetado(host, port, open_browser=open_browser)
        return
    if open_browser:
        webbrowser.open(f"http://{host}:{port}/")
    uvicorn.run(
        "consolidado.web.app:app",
        host=host,
        port=port,
        reload=True,
        log_level="info",
    )


def _puerto_libre(host: str, port: int, intentos: int = 10) -> int | None:
    import socket

    for candidato in range(port, port + intentos):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind((host, candidato))
            sock.close()
            return candidato
        except OSError:
            try:
                sock.close()
            except OSError:
                pass
    return None


def _run_empaquetado(host: str, port: int, *, open_browser: bool) -> None:
    import logging
    import threading

    from consolidado.web.avisos import mostrar_tarjeta

    elegido = _puerto_libre(host, port)
    if elegido is None:
        mostrar_tarjeta(
            "No se pudo iniciar",
            f"Los puertos {port}–{port + 9} están ocupados. Cierre la otra ventana de la aplicación e inténtelo de nuevo.",
            "error",
        )
        return

    log_dir = PROJECT_ROOT / "datos"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=str(log_dir / "servidor.log"),
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    if open_browser:
        threading.Timer(0.7, lambda: webbrowser.open(f"http://{host}:{elegido}/")).start()
    try:
        uvicorn.run(
            app,
            host=host,
            port=elegido,
            log_level="warning",
            access_log=False,
        )
    except OSError as exc:
        mostrar_tarjeta(
            "No se pudo iniciar",
            "No fue posible abrir el servidor. "
            f"Detalle: {exc}",
            "error",
        )
    except Exception as exc:
        mostrar_tarjeta(
            "Error inesperado",
            str(exc) or "La aplicación se detuvo al arrancar.",
            "error",
        )


if __name__ == "__main__":
    main()
