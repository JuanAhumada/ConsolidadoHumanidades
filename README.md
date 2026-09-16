# Consolidado de Humanidades

Aplicación para fusionar Excels de estudiantes (matriculados, becas, priorizados, alertas, horarios) en un consolidado con puntaje de prioridad, fichas, seguimiento y versiones históricas.

La interfaz principal es **web** (FastAPI). También hay GUI de escritorio y CLI. Versión **beta 0.7**. Usuario inicial: **admin** / **admin**.

## Descargas

| Sistema | Paquete | Cómo se instala |
|---------|---------|-----------------|
| **Windows** | [ConsolidadoHumanidades-Windows.zip](https://github.com/JuanAhumada/ConsolidadoHumanidades/raw/Torre/release/ConsolidadoHumanidades-Windows.zip) | Extraiga y pulse `ConsolidadoHumanidades.exe`. Incluye **Archivos iniciales.zip**. Este ZIP va con Git LFS (véase más abajo). |
| **macOS** | [ConsolidadoHumanidades-macOS.zip](https://github.com/JuanAhumada/ConsolidadoHumanidades/raw/Torre/release/ConsolidadoHumanidades-macOS.zip) | Extraiga, pulse `Instalar.command` (hace falta **Python 3.11+** de [python.org](https://www.python.org/downloads/macos/)) y luego **Consolidado Humanidades**. Si macOS bloquea el archivo: clic derecho → Abrir. |
| **Linux** | [ConsolidadoHumanidades-Linux.zip](https://github.com/JuanAhumada/ConsolidadoHumanidades/raw/Torre/release/ConsolidadoHumanidades-Linux.zip) | Extraiga, `chmod +x Instalar.sh Abrir.sh` y `./Instalar.sh` (**Python 3.11+** y `python3-venv`; en Debian/Ubuntu también `python3-tk`). |

Los tres paquetes incluyen **Archivos iniciales.zip**: cárguelo en **Data → Paquete inicial**. El **Download ZIP** de GitHub **no** baja los archivos LFS; el de Windows hay que bajarlo por el enlace de arriba o clonar con `git lfs pull`.

No se puede generar el `.exe` de Windows ni un binario nativo de Mac/Linux desde otro sistema. Mac y Linux llevan el código y un instalador local.

## Requisitos

- Python 3.11+ (recomendado 3.13) si instala desde código, Mac o Linux
- Windows: el `.exe` ya trae Python embebido

## Instalación desde código

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

En macOS/Linux: `python3 -m venv .venv` y `source .venv/bin/activate`.

## Git LFS

GitHub bloquea archivos de más de **100 MB** en git normal. Este repo usa [Git LFS](https://git-lfs.com/) para el instalable Windows.

| Qué | Cómo se versiona |
|-----|------------------|
| `release/ConsolidadoHumanidades-Windows.zip` | **Git LFS** (supera 100 MB) |
| `release/ConsolidadoHumanidades-macOS.zip` | git normal (código + instalador; no incluye Python) |
| `release/ConsolidadoHumanidades-Linux.zip` | git normal (código + instalador; no incluye Python) |
| `ConsolidadoHumanidades.exe` (lanzador de la raíz) | git normal (~7 KB) |
| `ArchivosPrueba2026-1.zip` | git normal (~19 MB) |
| `dist/` (salida de PyInstaller) | **no se sube**; regenerar con `build_exe.bat` |

Tras clonar (o la primera vez en este PC):

```bat
git lfs install
git lfs pull
```

GitHub Desktop usa LFS si Git LFS está instalado. Sin `git lfs pull`, `release/ConsolidadoHumanidades-Windows.zip` queda como un puntero de texto, no como el paquete real.

## Cómo ejecutar

```bat
python main.py
```

Abre la web en el navegador. Usuario inicial: **admin** / **admin** (cámbielo en Usuarios).

| Comando | Qué hace |
|---------|----------|
| `python main.py` | Web (FastAPI + Jinja) |
| `python main.py --web` | Igual |
| `python main.py --gui` | Escritorio CustomTkinter |
| `python main.py generar …` | CLI del consolidado |
| `python -m consolidado.web` | Web |
| `python -m consolidado.gui` | GUI |

## Roles

- **consulta:** Inicio, Estudiante, Seguimiento, Metas, Gráficas, Información, Versiones (listar/descargar).
- **admin:** lo anterior más Datos antiguos, Historial, Data, Configuración, Usuarios y generar/importar.

## Flujo de datos

1. El admin carga Excels en **Data** (`datos/entrada/`). El de Permanencia y ruta de grado es opcional.
2. **Generar** corre el pipeline (`consolidado.core.pipeline`): lee fuentes → fusiona por identificación → prioridad → alertas → ruta de grado → Excel + **nueva versión SQL**.
3. Las consultas (ficha, seguimiento, gráficas) leen la **última versión** en `datos/consolidado.db`.
4. Las **metas de graduación y permanencia** se leen del Excel de Permanencia (en vivo) y se muestran en Metas / Inicio; los ajustes de Meta # y Meta % de graduación sí van en SQL (`metas_grado_override`).
5. Cada generación es un snapshot nuevo. **Nunca se sobrescribe** una versión previa.

La clave del estudiante es la **identificación** normalizada. En SQL la fila es `(identificacion, version_id)`: no hay un maestro único; identidad y beca/horario se vuelven a guardar en cada corte.

Hay **una sola base SQLite** (`datos/consolidado.db`). Los libros `bd1`, `bd12`, `bd2`… no son bases aparte: son **Excel fuente** que, al generar, se fusionan en un corte versionado.

### Periodo de la versión vs periodo del estudiante

- **Periodo de la versión:** sale de la fecha del corte (ene–jun → `YYYY-1`, jul–dic → `YYYY-2`).
- **Periodo actual del estudiante:** `COD_PERIODO` / `COD_PENSUM` de BD1 y BD12, 5 dígitos (`20261` → `2026-1`). Es el que muestra el horario de la ficha.

## Excel fuente → SQLite y módulos

Para **poder generar** el consolidado hacen falta **cuatro** libros. El resto es opcional: el módulo queda vacío o incompleto.

`bd1` y `bd12` son los únicos que **crean estudiantes**. El resto **solo enriquecen** a quien ya salió de matriculados (o de un alta manual).

| Excel | Archivo | ¿Obligatorio? | Tabla SQL | Módulos que lo usan |
|-------|---------|---------------|-----------|---------------------|
| **bd1** Matriculados activos | `bd1.xlsx` (`BASE` + `HORARIO`) | **Sí** | `estudiantes_base` (datos, horario, periodo) | Ficha, Horario, Inicio, Seguimiento, Gráficas, Parcializado, Versiones |
| **bd12** Matriculados entrenamiento | `bd12.xlsx` | **Sí** | Igual que bd1 | Los mismos (población de entrenamiento) |
| **bd2** Grupos priorizados | `bd2.xlsx` | **Sí** | `estudiantes_priorizado` | Ficha Priorizado, Seguimiento Priorizado, puntaje |
| **bd_prio_psi** / **bd_prio_lic** | priorizado enriquecido | No | `estudiantes_priorizado` (adaptación / ruta) | Ficha Priorizado y Ruta, puntaje |
| **bd3** Becas y crédito | `bd3.xlsx` | **Sí** | `estudiantes_rendimiento` | Ficha Becas, Seguimiento Beca, puntaje |
| **bd_rep** Asignaturas repetidas | `bd_rep.xlsx` | No | `estudiantes_rendimiento` (`Repitiendo`) | Ficha Horario, Seguimiento Repitiendo |
| **bd_permanencia** | Permanencia y ruta de grado | No | Extras en `estudiantes_base` (ruta, cohorte, % créditos) | **Proyección**, ficha Ruta de grado. **Metas** lee este Excel en vivo |
| **bd_graduacion** | Gestión de graduación | No | Extras de ruta/estado de grado | Proyección y ficha (completa permanencia) |
| **Alertas** com/psi inicial y final | `bd_alertas_*` | No (finales marcados opcionales) | `estudiantes_alertas` | Ficha Alertas, Seguimiento Alertas |
| **Documentos adicionales** | los que añada el admin | No | Extras en `fila_json` de base | Ficha (categoría elegida) |

| Módulo web | De dónde sale |
|------------|----------------|
| Inicio, Ficha, Seguimiento, Gráficas, Parcializado | Última (o elegida) versión SQL |
| Proyección a grado | SQL (ruta/cohorte) + `estudiante_gradua_semestre` |
| Metas | Excel `bd_permanencia` **en vivo** + `metas_grado_override` |
| Versiones | Tabla `versiones` + Excel en `salida/` |
| Información / Usuarios / Historial | Código y tablas globales, no dependen de un Excel concreto |

## Base SQLite (`datos/consolidado.db`)

Al cambiar el esquema, suba `SCHEMA_VERSION` en `consolidado/storage/db.py` y añada la migración en `inicializar_db` (hoy va en **13**).

Clave de estudiante en cada corte: `(identificacion, version_id)`. `fila_json` guarda horario, ruta de grado y columnas extra.

### Por versión (se borran en cascada con el corte)

| Tabla | Rol |
|-------|-----|
| `versiones` | Periodo, fecha, conteos, `columnas_json`, ruta Excel |
| `estudiantes_base` | Identidad, contactos, periodos, puntaje, horario y extras en `fila_json` |
| `estudiantes_priorizado` | Priorizado, motivo, adaptación, activación |
| `estudiantes_rendimiento` | Beca, funcionario, repitiendo |
| `estudiantes_alertas` | Alertas inicial/final y alerta propia de ese corte |

### Globales (no dependen del consolidado)

| Tabla | Rol |
|-------|-----|
| `usuarios` | Login (admin / consulta) |
| `schema_meta` | Versión del esquema |
| `priorizados_propios` | Marca «priorizado propio» |
| `alertas_propias` | Alerta propia |
| `alertas_descartadas` | Tipos de alerta quitados a mano |
| `priorizados_contactados` | Check de Seguimiento |
| `seguimiento_atenciones` | Estadísticas de atenciones |
| `seguimiento_notas` | Notas de la ficha / Seguimiento |
| `estudiante_gradua_semestre` | «¿Se gradúa este semestre?» |
| `estudiante_ediciones` | Campos editados en la ficha |
| `estudiantes_manuales` | Alta a mano (se reinyectan al generar) |
| `metas_grado_override` | Meta # y Meta % de graduación editadas |
| `modificaciones` | Historial |

## Configuración

| Archivo | Uso |
|---------|-----|
| `config.json` | Config **viva** (aliases, programas, slots de archivos) |
| `config_fabrica.json` | Restaurar de fábrica |
| `consolidado/config/settings.py` | Defaults en código y fusión con el JSON |

Al cargar, los defaults se fusionan con el JSON: columnas nuevas del código se añaden a grupos existentes.

## Carpetas

| Ruta | Uso |
|------|-----|
| `datos/entrada/` | Excels fuente actuales (no se versionan en git) |
| `datos/historico/` | Fuentes de Datos antiguos (no toca `entrada`) |
| `datos/consolidado.db` | SQLite |
| `salida/` | Excel generado por versión |
| `docs/` | Manual técnico |
| `empaque/` | Lanzador Windows y paquetes Mac/Linux |
| `consolidado/` | Código |

Los `.xlsx` sueltos y la `.db` **no van al repositorio** (datos de estudiantes). Qué sí se versiona (git vs LFS) está en **Git LFS**.

## Mapa del código

```
main.py                 Punto de entrada (web / gui / cli)
consolidado/
  paths.py              Raíz del proyecto (o carpeta del .exe)
  config/               JSON + defaults de columnas y aliases
  core/                 Pipeline y reglas de negocio
    pipeline.py         Orquesta generar consolidado
    archivos.py         Lee cada Excel (listado + HORARIO)
    permanencia.py      Ruta de grado por documento y metas
    columnas.py         Mapea encabezados → columnas de salida
    fusion.py           Une filas por identificación
    prioridad.py        Puntaje y nivel
    seguimiento.py      Listas de Seguimiento (nivel ≥ 1)
    ficha_estudiante.py Vista de la ficha
    colores_programa.py Color por carrera
  storage/              SQLite y datos globales
    db.py               Schema, versiones, filas
    periodos.py         Backfill de Periodo actual
    usuarios.py         Login
    contactados.py      Check de Seguimiento
  web/                  FastAPI + plantillas Jinja + CSS
    app.py              Rutas y permisos
    services.py         Generar / estado de archivos
    manual_usuario.py   Textos del «?» por pestaña
    avisos.py           Tarjetas si el .exe no arranca
  gui/                  CustomTkinter (legado, aún usable)
docs/MANUAL_TECNICO.md  Arquitectura y reglas
empaque/                Lanzador Windows y paquetes Mac/Linux
```

Para seguir un cambio:

1. **Nueva columna de Excel** → alias en `settings.py` / `config.json` y mapeo en `columnas.py`.
2. **Nueva regla de puntaje** → `prioridad.py`.
3. **Nueva pantalla web** → ruta en `web/app.py`, plantilla en `web/templates/`, estilos en `web/static/app.css`. Si es solo admin, añádala a `_PREFIJOS_ADMIN`.
4. **Nuevo campo persistente** → `db.py` (schema + `fila_json`) y, si aplica, `_CAMPOS_INDEXABLES`.
5. **Periodo del estudiante** → `normalizacion.formatear_periodo_cod` y `storage/periodos.py`.

No mezcle el periodo de la **versión** (`periodo_desde_fecha`) con el **Periodo actual** del alumno.

## Ejecutable

- **Windows:** doble clic en `ConsolidadoHumanidades.exe`. No se abre una terminal. Si falla el arranque, aparece una tarjeta.
- **Mac:** extraiga el ZIP, pulse **Instalar** y luego **Consolidado Humanidades**.
- **Linux:** extraiga el ZIP y ejecute `./Instalar.sh`.

El manual de uso está dentro de la web: signo **?** (esquina superior derecha).

```bat
build_exe.bat
python empaque/macos/armar_paquete.py
```

`build_exe.bat` genera el ZIP de Windows. `armar_paquete.py` genera los de Mac y Linux (se puede correr en Windows). Fuentes del lanzador: `empaque/`. Manual técnico: `docs/MANUAL_TECNICO.md`.
