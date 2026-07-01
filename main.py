from __future__ import annotations

import sys


def _run() -> None:
    if len(sys.argv) == 1:
        from consolidado.gui import main as gui_main

        gui_main()
        return

    from consolidado.core.cli import main as cli_main

    cli_main()


if __name__ == "__main__":
    _run()
