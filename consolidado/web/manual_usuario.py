"""Textos del manual de usuario (barra derecha al pulsar «?» en cada pantalla)."""

from __future__ import annotations

MANUAL_USUARIO: dict[str, dict[str, object]] = {
    "inicio": {
        "titulo": "Inicio",
        "resumen": "Resumen de la última versión y descarga del Excel.",
        "pasos": [
            "A la derecha está el número de estudiantes de la última versión; pulse la tarjeta para abrir el historial.",
            "Arriba a la derecha, «Descargar último consolidado» baja el Excel más reciente.",
            "Si cierra la pestaña, el navegador preguntará; acéptelo para apagar la aplicación y liberar el puerto.",
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
            "Si es administrador, a la derecha de Buscar está «Nuevo estudiante». Abre un formulario con las mismas pestañas de la ficha (Datos, Académico, Priorizado…) para rellenar a mano todos los campos del consolidado. Al abrirlo se oculta Buscar; «Volver a buscar» restaura la consulta.",
            "Los datos del estudiante (incluido correo y celular) quedan siempre visibles. Debajo hay dos grupos de pestañas, a media pantalla cada uno.",
            "Izquierda: académico, priorizado, ruta de grado, becas y alertas. Derecha: notas, nueva nota, proyección a grado y horario.",
            "En Notas puede marcar al estudiante como priorizado propio. Queda en Seguimiento con el motivo «Priorizado propio».",
            "Las notas del semestre siguen la fecha: diciembre a mayo = primer semestre (diciembre cuenta el año siguiente); junio a noviembre = segundo. En Horario use Todos o un día; las materias sin día van al apartado Virtual. La semana también se desplaza en horizontal si no cabe.",
            "En Priorizado y Ruta de grado pulse «Editar estados» para cambiar los campos. Guardar deja el cambio; Restablecer vuelve a la fuente.",
            "En Proyección responda si se gradúa este semestre; queda en Proyección a Grado.",
            "El color de acento depende del programa (ver pestaña Colores).",
        ],
    },
    "seguimiento": {
        "titulo": "Seguimiento",
        "resumen": "Estudiantes activos con nivel de prioridad 1 o más.",
        "pasos": [
            "General muestra el puntaje total; las demás pestañas filtran por componente (beca, priorizado, etc.).",
            "Al lado de las carreras, Becas y Priorizados van en un desplegable cerrado: busque y marque los tipos. Puede elegir varios.",
            "Pendientes son quienes aún no están marcados como contactados; Todos incluye a los ya contactados.",
            "Cada tarjeta muestra nombre, puntaje y el botón para marcar que se atendió. El nombre abre la ficha completa.",
            "Al marcar se guarda la fecha y la pestaña (beca, priorizado, etc.). En Estadísticas verá cuántos se atendieron al día y el promedio.",
            "Alertas lista a quienes tienen alerta de las bases o una alerta propia. Las alertas se gestionan en la ficha del estudiante.",
            "El priorizado propio se marca desde Notas en la ficha, no desde esta pantalla.",
            "Notas guarda observaciones de lo que dijo el estudiante. También puede añadirlas desde la ficha. «Exportar anotaciones» baja un Excel por estudiante, con fecha y periodo.",
        ],
    },
    "seguimiento-estadisticas": {
        "titulo": "Estadísticas de seguimiento",
        "resumen": "Cuántas atenciones se marcaron por día y desde qué pestaña.",
        "pasos": [
            "Hoy es el recuento del día actual.",
            "El promedio por día usa solo los días en los que sí hubo al menos una marca.",
            "El promedio de 7 días incluye también los días en cero.",
            "La tabla por pestaña indica desde cuál vista (beca, priorizado, alertas…) se marcó.",
        ],
    },
    "proyeccion": {
        "titulo": "Proyección a Grado",
        "resumen": "Estudiantes próximos a graduarse y si se gradúan este semestre.",
        "pasos": [
            "Entran quienes, según ruta de grado y permanencia, tienen cohorte o periodo de grado cercano, muchos créditos, o opción de grado / inglés / Saber Pro en curso.",
            "Aún no: no han confirmado que se gradúan este semestre (incluye a quienes dijeron que no).",
            "Se gradúan: los que en la ficha respondieron Sí a «¿Se gradúa este semestre?».",
            "Organizar ordena las tarjetas por cohorte de graduación (la más cercana primero) o por porcentaje de créditos aprobados (de mayor a menor).",
            "Abra la ficha desde la tarjeta para marcar Sí o No y para dejar notas de seguimiento.",
        ],
    },
    "metas": {
        "titulo": "Metas",
        "resumen": "Graduación, permanencia e histórico del Excel de Permanencia.",
        "pasos": [
            "Las gráficas de graduación y permanencia son una por carrera: valor real y meta por cohorte. El tramo violeta punteado es proyección.",
            "A un costado, «Ver datos numéricos» muestra las tablas. El administrador puede cambiar Meta # y Meta % de graduación ahí, sin tocar el Excel.",
            "El consolidado cruza Gestión de graduación con Permanencia y añade el cohorte en el que el estudiante debería graduarse.",
            "Si no hay datos, pida al administrador que cargue esos Excel en Data (son opcionales).",
        ],
    },
    "graficas": {
        "titulo": "Gráficas",
        "resumen": "Tablero sobre cualquier versión del consolidado.",
        "pasos": [
            "Elija de qué consolidado (versión) sale cada gráfica. Cada espacio puede usar un corte distinto.",
            "Por defecto la gráfica es de línea, de menor a mayor, y no muestra categorías en cero. El eje se ajusta al máximo de quienes aplican.",
            "Cada espacio de gráfica puede tener su propia carrera. «Todas» usa la facultad completa.",
            "En Configuración marque las columnas que el tablero puede usar. Por defecto no salen identificación, nombres, celulares, correos ni materias.",
        ],
    },
    "informacion": {
        "titulo": "Información",
        "resumen": "Puntajes de prioridad y qué significa cada color.",
        "pasos": [
            "La fórmula suma beca, priorizado, repitiendo, reintegro, propio, activación y ruta de grado.",
            "La tabla indica cuántos puntos aporta cada condición. El nivel numérico sale del total.",
            "En el Excel, el color de la fila es el componente de puntaje más alto (beca, priorizado, activación…).",
            "En la web, el acento de la ficha y las listas es el color de la carrera, no el del Excel.",
            "El administrador puede guardar notas de la facultad (acuerdos o excepciones) en esta misma pantalla.",
        ],
    },
    "versiones": {
        "titulo": "Versiones",
        "resumen": "Cortes históricos del consolidado.",
        "pasos": [
            "Cada «Generar» (solo en Data) crea una versión nueva; no se borra la anterior.",
            "Arriba puede descargar el último Excel; cada fila también tiene su propio archivo.",
            "Solo el administrador puede generar o importar versiones.",
        ],
    },
    "parcializado": {
        "titulo": "Parcializado",
        "resumen": "Un Excel con solo las columnas y carreras que le pidan.",
        "pasos": [
            "Elija cualquier versión del consolidado (no solo la última).",
            "Marque una carrera, varias o «Todas las carreras». También puede filtrar por tipo de beca, nivel, cohorte y pensum en las listas desplegables.",
            "Marque las columnas. «Datos básicos» deja identificación, nombre y programa.",
            "Descargue el Excel: hoja principal, hoja Becas (Documento, Nombre, Carrera, Beca 1…), hoja Priorizados (Motivo 1…) y Anotaciones.",
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
            "Aquí queda quién generó, importó, cargó archivos, marcó contactados o cambió usuarios.",
            "Solo el administrador ve este listado.",
        ],
    },
    "archivos": {
        "titulo": "Data",
        "resumen": "Carga de los Excel fuente del periodo actual.",
        "pasos": [
            "Arriba verá si ya está listo para generar, o cuántos archivos obligatorios faltan.",
            "Arriba puede cargar un ZIP de fuentes (paquete inicial) o varios Excel de una vez por el nombre del archivo.",
            "En cada fila elija el Excel de ese apartado y, al final, pulse «Cargar seleccionados» para subirlos todos juntos.",
            "En Archivos adicionales pulse «Añadir Excel». La llave foránea es la columna de ese Excel que coincide con Identificación del consolidado: así se busca al estudiante y se añaden los datos a su fila (no crea personas nuevas). Luego elija si van a una categoría existente de la ficha (Datos, Académico, Priorizado…) o escriba el nombre de una categoría nueva.",
            "«Editar encabezados» o «Editar datos» abre una base concreta: hojas internas, previa de filas y el campo de entrada (Excel) frente al de salida (consolidado).",
            "Permanencia, gestión de graduación y algunas alertas son opcionales.",
            "Cuando estén listos, use «Generar nuevo consolidado» en esta misma pantalla (fecha de versión y botón).",
            "Los archivos se guardan en la carpeta de entrada de la aplicación.",
        ],
    },
    "config": {
        "titulo": "Configuración",
        "resumen": "Programas, aliases de columnas y colores.",
        "pasos": [
            "Marque las columnas que quiere ver en Gráficas. Identificación, nombres, teléfonos, correos y materias no entran por defecto.",
            "Cambie programas permitidos o nombres de columnas (encabezados de origen) si un Excel nuevo usa títulos distintos.",
            "«Restaurar de fábrica» vuelve a los valores por defecto (puede conservar la carpeta de salida).",
            "Solo el administrador.",
        ],
    },
    "usuarios": {
        "titulo": "Usuarios",
        "resumen": "Quién entra y con qué rol.",
        "pasos": [
            "consulta: Inicio, ficha, seguimiento, proyección a grado, metas, gráficas, información, versiones y parcializado.",
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
