"""
Punto de entrada del consolidado.

Sin argumentos abre la web. --gui abre CustomTkinter. El resto se delega a la CLI.
"""
from __future__ import annotations

import sys


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
    _run()
