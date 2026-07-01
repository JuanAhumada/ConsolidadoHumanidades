# Consolidado de Humanidades

Aplicación para fusionar Excels de estudiantes en un consolidado con priorización, alertas, becas y exportación a Excel.

## Requisitos

- Python 3.11+ (recomendado 3.13)
- Windows (interfaz gráfica probada en Windows)

## Instalación (desarrollo)

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Incluye dependencias de ejecución y de empaquetado (`pyinstaller`). Para generar el `.exe` basta con tener el entorno activo y ejecutar `build_exe.bat`.

## Uso

```bat
python main.py
```

Interfaz gráfica para cargar archivos fuente, configurar columnas y generar el consolidado.

### Carpetas de trabajo

| Carpeta | Uso |
|---------|-----|
| `datos/entrada/` | Excels fuente cargados por la app (no se versionan) |
| `salida/` | Consolidado generado (`estudiantes_consolidado.xlsx`) |
| `Ejemplos/` | Excels originales de referencia (opcional, local) |
| `config.json` | Configuración de columnas, archivos fuente y colores |

Los archivos `.xlsx` **no se suben al repositorio** por contener datos de estudiantes.

## Ejecutable (.exe)

```bat
build_exe.bat
```

Salida en `dist\ConsolidadoHumanidades\`. Comparta esa carpeta completa (incluye `_internal`).

**No suba `dist/` ni `build/` al repositorio:** están en `.gitignore`. Cada quien genera el `.exe` en su máquina con `build_exe.bat`.

## Estructura del código

```
consolidado/
  config/       # settings y config por defecto
  core/         # pipeline, fusión, export, prioridad
  gui/          # interfaz CustomTkinter
  storage/      # priorizados propios (JSON)
main.py         # punto de entrada
```
