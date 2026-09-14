# Paquetes de instalación

Descargas (rama `Torre`):

- [Windows](https://github.com/JuanAhumada/ConsolidadoHumanidades/raw/Torre/release/ConsolidadoHumanidades-Windows.zip)
- [macOS](https://github.com/JuanAhumada/ConsolidadoHumanidades/raw/Torre/release/ConsolidadoHumanidades-macOS.zip)
- [Linux](https://github.com/JuanAhumada/ConsolidadoHumanidades/raw/Torre/release/ConsolidadoHumanidades-Linux.zip)

Usuario inicial: **admin** / **admin**. En Data puede cargar **Archivos iniciales.zip**.

## Windows

Extraiga `ConsolidadoHumanidades-Windows.zip`. En la raíz verá:

- `ConsolidadoHumanidades.exe` — ábralo con doble clic (no se abre consola).
- `Archivos iniciales.zip` — los Excel fuente para cargar todos de una vez en **Data → Paquete inicial**.

Si algo falla, aparece una tarjeta en pantalla. El manual de cada pestaña está en la aplicación (signo **?**).

## Mac

Extraiga `ConsolidadoHumanidades-macOS.zip`. En la carpeta verá:

- `Instalar.command` — primera vez: crea el entorno e instala dependencias (hace falta **Python 3.11 o superior**; si no lo tiene, instálelo en [python.org](https://www.python.org/downloads/macos/)).
- `Consolidado Humanidades.app` o `Abrir.command` — para entrar después de instalar.
- `Archivos iniciales.zip` — igual que en Windows, cárguelo en **Data**.

Si macOS avisa que no se puede abrir, clic derecho en `Instalar.command` → **Abrir**. Deje juntas las carpetas `app` y la aplicación; no mueva solo el `.app`.

## Linux

Extraiga `ConsolidadoHumanidades-Linux.zip`. En la carpeta:

```bash
chmod +x Instalar.sh Abrir.sh
./Instalar.sh
```

Hace falta **Python 3.11+** con venv (Debian/Ubuntu: `python3 python3-venv python3-pip python3-tk`). Después use `./Abrir.sh`.

No se puede generar un `.exe` de Windows ni un binario nativo de Mac/Linux desde el otro sistema. Los ZIP de Mac y Linux llevan el código y un instalador local.
