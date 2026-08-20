"""
Punto de entrada del consolidado.

Sin argumentos abre la web. --gui abre CustomTkinter. El resto se delega a la CLI.
"""
from __future__ import annotations

import os
import sys
from multiprocessing import freeze_support


def _stdio_sin_consola() -> None:
    """En .exe sin consola stdout/stderr son None y uvicorn revienta al configurar logs."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="ignore")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="ignore")
    if sys.stdin is None:
        sys.stdin = open(os.devnull, "r", encoding="utf-8", errors="ignore")


def _run() -> None:
    args = sys.argv[1:]

    if not args:
        from consolidado.web.app import main as web_main

        web_main()
        return

    if args[0] in {"--gui", "gui"}:
        from consolidado.gui import main as gui_main

        gui_main()
        return

    if args[0] in {"--web", "web"}:
        from consolidado.web.app import main as web_main

        web_main()
        return

    from consolidado.core.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    freeze_support()
    if getattr(sys, "frozen", False):
        _stdio_sin_consola()
    _run()
