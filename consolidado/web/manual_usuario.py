"""Textos del manual de usuario (barra derecha al pulsar «?» en cada pantalla)."""

from __future__ import annotations

MANUAL_USUARIO: dict[str, dict[str, object]] = {
    "inicio": {
        "titulo": "Inicio",
        "resumen": "Punto de entrada: resumen de la facultad y atajos.",
        "pasos": [
            "A la derecha del título está el paso a paso y el número de estudiantes de la última versión.",
            "Las tarjetas de abajo abren ficha, seguimiento, gráficas y metas.",
            "Si es administrador, también verá accesos a Data, datos antiguos, historial, configuración y usuarios.",
            "El aviso de si ya se puede generar el consolidado aparece en Data, no aquí.",
        ],
    },
    "estudiante": {
        "titulo": "Estudiante",
        "resumen": "Ficha completa de una persona.",
        "pasos": [
            "Arriba a la derecha: atrás y adelante recorren las pantallas visitadas. En fichas, también pasan al estudiante anterior o siguiente de los que ya consultó.",
            "El signo de interrogación abre la guía de esta pantalla en la barra de la derecha.",
            "Escriba la cédula o parte del nombre y pulse Buscar.",
            "Si hay varias coincidencias, elija «Ver ficha».",
            "La ficha muestra contacto, beca, priorizado, alertas, ruta de grado y horario del periodo actual.",
            "El color de acento depende del programa (ver pestaña Colores).",
        ],
    },
    "seguimiento": {
        "titulo": "Seguimiento",
        "resumen": "Estudiantes activos con nivel de prioridad 1 o más.",
        "pasos": [
            "General muestra el puntaje total; las demás pestañas filtran por componente (beca, priorizado, etc.).",
            "Pendientes son quienes aún no están marcados como contactados; Todos incluye a los ya contactados.",
            "El check de contactado se guarda para siempre (no se borra al generar otra versión).",
            "Alertas lista a quienes tienen alerta de las bases o una alerta propia.",
        ],
    },
    "metas": {
        "titulo": "Metas",
        "resumen": "Graduación, permanencia e histórico del Excel de Permanencia.",
        "pasos": [
            "Las tablas salen del libro de Permanencia (hojas de metas e HISTÓRICO). No se guardan en SQL.",
            "Elija una meta en «Ver gráfica» para verla al instante: periodos actuales o la serie histórica.",
            "El consolidado cruza Gestión de graduación con Permanencia y añade el cohorte en el que el estudiante debería graduarse.",
            "Si no hay datos, pida al administrador que cargue esos Excel en Data (son opcionales).",
        ],
    },
    "graficas": {
        "titulo": "Gráficas",
        "resumen": "Tablero sobre la última versión del consolidado.",
        "pasos": [
            "Elija el tipo de gráfica y la variable (programa, nivel, etc.).",
            "El administrador puede descargar un Excel para Power BI.",
        ],
    },
    "colores": {
        "titulo": "Colores",
        "resumen": "Qué significa cada color.",
        "pasos": [
            "En el Excel, el color de la fila es el componente de puntaje más alto (beca, priorizado, activación…).",
            "En la web, el acento de la ficha y las listas es el color de la carrera.",
        ],
    },
    "versiones": {
        "titulo": "Versiones",
        "resumen": "Cortes históricos del consolidado.",
        "pasos": [
            "Cada «Generar» crea una versión nueva; no se borra la anterior.",
            "Descargue el Excel de un corte o el último consolidado.",
            "Solo el administrador puede generar o importar versiones.",
        ],
    },
    "datos-antiguos": {
        "titulo": "Datos antiguos",
        "resumen": "Fuentes de otra fecha, sin tocar los Excel actuales.",
        "pasos": [
            "Sirve para montar un consolidado con archivos viejos (carpeta histórico).",
            "No reemplaza lo que está en Data / datos de entrada.",
            "Solo el administrador entra aquí.",
        ],
    },
    "modificaciones": {
        "titulo": "Historial",
        "resumen": "Bitácora de cambios en la aplicación.",
        "pasos": [
            "Aquí queda quién generó, importó, marcó contactados o cambió usuarios.",
            "Solo el administrador ve este listado.",
        ],
    },
    "archivos": {
        "titulo": "Data",
        "resumen": "Carga de los Excel fuente del periodo actual.",
        "pasos": [
            "Arriba verá si ya está listo para generar, o cuántos archivos obligatorios faltan.",
            "Suba los libros obligatorios (matriculados, priorizados, becas). Permanencia, gestión de graduación y algunas alertas son opcionales.",
            "Cuando estén listos, use «Generar nuevo consolidado» en el menú.",
            "Los archivos se guardan en la carpeta de entrada de la aplicación.",
        ],
    },
    "config": {
        "titulo": "Configuración",
        "resumen": "Programas, aliases de columnas y colores.",
        "pasos": [
            "Cambie programas permitidos o nombres de columnas si un Excel nuevo usa encabezados distintos.",
            "«Restaurar de fábrica» vuelve a los valores por defecto (puede conservar la carpeta de salida).",
            "Solo el administrador.",
        ],
    },
    "usuarios": {
        "titulo": "Usuarios",
        "resumen": "Quién entra y con qué rol.",
        "pasos": [
            "consulta: Inicio, ficha, seguimiento, metas, gráficas, colores y descargar versiones.",
            "admin: además Data, generar, configuración, usuarios, datos antiguos e historial.",
            "Cambie la clave inicial admin / admin en cuanto instale la aplicación.",
        ],
    },
    "login": {
        "titulo": "Inicio de sesión",
        "resumen": "Entre con el usuario que le asignó el administrador.",
        "pasos": [
            "Si es la primera vez, el usuario inicial es admin y la clave admin. Cámbiela después en Usuarios.",
            "La sesión dura 12 horas en este equipo.",
        ],
    },
}


def texto_ayuda(clave: str) -> dict[str, object]:
    return MANUAL_USUARIO.get(clave) or {
        "titulo": "Ayuda",
        "resumen": "No hay una guía específica para esta pantalla.",
        "pasos": ["Use el menú de la izquierda para ir a otra sección y pulse el signo de interrogación."],
    }
