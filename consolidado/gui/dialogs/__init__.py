"""Diálogos de la interfaz gráfica."""

from consolidado.gui.dialogs.configuracion import DialogoCambiarDatos
from consolidado.gui.dialogs.documento import DialogoDocumento
from consolidado.gui.dialogs.alerta_propia import DialogoAlertaPropia
from consolidado.gui.dialogs.consulta_estudiante import DialogoConsultaEstudiante
from consolidado.gui.dialogs.info_prioridad import DialogoInfoPrioridad
from consolidado.gui.dialogs.priorizado import DialogoPriorizadoPropio
from consolidado.gui.dialogs.versiones import DialogoVersiones
from consolidado.gui.dialogs.vista_previa import DialogoVistaPrevia

__all__ = [
    "DialogoAlertaPropia",
    "DialogoCambiarDatos",
    "DialogoConsultaEstudiante",
    "DialogoDocumento",
    "DialogoInfoPrioridad",
    "DialogoPriorizadoPropio",
    "DialogoVersiones",
    "DialogoVistaPrevia",
]
