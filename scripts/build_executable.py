#!/usr/bin/env python
"""Build a standalone exportgeneanet-gui executable with PyInstaller.

Single source of truth for the PyInstaller invocation so local builds and
the release workflow (.github/workflows/release.yml) can't drift apart.
Builds from packaging/exportgeneanet-gui.spec rather than plain CLI flags —
that file excludes a few bundled shared libraries that conflict with the
host's own (see the comment there), which CLI flags alone can't express.

    pip install -e ".[gui,build]"
    python scripts/build_executable.py

Produces dist/exportgeneanet-gui (dist/exportgeneanet-gui.exe on Windows).
"""

from __future__ import annotations

from pathlib import Path

import PyInstaller.__main__

SPEC_FILE = Path(__file__).resolve().parent.parent / "packaging" / "exportgeneanet-gui.spec"

if __name__ == "__main__":
    PyInstaller.__main__.run([str(SPEC_FILE), "--noconfirm"])
