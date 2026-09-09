"""
Rutas FastAPI, sesión y control de acceso.

Consultor: hasta /versiones, /parcializado y /proyeccion (GET). Admin: Data, Historial, Config, Usuarios,
Datos antiguos, POST de generar/importar y alta de estudiantes.
Las plantillas reciben es_admin y el usuario de sesión vía _render.
"""

from __future__ import annotations

import json
import sys
import tempfile
import webbrowser
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import uvicorn
from fastapi import Body, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
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
from consolidado.core.ficha_estudiante import formulario_alta_estudiante, obtener_ficha_estudiante
from consolidado.core.priorizados import (
    buscar_estudiantes_en_fuentes,
)
from consolidado.core.seguimiento import CATEGORIAS_SEGUIMIENTO, listar_seguimiento
from consolidado.core.proyeccion_grado import listar_proyeccion
from consolidado.paths import BUNDLE_DIR, PROJECT_ROOT
from consolidado.version import APP_VERSION
from consolidado.storage.alertas_fuente import (
    descartar_alerta_fuente,
)
from consolidado.storage.alertas_propias import (
    agregar_alerta_propia,
    cargar_alertas_propias,
    quitar_alerta_propia,
)
from consolidado.storage.contactados import estadisticas_atenciones, marcar_contactado
from consolidado.storage.graduacion import marcar_gradua
from consolidado.storage.ediciones import GRUPOS_EDITABLES, borrar_ediciones_grupo, clave_campo_edicion, guardar_ediciones
from consolidado.storage.estudiantes_manuales import crear_estudiante_manual
from consolidado.storage.notas import agregar_nota, quitar_nota
from consolidado.storage.db import (
    buscar_estudiantes,
    listar_versiones,
    periodo_desde_fecha,
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

app = FastAPI(title="Consolidado de Humanidades", version=APP_VERSION)
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

_RUTAS_PUBLICAS = {"/login", "/logout", "/api/apagar"}
# Rutas solo para rol admin. Consulta: hasta Versiones (GET), más Metas e Información.
_PREFIJOS_ADMIN = (
    "/config",
    "/usuarios",
    "/archivos",
    "/upload",
    "/datos-antiguos",
    "/modificaciones",
    "/generar",
    "/api/documento",
    "/api/fuente",
)
_RUTAS_ADMIN_EXTRA = {"/versiones/importar", "/versiones/generar", "/estudiante/crear"}


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
        "app_version": APP_VERSION,
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
            "app_version": APP_VERSION,
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
    return await pagina_informacion(request)


@app.get("/informacion", response_class=HTMLResponse)
async def pagina_informacion(request: Request) -> HTMLResponse:
    try:
        info = services.definicion_puntajes()
    except Exception:
        info = {"formula": "", "bloques": [], "niveles": [], "colores": [], "notas": ""}
    try:
        leyenda = services.leyenda_colores()
    except Exception:
        leyenda = {"excel": [], "programas": [], "niveles": []}
    return _render(
        request,
        "informacion.html",
        nav="informacion",
        info=info,
        leyenda=leyenda,
    )


@app.get("/archivos", response_class=HTMLResponse)
async def pagina_archivos(request: Request) -> HTMLResponse:
    return _render(
        request,
        "archivos.html",
        nav="archivos",
        fuentes_mapeo=services.listar_fuentes_para_mapa(),
        paquete_inicial=services.hay_paquete_inicial(),
    )


def _redir_carga_fuentes(resultado: dict[str, Any]) -> RedirectResponse:
    n_ok = len(resultado.get("ok") or [])
    partes: list[str] = []
    if n_ok:
        partes.append(f"Se cargaron {n_ok} archivo{'s' if n_ok != 1 else ''} de fuente.")
    if resultado.get("sin_slot"):
        nombres = ", ".join(resultado["sin_slot"][:8])
        extra = f" y {len(resultado['sin_slot']) - 8} más" if len(resultado["sin_slot"]) > 8 else ""
        partes.append(f"No se reconocieron: {nombres}{extra}.")
    if resultado.get("errores"):
        partes.append(" ".join(str(e) for e in resultado["errores"][:4]))
    texto = " ".join(partes) or "Ningún archivo se pudo cargar."
    if not n_ok:
        return _redir("/archivos", err=texto)
    return _redir("/archivos", msg=texto)


@app.post("/upload/varios")
async def upload_varios(archivos: list[UploadFile] = File(...)) -> RedirectResponse:
    lote: list[tuple[str, bytes]] = []
    for archivo in archivos:
        nombre = archivo.filename or "archivo.xlsx"
        if nombre.startswith("."):
            continue
        contenido = await archivo.read()
        lote.append((nombre, contenido))
    if not lote:
        return _redir("/archivos", err="No se eligió ningún Excel.")
    if len(lote) == 1 and Path(lote[0][0]).suffix.lower() == ".zip":
        try:
            resultado = services.importar_paquete_fuentes(lote[0][1], nombre_zip=lote[0][0])
        except Exception as exc:
            return _redir("/archivos", err=str(exc))
        return _redir_carga_fuentes(resultado)
    try:
        resultado = services.subir_varios(lote)
    except Exception as exc:
        return _redir("/archivos", err=str(exc))
    return _redir_carga_fuentes(resultado)


@app.post("/upload/paquete")
async def upload_paquete(archivo: UploadFile = File(...)) -> RedirectResponse:
    nombre = archivo.filename or "paquete.zip"
    contenido = await archivo.read()
    if not contenido:
        return _redir("/archivos", err="El ZIP está vacío.")
    try:
        resultado = services.importar_paquete_fuentes(contenido, nombre_zip=nombre)
    except Exception as exc:
        return _redir("/archivos", err=str(exc))
    return _redir_carga_fuentes(resultado)


@app.post("/upload/paquete/ejemplo")
async def upload_paquete_ejemplo() -> RedirectResponse:
    info = services.hay_paquete_inicial()
    if not info:
        return _redir(
            "/archivos",
            err="No hay un paquete inicial junto a la aplicación. Suba el ZIP a mano.",
        )
    ruta = Path(info["ruta"])
    try:
        resultado = services.importar_paquete_fuentes(ruta.read_bytes(), nombre_zip=ruta.name)
    except Exception as exc:
        return _redir("/archivos", err=str(exc))
    return _redir_carga_fuentes(resultado)


@app.post("/upload/lote")
async def upload_lote(request: Request) -> RedirectResponse:
    form = await request.form()
    lote: dict[str, tuple[str, bytes]] = {}
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
        lote[slot_id] = (str(nombre), contenido)
    if not lote:
        return _redir("/archivos", err="No hay archivos seleccionados.")
    try:
        resultado = services.subir_lote(lote)
    except Exception as exc:
        return _redir("/archivos", err=str(exc))
    n_ok = len(resultado["ok"])
    partes: list[str] = []
    if n_ok:
        partes.append(f"Se actualizaron {n_ok} archivo{'s' if n_ok != 1 else ''}.")
    if resultado["errores"]:
        partes.append(" ".join(resultado["errores"][:4]))
    if not n_ok:
        return _redir("/archivos", err=" ".join(partes) or "Ningún archivo se pudo cargar.")
    return _redir("/archivos", msg=" ".join(partes))


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


@app.post("/api/documento/preview")
async def api_documento_preview(
    archivo: UploadFile = File(...),
    hoja: str = Form(""),
) -> JSONResponse:
    try:
        contenido = await archivo.read()
        data = services.previsualizar_excel_bytes(
            contenido, archivo.filename or "archivo.xlsx", hoja=hoja or None
        )
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse(data)


@app.get("/api/documento/{doc_id}")
async def api_documento_guardado(doc_id: str, hoja: str = "") -> JSONResponse:
    try:
        data = services.previsualizar_documento_guardado(doc_id, hoja=hoja or None)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse(data)


def _columnas_desde_form(texto: str) -> list[dict[str, Any]]:
    raw = (texto or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("No se pudieron leer las columnas seleccionadas.") from exc
    if not isinstance(data, list):
        raise ValueError("El listado de columnas no es válido.")
    return [item for item in data if isinstance(item, dict)]


@app.get("/api/fuente/{slot_id}")
async def api_fuente_preview(slot_id: str, hoja: str = "") -> JSONResponse:
    try:
        data = services.previsualizar_slot_fuente(slot_id, hoja=hoja or None)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse(data)


@app.post("/archivos/fuente/{slot_id}/mapeo")
async def guardar_mapeo_fuente(
    slot_id: str,
    hoja: str = Form(""),
    mapeo: str = Form("[]"),
) -> RedirectResponse:
    try:
        services.guardar_mapeo_slot(
            slot_id, hoja=hoja or None, mapeo=_columnas_desde_form(mapeo)
        )
    except Exception as exc:
        return _redir("/archivos", err=str(exc))
    return _redir("/archivos", msg="Se guardó el mapeo de esa base de datos.")


@app.post("/archivos/documento")
async def guardar_documento_web(
    titulo: str = Form(""),
    grupo: str = Form(""),
    pk: str = Form(""),
    hoja: str = Form(""),
    columnas: str = Form("[]"),
    doc_id: str = Form(""),
    archivo: UploadFile | None = File(default=None),
) -> RedirectResponse:
    try:
        contenido = None
        nombre = ""
        if archivo is not None and archivo.filename:
            contenido = await archivo.read()
            nombre = archivo.filename
            if not contenido:
                contenido = None
        info = services.guardar_documento_adicional(
            titulo=titulo,
            grupo=grupo,
            pk=pk,
            columnas=_columnas_desde_form(columnas),
            hoja=hoja or None,
            contenido=contenido,
            nombre_archivo=nombre,
            doc_id=doc_id or None,
        )
    except Exception as exc:
        return _redir("/archivos", err=str(exc))
    verbo = "actualizó" if doc_id else "añadió"
    return _redir("/archivos", msg=f"Se {verbo} «{info['titulo']}».")


@app.post("/archivos/documento/{doc_id}/eliminar")
async def eliminar_documento_web(doc_id: str) -> RedirectResponse:
    try:
        services.eliminar_documento_adicional(doc_id)
    except Exception as exc:
        return _redir("/archivos", err=str(exc))
    return _redir("/archivos", msg="Documento adicional eliminado.")


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
        return _redir("/archivos", err=str(exc))


@app.get("/consolidado", response_class=HTMLResponse)
async def vista_consolidado() -> RedirectResponse:
    return RedirectResponse("/graficas", status_code=303)


def _tabs_ficha(request: Request, ficha: dict | None) -> tuple[str, str]:
    cat = (request.query_params.get("cat") or "").strip()
    sec = (request.query_params.get("sec") or "").strip()
    cats: list[str] = []
    if ficha:
        cats.extend(
            str(c.get("clave") or "")
            for c in (ficha.get("categorias") or [])
            if c.get("clave") and c.get("clave") != "datos"
        )
    if cat not in cats:
        cat = cats[0] if cats else "academico"
    if sec not in {"notas", "nueva", "grado", "horario"}:
        sec = "notas"
    return cat, sec


def _ident_para_alta(texto: str) -> str:
    bruto = (texto or "").strip()
    compacto = bruto.replace(".", "").replace("-", "").replace(" ", "")
    return bruto if compacto.isdigit() else ""


def _esquema_alta_estudiante(
    valores: dict[str, Any] | None = None,
    *,
    ident_prefijo: str = "",
) -> dict[str, Any]:
    cfg = services.cfg_actual()
    programas = [
        str(p).strip()
        for p in (cfg.get("programas_permitidos") or [])
        if str(p).strip()
    ]
    ult = ultima_version(PROJECT_ROOT)
    periodo = str((ult or {}).get("periodo") or "").strip() or periodo_desde_fecha()
    vals = dict(valores or {})
    pref = _ident_para_alta(ident_prefijo)
    if pref and not vals.get("Identificación"):
        vals["Identificación"] = pref
    n_mat = int((ult or {}).get("num_materias") or 3) or 3
    return {
        "alta_form": formulario_alta_estudiante(
            cfg,
            valores=vals,
            programas=programas,
            periodo_actual=periodo,
            num_materias=n_mat,
        )
    }


def _valores_alta_form(form: Any, esquema: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    campos = list(esquema.get("identidad") or [])
    for sec in esquema.get("secciones") or []:
        campos.extend(sec.get("campos") or [])
    for campo in campos:
        clave = campo.get("name_key")
        col = campo.get("columna")
        if not clave or not col or clave not in form:
            continue
        val = form.get(clave)
        out[col] = "" if val is None else str(val).strip()
    return out


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
    ficha_cat, ficha_sec = _tabs_ficha(request, ficha)
    extra: dict[str, Any] = {}
    usuario = getattr(request.state, "usuario", None) or _usuario_sesion(request)
    if not ficha and usuario and usuario.get("es_admin"):
        extra = _esquema_alta_estudiante(ident_prefijo=q)
        extra["alta"] = (request.query_params.get("alta") or "").strip() in {
            "1",
            "true",
            "si",
            "sí",
        }
    return _render(
        request,
        "estudiante.html",
        nav="estudiante",
        q=q,
        resultados=resultados,
        ficha=ficha,
        ficha_cat=ficha_cat,
        ficha_sec=ficha_sec,
        **extra,
    )


@app.get("/estudiante/{identificacion}", response_class=HTMLResponse)
async def ficha_estudiante(request: Request, identificacion: str) -> HTMLResponse:
    cfg = services.cfg_actual()
    ficha = obtener_ficha_estudiante(cfg, PROJECT_ROOT, identificacion)
    if ficha is None:
        extra: dict[str, Any] = {}
        usuario = getattr(request.state, "usuario", None) or _usuario_sesion(request)
        if usuario and usuario.get("es_admin"):
            extra = _esquema_alta_estudiante(ident_prefijo=identificacion)
            extra["alta"] = (request.query_params.get("alta") or "").strip() in {
                "1",
                "true",
                "si",
                "sí",
            }
        return _render(
            request,
            "estudiante.html",
            nav="estudiante",
            q=identificacion,
            resultados=[],
            ficha=None,
            ficha_cat="academico",
            ficha_sec="notas",
            error="No se encontró el estudiante en el consolidado actual.",
            **extra,
        )
    ficha_cat, ficha_sec = _tabs_ficha(request, ficha)
    return _render(
        request,
        "estudiante.html",
        nav="estudiante",
        q=identificacion,
        resultados=[],
        ficha=ficha,
        ficha_cat=ficha_cat,
        ficha_sec=ficha_sec,
    )


def _url_seguimiento(cat: str, vista: str, programas: list[str] | None = None) -> str:
    pares: list[tuple[str, str]] = [("cat", cat), ("vista", vista)]
    for programa in programas or []:
        if programa:
            pares.append(("prog", programa))
    return "/seguimiento?" + urlencode(pares)


def _url_proyeccion(
    vista: str, programas: list[str] | None = None, orden: str = "cohorte"
) -> str:
    pares: list[tuple[str, str]] = [("vista", vista)]
    if orden == "pct":
        pares.append(("orden", "pct"))
    for programa in programas or []:
        if programa:
            pares.append(("prog", programa))
    return "/proyeccion?" + urlencode(pares)


def _volver_interno(raw: str, fallback: str) -> str:
    destino = (raw or "").strip()
    if destino.startswith("/") and not destino.startswith("//"):
        return destino
    return fallback


@app.get("/seguimiento", response_class=HTMLResponse)
async def pagina_seguimiento(
    request: Request,
    cat: str = "general",
    vista: str = "pendientes",
    prog: list[str] = Query(default=[]),
) -> HTMLResponse:
    data = listar_seguimiento(cat_id=cat, vista=vista, programas=prog, base=PROJECT_ROOT)
    cat_id = data["categoria"]["id"]
    vista_ok = data["vista"]
    sel = list(data["programas_sel"])
    categorias = [
        {**c, "href": _url_seguimiento(c["id"], vista_ok, sel)}
        for c in data["categorias"]
    ]
    programas_ui = []
    for nombre in data["programas"]:
        if nombre in sel:
            nuevo = [p for p in sel if p != nombre]
        else:
            nuevo = sel + [nombre]
        programas_ui.append(
            {
                "nombre": nombre,
                "corta": color_programa(nombre).get("corta") or nombre,
                "activo": nombre in sel,
                "href": _url_seguimiento(cat_id, vista_ok, nuevo),
            }
        )
    return _render(
        request,
        "seguimiento.html",
        nav="seguimiento",
        cat=cat_id,
        categorias=categorias,
        categoria=data["categoria"],
        filas=data["filas"],
        total=data["total"],
        visibles=data["visibles"],
        vista=vista_ok,
        meta=data["meta"],
        programas=programas_ui,
        programas_sel=sel,
        filtro_general=not sel,
        href_carreras_general=_url_seguimiento(cat_id, vista_ok, []),
        href_pendientes=_url_seguimiento(cat_id, "pendientes", sel),
        href_todos=_url_seguimiento(cat_id, "todos", sel),
        href_estadisticas="/seguimiento/estadisticas",
        alertas_propias=cargar_alertas_propias(PROJECT_ROOT) if cat_id == "alertas" else [],
    )


@app.get("/proyeccion", response_class=HTMLResponse)
async def pagina_proyeccion(
    request: Request,
    vista: str = "aun_no",
    orden: str = "cohorte",
    prog: list[str] = Query(default=[]),
) -> HTMLResponse:
    data = listar_proyeccion(vista=vista, programas=prog, orden=orden, base=PROJECT_ROOT)
    vista_ok = data["vista"]
    orden_ok = data["orden"]
    sel = list(data["programas_sel"])
    programas_ui = []
    for nombre in data["programas"]:
        if nombre in sel:
            nuevo = [p for p in sel if p != nombre]
        else:
            nuevo = sel + [nombre]
        programas_ui.append(
            {
                "nombre": nombre,
                "corta": color_programa(nombre).get("corta") or nombre,
                "activo": nombre in sel,
                "href": _url_proyeccion(vista_ok, nuevo, orden_ok),
            }
        )
    return _render(
        request,
        "proyeccion.html",
        nav="proyeccion",
        filas=data["filas"],
        total=data["total"],
        visibles=data["visibles"],
        n_si=data["n_si"],
        n_aun_no=data["n_aun_no"],
        vista=vista_ok,
        orden=orden_ok,
        periodo=data["periodo"],
        meta=data["meta"],
        programas=programas_ui,
        programas_sel=sel,
        filtro_general=not sel,
        href_carreras_general=_url_proyeccion(vista_ok, [], orden_ok),
        href_aun_no=_url_proyeccion("aun_no", sel, orden_ok),
        href_si=_url_proyeccion("si", sel, orden_ok),
        href_orden_cohorte=_url_proyeccion(vista_ok, sel, "cohorte"),
        href_orden_pct=_url_proyeccion(vista_ok, sel, "pct"),
    )


@app.post("/estudiante/crear", response_model=None)
async def crear_estudiante_web(request: Request) -> RedirectResponse | HTMLResponse:
    form = await request.form()
    esquema = _esquema_alta_estudiante()["alta_form"]
    valores = _valores_alta_form(form, esquema)
    try:
        creado = crear_estudiante_manual(valores=valores)
    except ValueError as exc:
        return _render(
            request,
            "estudiante.html",
            nav="estudiante",
            q="",
            resultados=[],
            ficha=None,
            ficha_cat="academico",
            ficha_sec="notas",
            alta=True,
            error=str(exc),
            **_esquema_alta_estudiante(valores),
        )
    ident = creado["identificacion"]
    registrar_modificacion(
        accion="estudiante_manual",
        resumen=f"Creó el estudiante {ident} ({creado.get('nombre') or valores.get('Nombre y apellidos') or ident})",
        entidad="estudiante",
        identificacion=ident,
    )
    if creado.get("en_version"):
        return _redir(f"/estudiante/{ident}", msg="Estudiante creado.")
    return _redir(
        "/estudiante",
        msg="Estudiante guardado. Genere un consolidado para ver la ficha.",
    )


@app.post("/estudiante/gradua")
async def guardar_gradua_semestre(
    identificacion: str = Form(...),
    se_gradua: str = Form(...),
    volver: str = Form(""),
) -> RedirectResponse:
    destino = _volver_interno(volver, f"/estudiante/{identificacion.strip()}")
    si = se_gradua in {"1", "true", "on", "si", "sí"}
    marcar_gradua(identificacion, se_gradua=si, base=PROJECT_ROOT)
    registrar_modificacion(
        accion="gradua_semestre",
        resumen=f"Marcó {identificacion} como {'sí' if si else 'no'} se gradúa este semestre",
        entidad="estudiante",
        identificacion=identificacion,
    )
    return _redir(destino, msg="Se guardó si se gradúa este semestre.")


@app.post("/estudiante/editar")
async def editar_ficha_estudiante(request: Request) -> RedirectResponse:
    form = await request.form()
    identificacion = str(form.get("identificacion") or "").strip()
    grupo = str(form.get("grupo") or "").strip().lower()
    destino = _volver_interno(
        str(form.get("volver") or ""),
        f"/estudiante/{identificacion}" if identificacion else "/estudiante",
    )
    columnas = GRUPOS_EDITABLES.get(grupo)
    if not identificacion:
        return _redir(destino, err="Falta la identificación.")
    if not columnas:
        return _redir(destino, err="No se reconoció el bloque a editar.")
    campos = {}
    for col in columnas:
        clave = clave_campo_edicion(col)
        if clave in form:
            val = form.get(clave)
            campos[col] = "" if val is None else str(val).strip()
    if not campos:
        return _redir(destino, err="No hay campos para guardar.")
    guardar_ediciones(identificacion, campos, base=PROJECT_ROOT)
    registrar_modificacion(
        accion="edicion_ficha",
        resumen=f"Editó {grupo} de {identificacion}",
        entidad="estudiante",
        identificacion=identificacion,
    )
    titulo = "priorizado" if grupo == "priorizado" else "ruta de grado"
    return _redir(destino, msg=f"Se guardaron los datos de {titulo}.")


@app.post("/estudiante/editar/restablecer")
async def restablecer_ficha_estudiante(
    identificacion: str = Form(...),
    grupo: str = Form(...),
    volver: str = Form(""),
) -> RedirectResponse:
    destino = _volver_interno(volver, f"/estudiante/{identificacion.strip()}")
    clave = (grupo or "").strip().lower()
    if clave not in GRUPOS_EDITABLES:
        return _redir(destino, err="No se reconoció el bloque a restablecer.")
    borrar_ediciones_grupo(identificacion, clave, base=PROJECT_ROOT)
    registrar_modificacion(
        accion="edicion_ficha",
        resumen=f"Restableció {clave} de {identificacion}",
        entidad="estudiante",
        identificacion=identificacion,
    )
    return _redir(destino, msg="Se restablecieron los datos de la fuente.")


@app.post("/notas/anadir")
async def anadir_nota_seguimiento(
    identificacion: str = Form(...),
    nota: str = Form(...),
    nombre: str = Form(""),
    volver: str = Form(""),
) -> RedirectResponse:
    destino = _volver_interno(volver, f"/estudiante/{identificacion.strip()}")
    texto = (nota or "").strip()
    if not texto:
        return _redir(destino, err="Escriba la nota.")
    agregar_nota(identificacion, texto, base=PROJECT_ROOT)
    registrar_modificacion(
        accion="nota_seguimiento",
        resumen=f"Añadió nota a {identificacion}" + (f" ({nombre})" if nombre.strip() else ""),
        entidad="estudiante",
        identificacion=identificacion,
    )
    return _redir(destino, msg="Nota guardada.")


@app.post("/notas/quitar")
async def quitar_nota_seguimiento(
    nota_id: int = Form(...),
    volver: str = Form(""),
) -> RedirectResponse:
    destino = _volver_interno(volver, "/seguimiento?cat=notas")
    quitar_nota(nota_id, base=PROJECT_ROOT)
    registrar_modificacion(
        accion="nota_seguimiento",
        resumen=f"Quitó una nota de seguimiento (id {nota_id})",
        entidad="estudiante",
    )
    return _redir(destino, msg="Nota eliminada.")


@app.get("/seguimiento/estadisticas", response_class=HTMLResponse)
async def pagina_seguimiento_estadisticas(request: Request) -> HTMLResponse:
    return _render(
        request,
        "seguimiento_estadisticas.html",
        nav="seguimiento",
        cat="estadisticas",
        ayuda_clave="seguimiento-estadisticas",
        stats=estadisticas_atenciones(base=PROJECT_ROOT),
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
    prog: list[str] = Form(default=[]),
) -> RedirectResponse:
    marcar_contactado(
        identificacion,
        contactado=contactado in {"1", "true", "on"},
        categoria=cat,
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
        _url_seguimiento(cat, vista, prog),
        status_code=303,
    )


@app.post("/priorizados/contactado")
async def toggle_contactado(
    identificacion: str = Form(...),
    contactado: str = Form("1"),
    vista: str = Form("primer_plano"),
) -> RedirectResponse:
    marcar_contactado(
        identificacion,
        contactado=contactado in {"1", "true", "on"},
        categoria="priorizado",
        base=PROJECT_ROOT,
    )
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
        aliases_filas=services.aliases_para_editar(),
        cols_grafica=services.columnas_config_graficas(),
    )


@app.post("/config/guardar")
async def guardar_config_web(request: Request) -> RedirectResponse:
    form = await request.form()
    cfg = cargar_config(PROJECT_ROOT)

    def _lineas(texto: str) -> list[str]:
        return [ln.strip() for ln in str(texto).splitlines() if ln.strip()]

    if "programas" in form:
        cfg["programas_permitidos"] = _lineas(str(form.get("programas") or ""))
    if "excluidos" in form:
        cfg["programas_excluidos"] = _lineas(str(form.get("excluidos") or ""))
    if "motivos" in form:
        cfg["columnas_motivo_priorizado"] = _lineas(str(form.get("motivos") or ""))
    aliases = dict(cfg.get("aliases") or {})
    for clave in list(aliases.keys()):
        campo = form.get(f"alias_{clave}")
        if campo is None:
            continue
        aliases[clave] = [p.strip() for p in str(campo).split(",") if p.strip()]
    cfg["aliases"] = aliases
    if "graficas_presentes" in form:
        cfg["columnas_graficas"] = [
            str(v).strip() for v in form.getlist("grafica") if str(v).strip()
        ]
    guardar_config(cfg, PROJECT_ROOT)
    aplicar_config(cfg, PROJECT_ROOT)
    registrar_modificacion(
        accion="config",
        resumen="Guardó la configuración (programas, encabezados y motivos)",
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


@app.get("/parcializado", response_class=HTMLResponse)
async def pagina_parcializado(
    request: Request,
    version: int | None = None,
) -> HTMLResponse:
    versiones = services.listar_versiones_parcializado()
    datos = None
    if versiones:
        vid = version if version is not None else int(versiones[0]["id"])
        try:
            datos = services.datos_parcializado(vid)
        except ValueError as exc:
            return _render(
                request,
                "parcializado.html",
                nav="parcializado",
                versiones=versiones,
                datos=None,
                error=str(exc),
            )
    return _render(
        request,
        "parcializado.html",
        nav="parcializado",
        versiones=versiones,
        datos=datos,
    )


@app.get("/api/parcializado/{version_id}")
async def api_parcializado(version_id: int) -> JSONResponse:
    try:
        return JSONResponse(services.datos_parcializado(version_id))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/parcializado/{version_id}/conteo")
async def api_parcializado_conteo(
    version_id: int,
    programa: list[str] = Query(default=[]),
) -> JSONResponse:
    try:
        n = services.conteo_parcializado(version_id, programa or None)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return JSONResponse({"filas": n})


@app.post("/parcializado/descargar")
async def descargar_parcializado(request: Request) -> Response:
    form = await request.form()
    try:
        version_id = int(str(form.get("version_id") or "0"))
    except ValueError as exc:
        raise HTTPException(400, "Indique una versión.") from exc
    columnas = [str(v).strip() for v in form.getlist("columna") if str(v).strip()]
    todas = str(form.get("todas_carreras") or "") in {"1", "on", "true"}
    programas = [] if todas else [str(v).strip() for v in form.getlist("programa") if str(v).strip()]
    try:
        contenido, nombre = services.excel_parcializado(
            version_id, columnas=columnas, programas=programas or None
        )
    except ValueError as exc:
        return _redir("/parcializado", err=str(exc))
    ascii_name = nombre.encode("ascii", "ignore").decode() or "parcializado.xlsx"
    return Response(
        content=contenido,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quote(nombre)}'
            )
        },
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


@app.post("/config/puntajes")
async def guardar_puntajes_web(notas: str = Form("")) -> RedirectResponse:
    services.guardar_notas_puntajes(notas)
    return _redir("/informacion", msg="Se guardó la información de puntajes.")


@app.get("/graficas", response_class=HTMLResponse)
async def pagina_graficas(request: Request) -> HTMLResponse:
    df, meta = services.df_ultima_version()
    cfg = services.cfg_actual()
    permitidas = cfg.get("columnas_graficas")
    if not isinstance(permitidas, list):
        permitidas = None
    columnas = columnas_graficables(df, permitidas=permitidas) if df is not None else []
    return _render(
        request,
        "graficas.html",
        nav="graficas",
        columnas=columnas,
        tipos=TIPOS_GRAFICA,
        meta=meta,
        programas=services.programas_ultima_version(),
    )


@app.get("/api/grafica")
async def api_grafica(
    columna: str,
    tipo: str = "bar",
    top: int = 25,
    programa: str = "",
) -> JSONResponse:
    df, _ = services.df_ultima_version()
    if df is None or df.height == 0:
        raise HTTPException(400, "No hay datos del consolidado. Genere uno primero.")
    cfg = services.cfg_actual()
    permitidas = cfg.get("columnas_graficas")
    if not isinstance(permitidas, list):
        permitidas = None
    habilitadas = columnas_graficables(df, permitidas=permitidas)
    if columna not in habilitadas:
        raise HTTPException(400, "Esa columna no está habilitada para gráficas.")
    try:
        data = preparar_datos_grafica(
            df, columna=columna, tipo=tipo, top=top, programa=programa or None
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return JSONResponse(data)


@app.post("/api/grafica/powerbi")
async def api_grafica_powerbi(payload: dict[str, Any] = Body(...)) -> Response:
    df, _ = services.df_ultima_version()
    if df is None or df.height == 0:
        raise HTTPException(400, "No hay datos del consolidado. Genere uno primero.")
    cfg = services.cfg_actual()
    permitidas = cfg.get("columnas_graficas")
    if not isinstance(permitidas, list):
        permitidas = None
    habilitadas = columnas_graficables(df, permitidas=permitidas)
    items = payload.get("graficas") if isinstance(payload, dict) else None
    if not items:
        raise HTTPException(400, "Indique al menos una gráfica lista.")
    series: list[dict[str, Any]] = []
    try:
        for item in items:
            columna = str(item.get("columna") or "")
            if columna not in habilitadas:
                raise ValueError(f"La columna «{columna}» no está habilitada para gráficas.")
            tipo = str(item.get("tipo") or "bar")
            top = int(item.get("top") or 20)
            programa = str(item.get("programa") or "")
            data = preparar_datos_grafica(
                df, columna=columna, tipo=tipo, top=top, programa=programa or None
            )
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


_SERVIDOR: uvicorn.Server | None = None


def _pedir_apagar() -> None:
    global _SERVIDOR
    if _SERVIDOR is not None:
        _SERVIDOR.should_exit = True
        _SERVIDOR.force_exit = True
        return
    import os
    import threading

    threading.Timer(0.2, lambda: os._exit(0)).start()


@app.post("/api/apagar")
async def api_apagar() -> JSONResponse:
    """Cierra el servidor local y libera el puerto (tras confirmar en el navegador)."""
    import threading

    threading.Timer(0.4, _pedir_apagar).start()
    return JSONResponse({"ok": True})


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
    global _SERVIDOR
    import logging
    import os
    import threading

    from consolidado.web.avisos import mostrar_tarjeta

    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="ignore")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="ignore")
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8", errors="ignore")

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
        config = uvicorn.Config(
            app,
            host=host,
            port=elegido,
            log_level="warning",
            access_log=False,
            log_config=None,
        )
        _SERVIDOR = uvicorn.Server(config)
        _SERVIDOR.run()
        _SERVIDOR = None
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
