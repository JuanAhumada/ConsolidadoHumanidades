"""
Interfaz web HTML (FastAPI + Jinja).

app.py: rutas y roles. services.py: generar e inventario de archivos.
Plantillas en templates/, estilos en static/app.css.
Consultores llegan hasta Versiones; admin incluye Data, Historial y generar.
"""

from consolidado.web.app import app, main

__all__ = ["app", "main"]
