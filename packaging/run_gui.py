"""PyInstaller entry point for the standalone exportgeneanet-gui build.

Deliberately not `src/exportgeneanet/gui/app.py` itself: PyInstaller runs
whatever script it's pointed at as `__main__`, and `app.py`'s `main()` does
a relative import (`from .main_window import MainWindow`) that only works
when the module is imported as part of the `exportgeneanet` package —
exactly how the pip-installed `exportgeneanet-gui` console script already
runs it (`from exportgeneanet.gui.app import main`). This script does the
same absolute import so PyInstaller's frozen `__main__` doesn't break it.
"""

from __future__ import annotations

from exportgeneanet.gui.app import main

if __name__ == "__main__":
    main()
