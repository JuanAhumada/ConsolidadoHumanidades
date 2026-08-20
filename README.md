# Consolidado de Humanidades

Aplicación para fusionar Excels de estudiantes (matriculados, becas, priorizados, alertas, horarios) en un consolidado con puntaje de prioridad, fichas, seguimiento y versiones históricas.

La interfaz principal es **web** (FastAPI). También hay GUI de escritorio y CLI.

**Usuarios (Windows, sin Python):** doble clic en `ConsolidadoHumanidades.exe`.

- Si bajó [ConsolidadoHumanidades-Windows.zip](https://github.com/JuanAhumada/ConsolidadoHumanidades/raw/Torre/release/ConsolidadoHumanidades-Windows.zip), extraiga y pulse el `.exe` de la **raíz** de lo extraído.
- Si bajó el ZIP del código, pulse el `ConsolidadoHumanidades.exe` de la **raíz del repo** (es un lanzador de 7 KB; localiza o descomprime el paquete). Usuario inicial: `admin` / `admin`.

## Requisitos

- Python 3.11+ (recomendado 3.13)
- Windows (GUI y `.exe` probados ahí)

## Instalación

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

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

- **consulta:** Inicio, Estudiante, Seguimiento, Metas, Gráficas, Colores, Versiones (listar/descargar).
- **admin:** lo anterior más Datos antiguos, Historial, Data, Configuración, Usuarios y generar/importar.

## Flujo de datos

1. El admin carga Excels en **Data** (`datos/entrada/`). El de Permanencia y ruta de grado es opcional.
2. **Generar** corre el pipeline (`consolidado.core.pipeline`): lee fuentes → fusiona por identificación → prioridad → alertas → ruta de grado → Excel + **nueva versión SQL**.
3. Las consultas (ficha, seguimiento, gráficas) leen la **última versión** en `datos/consolidado.db`.
4. Las **metas de graduación y permanencia** se leen del Excel de Permanencia y se muestran en Inicio (no van en SQL).
5. Cada generación es un snapshot nuevo. **Nunca se sobrescribe** una versión previa.

La clave del estudiante es la **identificación** normalizada. En SQL la fila es `(identificacion, version_id)`: no hay un maestro único; identidad y beca/horario se vuelven a guardar en cada corte.

### Periodo de la versión vs periodo del estudiante

- **Periodo de la versión:** sale de la fecha del corte (ene–jun → `YYYY-1`, jul–dic → `YYYY-2`).
- **Periodo actual del estudiante:** `COD_PERIODO` / `COD_PENSUM` de BD1 y BD12, 5 dígitos (`20261` → `2026-1`). Es el que muestra el horario de la ficha.

## Base SQLite (`datos/consolidado.db`)

Al cambiar el esquema, suba `SCHEMA_VERSION` en `consolidado/storage/db.py` y añada la migración en `inicializar_db` (hoy va en **9**).

| Tabla | Rol |
|-------|-----|
| `versiones` | Metadatos de cada corte |
| `estudiantes_base` | Identidad, contactos, periodo, puntaje, `fila_json` |
| `estudiantes_rendimiento` | Beca, funcionario, repitiendo |
| `estudiantes_priorizado` | Priorizado, adaptación, activación |
| `estudiantes_alertas` | Alertas de esa versión |
| `priorizados_propios` | Marca propia (global, no por versión) |
| `alertas_propias` | Alerta propia (global) |
| `priorizados_contactados` | Check de Seguimiento (global) |
| `modificaciones` | Bitácora (Historial) |
| `usuarios` | Login y roles |

`fila_json` es la fuente para reconstruir la ficha. Las columnas indexables son atajos de búsqueda.

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
| `consolidado/` | Código |

Los `.xlsx` y la `.db` **no van al repositorio** (datos de estudiantes).

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
  gui/                  CustomTkinter (legado, aún usable)
```

Para seguir un cambio:

1. **Nueva columna de Excel** → alias en `settings.py` / `config.json` y mapeo en `columnas.py`.
2. **Nueva regla de puntaje** → `prioridad.py`.
3. **Nueva pantalla web** → ruta en `web/app.py`, plantilla en `web/templates/`, estilos en `web/static/app.css`. Si es solo admin, añádala a `_PREFIJOS_ADMIN`.
4. **Nuevo campo persistente** → `db.py` (schema + `fila_json`) y, si aplica, `_CAMPOS_INDEXABLES`.
5. **Periodo del estudiante** → `normalizacion.formatear_periodo_cod` y `storage/periodos.py`.

No mezcle el periodo de la **versión** (`periodo_desde_fecha`) con el **Periodo actual** del alumno.

## Ejecutable

Doble clic en **`ConsolidadoHumanidades.exe`** de la raíz (lanzador). No hace falta un `.bat`.

Si clonó con Git LFS, el lanzador abre `dist/ConsolidadoHumanidades/`. Si bajó el ZIP del código, extrae `release/ConsolidadoHumanidades-Windows.zip` y abre la app.

Para regenerar el paquete grande:

```bat
build_exe.bat
```

Los binarios grandes de `dist/` van con Git LFS. El lanzador de la raíz no. No suba `build/`.
