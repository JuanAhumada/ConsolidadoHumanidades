"""Interfaz web HTML del consolidado (FastAPI)."""

from __future__ import annotations

import webbrowser
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from consolidado.config.settings import (
    cargar_config,
    guardar_config,
    restaurar_config_fabrica,
)
from consolidado.core.charts import TIPOS_GRAFICA, columnas_graficables, preparar_datos_grafica
from consolidado.core.constants import aplicar_config
from consolidado.core.ficha_estudiante import obtener_ficha_estudiante
from consolidado.core.priorizados import (
    buscar_estudiantes_en_fuentes,
    obtener_lista_priorizados_vista,
)
from consolidado.paths import PROJECT_ROOT
from consolidado.storage.alertas_propias import (
    agregar_alerta_propia,
    cargar_alertas_propias,
    quitar_alerta_propia,
)
from consolidado.storage.contactados import marcar_contactado
from consolidado.storage.db import listar_versiones
from consolidado.storage.priorizados import agregar_priorizado_propio, set_priorizado_activo
from consolidado.storage.versiones import asegurar_semilla_si_vacia
from consolidado.web import services

WEB_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(WEB_DIR / "templates"))

app = FastAPI(title="Consolidado de Humanidades")
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")


def _ctx(request: Request, **extra: Any) -> dict[str, Any]:
    cfg = services.cfg_actual()
    estado = services.estado_archivos(cfg)
    data = {
        "cfg": cfg,
        "estado": estado,
        "nav": extra.pop("nav", "archivos"),
        "flash": request.query_params.get("msg"),
        "error": request.query_params.get("err") or extra.pop("error", None),
    }
    data.update(extra)
    return data


def _render(request: Request, template: str, **extra: Any) -> HTMLResponse:
    return TEMPLATES.TemplateResponse(request, template, _ctx(request, **extra))


@app.on_event("startup")
def _startup() -> None:
    asegurar_semilla_si_vacia(PROJECT_ROOT)


@app.get("/", response_class=HTMLResponse)
async def inicio(request: Request) -> HTMLResponse:
    return _render(request, "archivos.html", nav="archivos")


@app.post("/upload/{slot_id}")
async def upload_slot(slot_id: str, archivo: UploadFile = File(...)) -> RedirectResponse:
    try:
        contenido = await archivo.read()
        if not contenido:
            raise ValueError("Archivo vacío.")
        services.subir_slot(slot_id, archivo.filename or "archivo.xlsx", contenido)
    except Exception as exc:
        return RedirectResponse(f"/?err={exc}", status_code=303)
    return RedirectResponse("/?msg=Archivo+actualizado", status_code=303)


@app.post("/generar")
async def generar_consolidado() -> RedirectResponse:
    try:
        info = services.generar()
        n = info["estudiantes"]
        return RedirectResponse(
            f"/graficas?msg=Generado:+{n}+estudiantes.+Se+abrió+el+Excel.",
            status_code=303,
        )
    except Exception as exc:
        return RedirectResponse(f"/?err={exc}", status_code=303)


@app.get("/consolidado", response_class=HTMLResponse)
async def vista_consolidado() -> RedirectResponse:
    return RedirectResponse("/graficas", status_code=303)


@app.get("/estudiante", response_class=HTMLResponse)
async def pagina_estudiante(request: Request, q: str = "") -> HTMLResponse:
    cfg = services.cfg_actual()
    resultados = []
    ficha = None
    if q.strip():
        resultados = buscar_estudiantes_en_fuentes(cfg, PROJECT_ROOT, q.strip(), limite=40)
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


@app.get("/priorizados", response_class=HTMLResponse)
async def pagina_priorizados(request: Request, vista: str = "primer_plano") -> HTMLResponse:
    cfg = services.cfg_actual()
    filas = obtener_lista_priorizados_vista(cfg, PROJECT_ROOT)
    if vista == "primer_plano":
        visibles = [f for f in filas if not f.get("contactado") and f.get("activo", True)]
    else:
        visibles = filas
    return _render(
        request,
        "priorizados.html",
        nav="priorizados",
        filas=visibles,
        vista=vista,
        total=len(filas),
        visibles=len(visibles),
    )


@app.post("/priorizados/contactado")
async def toggle_contactado(
    identificacion: str = Form(...),
    contactado: str = Form("1"),
    vista: str = Form("primer_plano"),
) -> RedirectResponse:
    marcar_contactado(identificacion, contactado=contactado in {"1", "true", "on"}, base=PROJECT_ROOT)
    return RedirectResponse(f"/priorizados?vista={vista}", status_code=303)


@app.post("/priorizados/activo")
async def toggle_activo(
    identificacion: str = Form(...),
    activo: str = Form("1"),
    vista: str = Form("completo"),
) -> RedirectResponse:
    set_priorizado_activo(identificacion, activo=activo in {"1", "true", "on"}, base=PROJECT_ROOT)
    return RedirectResponse(f"/priorizados?vista={vista}&msg=Estado+actualizado", status_code=303)


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
    return RedirectResponse("/priorizados?vista=completo&msg=Priorizado+guardado", status_code=303)


@app.get("/alertas", response_class=HTMLResponse)
async def pagina_alertas(request: Request) -> HTMLResponse:
    return _render(
        request,
        "alertas.html",
        nav="alertas",
        alertas=cargar_alertas_propias(PROJECT_ROOT),
    )


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
    return RedirectResponse("/alertas?msg=Alerta+guardada", status_code=303)


@app.post("/alertas/quitar")
async def quitar_alerta(identificacion: str = Form(...)) -> RedirectResponse:
    quitar_alerta_propia(identificacion, PROJECT_ROOT)
    return RedirectResponse("/alertas?msg=Alerta+eliminada", status_code=303)


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
    return RedirectResponse("/config?msg=Configuración+guardada", status_code=303)


@app.post("/config/fabrica")
async def config_fabrica() -> RedirectResponse:
    cfg = cargar_config(PROJECT_ROOT)
    restaurar_config_fabrica(cfg, PROJECT_ROOT)
    return RedirectResponse("/config?msg=Valores+de+fábrica+restaurados", status_code=303)


@app.get("/versiones", response_class=HTMLResponse)
async def pagina_versiones(request: Request) -> HTMLResponse:
    return _render(
        request,
        "versiones.html",
        nav="versiones",
        versiones=listar_versiones(PROJECT_ROOT),
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


@app.get("/api/buscar")
async def api_buscar(q: str = "") -> JSONResponse:
    cfg = services.cfg_actual()
    return JSONResponse(buscar_estudiantes_en_fuentes(cfg, PROJECT_ROOT, q, limite=30))


def main(host: str = "127.0.0.1", port: int = 8765, *, open_browser: bool = True) -> None:
    if open_browser:
        webbrowser.open(f"http://{host}:{port}/")
    uvicorn.run(
        "consolidado.web.app:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
