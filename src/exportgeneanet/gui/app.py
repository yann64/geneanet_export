"""Entry point for the `exportgeneanet-gui` console script.

PySide6 is an optional dependency (the `gui` extra) — but `[project.scripts]`
entry points register regardless of whether optional extras are installed,
so `exportgeneanet-gui` exists on PATH even for a CLI-only install. Import
PySide6 lazily here and fail with an install hint instead of a raw
traceback if it's missing.
"""

from __future__ import annotations

import sys


def main() -> None:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 is required for the GUI but isn't installed.\n"
            "Install it with:\n\n"
            "    pip install exportgeneanet[gui]\n",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    from .main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("ExportGeneanet")
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
