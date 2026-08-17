"""Persistencia auxiliar del consolidado."""

from consolidado.storage.priorizados import *  # noqa: F403
from consolidado.storage.alertas_propias import (  # noqa: F401
    agregar_alerta_propia,
    cargar_alertas_propias,
    guardar_alertas_propias,
    quitar_alerta_propia,
)
from consolidado.storage.alertas_fuente import (  # noqa: F401
    aplicar_alertas_descartadas,
    descartar_alerta_fuente,
    listar_alertas_fuente,
)
from consolidado.storage.usuarios import (  # noqa: F401
    asegurar_admin_inicial,
    autenticar,
    crear_usuario,
    listar_usuarios,
)
from consolidado.storage.contactados import (  # noqa: F401
    cargar_ids_contactados,
    es_contactado,
    listar_contactados,
    marcar_contactado,
)
from consolidado.storage.db import (  # noqa: F401
    buscar_estudiantes,
    buscar_estudiantes_version,
    contar_estudiantes_distintos,
    contar_versiones,
    cargar_dataframe_version,
    guardar_version,
    listar_versiones,
    nombre_excel_version,
    obtener_fila_estudiante,
    obtener_version,
    periodo_desde_fecha,
    ruta_base_datos,
    ultima_version,
    ultima_version_por_id,
)
from consolidado.storage.modificaciones import (  # noqa: F401
    comparar_versiones,
    listar_modificaciones,
    registrar_modificacion,
)
from consolidado.storage.versiones import (  # noqa: F401
    asegurar_excel_version,
    asegurar_semilla_si_vacia,
    exportar_excel_version,
    importar_excel_como_version,
    leer_dataframe_desde_excel_consolidado,
    sembrar_version_inicial,
)
