"""
Configuración del consolidado.

settings.py define defaults y fusiona con config.json en la raíz del proyecto.
config_fabrica.json restaura de fábrica. No edite a mano el JSON de
consolidado/config/ salvo que sea una plantilla de referencia.
"""

from consolidado.config.settings import *  # noqa: F403
