#!/usr/bin/env python
"""Build a standalone exportgeneanet-gui executable with PyInstaller.

Single source of truth for the PyInstaller invocation so local builds and
the release workflow (.github/workflows/release.yml) can't drift apart —
no separate .spec file to keep in sync, since there are no extra data
files/icon to justify one.

    pip install -e ".[gui,build]"
    python scripts/build_executable.py

Produces dist/exportgeneanet-gui (dist/exportgeneanet-gui.exe on Windows).
"""

from __future__ import annotations

from pathlib import Path

import PyInstaller.__main__

ENTRY_POINT = Path(__file__).resolve().parent.parent / "packaging" / "run_gui.py"

if __name__ == "__main__":
    PyInstaller.__main__.run(
        [
            str(ENTRY_POINT),
            "--name",
            "exportgeneanet-gui",
            "--onefile",
            "--windowed",
            "--noconfirm",
        ]
    )
